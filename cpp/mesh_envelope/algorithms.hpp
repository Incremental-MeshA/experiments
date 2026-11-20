#pragma once
#include "../mpgaa_lazy/factory.hpp"

namespace ima::mesh_envelope {
using mpgaa_lazy::MeshIndex;
struct Work : mpgaa_lazy::Work {
    std::uint64_t envelope_hits=0, envelope_builds=0, envelope_added=0, guard_installs=0;
    std::uint64_t guard_events=0, frontier_tests=0, endpoint_tests=0, envelope_goal=0;
    std::uint64_t circuit_nodes=0, circuit_stops=0, circuit_rows=0;
    void add(const Work& b) {
        mpgaa_lazy::Work::add(b);
        envelope_hits+=b.envelope_hits;envelope_builds+=b.envelope_builds;envelope_added+=b.envelope_added;
        guard_installs+=b.guard_installs;guard_events+=b.guard_events;frontier_tests+=b.frontier_tests;
        endpoint_tests+=b.endpoint_tests;envelope_goal+=b.envelope_goal;
        circuit_nodes+=b.circuit_nodes;circuit_stops+=b.circuit_stops;circuit_rows+=b.circuit_rows;
    }
};

// Closed supersets certify non-reachability. Deletions need no repair;
// insertions extend only the outgoing frontier. Positive answers are always
// produced by an exact weighted search, never by the reachability flood.
class Envelope : public Planner {
    const MeshIndex& mesh;const Model& m;Grid grid;State goal;
    std::string mode;std::uint64_t limit;Suffix suffix;
    std::vector<std::uint64_t> region;
    std::vector<State> members,pending;
    CellMap<std::vector<EdgeKey>> watchers;
    std::unordered_set<EdgeKey,EdgeHash> guards;
    bool active=false,reached=false;
    Stats stats;Work work;
    std::size_t bit(State u) const {return (std::size_t(u.i)*grid.width+u.j)*m.headings+u.k;}
    bool inside(State u) const {return grid.inside(u.cell()) && u.k>=0 && u.k<m.headings;}
    bool contains(State u) const {if(!inside(u))return false;auto b=bit(u);return (region[b/64]>>(b%64))&1;}
    void mark(State u,bool enqueue) {
        if(contains(u))return;
        auto b=bit(u);region[b/64]|=std::uint64_t(1)<<(b%64);members.push_back(u);++work.envelope_added;
        if(enqueue)pending.push_back(u);
        if(u==goal){reached=true;++work.envelope_goal;}
    }
    void clear() {
        active=false;reached=false;members.clear();pending.clear();watchers.clear();guards.clear();
        std::fill(region.begin(),region.end(),0);
    }
    bool candidate(State u,int pid) const {
        State v=m.head(u,pid);return inside(v) && !contains(v) && grid.free(v.cell());
    }
    bool wanted(State u,int node) {
        ++work.frontier_tests;
        for(int pid:mesh.forest[u.k][node].members)if(candidate(u,pid))return true;
        return false;
    }
    void watch(State u,int node,Cell q) {
        if(!grid.inside(q))return; // Outside the finite grid can never open.
        if(guards.insert({u,node}).second){watchers[q].push_back({u,node});++work.guard_installs;}
    }
    void visit(State u,int node) {
        if(reached || !wanted(u,node))return;
        const auto& n=mesh.forest[u.k][node];++stats.checked_cells;++work.mesh_nodes;
        Cell q{u.i+n.offset.i,u.j+n.offset.j};
        if(!grid.free(q)){watch(u,node,q);return;}
        for(int pid:n.terminals)if(candidate(u,pid))mark(m.head(u,pid),true);
        for(int c:n.children)visit(u,c);
    }
    void arc(State u,int pid) {
        if(reached || !candidate(u,pid))return;
        ++work.frontier_tests;
        for(std::size_t j=1;j<m.primitives[pid].cells.size();++j) {
            auto off=m.primitives[pid].cells[j];Cell q{u.i+off.i,u.j+off.j};++stats.checked_cells;
            if(!grid.free(q)){watch(u,pid,q);return;}
        }
        mark(m.head(u,pid),true);
    }
    bool lattice() const {return mode=="lattice_envelope";}
    void expand(State u) {
        if(lattice()){for(int pid:m.by_start[u.k])arc(u,pid);}
        else for(int n:mesh.forest[u.k][0].children)visit(u,n);
    }
    void drain() {
        for(std::size_t at=0;at<pending.size() && !reached;++at)expand(pending[at]);
        pending.clear();
    }
    void reopen_guard(EdgeKey ref) {
        if(lattice()){arc(ref.u,ref.pid);return;}
        if(!wanted(ref.u,ref.pid))return;
        // A newly inserted obstacle may precede the old witness. Check the
        // complete prefix before extending the conservative closed envelope.
        std::vector<int> prefix;
        for(int n=mesh.forest[ref.u.k][ref.pid].parent;n>0;n=mesh.forest[ref.u.k][n].parent)prefix.push_back(n);
        for(auto it=prefix.rbegin();it!=prefix.rend();++it) {
            auto off=mesh.forest[ref.u.k][*it].offset;Cell q{ref.u.i+off.i,ref.u.j+off.j};++stats.checked_cells;
            if(!grid.free(q)){watch(ref.u,*it,q);return;}
        }
        visit(ref.u,ref.pid);
    }
    void repair(const std::vector<Cell>& opens) {
        for(Cell q:opens) {
            auto found=watchers.find(q);if(found==watchers.end())continue;
            auto refs=std::move(found->second);watchers.erase(found);
            for(auto ref:refs)if(guards.erase(ref)){++work.guard_events;reopen_guard(ref);}
        }
        // Arcs ending in blocked cells have an implicit endpoint witness,
        // avoiding one explicit watcher per incoming primitive and origin.
        for(Cell q:opens)for(int heading=0;heading<m.headings;++heading) {
            State v{q.i,q.j,heading};if(contains(v))continue;
            for(int pid:m.by_end[heading]) {
                const auto& p=m.primitives[pid];State u{q.i-p.di,q.j-p.dj,p.start};++work.endpoint_tests;
                if(!contains(u))continue;
                if(lattice())arc(u,pid);
                else {
                    bool free=true;
                    for(int node:mesh.paths[pid]) {
                        auto off=mesh.forest[u.k][node].offset;Cell c{u.i+off.i,u.j+off.j};++stats.checked_cells;
                        if(!grid.free(c)){watch(u,node,c);free=false;break;}
                    }
                    if(free)mark(v,true);
                }
            }
        }
        drain();if(reached)clear();
    }
    Path cold(State s,std::vector<State>& exhausted) {
        Path result;if(!grid.free(s.cell()) || !grid.free(goal.cell()))return result;
        ++stats.backend_calls;Open open;StateMap<double> best;StateMap<Arrow> parent;StateSet closed;
        std::uint64_t seq=0;best[s]=0;open.push({distance(s.cell(),goal.cell()),0,seq,s,{},-1});
        auto relax=[&](State u,int pid,double gu) {
            State v=m.head(u,pid);double d=gu+m.primitives[pid].cost;
            if(closed.count(v) || d>=value(best,v)-EPS)return;
            best[v]=d;parent[v]={u,pid};open.push({d+distance(v.cell(),goal.cell()),d,++seq,v,u,pid});
        };
        while(!open.empty()) {
            auto item=open.top();open.pop();State u=item.u;
            if(closed.count(u) || item.g>value(best,u)+EPS)continue;
            if(u==goal) {
                std::vector<int> ids;for(State v=u;v!=s;v=parent.at(v).to)ids.push_back(parent.at(v).pid);
                std::reverse(ids.begin(),ids.end());return path_from_ids(m,s,ids);
            }
            if(stats.expansions>=limit){result.stats.capped=true;return result;}
            closed.insert(u);++stats.expansions;
            auto dfs=[&](auto&& self,int node)->void {
                const auto& n=mesh.forest[u.k][node];++stats.checked_cells;++work.mesh_nodes;
                if(!grid.free({u.i+n.offset.i,u.j+n.offset.j}))return;
                for(int pid:n.terminals)relax(u,pid,item.g);
                for(int child:n.children)self(self,child);
            };
            for(int child:mesh.forest[u.k][0].children)dfs(dfs,child);
        }
        exhausted.assign(closed.begin(),closed.end());std::sort(exhausted.begin(),exhausted.end());return result;
    }
public:
    Envelope(const MeshIndex& index,const Grid& g,State t,std::string name,std::uint64_t cap)
        :mesh(index),m(index.model),grid(g),goal(t),mode(std::move(name)),limit(cap),suffix(m),
         region((std::size_t(g.height)*g.width*m.headings+63)/64,0) {}
    const Work& counters() const {return work;}
    Path replan(State s,const std::vector<Cell>& blocks={},const std::vector<Cell>& opens={}) override {
        stats={};work={};auto [b,o]=net_changes(grid,blocks,opens);suffix.update(b,o);
        if(!o.empty())suffix.install(Path{});
        for(Cell q:b)grid.set(q,true);
        for(Cell q:o)grid.set(q,false);
        if(active) {
            if(mode=="cut_mesh" && !o.empty())clear();else repair(o);
        }
        Path p;
        if(!grid.free(s.cell()) || !grid.free(goal.cell())){suffix.install(Path{});p.stats=stats;return p;}
        std::size_t pos=0;
        if((mode=="dual_mesh" || mode=="mesh_reuse") && o.empty() && suffix.position(s,pos)) {
            p=suffix.tail(pos);stats.certified=true;
        } else if(active && contains(s) && !contains(goal)) {
            stats.certified=true;++work.envelope_hits;
        } else {
            clear();std::vector<State> exhausted;p=cold(s,exhausted);
            if(!p.stats.capped && !p.success() && !exhausted.empty() && mode!="mesh_cold" && mode!="mesh_reuse") {
                active=true;++work.envelope_builds;
                for(State u:exhausted)mark(u,false);
                for(State u:exhausted)expand(u);
                drain();require(!reached,"exhausted search had an outgoing path to goal");
            }
            suffix.install(p.stats.capped?Path{}:p);
        }
        bool capped=p.stats.capped;p.stats=stats;p.stats.capped=capped;return p;
    }
    void audit() const {
        if(!active)return;
        require(!contains(goal),"goal in negative certificate");Stats dummy;
        for(State u:members)for(int pid:m.by_start[u.k])if(valid_edge(grid,m,u,pid,dummy))
            require(contains(m.head(u,pid)),"negative envelope is not closed");
    }
};
} // namespace ima::mesh_envelope
