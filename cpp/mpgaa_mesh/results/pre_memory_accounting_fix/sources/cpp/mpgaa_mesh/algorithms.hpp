#pragma once
#include "ima/deferred.hpp"

namespace ima::mpgaa_mesh {

enum class Mode { Boundary, Selective, Delta, Policy };

struct Work {
    std::uint64_t mesh_nodes=0, bound_evals=0, pruned_branches=0, pruned_primitives=0;
    std::uint64_t watch_hits=0, validity_flips=0, witness_stops=0;
    std::uint64_t policy_probes=0, policy_hits=0, alternate_uses=0;
    void add(const Work& b) {
        mesh_nodes+=b.mesh_nodes;bound_evals+=b.bound_evals;pruned_branches+=b.pruned_branches;
        pruned_primitives+=b.pruned_primitives;watch_hits+=b.watch_hits;
        validity_flips+=b.validity_flips;witness_stops+=b.witness_stops;
        policy_probes+=b.policy_probes;policy_hits+=b.policy_hits;alternate_uses+=b.alternate_uses;
    }
};

// A prefix forest over the ORIGINAL ordered collision-cell traces. Nodes are
// local to a heading. No geometric resampling or primitive-cost change occurs.
struct MeshIndex {
    struct Node {
        Cell offset;int parent=-1,depth=0;
        std::vector<int> children,terminals,members;
    };
    const Model& model;
    std::vector<std::vector<Node>> forest;
    std::vector<std::vector<int>> paths;
    std::vector<int> slot;
    double compile_s=0;
    explicit MeshIndex(const Model& m):model(m),forest(m.headings),paths(m.primitives.size()),slot(m.primitives.size()) {
        auto clock=Clock::now();
        for(int heading=0;heading<m.headings;++heading) {
            auto& tree=forest[heading];tree.push_back({{},-1,0,{},{},{}});
            for(std::size_t k=0;k<m.by_start[heading].size();++k) {
                int pid=m.by_start[heading][k];slot[pid]=int(k);const auto& p=m.primitives[pid];
                int at=0;tree[at].members.push_back(pid);
                for(std::size_t j=1;j<p.cells.size();++j) {
                    int to=-1;
                    for(int child:tree[at].children)if(tree[child].offset==p.cells[j]){to=child;break;}
                    if(to<0) {
                        to=int(tree.size());int depth=tree[at].depth+1;
                        tree.push_back({p.cells[j],at,depth,{},{},{}});tree[at].children.push_back(to);
                    }
                    at=to;tree[at].members.push_back(pid);paths[pid].push_back(at);
                }
                tree[at].terminals.push_back(pid);
            }
        }
        compile_s=seconds(clock);
    }
    std::size_t nodes() const {std::size_t result=0;for(const auto& t:forest)result+=t.size();return result;}
};

// Shared directed MPGAA* logic; interventions are collision evaluation,
// branch bounds, event delivery, and the continuation graph respectively.
class MeshMPGAA : public Planner {
    struct Mask {
        std::vector<std::int8_t> flags; // -1 unknown; bound-pruned != blocked
        std::vector<std::uint8_t> active; // Delta: reached nodes, including witnesses
    };
    const Model& m;const MeshIndex& index;Grid grid;State goal;Mode mode;std::uint64_t limit;
    StateMap<double> h;
    StateMap<Arrow> next,support;
    StateMap<std::vector<int>> policy;
    StateMap<Mask> masks;
    using WatchSet=std::unordered_set<EdgeKey,EdgeHash>;
    CellMap<WatchSet> watchers;
    Suffix incumbent_suffix;
    bool has_box=false,has_no_path=false;State no_path;
    int min_i=0,min_j=0,max_i=0,max_j=0;
    Stats stats;Work work;bool enable_bounds=true,learned_bounds=true;

    double base(State u) const {return distance(u.cell(),goal.cell());}
    double lower(State u) const {auto it=h.find(u);return it==h.end()?base(u):it->second;}
    bool tight(State u,int pid) const {
        return std::abs(lower(u)-m.primitives[pid].cost-lower(m.head(u,pid)))<=8*EPS;
    }
    Mask& mask_for(State u) {
        auto [it,inserted]=masks.try_emplace(u);
        if(inserted) {
            it->second.flags.assign(m.by_start[u.k].size(),-1);
            if(mode==Mode::Delta)it->second.active.assign(index.forest[u.k].size(),0);
        }
        return it->second;
    }
    void subtree_flags(State u,Mask& mask,int node,std::int8_t value) {
        for(int pid:index.forest[u.k][node].members)mask.flags[index.slot[pid]]=value;
    }
    void evaluate(State u,Mask& mask,int node) {
        const auto& n=index.forest[u.k][node];++work.mesh_nodes;++stats.checked_cells;
        Cell q{u.i+n.offset.i,u.j+n.offset.j};
        if(mode==Mode::Delta && grid.inside(q)) {
            mask.active[node]=1;watchers[q].insert({u,node});
        }
        if(!grid.free(q)) {subtree_flags(u,mask,node,0);++work.witness_stops;return;}
        for(int pid:n.terminals)mask.flags[index.slot[pid]]=1;
        for(int child:n.children)evaluate(u,mask,child);
    }
    void evaluate_all(State u,Mask& mask) {
        for(int child:index.forest[u.k][0].children)evaluate(u,mask,child);
    }
    bool valid(State u,int pid) {
        auto& mask=mask_for(u);
        if(mask.flags[index.slot[pid]]<0)evaluate_all(u,mask);
        return mask.flags[index.slot[pid]]>0;
    }
    void remove_subtree(State u,Mask& mask,int node) {
        // Watch only reached nodes: descendants of an obstacle are deliberately
        // unregistered until that obstacle opens.
        if(!mask.active[node])return;
        const auto& n=index.forest[u.k][node];Cell q{u.i+n.offset.i,u.j+n.offset.j};
        auto it=watchers.find(q);
        if(it!=watchers.end()) {it->second.erase({u,node});if(it->second.empty())watchers.erase(it);}
        mask.active[node]=0;
        for(int child:n.children)remove_subtree(u,mask,child);
    }
    using Affected=std::map<State,std::set<int>>;
    Affected delta_events(const std::vector<Cell>& blocks,const std::vector<Cell>& opens) {
        std::map<State,std::set<int>> touched;
        for(const auto* edits:{&blocks,&opens})for(Cell q:*edits) {
            auto it=watchers.find(q);if(it==watchers.end())continue;
            for(const auto& ref:it->second){touched[ref.u].insert(ref.pid);++work.watch_hits;++stats.notify_probes;}
        }
        Affected affected;
        for(const auto& [u,nodes]:touched) {
            auto& mask=masks.at(u);auto old=mask.flags;
            // A changed ancestor subsumes its changed descendants in this batch.
            for(int node:nodes) {
                bool covered=false;
                for(int at=index.forest[u.k][node].parent;at>0;at=index.forest[u.k][at].parent)
                    if(nodes.count(at)){covered=true;break;}
                if(covered)continue;
                remove_subtree(u,mask,node);evaluate(u,mask,node);
            }
            for(int pid:m.by_start[u.k]) {
                int slot=index.slot[pid];if(old[slot]==mask.flags[slot])continue;
                ++work.validity_flips;
                if(mask.flags[slot]==0) {
                    auto it=next.find(u);if(it!=next.end() && it->second.pid==pid)next.erase(it);
                } else if(h.count(u))affected[u].insert(pid);
            }
        }
        return affected;
    }
    bool relevant(Cell q) const {
        return has_box && q.i>=min_i-m.reach_i && q.i<=max_i+m.reach_i && q.j>=min_j-m.reach_j && q.j<=max_j+m.reach_j;
    }
    Affected grouped_events(const std::vector<Cell>& blocks,const std::vector<Cell>& opens) {
        Affected affected;
        for(int opening=0;opening<2;++opening)for(Cell q:opening?opens:blocks) {
            if(!relevant(q))continue;
            for(const auto& group:m.groups) {
                ++stats.notify_probes;State u{q.i-group.di,q.j-group.dj,group.theta};
                if(!grid.inside(u.cell()))continue;
                masks.erase(u);
                auto arrow=next.find(u);
                if(!opening && arrow!=next.end() && std::binary_search(group.ids.begin(),group.ids.end(),arrow->second.pid))next.erase(arrow);
                if(opening && h.count(u))affected[u].insert(group.ids.begin(),group.ids.end());
            }
        }
        return affected;
    }
    void observe(const std::vector<Cell>& blocks,const std::vector<Cell>& opens) {
        auto affected=mode==Mode::Delta?delta_events(blocks,opens):grouped_events(blocks,opens);
        using Repair=std::pair<double,State>;
        std::priority_queue<Repair,std::vector<Repair>,std::greater<Repair>> queue;
        auto lower_h=[&](State u,double v,State to,int pid) {
            auto old=h.find(u);if(old==h.end() || v>=old->second-EPS)return;
            v=std::max(base(u),v);old->second=v;next.erase(u);support[u]={to,pid};queue.push({v,u});
        };
        for(const auto& [u,ids]:affected)for(int pid:ids) {
            State v=m.head(u,pid);double estimate=m.primitives[pid].cost+lower(v);
            if(estimate<h.at(u)-EPS && valid(u,pid))lower_h(u,estimate,v,pid);
        }
        while(!queue.empty()) {
            auto [v,u]=queue.top();queue.pop();++stats.heuristic_pops;if(v!=lower(u))continue;
            auto arrow=support.find(u);
            if(arrow!=support.end() && (arrow->second.to==goal || next.count(arrow->second.to)))next[u]=arrow->second;
            for(int pid:m.by_end[u.k]) {
                const auto& p=m.primitives[pid];State pred{u.i-p.di,u.j-p.dj,p.start};auto it=h.find(pred);
                if(it!=h.end() && p.cost+v<it->second-EPS && valid(pred,pid))lower_h(pred,p.cost+v,u,pid);
            }
        }
    }
    bool single_goal_condition(State u,StateMap<bool>& memo) const {
        std::vector<State> chain;StateSet seen;bool good=false;
        while(u!=goal && !memo.count(u)) {
            require(seen.insert(u).second,"mesh MPGAA next cycle");chain.push_back(u);
            auto arrow=next.find(u);if(arrow==next.end() || !tight(u,arrow->second.pid))goto finish;
            u=arrow->second.to;
        }
        good=u==goal || memo.at(u);
    finish:
        for(State v:chain)memo[v]=good;
        return good;
    }
    std::vector<int> alternatives(State u) const {
        std::vector<int> result;auto arrow=next.find(u);if(arrow!=next.end())result.push_back(arrow->second.pid);
        auto it=policy.find(u);if(it!=policy.end())for(int pid:it->second)
            if(arrow==next.end() || arrow->second.pid!=pid)result.push_back(pid);
        return result;
    }
    bool policy_goal_condition(State root,StateMap<bool>& memo) {
        if(root==goal)return true;
        if(memo.count(root))return memo.at(root);
        struct Frame {State u;std::vector<int> ids;std::size_t at=0;};
        std::vector<Frame> stack={{root,alternatives(root),0}};StateSet active;active.insert(root);
        while(!stack.empty()) {
            auto& frame=stack.back();State u=frame.u;
            if(frame.at==frame.ids.size()) {memo[u]=false;active.erase(u);stack.pop_back();continue;}
            int pid=frame.ids[frame.at];State v=m.head(u,pid);++work.policy_probes;
            if(!tight(u,pid) || !valid(u,pid) || active.count(v)){++frame.at;continue;}
            if(v==goal || (memo.count(v) && memo.at(v))) {
                auto old=next.find(u);if(old==next.end() || old->second.pid!=pid)++work.alternate_uses;
                next[u]={v,pid};memo[u]=true;active.erase(u);stack.pop_back();continue;
            }
            if(memo.count(v)){++frame.at;continue;}
            active.insert(v);stack.push_back({v,alternatives(v),0});
        }
        bool found=memo.at(root);if(found)++work.policy_hits;return found;
    }
    bool goal_condition(State u,StateMap<bool>& memo) {
        return mode==Mode::Policy?policy_goal_condition(u,memo):single_goal_condition(u,memo);
    }
    Path joined(State start,State join,const StateMap<Arrow>& parent) const {
        std::vector<int> ids;State u=join;
        for(std::size_t steps=0;u!=start;++steps) {
            require(steps<=parent.size(),"mesh MPGAA parent cycle");auto a=parent.at(u);ids.push_back(a.pid);u=a.to;
        }
        std::reverse(ids.begin(),ids.end());u=join;
        for(std::size_t steps=0;u!=goal;++steps) {
            require(steps<=next.size(),"mesh MPGAA suffix cycle");auto a=next.at(u);ids.push_back(a.pid);u=a.to;
        }
        return path_from_ids(m,start,ids);
    }
    void selective_visit(State u,Mask& mask,int node,double gu,double upper,std::vector<std::uint8_t>& eligible) {
        const auto& n=index.forest[u.k][node];
        if(enable_bounds && std::isfinite(upper)) {
            double bound=INF;
            for(int pid:n.members){++work.bound_evals;State v=m.head(u,pid);bound=std::min(bound,m.primitives[pid].cost+(learned_bounds?lower(v):base(v)));}
            if(gu+bound>=upper+8*EPS) {
                ++work.pruned_branches;work.pruned_primitives+=n.members.size();return;
            }
        }
        // Cached collision results can coexist with unvisited (pruned) branches.
        bool known=true;for(int pid:n.members)if(mask.flags[index.slot[pid]]<0){known=false;break;}
        if(known) {
            for(int pid:n.members)if(mask.flags[index.slot[pid]]>0)eligible[index.slot[pid]]=1;
            return;
        }
        ++work.mesh_nodes;++stats.checked_cells;
        if(!grid.free({u.i+n.offset.i,u.j+n.offset.j})){subtree_flags(u,mask,node,0);++work.witness_stops;return;}
        for(int pid:n.terminals){mask.flags[index.slot[pid]]=1;eligible[index.slot[pid]]=1;}
        for(int child:n.children)selective_visit(u,mask,child,gu,upper,eligible);
    }
    void learn(const Path& path,const StateMap<double>& closed) {
        for(auto [u,gu]:closed) {
            double old=lower(u);require(path.cost-gu>=old-1e-7,"mesh adaptive heuristic inconsistency");
            h[u]=std::max(old,path.cost-gu);
        }
        for(std::size_t k=0;k<path.ids.size();++k)next[path.states[k]]={path.states[k+1],path.ids[k]};
        if(mode==Mode::Policy) {
            StateSet touched;for(auto [u,gu]:closed){(void)gu;touched.insert(u);}
            for(State u:path.states)if(u!=goal)touched.insert(u);
            for(State u:touched) {
                auto& ids=policy[u];ids.clear();
                for(int pid:m.by_start[u.k])if(tight(u,pid) && valid(u,pid))ids.push_back(pid);
            }
        }
        if(mode==Mode::Selective)incumbent_suffix.install(path);
    }
    Path solve(State start) {
        Path failed;if(!grid.free(start.cell()) || !grid.free(goal.cell()))return failed;
        StateMap<double> best,closed;StateMap<Arrow> parent;StateMap<bool> memo;
        best[start]=0;Open queue;queue.push({lower(start),0,0,start,{},-1});std::uint64_t seq=0;
        Path incumbent;
        if(mode==Mode::Selective) {
            std::size_t at=0;if(incumbent_suffix.position(start,at))incumbent=incumbent_suffix.tail(at);
        }
        Path result;
        while(!queue.empty()) {
            auto item=queue.top();queue.pop();State u=item.u;if(item.g!=value(best,u))continue;
            if(incumbent.success() && item.f>=incumbent.cost+8*EPS){result=std::move(incumbent);break;}
            if(goal_condition(u,memo)){result=joined(start,u,parent);break;}
            if(stats.expansions>=limit){failed.stats.capped=true;return failed;}
            ++stats.expansions;closed[u]=item.g;
            if(!has_box){min_i=max_i=u.i;min_j=max_j=u.j;has_box=true;}
            else{min_i=std::min(min_i,u.i);max_i=std::max(max_i,u.i);min_j=std::min(min_j,u.j);max_j=std::max(max_j,u.j);}
            std::vector<std::uint8_t> eligible;
            if(mode==Mode::Delta) {
                // A learned state needs dependencies for EVERY outgoing arc,
                // including arcs dominated by another search-tree prefix.
                auto& mask=mask_for(u);
                if(std::find(mask.flags.begin(),mask.flags.end(),std::int8_t(-1))!=mask.flags.end())evaluate_all(u,mask);
            }
            if(mode==Mode::Selective) {
                eligible.assign(m.by_start[u.k].size(),0);auto& mask=mask_for(u);
                for(int child:index.forest[u.k][0].children)selective_visit(u,mask,child,item.g,incumbent.cost,eligible);
            }
            for(int pid:m.by_start[u.k]) {
                State v=m.head(u,pid);double ng=item.g+m.primitives[pid].cost;
                if(ng>=value(best,v)-EPS)continue;
                bool ok=mode==Mode::Selective?bool(eligible[index.slot[pid]]):valid(u,pid);
                if(!ok)continue;
                best[v]=ng;parent[v]={u,pid};queue.push({ng+lower(v),ng,++seq,v,{},-1});
                if(mode==Mode::Selective && ng+lower(v)<incumbent.cost-EPS && goal_condition(v,memo))incumbent=joined(start,v,parent);
            }
        }
        if(!result.success() && incumbent.success())result=std::move(incumbent);
        if(!result.success())return failed;
        learn(result,closed);return result;
    }
public:
    MeshMPGAA(const MeshIndex& idx,const Grid& g,State target,Mode variant,std::uint64_t cap,bool bounds=true,bool learned=true)
        :m(idx.model),index(idx),grid(g),goal(target),mode(variant),limit(cap),incumbent_suffix(m),enable_bounds(bounds),learned_bounds(learned) {}
    const Work& counters() const {return work;}
    void set_limit(std::uint64_t cap){limit=cap;}
    Path replan(State start,const std::vector<Cell>& blocks={},const std::vector<Cell>& opens={}) override {
        auto [b,o]=net_changes(grid,blocks,opens);stats={};work={};stats.backend_calls=1;
        if(mode==Mode::Selective)incumbent_suffix.update(b,o);
        for(Cell q:b)grid.set(q,true);
        for(Cell q:o)grid.set(q,false);
        observe(b,o);
        Path result;if(!(has_no_path && start==no_path && o.empty()))result=solve(start);
        has_no_path=!result.success() && !result.stats.capped;no_path=start;
        bool capped=result.stats.capped;result.stats=stats;result.stats.capped=capped;
        if(mode==Mode::Policy && result.success() && !stats.expansions)result.stats.certified=true;
        return result;
    }
    void audit() {
        require(std::abs(lower(goal))<EPS,"mesh h(goal) not zero");
        for(auto [u,hu]:h) {
            require(hu>=base(u)-EPS,"mesh heuristic below base");
            Stats ignored;
            for(int pid:m.by_start[u.k])if(valid_edge(grid,m,u,pid,ignored))
                require(hu<=m.primitives[pid].cost+lower(m.head(u,pid))+1e-7,"inconsistent mesh learned heuristic");
        }
        for(const auto& [u,mask]:masks)for(int pid:m.by_start[u.k]) {
            int flag=mask.flags[index.slot[pid]];if(flag<0)continue;
            bool direct=true;const auto& p=m.primitives[pid];
            for(std::size_t j=1;j<p.cells.size();++j)if(!grid.free({u.i+p.cells[j].i,u.j+p.cells[j].j})){direct=false;break;}
            require(bool(flag)==direct,"stale mesh collision mask");
        }
    }
};

class BoundaryMPGAA final:public MeshMPGAA {
public:BoundaryMPGAA(const MeshIndex& idx,const Grid& g,State t,std::uint64_t cap):MeshMPGAA(idx,g,t,Mode::Boundary,cap){}
};
class SelectiveMPGAA final:public MeshMPGAA {
public:SelectiveMPGAA(const MeshIndex& idx,const Grid& g,State t,std::uint64_t cap):MeshMPGAA(idx,g,t,Mode::Selective,cap){}
};
class DeltaMPGAA final:public MeshMPGAA {
public:DeltaMPGAA(const MeshIndex& idx,const Grid& g,State t,std::uint64_t cap):MeshMPGAA(idx,g,t,Mode::Delta,cap){}
};
class PolicyMPGAA final:public MeshMPGAA {
public:PolicyMPGAA(const MeshIndex& idx,const Grid& g,State t,std::uint64_t cap):MeshMPGAA(idx,g,t,Mode::Policy,cap){}
};
inline Work counters(const Planner& planner) {
    const auto* p=dynamic_cast<const MeshMPGAA*>(&planner);return p?p->counters():Work{};
}
} // namespace ima::mpgaa_mesh
