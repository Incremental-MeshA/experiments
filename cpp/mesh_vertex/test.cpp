#include "factory.hpp"
#include <iostream>
#include <random>
using namespace ima;
double oracle(const Grid& grid,const Model& m,State s,State t) {
    if(!grid.free(s.cell()) || !grid.free(t.cell()))return INF;
    using Q=std::pair<double,State>;std::priority_queue<Q,std::vector<Q>,std::greater<Q>> queue;
    std::map<State,double> d;d[s]=0;queue.push({0,s});
    while(!queue.empty()) {
        auto [cost,u]=queue.top();queue.pop();if(d.at(u)!=cost)continue;if(u==t)return cost;
        for(const auto& p:m.primitives)if(p.start==u.k) {
            bool valid=true;
            for(std::size_t j=1;j<p.cells.size();++j) {
                Cell c{u.i+p.cells[j].i,u.j+p.cells[j].j};
                if(c.i<0 || c.j<0 || c.i>=grid.height || c.j>=grid.width || grid.cells[std::size_t(c.i)*grid.width+c.j]){valid=false;break;}
            }
            if(!valid)continue;
            State v{u.i+p.di,u.j+p.dj,p.end};double candidate=cost+p.cost;auto it=d.find(v);
            if(it==d.end() || candidate<it->second){d[v]=candidate;queue.push({candidate,v});}
        }
    }
    return INF;
}
int main(int argc,char** argv)try {
    require(argc==2,"provide frozen model");auto suite=read_suite(argv[1]);const auto& m=suite.model;
    variants::Prepared prepared(m);mesh_vertex::MeshIndex index(m,prepared);Certificate certificate(m);
    std::uint64_t comparisons=0,interior=0,watches=0,local=0,joins=0;
    for(int seed=0;seed<12;++seed) {
        std::mt19937 rng(982103+seed);Grid grid(m.headings==1?15:23,m.headings==1?17:25);
        State fixed{2,2,0},goal{grid.height-3,grid.width-3,0};
        for(int i=0;i<grid.height;++i)for(int j=0;j<grid.width;++j)if(rng()%100<14)grid.set({i,j},true);
        grid.set(fixed.cell(),false);grid.set(goal.cell(),false);
        std::vector<std::unique_ptr<Planner>> planners;
        for(const auto& name:mesh_vertex::native_methods)planners.push_back(mesh_vertex::make(name,grid,m,certificate,prepared,index,fixed,goal,1000000));
        Path previous;
        for(int q=0;q<40;++q) {
            State start=fixed;
            if(q%5==2 && previous.success() && previous.states.size()>2)start=previous.states[previous.states.size()/2];
            if(q%7==4)start={int(rng()%grid.height),int(rng()%grid.width),int(rng()%m.headings)};
            std::set<Cell> edits;std::vector<Cell> b,o;
            if(q && q%6!=1)for(int k=0;k<(q%3==0?64:4);++k)edits.insert({int(rng()%grid.height),int(rng()%grid.width)});
            if(q==9 || (q==10 && grid.blocked(goal.cell())))edits.insert(goal.cell());
            for(Cell c:edits){if((q%6==2 && grid.blocked(c)) || (q%6==3 && !grid.blocked(c)))continue;(grid.blocked(c)?o:b).push_back(c);grid.set(c,!grid.blocked(c));}
            if(q%4==0 && !b.empty())b.push_back(b.front());
            if(q%4==0 && !o.empty())o.push_back(o.front());
            double expected=oracle(grid,m,start,goal);
            Path trigger;mesh_vertex::Work trigger_work;
            for(std::size_t k=0;k<planners.size();++k) {
                auto p=planners[k]->replan(start,b,o);std::string context=" seed="+std::to_string(seed)+" q="+std::to_string(q)+" mode="+mesh_vertex::native_methods[k];
                require(!p.stats.capped,"cap"+context);require(p.success()==std::isfinite(expected),"reachability"+context);
                if(p.success())require(std::abs(p.cost-expected)<1e-6,"cost"+context);
                validate_path(grid,m,start,goal,p);auto& solver=dynamic_cast<mesh_vertex::MeshMPGAA&>(*planners[k]);solver.audit();auto w=solver.counters();
                interior+=w.interior_expansions;watches+=w.watch_inserts;local+=w.contour_steps+w.repair_local_steps;joins+=w.interior_joins;++comparisons;
                if(k==0)previous=p;
                if(mesh_vertex::native_methods[k]=="trigger_mesh"){trigger=p;trigger_work=w;}
                if(mesh_vertex::native_methods[k]=="contour_only")require(p.ids==trigger.ids && p.stats.expansions==trigger.stats.expansions && w.trace_hash==trigger_work.trace_hash,"contour changed the exact pop/path order"+context);
            }
        }
    }
    // A previously learned map, a cap, then an opening and recovery.
    Grid g(29,37);State s{5,5,0},t{22,29,0};
    for(const auto& name:mesh_vertex::native_methods) {
        auto p=mesh_vertex::make(name,g,m,certificate,prepared,index,s,t,1000000);p->replan(s);
        auto& a=dynamic_cast<mesh_vertex::MeshMPGAA&>(*p);a.set_limit(1);
        Grid changed=g;std::vector<Cell> b={{12,17},{12,18},{13,18}};for(auto q:b)changed.set(q,true);
        p->replan({4,6,0},b);a.set_limit(1000000);changed.set({12,17},false);
        auto answer=p->replan(s,{},{{12,17}});double expected=oracle(changed,m,s,t);
        require(!answer.stats.capped && answer.success()==std::isfinite(expected),"cap recovery reachability");
        if(answer.success())require(std::abs(answer.cost-expected)<1e-6,"cap recovery cost");
        validate_path(changed,m,s,t,answer);a.audit();++comparisons;
    }
    require(local>0,"no contour continuation exercised");if(m.headings>1)require(interior>0,"no actual mesh-interior search");
    std::cout<<"{\"status\":\"passed\",\"model\":\""<<m.name<<"\",\"comparisons\":"<<comparisons<<",\"interior_expansions\":"<<interior<<",\"watch_inserts\":"<<watches<<",\"local_steps\":"<<local<<",\"interior_joins\":"<<joins<<"}\n";
    return 0;
}catch(const std::exception& e){std::cerr<<"error: "<<e.what()<<'\n';return 1;}
