#pragma once
#include "index.hpp"
#include <optional>
namespace ima::mesh_lift_fast {
class LiftMPGAA final:public Planner {
    struct Record {
        State state;double h=0,g=INF,initial=0;std::uint64_t epoch=0,closed=0,memo=0,watch=0;
        int parent=-1,parent_edge=-1,next=-1,next_edge=-1;bool good=false,pruned=false;
    };
    struct Item {
        double f,g;std::uint64_t sequence;int id,depth;
        bool operator>(const Item& b) const{return std::tuple(f,-g,-depth,sequence)>std::tuple(b.f,-b.g,-b.depth,b.sequence);}
    };
    struct Watch {int tail,slot;};
    using Repair=std::pair<double,int>;
    const Index& graph;const Model& model;
    Grid grid;State goal,physical_goal;std::uint64_t limit,epoch=0,watch_count=0;
    Options options;bool no_path=false;State failed_start;
    std::unordered_map<std::uint64_t,int> identifiers;std::vector<Record> nodes;CellMap<std::vector<Watch>> watches;
    std::vector<int> policy_chain,closed;
    Work work;Stats stats;
    bool free(Cell q){++stats.checked_cells;return grid.free(q);}
    State head(State u,int id) const{const auto& e=graph.edges[id];return {u.i+e.delta.i,u.j+e.delta.j,e.to};}
    double initial_bound(State u) const {
        const auto& n=graph.nodes[u.k];
        if(n.heading>=0)return distance(u.cell(),physical_goal.cell());
        double value=INF;
        for(auto f:n.finals)value=std::min(value,f.cost+distance({u.i+f.di,u.j+f.dj},physical_goal.cell()));
        return value;
    }
    double base(State u){++work.base_evaluations;return initial_bound(u);}
    std::uint64_t key(State u) const{return (std::uint64_t(u.i)*std::uint64_t(grid.width)+std::uint64_t(u.j))*graph.nodes.size()+std::uint64_t(u.k);}
    int find(State u) const {
        if(!grid.inside(u.cell()))return -1;
        auto it=identifiers.find(key(u));return it==identifiers.end()?-1:it->second;
    }
    double lower(State u){int id=find(u);return id<0?base(u):nodes[id].h;}
    int ensure(State u) {
        auto [it,inserted]=identifiers.try_emplace(key(u),int(nodes.size()));
        if(inserted){Record r;r.state=u;r.h=r.initial=base(u);nodes.push_back(r);}
        return it->second;
    }
    void subscribe(int u,int slot) {
        if(!options.watches)return;
        auto bit=std::uint64_t(1)<<slot;if(nodes[u].watch&bit)return;
        int e=graph.out[nodes[u].state.k][slot];State v=head(nodes[u].state,e);
        if(!grid.inside(v.cell()))return;
        nodes[u].watch|=bit;watches[v.cell()].push_back({u,slot});++watch_count;++work.watch_inserts;
    }
    void repair(const std::vector<Cell>& openings) {
        if(openings.empty())return;
        std::priority_queue<Repair,std::vector<Repair>,std::greater<Repair>> queue;
        std::vector<Repair> local;
        auto decrease=[&](int u,int e,bool use_local) {
            State v=head(nodes[u].state,e);int to=find(v);double candidate=graph.edges[e].cost+(to<0?base(v):nodes[to].h);
            if(candidate>=nodes[u].h-EPS)return;
            if(to<0)to=ensure(v);
            double nv=std::max(options.cache_base?nodes[u].initial:base(nodes[u].state),candidate);
            if(nv>=nodes[u].h-EPS)return;
            nodes[u].h=nv;nodes[u].next=to;nodes[u].next_edge=e;
            Repair item{nv,u};
            if(use_local)local.push_back(item);else{queue.push(item);++work.repair_heap_pushes;}
        };
        if(options.watches) {
            for(Cell q:openings) {
                auto it=watches.find(q);if(it==watches.end())continue;
                auto bucket=std::move(it->second);watches.erase(it);
                for(auto w:bucket) {
                    nodes[w.tail].watch&=~(std::uint64_t(1)<<w.slot);--watch_count;++work.watch_events;++work.seed_tests;++stats.notify_probes;
                    decrease(w.tail,graph.out[nodes[w.tail].state.k][w.slot],false);
                }
            }
        } else {
            for(Cell q:openings)for(std::size_t e=0;e<graph.edges.size();++e) {
                ++stats.notify_probes;const auto& edge=graph.edges[e];State u{q.i-edge.delta.i,q.j-edge.delta.j,edge.from};
                int id=find(u);if(id<0 || nodes[id].h<=nodes[id].initial)continue;
                ++work.seed_tests;decrease(id,int(e),false);
            }
        }
        while(!local.empty() || !queue.empty()) {
            Repair item;
            if(!local.empty()){item=local.back();local.pop_back();++work.repair_local_steps;}
            else{item=queue.top();queue.pop();}
            ++stats.heuristic_pops;auto [key,v]=item;State state=nodes[v].state;
            if(key!=nodes[v].h)continue;
            for(int e:graph.in[state.k]) {
                ++work.repair_edges;const auto& edge=graph.edges[e];State u{state.i-edge.delta.i,state.j-edge.delta.j,edge.from};
                int tail=find(u);if(tail<0 || nodes[tail].h<=nodes[tail].initial)continue;
                if(edge.cost+nodes[v].h>=nodes[tail].h-EPS)continue;
                if(free(state.cell()))decrease(tail,e,options.cascade && edge.cost==0);
                else {
                    subscribe(tail,edge.slot);
                }
            }
        }
    }
    bool goal_condition_slow(int id) {
        std::vector<int> chain;int u=id;bool good=false;
        while(nodes[u].state!=goal && nodes[u].memo!=epoch) {
            checked(chain.size()<=nodes.size(),"mesh policy cycle");chain.push_back(u);++work.policy_tests;
            int v=nodes[u].next,e=nodes[u].next_edge;
            if(v<0 || e<0 || std::abs(nodes[u].h-graph.edges[e].cost-nodes[v].h)>8*EPS || !free(nodes[v].state.cell()))goto finish;
            u=v;
        }
        good=nodes[u].state==goal || nodes[u].good;
    finish:
        for(int v:chain){nodes[v].memo=epoch;nodes[v].good=good;}
        if(good && nodes[id].state!=goal){++work.policy_hits;if(graph.nodes[nodes[id].state.k].heading<0)++work.interior_joins;}
        return good;
    }
    bool goal_condition(int id) {
        if(!options.policy_fast)return goal_condition_slow(id);
        if(nodes[id].state==goal)return true;
        if(nodes[id].next<0)return false;
        if(nodes[id].memo==epoch)return nodes[id].good;
        policy_chain.clear();int u=id;bool good=false;
        while(nodes[u].state!=goal && nodes[u].memo!=epoch) {
            checked(policy_chain.size()<=nodes.size(),"mesh policy cycle");
            policy_chain.push_back(u);++work.policy_tests;
            int v=nodes[u].next,e=nodes[u].next_edge;
            if(v<0 || e<0 || std::abs(nodes[u].h-graph.edges[e].cost-nodes[v].h)>8*EPS || !free(nodes[v].state.cell()))goto finish;
            u=v;
        }
        good=nodes[u].state==goal || nodes[u].good;
    finish:
        for(int v:policy_chain){nodes[v].memo=epoch;nodes[v].good=good;}
        if(good){++work.policy_hits;if(graph.nodes[nodes[id].state.k].heading<0)++work.interior_joins;}
        return good;
    }
    bool terminal_closed(int id) {
        State u=nodes[id].state;
        if(graph.nodes[u.k].heading>=0)return false;
        for(const auto& group:graph.nodes[u.k].terminals) {
            ++work.terminal_cells;Cell q{u.i+group.delta.i,u.j+group.delta.j};
            if(!free(q)){work.terminal_tests+=group.roots.size();continue;}
            for(int root:group.roots) {
                ++work.terminal_tests;int id=find({q.i,q.j,root});
                if(id<0 || nodes[id].closed!=epoch)return false;
            }
        }
        return true;
    }
    void lift() {
        work.closure_seeds+=closed.size();
        while(!closed.empty()) {
            int u=closed.back();closed.pop_back();State state=nodes[u].state;
            for(std::size_t slot=0;slot<graph.out[state.k].size();++slot) {
                ++work.lift_edges;int e=graph.out[state.k][slot];State v=head(state,e);
                double need=nodes[u].h-graph.edges[e].cost;
                if(need<=lower(v)+EPS)continue;
                if(free(v.cell())) {
                    // Closed terminal labels already dominate every valid
                    // skipped completion. Lifting must stop before a root.
                    checked(graph.nodes[v.k].heading<0,"adaptive lift escaped a closed terminal envelope");
                    int child=ensure(v);nodes[child].h=need;
                    ++work.lift_writes;++work.closure_pushes;closed.push_back(child);
                } else subscribe(u,int(slot));
            }
        }
    }
    Path solve(State physical_start) {
        Path failed;int start=ensure({physical_start.i,physical_start.j,graph.roots[physical_start.k]});
        std::priority_queue<Item,std::vector<Item>,std::greater<Item>> open;
        std::optional<Item> inline_item;std::uint64_t sequence=0;closed.clear();
        auto push=[&](Item item){open.push(item);++work.heap_pushes;};
        auto current=[&](const Item& x){return nodes[x.id].epoch==epoch && x.g==nodes[x.id].g && nodes[x.id].closed!=epoch;};
        auto clean=[&](){while(!open.empty() && !current(open.top())){open.pop();++work.heap_pops;}};
        nodes[start].epoch=epoch;nodes[start].g=0;nodes[start].parent=-1;
        push({nodes[start].h,0,sequence++,start,0});int join=-1;
        while(inline_item || !open.empty()) {
            clean();Item item;
            if(inline_item){item=*inline_item;inline_item.reset();++work.contour_steps;}
            else{if(open.empty())break;item=open.top();open.pop();++work.heap_pops;}
            if(!current(item))continue;
            int u=item.id;State state=nodes[u].state;
            if(options.trace)work.trace_hash=mix(work.trace_hash^Hash{}(state));
            if(goal_condition(u)){join=u;break;}
            if(terminal_closed(u)) {
                nodes[u].closed=epoch;nodes[u].pruned=true;closed.push_back(u);++work.terminal_prunes;continue;
            }
            if(stats.expansions>=limit){failed.stats.capped=true;return failed;}
            ++stats.expansions;nodes[u].closed=epoch;nodes[u].pruned=false;closed.push_back(u);
            if(graph.nodes[state.k].heading>=0)++work.boundary_expansions;else++work.interior_expansions;
            std::optional<Item> child;
            for(const auto& group:graph.groups[state.k]) {
                Cell cell{state.i+group.delta.i,state.j+group.delta.j};if(!free(cell))continue;
                for(int e:group.edges) {
                    State vstate=head(state,e);int v=ensure(vstate);double ng=item.g+graph.edges[e].cost;
                    if(nodes[v].epoch==epoch && ng>=nodes[v].g-EPS)continue;
                    // A consistent heuristic settles each vertex once; allow
                    // numerical reopenings rather than discard a better path.
                    if(nodes[v].closed==epoch)nodes[v].closed=0;
                    nodes[v].epoch=epoch;nodes[v].g=ng;nodes[v].parent=u;nodes[v].parent_edge=e;
                    Item next{ng+nodes[v].h,ng,sequence++,v,options.depth_tie?graph.nodes[vstate.k].depth:0};
                    if(options.contour && (!child || *child>next)){if(child)push(*child);child=next;}else push(next);
                }
            }
            if(child) {
                clean();
                if(current(*child) && (open.empty() || !(*child>open.top())))inline_item=child;
                else push(*child);
            }
        }
        if(join<0)return failed;
        std::vector<int> vertices{join},edges;
        for(int u=join;u!=start;) {
            checked(vertices.size()<=nodes.size()+1,"mesh parent cycle");edges.push_back(nodes[u].parent_edge);u=nodes[u].parent;checked(u>=0,"missing mesh parent");vertices.push_back(u);
        }
        std::reverse(vertices.begin(),vertices.end());std::reverse(edges.begin(),edges.end());
        for(int u=join;nodes[u].state!=goal;) {
            checked(vertices.size()<=nodes.size()+1,"mesh suffix cycle");int e=nodes[u].next_edge;u=nodes[u].next;checked(u>=0 && e>=0,"missing mesh suffix");edges.push_back(e);vertices.push_back(u);
        }
        std::vector<int> primitives;for(int e:edges)if(graph.edges[e].pid>=0)primitives.push_back(graph.edges[e].pid);
        Path result=path_from_ids(model,physical_start,primitives);
        checked(result.states.back()==physical_goal && std::abs(result.cost-(nodes[join].g+nodes[join].h))<1e-6,"native mesh projection/cost mismatch");
        {
            std::size_t kept=0;
            for(int u:closed) {
                double value=result.cost-nodes[u].g;
                checked(value>=nodes[u].h-1e-6,"native adaptive update below old bound");
                bool changed=value>nodes[u].h;
                if(changed){nodes[u].h=value;++work.learning_updates;}
                if(!options.focused || (changed && (options.watches || nodes[u].pruned)))closed[kept++]=u;
            }
            // Install only after the entire adaptive batch: watches concern
            // violated inequalities, not temporary intermediate label values.
            closed.resize(kept);lift();
        }
        for(std::size_t k=0;k<edges.size();++k){nodes[vertices[k]].next=vertices[k+1];nodes[vertices[k]].next_edge=edges[k];}
        result.stats.certified=stats.expansions==0;return result;
    }
public:
    LiftMPGAA(const Index& idx,const Grid& g,State target,std::uint64_t cap,Options tuning=Options::plain())
        :graph(idx),model(idx.model),grid(g),goal{target.i,target.j,idx.roots[target.k]},physical_goal(target),limit(cap),options(tuning){
        checked(grid.cells.size()<=std::numeric_limits<std::uint64_t>::max()/graph.nodes.size(),"state key overflow");
    }
    Work counters() const{return work;}
    void set_limit(std::uint64_t cap){limit=cap;}
    Path replan(State start,const std::vector<Cell>& blocks={},const std::vector<Cell>& openings={}) override {
        auto [b,o]=net_changes(grid,blocks,openings);work={};stats={};stats.backend_calls=1;++epoch;
        for(auto q:b)grid.set(q,true);
        for(auto q:o)grid.set(q,false);
        repair(o);Path answer;
        if(free(start.cell()) && free(physical_goal.cell())) {
            if(no_path && start==failed_start && o.empty()){stats.backend_calls=0;answer.stats.certified=true;}
            else answer=solve(start);
        }
        no_path=!answer.success() && !answer.stats.capped;failed_start=start;
        bool cap=answer.stats.capped,cert=answer.stats.certified;answer.stats=stats;answer.stats.capped=cap;answer.stats.certified=cert;
        work.active_watches=watch_count;work.records=nodes.size();return answer;
    }
    void audit() const {
        auto bound=[&](State u){int id=find(u);return id<0?initial_bound(u):nodes[id].h;};
        for(const auto& u:nodes) {
            checked(u.h>=initial_bound(u.state)-1e-7,"native heuristic below base");
            for(std::size_t slot=0;slot<graph.out[u.state.k].size();++slot) {
                int e=graph.out[u.state.k][slot];State v=head(u.state,e);double rhs=graph.edges[e].cost+bound(v);
                if(grid.free(v.cell()))checked(u.h<=rhs+1e-6,"inconsistent native mesh heuristic");
                else if(options.watches && grid.inside(v.cell()) && u.h>rhs+EPS)checked(u.watch&(std::uint64_t(1)<<slot),"missing cell violation watch");
            }
        }
    }
};
}
