#pragma once
// Stage two: terminal pruning with consistency-preserving local adaptive lifting.
// The unchanged native kernel remains in ../mesh_vertex/algorithms.hpp.
#include "../mesh_vertex/factory.hpp"
namespace ima::mesh_lift {
using Index=mesh_vertex::Index;
struct Work:mesh_vertex::Work {
    std::uint64_t terminal_tests=0,terminal_prunes=0,lift_edges=0,lift_writes=0;
    void add(const Work& b){mesh_vertex::Work::add(b);terminal_tests+=b.terminal_tests;terminal_prunes+=b.terminal_prunes;lift_edges+=b.lift_edges;lift_writes+=b.lift_writes;}
};
class LiftMPGAA final:public Planner {
    struct Record {
        State state;double h=0,g=INF;std::uint64_t epoch=0,closed=0,memo=0,watch=0;
        int parent=-1,parent_edge=-1,next=-1,next_edge=-1;bool learned=false,good=false;
    };
    struct Item {
        double f,g;std::uint64_t sequence;int id;
        bool operator>(const Item& b) const{return std::tuple(f,-g,sequence)>std::tuple(b.f,-b.g,b.sequence);}
    };
    struct Watch {int tail,slot;};
    using Repair=std::tuple<double,State,int>;
    const Index& index;const Model& model;const variants::TemplateGraph& graph;
    Grid grid;State goal,physical_goal;std::uint64_t limit,epoch=0,watch_count=0;
    bool triggered,contour,cascade,adaptive,policy,prune,no_path=false;State failed_start;
    StateMap<int> identifiers;std::vector<Record> nodes;CellMap<std::vector<Watch>> watches;
    Work work;Stats stats;
    bool free(Cell q){++stats.checked_cells;return grid.free(q);}
    State head(State u,int id) const{const auto& e=graph.edges[id];return {u.i+e.delta.i,u.j+e.delta.j,e.to};}
    double base(State u) const {
        const auto& n=graph.nodes[u.k];
        if(n.heading>=0)return distance(u.cell(),physical_goal.cell());
        double v=INF;
        for(auto f:n.finals)v=std::min(v,f.cost+distance({u.i+f.di,u.j+f.dj},physical_goal.cell()));
        return v-n.potential;
    }
    double lower(State u) const{auto it=identifiers.find(u);return it==identifiers.end()?base(u):nodes[it->second].h;}
    int ensure(State u) {
        auto it=identifiers.find(u);if(it!=identifiers.end())return it->second;
        int id=int(nodes.size());Record r;r.state=u;r.h=base(u);nodes.push_back(r);identifiers.emplace(u,id);return id;
    }
    void subscribe(int u,int slot) {
        if(!triggered)return;
        auto bit=std::uint64_t(1)<<slot;if(nodes[u].watch&bit)return;
        int e=graph.out[nodes[u].state.k][slot];State v=head(nodes[u].state,e);
        if(!grid.inside(v.cell()))return;
        nodes[u].watch|=bit;watches[v.cell()].push_back({u,slot});++watch_count;++work.watch_inserts;
    }
    void repair(const std::vector<Cell>& openings) {
        if(!adaptive || openings.empty())return;
        std::priority_queue<Repair,std::vector<Repair>,std::greater<Repair>> queue;
        std::vector<Repair> local;
        auto decrease=[&](int u,int e,bool use_local) {
            State v=head(nodes[u].state,e);double candidate=graph.edges[e].cost+lower(v);
            if(candidate>=nodes[u].h-EPS)return;
            int to=ensure(v);double nv=std::max(base(nodes[u].state),candidate);
            if(nv>=nodes[u].h-EPS)return;
            nodes[u].h=nv;nodes[u].next=to;nodes[u].next_edge=e;
            Repair item{nv+graph.nodes[nodes[u].state.k].potential,nodes[u].state,u};
            if(use_local)local.push_back(item);else{queue.push(item);++work.repair_heap_pushes;}
        };
        if(triggered) {
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
                auto it=identifiers.find(u);if(it==identifiers.end() || !nodes[it->second].learned)continue;
                ++work.seed_tests;decrease(it->second,int(e),false);
            }
        }
        while(!local.empty() || !queue.empty()) {
            Repair item;
            if(!local.empty()){item=local.back();local.pop_back();++work.repair_local_steps;}
            else{item=queue.top();queue.pop();}
            ++stats.heuristic_pops;auto [key,state,v]=item;
            if(key!=nodes[v].h+graph.nodes[state.k].potential)continue;
            for(int e:graph.in[state.k]) {
                ++work.repair_edges;const auto& edge=graph.edges[e];State u{state.i-edge.delta.i,state.j-edge.delta.j,edge.from};
                auto it=identifiers.find(u);if(it==identifiers.end() || !nodes[it->second].learned)continue;
                int tail=it->second;
                if(edge.cost+nodes[v].h>=nodes[tail].h-EPS)continue;
                if(free(state.cell()))decrease(tail,e,cascade && edge.base==0);
                else {
                    const auto& out=graph.out[u.k];auto at=std::find(out.begin(),out.end(),e);require(at!=out.end(),"missing reverse mesh edge");
                    subscribe(tail,int(at-out.begin()));
                }
            }
        }
    }
    bool goal_condition(int id) {
        if(!policy)return nodes[id].state==goal;
        std::vector<int> chain;int u=id;bool good=false;
        while(nodes[u].state!=goal && nodes[u].memo!=epoch) {
            require(chain.size()<=nodes.size(),"mesh policy cycle");chain.push_back(u);++work.policy_tests;
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
    bool terminal_closed(int id) {
        State u=nodes[id].state;
        if(graph.nodes[u.k].heading>=0)return false;
        for(auto f:graph.nodes[u.k].finals) {
            ++work.terminal_tests;
            State v{u.i+f.di,u.j+f.dj,graph.roots[f.theta]};
            if(!free(v.cell()))continue;
            auto it=identifiers.find(v);
            if(it==identifiers.end() || nodes[it->second].closed!=epoch)return false;
        }
        return true;
    }
    void lift(const std::vector<int>& closed) {
        std::vector<int> local=closed;
        while(!local.empty()) {
            int u=local.back();local.pop_back();State state=nodes[u].state;
            for(std::size_t slot=0;slot<graph.out[state.k].size();++slot) {
                ++work.lift_edges;int e=graph.out[state.k][slot];State v=head(state,e);
                double need=nodes[u].h-graph.edges[e].cost;
                if(need<=lower(v)+EPS)continue;
                if(free(v.cell())) {
                    // Closed terminal labels already dominate every valid
                    // skipped completion. Lifting must stop before a root.
                    require(graph.nodes[v.k].heading<0,"adaptive lift escaped a closed terminal envelope");
                    int child=ensure(v);nodes[child].h=need;nodes[child].learned=true;
                    ++work.lift_writes;local.push_back(child);
                } else subscribe(u,int(slot));
            }
        }
    }
    Path solve(State physical_start) {
        Path failed;int start=ensure({physical_start.i,physical_start.j,graph.roots[physical_start.k]});
        std::priority_queue<Item,std::vector<Item>,std::greater<Item>> open;
        std::optional<Item> inline_item;std::uint64_t sequence=0;std::vector<int> closed;
        auto push=[&](Item item){open.push(item);++work.heap_pushes;};
        auto current=[&](const Item& x){return nodes[x.id].epoch==epoch && x.g==nodes[x.id].g && nodes[x.id].closed!=epoch;};
        auto clean=[&](){while(!open.empty() && !current(open.top())){open.pop();++work.heap_pops;}};
        nodes[start].epoch=epoch;nodes[start].g=0;nodes[start].parent=-1;
        push({nodes[start].h,0,sequence++,start});int join=-1;
        while(inline_item || !open.empty()) {
            clean();Item item;
            if(inline_item){item=*inline_item;inline_item.reset();++work.contour_steps;}
            else{if(open.empty())break;item=open.top();open.pop();++work.heap_pops;}
            if(!current(item))continue;
            int u=item.id;State state=nodes[u].state;
            work.trace_hash=mix(work.trace_hash^Hash{}(state));
            if(goal_condition(u)){join=u;break;}
            if(prune && terminal_closed(u)) {
                nodes[u].closed=epoch;closed.push_back(u);++work.terminal_prunes;continue;
            }
            if(stats.expansions>=limit){failed.stats.capped=true;return failed;}
            ++stats.expansions;nodes[u].closed=epoch;closed.push_back(u);
            if(graph.nodes[state.k].heading>=0)++work.boundary_expansions;else++work.interior_expansions;
            std::optional<Item> child;
            for(const auto& group:index.groups[state.k]) {
                Cell cell{state.i+group.delta.i,state.j+group.delta.j};if(!free(cell))continue;
                for(int e:group.edges) {
                    State vstate=head(state,e);int v=ensure(vstate);double ng=item.g+graph.edges[e].cost;
                    if(nodes[v].epoch==epoch && ng>=nodes[v].g-EPS)continue;
                    // A consistent heuristic settles each vertex once; allow
                    // numerical reopenings rather than discard a better path.
                    if(nodes[v].closed==epoch)nodes[v].closed=0;
                    nodes[v].epoch=epoch;nodes[v].g=ng;nodes[v].parent=u;nodes[v].parent_edge=e;
                    Item next{ng+nodes[v].h,ng,sequence++,v};
                    if(contour && (!child || *child>next)){if(child)push(*child);child=next;}else push(next);
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
            require(vertices.size()<=nodes.size()+1,"mesh parent cycle");edges.push_back(nodes[u].parent_edge);u=nodes[u].parent;require(u>=0,"missing mesh parent");vertices.push_back(u);
        }
        std::reverse(vertices.begin(),vertices.end());std::reverse(edges.begin(),edges.end());
        for(int u=join;nodes[u].state!=goal;) {
            require(vertices.size()<=nodes.size()+1,"mesh suffix cycle");int e=nodes[u].next_edge;u=nodes[u].next;require(u>=0 && e>=0,"missing mesh suffix");edges.push_back(e);vertices.push_back(u);
        }
        std::vector<int> primitives;for(int e:edges)if(graph.edges[e].pid>=0)primitives.push_back(graph.edges[e].pid);
        Path result=path_from_ids(model,physical_start,primitives);
        require(result.states.back()==physical_goal && std::abs(result.cost-(nodes[join].g+nodes[join].h))<1e-6,"native mesh projection/cost mismatch");
        if(adaptive) {
            for(int u:closed) {
                double value=result.cost-nodes[u].g;
                require(value>=nodes[u].h-1e-6,"native adaptive update below old bound");
                if(value>nodes[u].h){nodes[u].h=value;++work.learning_updates;}
                nodes[u].learned=true;
            }
            // Install only after the entire adaptive batch: watches concern
            // violated inequalities, not temporary intermediate label values.
            lift(closed);
        }
        if(policy)for(std::size_t k=0;k<edges.size();++k){nodes[vertices[k]].next=vertices[k+1];nodes[vertices[k]].next_edge=edges[k];}
        result.stats.certified=stats.expansions==0;return result;
    }
public:
    LiftMPGAA(const Index& idx,const Grid& g,State target,std::uint64_t cap,bool trigger,bool fast,bool repair_cascade,bool learn=true,bool reuse=true,bool terminal_pruning=true)
        :index(idx),model(idx.model),graph(idx.graph),grid(g),goal{target.i,target.j,graph.roots[target.k]},physical_goal(target),limit(cap),triggered(trigger),contour(fast),cascade(repair_cascade),adaptive(learn),policy(reuse),prune(terminal_pruning){}
    Work counters() const{return work;}
    void set_limit(std::uint64_t cap){limit=cap;}
    Path replan(State start,const std::vector<Cell>& blocks={},const std::vector<Cell>& openings={}) override {
        auto [b,o]=net_changes(grid,blocks,openings);work={};stats={};stats.backend_calls=1;++epoch;
        for(auto q:b)grid.set(q,true);
        for(auto q:o)grid.set(q,false);
        repair(o);Path answer;
        if(free(start.cell()) && free(physical_goal.cell())) {
            if(adaptive && no_path && start==failed_start && o.empty()){stats.backend_calls=0;answer.stats.certified=true;}
            else answer=solve(start);
        }
        no_path=!answer.success() && !answer.stats.capped;failed_start=start;
        bool cap=answer.stats.capped,cert=answer.stats.certified;answer.stats=stats;answer.stats.capped=cap;answer.stats.certified=cert;
        work.active_watches=watch_count;work.records=nodes.size();return answer;
    }
    void audit() const {
        for(const auto& u:nodes) {
            require(u.h>=base(u.state)-1e-7,"native heuristic below base");
            for(std::size_t slot=0;slot<graph.out[u.state.k].size();++slot) {
                int e=graph.out[u.state.k][slot];State v=head(u.state,e);double rhs=graph.edges[e].cost+lower(v);
                if(grid.free(v.cell()))require(u.h<=rhs+1e-6,"inconsistent native mesh heuristic");
                else if(triggered && grid.inside(v.cell()) && u.h>rhs+EPS)require(u.watch&(std::uint64_t(1)<<slot),"missing cell violation watch");
            }
        }
    }
};
}
