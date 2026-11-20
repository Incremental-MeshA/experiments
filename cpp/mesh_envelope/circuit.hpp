#pragma once
#include "algorithms.hpp"

namespace ima::mesh_envelope {
// A local min-plus circuit eliminates intermediate mesh states from OPEN.
// Only a changed root minimum can make a primitive-boundary state inconsistent.
class Circuit : public Planner {
    using Key=std::pair<double,double>;
    struct Row {std::vector<double> values;};
    struct Item {Key key;std::uint64_t seq;State u;
        bool operator>(const Item& b) const {return std::tie(key,seq)>std::tie(b.key,b.seq);}};
    const MeshIndex& mesh;const Model& m;Grid grid;State start,last,goal;
    StateMap<Row> rows;StateMap<double> g;StateMap<Key> current;
    std::priority_queue<Item,std::vector<Item>,std::greater<Item>> queue;
    CellMap<std::vector<std::pair<int,int>>> dependencies;
    double km=0;std::uint64_t sequence=0,limit;Stats stats;Work work;
    bool inconsistent(double a,double b) const {return a!=b && !(std::abs(a-b)<=EPS);}
    double rhs(State u) const {
        if(u==goal)return grid.free(u.cell())?0:INF;
        auto it=rows.find(u);return it==rows.end()?INF:it->second.values[0];
    }
    Key key(State u) const {double v=std::min(value(g,u),rhs(u));return {v+distance(start.cell(),u.cell())+km,v};}
    void sync(State u) {
        current.erase(u);if(inconsistent(value(g,u),rhs(u))){auto k=key(u);current[u]=k;queue.push({k,++sequence,u});}
    }
    double evaluate(State u,int node,const Row& row) {
        ++work.circuit_nodes;const auto& n=mesh.forest[u.k][node];++stats.checked_cells;
        if(!grid.free({u.i+n.offset.i,u.j+n.offset.j}))return INF;
        double v=INF;
        for(int pid:n.terminals)v=std::min(v,m.primitives[pid].cost+value(g,m.head(u,pid)));
        for(int child:n.children)v=std::min(v,row.values[child]);
        return v;
    }
    Row& ensure(State u) {
        auto [it,created]=rows.try_emplace(u);
        if(created) {
            ++work.circuit_rows;auto& row=it->second;row.values.assign(mesh.forest[u.k].size(),INF);
            for(int node=int(row.values.size())-1;node>=0;--node)row.values[node]=evaluate(u,node,row);
        }
        return it->second;
    }
    void propagate(State u,int node) {
        auto& row=rows.at(u);
        while(node>=0) {
            double v=evaluate(u,node,row);
            if(v==row.values[node]){++work.circuit_stops;break;}
            row.values[node]=v;node=mesh.forest[u.k][node].parent;
        }
        sync(u);
    }
    void assign(State v,double gv) {
        g[v]=gv;
        for(int pid:m.by_end[v.k]) {
            const auto& p=m.primitives[pid];State u{v.i-p.di,v.j-p.dj,p.start};
            if(!grid.inside(u.cell()))continue;
            if(!rows.count(u)) {
                if(!std::isfinite(gv))continue;
                ensure(u);sync(u);
            } else propagate(u,mesh.paths[pid].empty()?0:mesh.paths[pid].back());
        }
        sync(v);
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
            if(!inconsistent(value(g,start),rhs(start)) && item.key.first>boundary+guard)return true;
            if(stats.expansions>=limit)return false;
            queue.pop();current.erase(item.u);auto updated=key(item.u);
            if(item.key<updated){sync(item.u);continue;}
            ++stats.expansions;double gu=value(g,item.u),ru=rhs(item.u);
            if(gu>ru)assign(item.u,ru);else assign(item.u,INF);
        }
        return true;
    }
public:
    Circuit(const MeshIndex& index,const Grid& world,State s,State t,std::uint64_t cap)
        :mesh(index),m(index.model),grid(world),start(s),last(s),goal(t),limit(cap) {
        for(int h=0;h<m.headings;++h)for(std::size_t n=0;n<mesh.forest[h].size();++n)
            dependencies[mesh.forest[h][n].offset].push_back({h,int(n)});
        sync(goal);
    }
    const Work& counters() const {return work;}
    Path replan(State s,const std::vector<Cell>& blocks={},const std::vector<Cell>& opens={}) override {
        stats={};work={};stats.backend_calls=1;auto [b,o]=net_changes(grid,blocks,opens);
        start=s;km+=distance(last.cell(),s.cell());last=s;
        for(Cell q:b)grid.set(q,true);
        for(Cell q:o)grid.set(q,false);
        for(const auto* edits:{&b,&o})for(Cell q:*edits)for(const auto& [off,nodes]:dependencies) {
            Cell origin{q.i-off.i,q.j-off.j};if(!grid.inside(origin))continue;
            for(auto [h,node]:nodes){++stats.notify_probes;State u{origin.i,origin.j,h};if(rows.count(u))propagate(u,node);}
        }
        sync(goal);Path p;
        if(!compute())p.stats.capped=true;
        else if(grid.free(s.cell()) && grid.free(goal.cell()) && std::isfinite(value(g,s))) {
            std::vector<int> ids;State u=s;StateSet seen;
            while(u!=goal) {
                require(seen.insert(u).second,"circuit extraction cycle");double best=INF;int selected=-1;
                for(int pid:m.by_start[u.k]) {
                    double v=m.primitives[pid].cost+value(g,m.head(u,pid));
                    if(v<best-1e-12 && valid_edge(grid,m,u,pid,stats)){best=v;selected=pid;}
                }
                require(selected>=0,"circuit finite label without successor");ids.push_back(selected);u=m.head(u,selected);
            }
            p=path_from_ids(m,s,ids);require(std::abs(p.cost-value(g,s))<1e-6,"circuit label mismatch");
        }
        bool capped=p.stats.capped;p.stats=stats;p.stats.capped=capped;return p;
    }
};
} // namespace ima::mesh_envelope
