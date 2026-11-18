#pragma once
// Experiment-local numerical correction of the DStarLite class from
// cpp/include/ima/dstar.hpp at commit 30f18579. DynamicGraph is reused unchanged.
// Only the stopping boundary and stale-key comparison differ. The legacy
// header stays byte-for-byte unchanged for reproduction of earlier results.
namespace ima {
class BoundaryDStarLite final : public Planner {
    using Key=std::pair<double,double>;
    struct Item {
        Key key; std::uint64_t seq; State u;
        bool operator>(const Item& b) const { return std::tie(key,seq)>std::tie(b.key,b.seq); }
    };
    const Model& m;
    DynamicGraph graph;
    State goal,start,last,lattice_goal;
    StateMap<double> g,rhs;
    StateMap<Key> current;
    std::priority_queue<Item,std::vector<Item>,std::greater<Item>> queue;
    std::uint64_t seq=0,limit;
    double km=0;
    Key key(State u) const { double v=std::min(value(g,u),value(rhs,u)); return {v+distance(start.cell(),graph.origin(u))+km,v}; }
    void push(State u) { Key k=key(u); current[u]=k; queue.push({k,++seq,u}); }
    void update(State u) {
        if (u!=goal) {
            double v=INF; for (auto e:graph.successors(u)) v=std::min(v,e.cost+value(g,e.to));
            rhs[u]=v;
        }
        current.erase(u); if (value(g,u)!=value(rhs,u)) push(u);
    }
    bool top(Item& result) {
        while (!queue.empty()) {
            auto item=queue.top(); auto it=current.find(item.u);
            if (it!=current.end() && it->second==item.key) { result=item; return true; }
            queue.pop();
        }
        return false;
    }
    bool compute() {
        while (true) {
            Item item; bool present=top(item); Key top_key=present ? item.key : Key{INF,INF};
            double gs=value(g,start),rs=value(rhs,start);
            bool inconsistent=gs!=rs && !(std::abs(gs-rs)<=EPS);
            // The heap uses exact lexicographic keys. An epsilon comparison with
            // the second coordinate at termination can stop before a near-equal
            // first-key entry hidden behind the heap top, leaving stale g labels
            // on a zero-cost mesh prefix. Drain the entire first-key boundary.
            double boundary=key(start).first;
            double guard=EPS*(1+std::abs(boundary));
            if (!present || (!inconsistent && top_key.first>boundary+guard)) return true;
            if (graph.stats.expansions>=limit) return false;
            State u=item.u; Key updated=key(u);
            if (top_key<updated) { push(u); continue; }
            queue.pop(); current.erase(u); ++graph.stats.expansions;
            double gu=value(g,u),ru=value(rhs,u);
            if (gu>ru) {
                g[u]=ru;
                for (auto e:graph.predecessors(u)) {
                    if (e.to==goal) continue;
                    double v=e.cost+ru;
                    if (v<value(rhs,e.to)) {
                        rhs[e.to]=v; current.erase(e.to); if (value(g,e.to)!=v) push(e.to);
                    }
                }
            } else {
                g[u]=INF; update(u);
                for (auto e:graph.predecessors(u)) {
                    double old=e.cost+gu,now=value(rhs,e.to);
                    if (now==old || std::abs(now-old)<EPS) update(e.to);
                }
            }
        }
    }
    Path extract(State s,double label) {
        State u=start; std::vector<int> ids;
        for (std::size_t steps=0;u!=goal;++steps) {
            require(steps<100000,"D* Lite extraction exceeded path limit");
            double best=INF; Transition selected{}; bool found=false;
            for (auto e:graph.successors(u)) {
                double v=e.cost+value(g,e.to);
                if (!found || v<best-1e-12) { selected=e; best=v; found=true; }
            }
            require(found && std::isfinite(best),"finite D* Lite label has no path");
            if (selected.pid>=0) ids.push_back(selected.pid);
            u=selected.to;
        }
        Path p=path_from_ids(m,s,ids);
        require(std::abs(p.cost-label)<1e-6 && p.states.back()==lattice_goal,"D* Lite path/label mismatch");
        return p;
    }
public:
    BoundaryDStarLite(const Model& model,const Grid& grid,State s,State t,bool mesh,std::uint64_t cap)
        :m(model),graph(model,grid,mesh),goal(graph.vertex(t)),start(graph.vertex(s)),last(start),lattice_goal(t),limit(cap) { rhs[goal]=0; push(goal); }
    Path replan(State s,const std::vector<Cell>& blocks={},const std::vector<Cell>& opens={}) override {
        auto [b,o]=net_changes(graph.grid,blocks,opens); graph.stats={}; graph.stats.backend_calls=1;
        // As in Python D* Lite, endpoints are assumed free; reject violations explicitly.
        for (auto q:b) require(q!=s.cell() && q!=lattice_goal.cell(),"D* Lite requires free endpoints");
        start=graph.vertex(s); km+=distance(last.cell(),start.cell()); last=start;
        for (auto q:b) graph.grid.set(q,true);
        for (State u:graph.notify(b,false)) if (g.count(u) || rhs.count(u)) update(u);
        for (auto q:o) graph.grid.set(q,false);
        for (State u:graph.notify(o,true)) update(u); // include previously unseen sources
        require(graph.grid.free(s.cell()) && graph.grid.free(lattice_goal.cell()),"D* Lite requires free endpoints");
        Path result;
        if (!compute()) result.stats.capped=true;
        else {
            double label=std::min(value(g,start),value(rhs,start));
            if (std::isfinite(label)) result=extract(s,label);
        }
        bool capped=result.stats.capped; result.stats=graph.stats; result.stats.capped=capped; return result;
    }
};
} // namespace ima
