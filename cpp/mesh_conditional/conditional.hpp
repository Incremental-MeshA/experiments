#pragma once
#include "../mesh_envelope/factory.hpp"
namespace ima::mesh_conditional {
// Standard optimized D* Lite control: decreases seed c_new+g(v), increases
// back up u only when a removed arc could support rhs(u). No mesh compilation.
class Conditional : public Planner {
    using Key=std::pair<double,double>;
    struct Item {Key key;std::uint64_t seq;State u;
        bool operator>(const Item& b) const {return std::tie(key,seq)>std::tie(b.key,b.seq);}};
    const Model& m;Grid grid;State start,last,goal;std::uint64_t limit,seq=0;double km=0;
    StateMap<double> g,rhs;StateMap<Key> current;
    std::unordered_map<EdgeKey,bool,EdgeHash> valid_cache;
    std::priority_queue<Item,std::vector<Item>,std::greater<Item>> queue;
    Stats stats;
    bool different(double a,double b) const {return a!=b && !(std::abs(a-b)<=EPS);}
    Key key(State u) const {double v=std::min(value(g,u),value(rhs,u));return {v+distance(start.cell(),u.cell())+km,v};}
    void sync(State u) {
        if(!different(value(g,u),value(rhs,u))){current.erase(u);return;}
        auto k=key(u);auto it=current.find(u);if(it!=current.end() && it->second==k)return;
        current[u]=k;queue.push({k,++seq,u});
    }
    bool valid(State u,int pid) {
        EdgeKey edge{u,pid};auto it=valid_cache.find(edge);if(it!=valid_cache.end())return it->second;
        bool result=valid_edge(grid,m,u,pid,stats);valid_cache.emplace(edge,result);return result;
    }
    void backup(State u) {
        if(u==goal){rhs[u]=grid.free(goal.cell())?0:INF;return;}
        double v=INF;
        for(int pid:m.by_start[u.k]) {
            double candidate=m.primitives[pid].cost+value(g,m.head(u,pid));
            if(candidate<v && valid(u,pid))v=candidate;
        }
        rhs[u]=v;
    }
    template<class F> void incoming(State v,F fun) {
        for(int pid:m.by_end[v.k]) {
            const auto& p=m.primitives[pid];State u{v.i-p.di,v.j-p.dj,p.start};
            if(grid.inside(u.cell()) && u!=goal)fun(u,pid,p.cost);
        }
    }
    bool top(Item& item) {
        while(!queue.empty()) {
            item=queue.top();auto it=current.find(item.u);
            if(it!=current.end() && it->second==item.key)return true;
            queue.pop();
        }
        return false;
    }
    bool compute() {
        Item item;
        while(top(item)) {
            double boundary=key(start).first,guard=EPS*(1+std::abs(boundary));
            if(!different(value(g,start),value(rhs,start)) && item.key.first>boundary+guard)return true;
            if(stats.expansions>=limit)return false;
            queue.pop();current.erase(item.u);auto updated=key(item.u);
            if(item.key<updated){sync(item.u);continue;}
            ++stats.expansions;double gu=value(g,item.u),ru=value(rhs,item.u);
            if(gu>ru) {
                g[item.u]=ru;
                incoming(item.u,[&](State u,int pid,double c){
                    double candidate=c+ru;
                    if(candidate<value(rhs,u)-EPS && valid(u,pid)){rhs[u]=candidate;sync(u);}
                });
            } else {
                g[item.u]=INF;backup(item.u);sync(item.u);
                incoming(item.u,[&](State u,int pid,double c){
                    double r=value(rhs,u),old=c+gu;
                    if(std::isfinite(r) && std::abs(r-old)<=8*EPS && valid(u,pid)){backup(u);sync(u);}
                });
            }
        }
        return true;
    }
public:
    Conditional(const Model& model,const Grid& world,State s,State t,std::uint64_t cap)
        :m(model),grid(world),start(s),last(s),goal(t),limit(cap) {backup(goal);sync(goal);}
    Path replan(State s,const std::vector<Cell>& blocks={},const std::vector<Cell>& opens={}) override {
        stats={};stats.backend_calls=1;auto [b,o]=net_changes(grid,blocks,opens);
        start=s;km+=distance(last.cell(),s.cell());last=s;
        StateMap<std::vector<int>> affected;
        for(const auto* edits:{&b,&o})for(Cell q:*edits)for(const auto& group:m.groups) {
            ++stats.notify_probes;State u{q.i-group.di,q.j-group.dj,group.theta};
            if(!grid.inside(u.cell()))continue;
            auto& ids=affected[u];ids.insert(ids.end(),group.ids.begin(),group.ids.end());
        }
        for(Cell q:b)grid.set(q,true);
        for(Cell q:o)grid.set(q,false);
        std::vector<State> order;order.reserve(affected.size());for(const auto& kv:affected)order.push_back(kv.first);std::sort(order.begin(),order.end());
        // Invalidate the whole batch before any backup reads another changed arc.
        for(State u:order) {
            auto& ids=affected.at(u);std::sort(ids.begin(),ids.end());ids.erase(std::unique(ids.begin(),ids.end()),ids.end());
            for(int pid:ids)valid_cache.erase({u,pid});
        }
        for(State u:order) {
            if(u==goal)continue;
            bool needs_backup=false;
            for(int pid:affected.at(u)) {
                double candidate=m.primitives[pid].cost+value(g,m.head(u,pid)),r=value(rhs,u);
                if(candidate<r-EPS) {
                    if(valid(u,pid))rhs[u]=candidate;
                } else if(std::isfinite(r) && std::abs(candidate-r)<=8*EPS && !valid(u,pid))needs_backup=true;
            }
            if(needs_backup)backup(u);
            sync(u);
        }
        backup(goal);sync(goal);Path p;
        if(!compute())p.stats.capped=true;
        else if(grid.free(s.cell()) && grid.free(goal.cell()) && std::isfinite(value(g,s))) {
            State u=s;std::vector<int> ids;StateSet seen;
            while(u!=goal) {
                require(seen.insert(u).second,"conditional D* extraction cycle");double best=INF;int selected=-1;
                for(int pid:m.by_start[u.k]) {
                    double v=m.primitives[pid].cost+value(g,m.head(u,pid));
                    if(v<best-1e-12 && valid(u,pid)){best=v;selected=pid;}
                }
                require(selected>=0,"conditional D* finite label without path");ids.push_back(selected);u=m.head(u,selected);
            }
            p=path_from_ids(m,s,ids);require(std::abs(p.cost-value(g,s))<1e-6,"conditional D* label mismatch");
        }
        bool capped=p.stats.capped;p.stats=stats;p.stats.capped=capped;return p;
    }
};
}
