#pragma once
#include "model.hpp"

namespace ima {
// Directed MPGAA*: the standalone control and MD-A* use this identical class.
class MPGAA final : public Planner {
    const Model& m;
    Grid grid;
    State goal;
    std::uint64_t limit;
    StateMap<double> h;
    StateMap<Arrow> next,support;
    EdgeCache cache;
    bool has_box=false,has_no_path=false;
    State no_path;
    int min_i=0,min_j=0,max_i=0,max_j=0;
    Stats stats;

    double base(State u) const { return distance(u.cell(),goal.cell()); }
    double lower(State u) const { auto it=h.find(u); return it==h.end() ? base(u) : it->second; }
    bool valid(State u,int pid) {
        EdgeKey key{u,pid}; auto hit=cache.find(key);
        if (hit!=cache.end()) return hit->second;
        bool ok=valid_edge(grid,m,u,pid,stats); cache.emplace(key,ok); return ok;
    }
    bool relevant(Cell q) const {
        return has_box && q.i>=min_i-m.reach_i && q.i<=max_i+m.reach_i && q.j>=min_j-m.reach_j && q.j<=max_j+m.reach_j;
    }
    void observe(const std::vector<Cell>& blocks,const std::vector<Cell>& opens) {
        std::map<State,std::set<int>> affected;
        for (int opening=0;opening<2;++opening) for (Cell q:opening ? opens : blocks) {
            if (!relevant(q)) continue;
            for (const auto& group:m.groups) {
                ++stats.notify_probes;
                State u{q.i-group.di,q.j-group.dj,group.theta};
                if (!grid.inside(u.cell())) continue;
                for (int pid:group.ids) cache.erase({u,pid});
                auto arrow=next.find(u);
                if (!opening && arrow!=next.end() && std::binary_search(group.ids.begin(),group.ids.end(),arrow->second.pid)) next.erase(arrow);
                if (opening && h.count(u)) affected[u].insert(group.ids.begin(),group.ids.end());
            }
        }
        using Repair=std::pair<double,State>;
        std::priority_queue<Repair,std::vector<Repair>,std::greater<Repair>> queue;
        auto lower_h=[&](State u,double v,State to,int pid) {
            auto old=h.find(u); if (old==h.end() || v>=old->second-EPS) return;
            v=std::max(base(u),v); old->second=v; next.erase(u); support[u]={to,pid}; queue.push({v,u});
        };
        for (const auto& [u,ids]:affected) for (int pid:ids) {
            State v=m.head(u,pid); double estimate=m.primitives[pid].cost+lower(v);
            if (estimate<h.at(u)-EPS && valid(u,pid)) lower_h(u,estimate,v,pid);
        }
        while (!queue.empty()) {
            auto [v,u]=queue.top(); queue.pop(); ++stats.heuristic_pops;
            if (v!=lower(u)) continue;
            auto arrow=support.find(u);
            if (arrow!=support.end() && (arrow->second.to==goal || next.count(arrow->second.to))) next[u]=arrow->second;
            for (int pid:m.by_end[u.k]) {
                const auto& p=m.primitives[pid]; State pred{u.i-p.di,u.j-p.dj,p.start};
                auto it=h.find(pred);
                if (it!=h.end() && p.cost+v<it->second-EPS && valid(pred,pid)) lower_h(pred,p.cost+v,u,pid);
            }
        }
    }
    bool goal_condition(State u,StateMap<bool>& memo) const {
        std::vector<State> chain; StateSet seen; bool good=false;
        while (u!=goal && !memo.count(u)) {
            require(seen.insert(u).second,"MPGAA next-pointer cycle"); chain.push_back(u);
            auto arrow=next.find(u);
            if (arrow==next.end() || std::abs(lower(u)-m.primitives[arrow->second.pid].cost-lower(arrow->second.to))>8*EPS) goto finish;
            u=arrow->second.to;
        }
        good=u==goal || memo.at(u);
    finish:
        for (State v:chain) memo[v]=good;
        return good;
    }
    Path solve(State start) {
        Path failed;
        if (!grid.free(start.cell()) || !grid.free(goal.cell())) return failed;
        StateMap<double> best,closed; StateMap<Arrow> parent; StateMap<bool> memo;
        best[start]=0; Open queue; queue.push({lower(start),0,0,start,{},-1}); std::uint64_t seq=0;
        State join; bool found=false;
        while (!queue.empty()) {
            auto item=queue.top(); queue.pop(); State u=item.u;
            if (item.g!=value(best,u)) continue;
            if (goal_condition(u,memo)) { join=u; found=true; break; }
            if (stats.expansions>=limit) { failed.stats.capped=true; return failed; }
            ++stats.expansions; closed[u]=item.g;
            if (!has_box) { min_i=max_i=u.i; min_j=max_j=u.j; has_box=true; }
            else { min_i=std::min(min_i,u.i); max_i=std::max(max_i,u.i); min_j=std::min(min_j,u.j); max_j=std::max(max_j,u.j); }
            for (int pid:m.by_start[u.k]) {
                State v=m.head(u,pid); double ng=item.g+m.primitives[pid].cost;
                if (ng<value(best,v)-EPS && valid(u,pid)) {
                    best[v]=ng; parent[v]={u,pid}; queue.push({ng+lower(v),ng,++seq,v,{},-1});
                }
            }
        }
        if (!found) return failed;
        std::vector<int> ids; State u=join;
        while (u!=start) { auto a=parent.at(u); ids.push_back(a.pid); u=a.to; }
        std::reverse(ids.begin(),ids.end()); u=join;
        while (u!=goal) { auto a=next.at(u); ids.push_back(a.pid); u=a.to; }
        Path result=path_from_ids(m,start,ids);
        for (auto [v,gu]:closed) {
            double old=lower(v); require(result.cost-gu>=old-1e-7,"adaptive heuristic inconsistency");
            h[v]=std::max(old,result.cost-gu);
        }
        for (std::size_t k=0;k<ids.size();++k) next[result.states[k]]={result.states[k+1],ids[k]};
        return result;
    }
public:
    MPGAA(const Model& model,const Grid& g,State t,std::uint64_t cap):m(model),grid(g),goal(t),limit(cap) {}
    void set_limit(std::uint64_t cap) { limit=cap; }
    Path replan(State start,const std::vector<Cell>& blocks={},const std::vector<Cell>& opens={}) override {
        auto [b,o]=net_changes(grid,blocks,opens); stats={}; stats.backend_calls=1;
        for (auto q:b) grid.set(q,true);
        for (auto q:o) grid.set(q,false);
        observe(b,o);
        Path result;
        if (!(has_no_path && start==no_path && o.empty())) result=solve(start);
        has_no_path=!result.success() && !result.stats.capped; no_path=start;
        bool capped=result.stats.capped; result.stats=stats; result.stats.capped=capped;
        return result;
    }
    void audit() {
        require(std::abs(lower(goal))<EPS,"h(goal) is not zero");
        for (auto [u,hu]:h) {
            require(hu>=base(u)-EPS,"heuristic below base");
            for (int pid:m.by_start[u.k]) if (valid(u,pid)) require(hu<=m.primitives[pid].cost+lower(m.head(u,pid))+1e-7,"inconsistent learned heuristic");
        }
    }
};
} // namespace ima
