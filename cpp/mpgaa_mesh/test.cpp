#include "factory.hpp"
#include <iostream>
#include <random>
using namespace ima;
using namespace ima::mpgaa_mesh;

// Independent Dijkstra: direct primitive enumeration and raw occupancy reads.
// It does not use the mesh, learned heuristic, edge cache, or planner search.
double oracle(const Grid& grid,const Model& m,State s,State t) {
    if(!grid.free(s.cell()) || !grid.free(t.cell()))return INF;
    using Item=std::pair<double,State>;
    std::priority_queue<Item,std::vector<Item>,std::greater<Item>> queue;
    std::map<State,double> d;d[s]=0;queue.push({0,s});
    while(!queue.empty()) {
        auto [cost,u]=queue.top();queue.pop();if(d.at(u)!=cost)continue;if(u==t)return cost;
        for(const auto& p:m.primitives)if(p.start==u.k) {
            bool good=true;
            for(std::size_t j=1;j<p.cells.size();++j) {
                int i=u.i+p.cells[j].i,k=u.j+p.cells[j].j;
                if(i<0 || k<0 || i>=grid.height || k>=grid.width || grid.cells[std::size_t(i)*grid.width+k]){good=false;break;}
            }
            if(!good)continue;
            State v{u.i+p.di,u.j+p.dj,p.end};double candidate=cost+p.cost;auto it=d.find(v);
            if(it==d.end() || candidate<it->second){d[v]=candidate;queue.push({candidate,v});}
        }
    }
    return INF;
}
int main(int argc,char** argv)try {
    require(argc==2,"provide frozen model");auto suite=read_suite(argv[1]);const auto& m=suite.model;MeshIndex mesh(m);
    std::uint64_t comparisons=0,queries=0;Work total;
    for(int seed=0;seed<18;++seed) {
        std::mt19937 rng(781301+seed);Grid grid(m.headings==1?13:23,m.headings==1?15:25);
        State fixed{2,2,0},goal{grid.height-3,grid.width-3,0};
        for(int i=0;i<grid.height;++i)for(int j=0;j<grid.width;++j)if(rng()%100<12)grid.set({i,j},true);
        grid.set(fixed.cell(),false);grid.set(goal.cell(),false);
        MPGAA baseline(m,grid,goal,1000000);
        std::vector<std::unique_ptr<MeshMPGAA>> planners;
        planners.push_back(std::make_unique<BoundaryMPGAA>(mesh,grid,goal,1000000));
        planners.push_back(std::make_unique<SelectiveMPGAA>(mesh,grid,goal,1000000));
        planners.push_back(std::make_unique<DeltaMPGAA>(mesh,grid,goal,1000000));
        planners.push_back(std::make_unique<PolicyMPGAA>(mesh,grid,goal,1000000));
        planners.push_back(std::make_unique<MeshMPGAA>(mesh,grid,goal,Mode::Selective,1000000,false,true));
        planners.push_back(std::make_unique<MeshMPGAA>(mesh,grid,goal,Mode::Selective,1000000,true,false));
        Path previous;
        for(int q=0;q<30;++q) {
            State start=fixed;
            if(q%5==2 && previous.success() && previous.states.size()>2)start=previous.states[previous.states.size()/2];
            if(q%7==4)start={int(rng()%grid.height),int(rng()%grid.width),int(rng()%m.headings)};
            std::set<Cell> edits;std::vector<Cell> blocks,opens;
            if(q)for(int k=0;k<(q%3==0?25:4);++k)edits.insert({int(rng()%grid.height),int(rng()%grid.width)});
            if(q==9)edits.insert(goal.cell()); // endpoint blocking, then reopening
            if(q==10 && grid.blocked(goal.cell()))edits.insert(goal.cell());
            for(Cell c:edits){(grid.blocked(c)?opens:blocks).push_back(c);grid.set(c,!grid.blocked(c));}
            double expected=oracle(grid,m,start,goal);auto reference=baseline.replan(start,blocks,opens);++queries;
            for(std::size_t k=0;k<planners.size();++k) {
                auto& planner=*planners[k];auto path=planner.replan(start,blocks,opens);
                require(!path.stats.capped,"unexpected cap");
                std::string context=" seed="+std::to_string(seed)+" query="+std::to_string(q)+" variant="+std::to_string(k);
                require(path.success()==std::isfinite(expected),"reachability"+context);
                if(path.success())require(std::abs(path.cost-expected)<1e-6,"optimality"+context);
                validate_path(grid,m,start,goal,path);planner.audit();total.add(planner.counters());++comparisons;
                if(k==0)require(path.stats.expansions==reference.stats.expansions,"boundary changed search expansion order"+context);
            }
            previous=std::move(reference);
        }
    }
    // A cap must remain a cap, and a subsequent larger budget must recover.
    Grid open(24,25);State s{2,2,0},t{20,21,0};
    for(Mode mode:{Mode::Boundary,Mode::Selective,Mode::Delta,Mode::Policy}) {
        MeshMPGAA planner(mesh,open,t,mode,0);auto p=planner.replan(s);require(p.stats.capped,"zero cap not reported");
        planner.set_limit(1000000);p=planner.replan(s);double expected=oracle(open,m,s,t);
        require(p.success()==std::isfinite(expected),"recovery after cap reachability");
        if(p.success())require(std::abs(p.cost-expected)<1e-6,"recovery after cap cost");
        ++comparisons;
    }
    std::cout<<"{\"status\":\"passed\",\"model\":\""<<m.name<<"\",\"queries\":"<<queries<<",\"comparisons\":"<<comparisons
             <<",\"pruned_branches\":"<<total.pruned_branches<<",\"validity_flips\":"<<total.validity_flips
             <<",\"alternate_uses\":"<<total.alternate_uses<<"}\n";
    return 0;
}catch(const std::exception& e){std::cerr<<"error: "<<e.what()<<'\n';return 1;}
