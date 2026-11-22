#pragma once
#include "ima/model.hpp"

namespace ima::mesh_lift_fast {
// Do not allocate a diagnostic std::string on successful hot-path checks.
inline void checked(bool condition,const char* message){if(!condition)throw std::runtime_error(message);}
// Direct view of the original zero-cost prefix automaton. No potentials or
// contracted/reversed/boundary templates are constructed.
struct Index {
    struct Terminal {Cell delta;std::vector<int> roots;};
    struct Node {int heading=-1,depth=0;std::vector<Final> finals;std::vector<Terminal> terminals;};
    struct Edge {int from,to,pid,slot;Cell delta;double cost;};
    struct Group {Cell delta;std::vector<int> edges;};
    const Model& model;const std::vector<int>& roots;
    std::vector<Node> nodes;std::vector<Edge> edges;
    std::vector<std::vector<int>> out,in;
    std::vector<std::vector<Group>> groups;
    double compile_s=0;std::size_t original_finals=0,heuristic_finals=0,terminal_roots=0;
    explicit Index(const Model& m,bool deduplicate=true):model(m),roots(m.initial),nodes(m.configs.size()),out(nodes.size()),in(nodes.size()),groups(nodes.size()) {
        auto begin=Clock::now();
        for(std::size_t u=0;u<nodes.size();++u) {
            auto& n=nodes[u];const auto& c=m.configs[u];n.heading=c.theta;
            if(c.theta<0) {
            original_finals+=c.finals.size();
            if(deduplicate) {
                std::map<Cell,double> lower;std::map<Cell,std::set<int>> terminals;
                for(auto f:c.finals) {
                    Cell q{f.di,f.dj};auto it=lower.find(q);
                    if(it==lower.end() || f.cost<it->second)lower[q]=f.cost;
                    terminals[q].insert(roots[f.theta]);
                }
                for(auto [q,cost]:lower)n.finals.push_back({q.i,q.j,0,cost});
                for(auto& [q,heads]:terminals)n.terminals.push_back({q,{heads.begin(),heads.end()}});
            } else {
                n.finals=c.finals;
                for(auto f:c.finals)n.terminals.push_back({{f.di,f.dj},{roots[f.theta]}});
            }
            heuristic_finals+=n.finals.size();for(auto& t:n.terminals)terminal_roots+=t.roots.size();
            }
            std::map<Cell,std::vector<int>> grouped;
            for(auto e:c.edges) {
                checked(e.cost>=0 && std::isfinite(e.cost),"invalid original mesh cost");
                checked(e.pid<0 ? e.cost==0 && m.configs[e.to].theta<0 : e.cost>0 && m.configs[e.to].theta>=0,"not a primitive prefix automaton");
                int id=int(edges.size()),slot=int(out[u].size());
                edges.push_back({int(u),e.to,e.pid,slot,{e.di,e.dj},e.cost});out[u].push_back(id);in[e.to].push_back(id);grouped[{e.di,e.dj}].push_back(id);
            }
            checked(out[u].size()<=64,"watch mask degree exceeded");
            for(auto& [q,ids]:grouped)groups[u].push_back({q,std::move(ids)});
        }
        // Zero arcs form a DAG. This replaces the unjustified requirement that
        // every arc must have a strictly positive reweighted cost.
        std::vector<int> degree(nodes.size()),order;
        for(auto e:edges)if(e.cost==0)++degree[e.to];
        for(std::size_t u=0;u<nodes.size();++u)if(!degree[u])order.push_back(int(u));
        for(std::size_t at=0;at<order.size();++at)for(int id:out[order[at]]) {
            auto e=edges[id];if(e.cost!=0)continue;
            nodes[e.to].depth=std::max(nodes[e.to].depth,nodes[e.from].depth+1);
            if(!--degree[e.to])order.push_back(e.to);
        }
        checked(order.size()==nodes.size(),"zero-cost cycle in prefix automaton");compile_s=seconds(begin);
    }
};
struct Options {
    bool watches=false,contour=false,cascade=false;
    bool policy_fast=true,focused=true,depth_tie=true,trace=false,cache_base=true;
    static Options plain(){return {};}
    static Options cascading(){Options o;o.watches=o.contour=o.cascade=true;return o;}
};
struct Work {
    std::uint64_t boundary_expansions=0,interior_expansions=0,heap_pushes=0,heap_pops=0,contour_steps=0;
    std::uint64_t learning_updates=0,repair_edges=0,repair_heap_pushes=0,repair_local_steps=0,seed_tests=0,watch_inserts=0,watch_events=0,active_watches=0,policy_tests=0,policy_hits=0,interior_joins=0,records=0,trace_hash=0;
    std::uint64_t terminal_tests=0,terminal_prunes=0,lift_edges=0,lift_writes=0;
    std::uint64_t base_evaluations=0,closure_seeds=0,closure_pushes=0,terminal_cells=0;
    void add(const Work& b) {
#define ADD(field) field+=b.field;
        ADD(boundary_expansions) ADD(interior_expansions) ADD(heap_pushes) ADD(heap_pops) ADD(contour_steps) ADD(learning_updates) ADD(repair_edges) ADD(repair_heap_pushes) ADD(repair_local_steps) ADD(seed_tests) ADD(watch_inserts) ADD(watch_events) ADD(active_watches) ADD(policy_tests) ADD(policy_hits) ADD(interior_joins) ADD(records) ADD(trace_hash) ADD(terminal_tests) ADD(terminal_prunes) ADD(lift_edges) ADD(lift_writes) ADD(base_evaluations) ADD(closure_seeds) ADD(closure_pushes) ADD(terminal_cells)
#undef ADD
    }
};
}
