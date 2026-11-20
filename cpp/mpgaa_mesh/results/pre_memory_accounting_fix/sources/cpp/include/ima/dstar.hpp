#pragma once
#include "model.hpp"

namespace ima {
struct MeshCacheKey {
    State u; Cell q;
    bool operator==(const MeshCacheKey& b) const { return u==b.u && q==b.q; }
};
struct MeshCacheHash {
    std::size_t operator()(const MeshCacheKey& k) const { return Hash{}(k.u)^mix(Hash{}(k.q)); }
};
struct Transition { State to; double cost; int pid; };

// One backward-search implementation; only this graph adapter changes.
class DynamicGraph {
    const Model& m;
    bool mesh;
    EdgeCache lattice_cache;
    std::unordered_map<MeshCacheKey,bool,MeshCacheHash> mesh_cache;
    bool free_lattice(State u,int pid) {
        auto key=EdgeKey{u,pid}; auto it=lattice_cache.find(key);
        if (it!=lattice_cache.end()) return it->second;
        bool valid=valid_edge(grid,m,u,pid,stats); lattice_cache[key]=valid; return valid;
    }
    bool free_mesh(State u,Cell q) {
        auto key=MeshCacheKey{u,q}; auto it=mesh_cache.find(key);
        if (it!=mesh_cache.end()) return it->second;
        ++stats.checked_cells; bool valid=grid.free(q); mesh_cache[key]=valid; return valid;
    }
public:
    Grid grid;
    Stats stats;
    DynamicGraph(const Model& model,const Grid& g,bool on_mesh):m(model),mesh(on_mesh),grid(g) {}
    State vertex(State u) const { if (mesh) u.k=m.initial[u.k]; return u; }
    Cell origin(State u) const {
        if (!mesh) return u.cell();
        auto d=m.configs[u.k].origin; return {u.i+d.i,u.j+d.j};
    }
    std::vector<Transition> successors(State u) {
        std::vector<Transition> edges;
        if (mesh) {
            for (auto e:m.configs[u.k].edges) {
                State v{u.i+e.di,u.j+e.dj,e.to};
                if (free_mesh(u,v.cell())) edges.push_back({v,e.cost,e.pid});
            }
        } else for (int pid:m.by_start[u.k]) if (free_lattice(u,pid)) edges.push_back({m.head(u,pid),m.primitives[pid].cost,pid});
        return edges;
    }
    std::vector<Transition> predecessors(State v) {
        std::vector<Transition> edges;
        if (mesh) {
            for (auto e:m.predecessors[v.k]) {
                State u{v.i-e.di,v.j-e.dj,e.to};
                if (free_mesh(u,v.cell())) edges.push_back({u,e.cost,e.pid});
            }
        } else for (int pid:m.by_end[v.k]) {
            const auto& p=m.primitives[pid]; State u{v.i-p.di,v.j-p.dj,p.start};
            if (free_lattice(u,pid)) edges.push_back({u,p.cost,pid});
        }
        return edges;
    }
    std::set<State> notify(const std::vector<Cell>& changes,bool opening) {
        std::set<State> sources;
        for (auto q:changes) {
            if (mesh) {
                for (std::size_t cfg=0;cfg<m.configs.size();++cfg) for (auto e:m.configs[cfg].edges) {
                    State u{q.i-e.di,q.j-e.dj,int(cfg)}; MeshCacheKey key{u,q};
                    if (opening) mesh_cache.erase(key);
                    else { auto it=mesh_cache.find(key); if (it!=mesh_cache.end()) it->second=false; }
                    if (!opening || grid.inside(u.cell())) sources.insert(u);
                }
            } else {
                for (std::size_t pid=0;pid<m.primitives.size();++pid) {
                    const auto& p=m.primitives[pid];
                    for (std::size_t k=1;k<p.cells.size();++k) {
                        auto d=p.cells[k]; State u{q.i-d.i,q.j-d.j,p.start}; EdgeKey key{u,int(pid)};
                        if (opening) lattice_cache.erase(key);
                        else { auto it=lattice_cache.find(key); if (it!=lattice_cache.end()) it->second=false; }
                        if (!opening || grid.inside(u.cell())) sources.insert(u);
                    }
                }
            }
        }
        return sources;
    }
};

class DStarLite final : public Planner {
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
    static bool le(Key a,Key b) {
        if (a.first<b.first-EPS) return true;
        if (a.first>b.first+EPS) return false;
        return a.second<=b.second+EPS;
    }
    static bool lt(Key a,Key b) {
        if (a.first<b.first-EPS) return true;
        if (a.first>b.first+EPS) return false;
        return a.second<b.second-EPS;
    }
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
            if (!(le(top_key,key(start)) || inconsistent) || !present) return true;
            if (graph.stats.expansions>=limit) return false;
            State u=item.u; Key updated=key(u);
            if (lt(top_key,updated)) { push(u); continue; }
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
    DStarLite(const Model& model,const Grid& grid,State s,State t,bool mesh,std::uint64_t cap)
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
