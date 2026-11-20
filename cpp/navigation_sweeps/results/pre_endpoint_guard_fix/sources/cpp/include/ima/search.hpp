#pragma once
#include "model.hpp"

namespace ima {
// A step returns after one real expansion, matching the Python generators.
// The two steppers share counters when Mesh/ParallA* interleaves them.
class SearchStepper {
    const Model& m;
    const Grid& grid;
    State start,goal,root,target;
    bool mesh,lazy,soft;
    Stats& stats;
    Open open;
    StateMap<double> best;
    StateMap<Arrow> parent;
    StateMap<State> anchor;
    StateSet closed,signatures;
    std::uint64_t sequence=0;

    double heuristic(State u) const {
        if (!mesh || m.configs[u.k].theta>=0) return distance(u.cell(),goal.cell());
        double h=INF;
        for (auto f:m.configs[u.k].finals) h=std::min(h,f.cost+distance({u.i+f.di,u.j+f.dj},goal.cell()));
        return h;
    }
    void finish(State u,double cost) {
        std::vector<int> ids;
        if (mesh) {
            std::vector<State> chain{u};
            while (u!=root) { u=anchor.at(u); chain.push_back(u); }
            std::reverse(chain.begin(),chain.end());
            for (std::size_t k=1;k<chain.size();++k) {
                State a=chain[k-1],b=chain[k]; a.k=m.configs[a.k].theta; b.k=m.configs[b.k].theta;
                ids.push_back(m.between(a,b));
            }
        } else {
            while (u!=start) { auto a=parent.at(u); ids.push_back(a.pid); u=a.to; }
            std::reverse(ids.begin(),ids.end());
        }
        result=path_from_ids(m,start,ids);
        require(std::abs(result.cost-cost)<1e-6,"A* reconstruction cost mismatch");
        done=true;
    }
public:
    bool done=false;
    Path result;
    SearchStepper(const Model& model,const Grid& g,State s,State t,bool on_mesh,bool is_lazy,bool prune,Stats& counters)
        :m(model),grid(g),start(s),goal(t),mesh(on_mesh),lazy(is_lazy),soft(prune),stats(counters) {
        root=s; target=t;
        if (mesh) { root.k=m.initial[s.k]; target.k=m.initial[t.k]; }
        if (!lazy) best[root]=0;
        open.push({distance(s.cell(),t.cell()),0,0,root,{},-1});
    }
    void step() {
        while (!open.empty()) {
            auto item=open.top(); open.pop(); State u=item.u;
            if (closed.count(u) || (!lazy && item.g>value(best,u)+EPS)) continue;
            if (lazy && item.pid>=0 && !valid_edge(grid,m,item.prev,item.pid,stats)) continue;
            if (!mesh && item.pid>=0) parent[u]={item.prev,item.pid};
            if (mesh) closed.insert(u);
            if (u==target) { finish(u,item.g); return; }
            if (mesh && m.configs[u.k].theta<0) {
                bool all_done=true;
                for (auto f:m.configs[u.k].finals) {
                    Cell q{u.i+f.di,u.j+f.dj}; ++stats.checked_cells;
                    if (grid.free(q) && !closed.count({q.i,q.j,m.initial[f.theta]})) { all_done=false; break; }
                }
                if (all_done) continue;
                if (soft && !signatures.insert({u.i,u.j,m.configs[u.k].signature}).second) continue;
            }
            closed.insert(u); best[u]=item.g; ++stats.expansions;
            if (!mesh) {
                for (int pid:m.by_start[u.k]) {
                    State v=m.head(u,pid); double ng=item.g+m.primitives[pid].cost;
                    if (closed.count(v) || ng>=value(best,v)-EPS) continue;
                    if (!lazy && !valid_edge(grid,m,u,pid,stats)) continue;
                    if (!lazy) best[v]=ng;
                    open.push({ng+heuristic(v),ng,++sequence,v,u,pid});
                }
            } else {
                std::map<Cell,bool> seen;
                for (auto e:m.configs[u.k].edges) {
                    State v{u.i+e.di,u.j+e.dj,e.to};
                    auto found=seen.find(v.cell());
                    if (found==seen.end()) { ++stats.checked_cells; found=seen.emplace(v.cell(),grid.free(v.cell())).first; }
                    if (!found->second) continue;
                    double ng=item.g+e.cost;
                    if (closed.count(v) || ng>=value(best,v)-EPS) continue;
                    double h=heuristic(v); if (!std::isfinite(h)) continue;
                    best[v]=ng;
                    anchor[v]=m.configs[u.k].theta>=0 ? u : anchor.at(u);
                    open.push({ng+h,ng,++sequence,v,{},-1});
                }
            }
            return;
        }
        done=true;
    }
};

inline Path search(const std::string& method,const Grid& grid,const Model& m,State s,State t,std::uint64_t limit) {
    Path empty;
    if (!grid.free(s.cell()) || !grid.free(t.cell())) return empty;
    if (s==t) return path_from_ids(m,s,{});
    Stats stats; stats.backend_calls=1;
    bool parallel=method=="mesh_parall";
    std::vector<std::unique_ptr<SearchStepper>> steps;
    if (method=="lba" || method=="lazy_lba")
        steps.push_back(std::make_unique<SearchStepper>(m,grid,s,t,false,method=="lazy_lba",false,stats));
    else if (method=="mesha" || parallel)
        steps.push_back(std::make_unique<SearchStepper>(m,grid,s,t,true,false,parallel,stats));
    else throw std::runtime_error("unknown one-shot method: "+method);
    if (parallel) steps.push_back(std::make_unique<SearchStepper>(m,grid,s,t,false,false,false,stats));
    while (true) {
        bool alive=false;
        for (std::size_t k=0;k<steps.size();++k) {
            auto& step=*steps[k]; if (step.done) continue; alive=true;
            int burst=parallel && k==0 ? 100 : 1;
            for (int n=0;n<burst && !step.done;++n) {
                if (stats.expansions>=limit) { empty.stats=stats; empty.stats.capped=true; return empty; }
                step.step();
            }
            if (step.result.success()) { step.result.stats=stats; return std::move(step.result); }
        }
        if (!alive) { empty.stats=stats; return empty; }
    }
}

class Repeated final : public Planner {
    const Model& m;
    Grid grid;
    State goal;
    std::string method;
    std::uint64_t limit;
public:
    Repeated(const Model& model,const Grid& g,State t,std::string name,std::uint64_t cap)
        :m(model),grid(g),goal(t),method(std::move(name)),limit(cap) {}
    Path replan(State s,const std::vector<Cell>& blocks={},const std::vector<Cell>& opens={}) override {
        auto [b,o]=net_changes(grid,blocks,opens);
        for (auto q:b) grid.set(q,true);
        for (auto q:o) grid.set(q,false);
        return search(method,grid,m,s,goal,limit);
    }
};
} // namespace ima
