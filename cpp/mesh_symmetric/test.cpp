#include "factory.hpp"
#include <iostream>
#include <random>
using namespace ima;
using namespace ima::mesh_envelope;
using ima::mesh_symmetric::Symmetric;
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
    require(argc==2,"provide frozen model");auto suite=read_suite(argv[1]);const auto& m=suite.model;MeshIndex mesh(m);Certificate certificate(m);
    std::uint64_t comparisons=0,hits=0,events=0;
    for(int seed=0;seed<16;++seed) {
        std::mt19937 rng(87131+seed);Grid grid(m.headings==1?15:23,m.headings==1?17:25);
        State fixed{2,2,0},goal{grid.height-3,grid.width-3,0};
        for(int i=0;i<grid.height;++i)for(int j=0;j<grid.width;++j)if(rng()%100<14)grid.set({i,j},true);
        grid.set(fixed.cell(),false);grid.set(goal.cell(),false);
        std::vector<std::unique_ptr<Planner>> planners;
        for(const auto* name:{"mesh_cold","mesh_reuse","cut_mesh","envelope_mesh","dual_mesh","lattice_envelope"})
            planners.push_back(std::make_unique<Envelope>(mesh,grid,goal,name,1000000));
        planners.push_back(std::make_unique<Circuit>(mesh,grid,fixed,goal,1000000));
        planners.push_back(std::make_unique<Symmetric>(mesh,certificate,grid,goal,true,1000000));
        planners.push_back(std::make_unique<Symmetric>(mesh,certificate,grid,goal,false,1000000));
        planners.push_back(std::make_unique<Symmetric>(mesh,certificate,grid,goal,true,1000000,false));
        planners.push_back(std::make_unique<Symmetric>(mesh,certificate,grid,goal,true,1000000,true,false));
        Path previous;
        for(int q=0;q<48;++q) {
            State start=fixed;if(q%5==2 && previous.success() && previous.states.size()>2)start=previous.states[previous.states.size()/2];
            if(q%7==4)start={int(rng()%grid.height),int(rng()%grid.width),int(rng()%m.headings)};
            std::set<Cell> edits;std::vector<Cell> blocks,opens;
            if(q && q%6!=1)for(int k=0;k<(q%3==0?64:4);++k)edits.insert({int(rng()%grid.height),int(rng()%grid.width)});
            if(q==9 || (q==10 && grid.blocked(goal.cell())))edits.insert(goal.cell());
            if(q==20)edits.insert(start.cell());
            for(Cell c:edits) {
                if((q%6==2 && grid.blocked(c)) || (q%6==3 && !grid.blocked(c)))continue;
                (grid.blocked(c)?opens:blocks).push_back(c);grid.set(c,!grid.blocked(c));
            }
            if(q%4==0 && !blocks.empty())blocks.push_back(blocks.front());
            if(q%4==0 && !opens.empty())opens.push_back(opens.front());
            double expected=oracle(grid,m,start,goal);
            for(std::size_t k=0;k<planners.size();++k) {
                auto p=planners[k]->replan(start,blocks,opens);
                std::string context=" seed="+std::to_string(seed)+" query="+std::to_string(q)+" variant="+std::to_string(k);
                require(!p.stats.capped,"cap"+context);require(p.success()==std::isfinite(expected),"reachability"+context);
                if(p.success())require(std::abs(p.cost-expected)<1e-6,"optimality"+context);
                validate_path(grid,m,start,goal,p);++comparisons;
                if(auto* s=dynamic_cast<Symmetric*>(planners[k].get()))s->audit();
                if(auto* a=dynamic_cast<Envelope*>(planners[k].get())){a->audit();hits+=a->counters().envelope_hits;events+=a->counters().guard_events;}
                if(k==0)previous=p;
            }
        }
    }
    // A full separator, off-frontier openings, a newly blocked prefix,
    // reconnection, and moving starts exercise the negative certificate.
    Grid doors(31,43);State s{15,6,0},t{15,36,0};
    for(int i=0;i<31;++i)for(int j=19;j<=23;++j)doors.set({i,j},true);
    for(int i=2;i<29;i+=3)doors.set({i,33},true);
    std::vector<std::unique_ptr<Planner>> variants;
    for(const auto* name:{"cut_mesh","envelope_mesh","dual_mesh","lattice_envelope"})
        variants.push_back(std::make_unique<Envelope>(mesh,doors,t,name,1000000));
    variants.push_back(std::make_unique<Circuit>(mesh,doors,s,t,1000000));
    variants.push_back(std::make_unique<Symmetric>(mesh,certificate,doors,t,true,1000000));
    variants.push_back(std::make_unique<Symmetric>(mesh,certificate,doors,t,false,1000000));
    variants.push_back(std::make_unique<Symmetric>(mesh,certificate,doors,t,true,1000000,false));
    variants.push_back(std::make_unique<Symmetric>(mesh,certificate,doors,t,true,1000000,true,false));
    for(int phase=0;phase<10;++phase) {
        std::vector<Cell> b,o;
        if(phase==1)o.push_back({2,33});
        if(phase==2){o.push_back({14,19});b.push_back({15,18});}
        if(phase==3)for(int i=10;i<=20;++i)for(int j=19;j<=23;++j)o.push_back({i,j});
        if(phase==4)for(int i=10;i<=20;++i)for(int j=19;j<=23;++j)b.push_back({i,j});
        if(phase==5)o.push_back({5,33});
        if(phase==6){o.push_back({15,20});b.push_back({15,19});}
        if(phase==7)for(int i=10;i<=20;++i)for(int j=19;j<=23;++j)o.push_back({i,j});
        for(Cell q:b)doors.set(q,true);
        for(Cell q:o)doors.set(q,false);
        State start=phase==9?State{15,35,0}:(phase==8?State{16,7,0}:s);
        double expected=oracle(doors,m,start,t);
        for(auto& v:variants) {
            auto p=v->replan(start,b,o);require(!p.stats.capped && p.success()==std::isfinite(expected),"door reachability");
            if(p.success())require(std::abs(p.cost-expected)<1e-6,"door optimality");
            validate_path(doors,m,start,t,p);++comparisons;
            if(auto* s=dynamic_cast<Symmetric*>(v.get()))s->audit();
            if(auto* e=dynamic_cast<Envelope*>(v.get())){e->audit();hits+=e->counters().envelope_hits;events+=e->counters().guard_events;}
        }
    }
    for(bool both:{false,true}) {
        Grid free(24,25);State from{2,2,0},to{20,21,0};Symmetric planner(mesh,certificate,free,to,both,0);
        auto capped=planner.replan(from);require(capped.stats.capped,"symmetric cap not reported");
        planner.set_limit(1000000);auto path=planner.replan(from);double expected=oracle(free,m,from,to);
        require(path.success()==std::isfinite(expected),"symmetric cap recovery");
        if(path.success())require(std::abs(path.cost-expected)<1e-6,"symmetric cap recovery cost");
        planner.audit();++comparisons;
    }
    if(m.name=="grid8") {
        Grid grid(24,25);State from{2,2,0},to{20,21,0};Cell opening{2,3},remote{0,0};grid.set(opening,true);
        Symmetric gap(mesh,certificate,grid,to,true,1000000,true),plain(mesh,certificate,grid,to,true,1000000,false),recover(mesh,certificate,grid,to,true,1000000,true);
        for(auto* p:{&gap,&plain,&recover}){auto a=p->replan(from);require(a.success(),"gap fixture initial");++comparisons;}
        grid.set(opening,false);grid.set(remote,true);
        auto a=gap.replan(from,{remote},{opening}),b=plain.replan(from,{remote},{opening});double expected=oracle(grid,m,from,to);
        require(a.success() && b.success() && std::abs(a.cost-expected)<1e-6 && std::abs(b.cost-expected)<1e-6,"gap fixture optimality");comparisons+=2;
        require(gap.counters().gap_hits>0 && gap.counters().path_probes<plain.counters().path_probes,"gap certificate not exercised");
        recover.set_limit(0);auto c=recover.replan(from,{remote},{opening});require(c.stats.capped,"cap after releasing an opening");
        recover.set_limit(1000000);c=recover.replan(from);require(c.success() && std::abs(c.cost-expected)<1e-6,"recovery with unflushed opening");++comparisons;
        gap.audit();plain.audit();recover.audit();
    }
    require(hits>0,"no envelope hit exercised");
    std::cout<<"{\"status\":\"passed\",\"model\":\""<<m.name<<"\",\"comparisons\":"<<comparisons<<",\"hits\":"<<hits<<",\"guard_events\":"<<events<<"}\n";
    return 0;
}catch(const std::exception& e){std::cerr<<"error: "<<e.what()<<'\n';return 1;}
