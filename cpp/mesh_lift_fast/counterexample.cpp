#include "new_factory.hpp"
#include <iostream>
using namespace ima;
Model fixture() {
    Model m;m.name="formal_prefix_opening_counterexample";m.headings=4;
    auto add=[&](int start,int end,double cost,std::vector<Cell> cells){m.primitives.push_back({start,end,0,0,cost,std::move(cells)});};
    // Four boundary headings at one cell represent r,s,v,t. The s-v
    // primitive has two distinct internal configurations u,w. Two initially
    // blocked shortcut primitives have private collision cells x,y.
    add(0,1,1,{{0,0},{0,0}}); // r-s
    add(0,2,2,{{0,0},{0,0}}); // r-v
    add(1,2,3,{{0,0},{0,0},{0,0},{0,0}}); // s-u-w-v
    add(2,3,10,{{0,0},{0,0}}); // v-t, expensive and free
    add(2,3,1,{{0,0},{0,1},{0,0}}); // cheap v-t, blocked at x
    add(1,3,5,{{0,0},{1,0},{0,0}}); // s-t, blocked at y
    auto graph=variants::prefix(m.primitives,m.headings);m.initial=graph.roots;
    for(std::size_t i=0;i<graph.nodes.size();++i) {
        const auto& n=graph.nodes[i];Config c;c.theta=n.heading;c.signature=int(i);c.origin=n.origin;c.finals=n.finals;
        for(int id:graph.out[i]){const auto& e=graph.edges[id];c.edges.push_back({e.delta.i,e.delta.j,e.to,e.base,e.pid});}
        m.configs.push_back(std::move(c));
    }
    m.prepare();return m;
}
double oracle(const Grid& grid,const Model& model,State start,State goal) {
    using Item=std::pair<double,State>;std::priority_queue<Item,std::vector<Item>,std::greater<Item>> queue;
    std::map<State,double> d;d[start]=0;queue.push({0,start});
    while(!queue.empty()) {
        auto [g,u]=queue.top();queue.pop();if(g!=d[u])continue;if(u==goal)return g;
        for(int id:model.by_start[u.k]) {
            auto& p=model.primitives[id];bool valid=true;
            for(auto c:p.cells)if(!grid.free({u.i+c.i,u.j+c.j})){valid=false;break;}
            if(!valid)continue;
            auto v=model.head(u,id);double candidate=g+p.cost;auto it=d.find(v);
            if(it==d.end() || candidate<it->second){d[v]=candidate;queue.push({candidate,v});}
        }
    }
    return INF;
}

template<class Solver>void check(Solver& solver,const Model& m,const Grid& old) {
    auto first=solver.replan({2,2,0});require(first.success() && first.cost==12,"first fixture cost");
    auto next=solver.replan({2,2,1},{},{{2,3},{3,2}});Grid open=old;open.set({2,3},false);open.set({3,2},false);
    require(next.success() && next.cost==oracle(open,m,{2,2,1},{2,2,3}) && next.cost==4,"opening fixture must return four");
    validate_path(open,m,{2,2,1},{2,2,3},next);solver.audit();
}
int main()try {
    auto m=fixture();Grid old(5,5);old.set({2,3},true);old.set({3,2},true);
    mesh_lift_fast::Index compact(m),raw(m,false);State goal{2,2,3};
    for(bool cascade:{false,true})for(bool focused:{false,true}) {
        auto options=cascade?mesh_lift_fast::Options::cascading():mesh_lift_fast::Options::plain();options.focused=focused;
        mesh_lift_fast::LiftMPGAA solver(compact,old,goal,10000,options);check(solver,m,old);
    }
    variants::Prepared prepared(m);mesh_vertex::Index index(m,prepared);
    for(bool cascade:{false,true}){mesh_lift_zero::LiftMPGAA solver(index,old,goal,10000,cascade,cascade,cascade);check(solver,m,old);}
    auto invalid=m;int internal=-1;for(std::size_t i=0;i<m.configs.size();++i)if(m.configs[i].theta<0){internal=int(i);break;}
    invalid.configs[internal].edges.push_back({0,0,internal,0,-1});bool rejected=false;
    try{mesh_lift_fast::Index bad(invalid);}catch(const std::runtime_error& e){rejected=std::string(e.what())=="zero-cost cycle in prefix automaton";}
    require(rejected,"zero cycle not rejected");
    std::cout<<"{\"status\":\"passed\",\"correct_opening_variants\":6,\"cost_after_openings\":4,\"zero_cycle_rejected\":true}\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
