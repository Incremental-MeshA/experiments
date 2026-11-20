#include "factory.hpp"
#include <iostream>
#include <random>
using namespace ima;
using namespace ima::mpgaa_lazy;
// Direct primitive Dijkstra, independent of mesh, caches, and learned heuristic.
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
        std::mt19937 rng(831701+seed);Grid grid(m.headings==1?13:23,m.headings==1?15:25);
        State fixed{2,2,0},goal{grid.height-3,grid.width-3,0};
        for(int i=0;i<grid.height;++i)for(int j=0;j<grid.width;++j)if(rng()%100<12)grid.set({i,j},true);
        grid.set(fixed.cell(),false);grid.set(goal.cell(),false);
        std::vector<std::unique_ptr<LazyMPGAA>> planners;
        for(Mode mode:{Mode::Stamp,Mode::Batch,Mode::Witness})planners.push_back(std::make_unique<LazyMPGAA>(mesh,grid,goal,mode,1000000));
        planners.push_back(std::make_unique<LazyMPGAA>(mesh,grid,goal,Mode::Stamp,1000000,1));
        planners.push_back(std::make_unique<LazyMPGAA>(mesh,grid,goal,Mode::Batch,1000000,8,true));
        planners.push_back(std::make_unique<LazyMPGAA>(mesh,grid,goal,Mode::Witness,1000000,32));
        Path previous;
        for(int q=0;q<36;++q) {
            State start=fixed;
            if(q%5==2 && previous.success() && previous.states.size()>2)start=previous.states[previous.states.size()/2];
            if(q%7==4)start={int(rng()%grid.height),int(rng()%grid.width),int(rng()%m.headings)};
            std::set<Cell> edits;std::vector<Cell> blocks,opens;
            if(q && q%6!=1)for(int k=0;k<(q%3==0?64:4);++k)edits.insert({int(rng()%grid.height),int(rng()%grid.width)});
            if(q==9)edits.insert(goal.cell());
            if(q==10 && grid.blocked(goal.cell()))edits.insert(goal.cell());
            if(q==20)edits.insert(start.cell());
            for(Cell c:edits) {
                // Also exercise one-sided and unchanged batches.
                if((q%6==2 && grid.blocked(c)) || (q%6==3 && !grid.blocked(c)))continue;
                (grid.blocked(c)?opens:blocks).push_back(c);grid.set(c,!grid.blocked(c));
            }
            // Duplicate notifications must not create duplicate changes.
            if(q%4==0 && !blocks.empty())blocks.push_back(blocks.front());
            if(q%4==0 && !opens.empty())opens.push_back(opens.front());
            double expected=oracle(grid,m,start,goal);++queries;
            for(std::size_t k=0;k<planners.size();++k) {
                auto& planner=*planners[k];auto path=planner.replan(start,blocks,opens);
                std::string context=" seed="+std::to_string(seed)+" query="+std::to_string(q)+" variant="+std::to_string(k);
                require(!path.stats.capped,"unexpected cap"+context);
                require(path.success()==std::isfinite(expected),"reachability"+context);
                if(path.success())require(std::abs(path.cost-expected)<1e-6,"optimality"+context);
                validate_path(grid,m,start,goal,path);planner.audit();total.add(planner.counters());++comparisons;
                if(k==0)previous=path;
            }
        }
    }
    Grid open(24,25);State s{2,2,0},t{20,21,0};
    for(Mode mode:{Mode::Stamp,Mode::Batch,Mode::Witness}) {
        LazyMPGAA planner(mesh,open,t,mode,0);auto p=planner.replan(s);require(p.stats.capped,"zero cap not reported");
        planner.set_limit(1000000);p=planner.replan(s);double expected=oracle(open,m,s,t);
        require(p.success()==std::isfinite(expected),"recovery after cap reachability");
        if(p.success())require(std::abs(p.cost-expected)<1e-6,"recovery after cap cost");
        ++comparisons;
    }
    bool rejected=false;try{LazyMPGAA invalid(mesh,open,t,Mode::Stamp,100,0);}catch(const std::exception&){rejected=true;}
    require(rejected,"invalid tile accepted");
    require(total.scan_batches && total.edit_batches && total.cut_reuses,"mechanism not exercised");
    std::cout<<"{\"status\":\"passed\",\"model\":\""<<m.name<<"\",\"queries\":"<<queries<<",\"comparisons\":"<<comparisons
             <<",\"scan_batches\":"<<total.scan_batches<<",\"edit_batches\":"<<total.edit_batches<<",\"cut_reuses\":"<<total.cut_reuses<<"}\n";
    return 0;
}catch(const std::exception& e){std::cerr<<"error: "<<e.what()<<'\n';return 1;}
