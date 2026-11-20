#pragma once
#include "../mpgaa_mesh/algorithms.hpp"

namespace ima::mpgaa_lazy {
// All variants search the same directed primitive graph as MPGAA*. Mesh nodes
// share occupancy reads; they never become extra search states.
enum class Mode { Stamp, Batch, Witness };
struct Work:mpgaa_mesh::Work {
    std::uint64_t stamp_writes=0,tile_reads=0,mask_refreshes=0,mask_hits=0;
    std::uint64_t cut_checks=0,cut_reuses=0,cut_primitives=0;
    std::uint64_t edit_batches=0,scan_batches=0,seed_tests=0,arrow_checks=0,cover_tests=0;
    void add(const Work& b) {
        mpgaa_mesh::Work::add(b);
        stamp_writes+=b.stamp_writes;tile_reads+=b.tile_reads;mask_refreshes+=b.mask_refreshes;mask_hits+=b.mask_hits;
        cut_checks+=b.cut_checks;cut_reuses+=b.cut_reuses;cut_primitives+=b.cut_primitives;
        edit_batches+=b.edit_batches;scan_batches+=b.scan_batches;seed_tests+=b.seed_tests;arrow_checks+=b.arrow_checks;
        cover_tests+=b.cover_tests;
    }
};
struct MeshIndex:mpgaa_mesh::MeshIndex {
    // Exact bounding rectangle of the original trace offsets, per heading.
    std::vector<std::array<int,4>> boxes;
    std::vector<std::vector<int>> enter,leave;
    explicit MeshIndex(const Model& m):mpgaa_mesh::MeshIndex(m) {
        auto clock=Clock::now();
        boxes.resize(m.headings);enter.resize(m.headings);leave.resize(m.headings);
        for(int k=0;k<m.headings;++k)for(std::size_t n=1;n<forest[k].size();++n) {
            Cell q=forest[k][n].offset;auto& b=boxes[k];
            b[0]=std::min(b[0],q.i);b[1]=std::max(b[1],q.i);b[2]=std::min(b[2],q.j);b[3]=std::max(b[3],q.j);
        }
        for(int k=0;k<m.headings;++k) {
            enter[k].resize(forest[k].size());leave[k].resize(forest[k].size());int rank=0;
            std::vector<std::pair<int,bool>> stack={{0,false}};
            while(!stack.empty()) {
                auto [node,done]=stack.back();stack.pop_back();
                if(done){leave[k][node]=rank;continue;}
                enter[k][node]=rank++;stack.push_back({node,true});
                const auto& children=forest[k][node].children;
                for(auto it=children.rbegin();it!=children.rend();++it)stack.push_back({*it,false});
            }
        }
        compile_s+=seconds(clock);
    }
};

class LazyMPGAA:public Planner {
    struct Mask {
        std::vector<std::int8_t> flags;
        // Prefix-free blocked witnesses may jointly certify an ancestor branch
        // without revisiting its free prefix.
        std::vector<int> cut;
        std::uint64_t born=0,verified=0;
    };
    const Model& m;const MeshIndex& index;Grid grid;State goal;Mode mode;
    std::uint64_t limit,epoch=1,learned_arcs=0;int tile_side,tile_cols;bool force_scan;
    std::vector<std::uint64_t> stamps;
    StateMap<double> h;StateMap<Arrow> next,support;StateMap<Mask> masks;
    bool has_box=false,has_no_path=false;State no_path;
    int min_i=0,min_j=0,max_i=0,max_j=0;
    Stats stats;Work work;

    static int checked_tile(int side){require(side>0,"invalid tile size");return side;}

    double base(State u) const {return distance(u.cell(),goal.cell());}
    double lower(State u) const {auto it=h.find(u);return it==h.end()?base(u):it->second;}
    bool relevant(Cell q) const {
        return has_box && q.i>=min_i-m.reach_i && q.i<=max_i+m.reach_i && q.j>=min_j-m.reach_j && q.j<=max_j+m.reach_j;
    }
    template<class Read> bool fresh(State u,const Mask& mask,Read read) const {
        const auto& b=index.boxes[u.k];
        int i0=std::max(0,u.i+b[0]),i1=std::min(grid.height-1,u.i+b[1]);
        int j0=std::max(0,u.j+b[2]),j1=std::min(grid.width-1,u.j+b[3]);
        if(i0>i1 || j0>j1)return true;
        for(int i=i0/tile_side;i<=i1/tile_side;++i)for(int j=j0/tile_side;j<=j1/tile_side;++j) {
            read();if(stamps[std::size_t(i)*tile_cols+j]>mask.born)return false;
        }
        return true;
    }
    void flag_subtree(State u,Mask& mask,int node,std::int8_t flag) {
        for(int pid:index.forest[u.k][node].members)mask.flags[index.slot[pid]]=flag;
    }
    void evaluate(State u,Mask& mask,int node,const std::vector<std::uint8_t>& covered) {
        const auto& n=index.forest[u.k][node];
        if(!covered.empty()) {
            bool all=true;
            for(int pid:n.members){++work.cover_tests;if(!covered[index.slot[pid]]){all=false;break;}}
            // A union of surviving blockers can skip a free ancestor prefix.
            // Skipping only the blocker itself would save no occupancy reads.
            if(all) {
                ++work.cut_reuses;work.cut_primitives+=n.members.size();
                flag_subtree(u,mask,node,0);return;
            }
        }
        ++work.mesh_nodes;++stats.checked_cells;
        if(!grid.free({u.i+n.offset.i,u.j+n.offset.j})) {
            flag_subtree(u,mask,node,0);++work.witness_stops;
            if(mode==Mode::Witness)mask.cut.push_back(node);
            return;
        }
        for(int pid:n.terminals)mask.flags[index.slot[pid]]=1;
        for(int child:n.children)evaluate(u,mask,child,covered);
    }
    Mask& current_mask(State u) {
        auto [it,inserted]=masks.try_emplace(u);auto& mask=it->second;
        if(!inserted && (mask.verified==epoch || fresh(u,mask,[&](){++work.tile_reads;}))) {
            mask.verified=epoch;++work.mask_hits;return mask;
        }
        ++work.mask_refreshes;
        std::vector<std::uint8_t> covered;
        if(mode==Mode::Witness) {
            std::size_t kept=0;
            for(int node:mask.cut) {
                ++work.cut_checks;++stats.checked_cells;Cell off=index.forest[u.k][node].offset;
                if(!grid.free({u.i+off.i,u.j+off.j}))mask.cut[kept++]=node;
            }
            mask.cut.resize(kept);
            if(kept) {
                covered.assign(m.by_start[u.k].size(),0);
                for(int node:mask.cut)for(int pid:index.forest[u.k][node].members)covered[index.slot[pid]]=1;
            }
        }
        mask.flags.assign(m.by_start[u.k].size(),-1);
        for(int child:index.forest[u.k][0].children)evaluate(u,mask,child,covered);
        if(mode==Mode::Witness) {
            // New blockers may subsume old witnesses. DFS intervals compact
            // their union without a dense per-state activity tree.
            std::sort(mask.cut.begin(),mask.cut.end(),[&](int a,int b){return index.enter[u.k][a]<index.enter[u.k][b];});
            std::size_t kept=0;int end=-1;
            for(int node:mask.cut)if(index.enter[u.k][node]>=end){mask.cut[kept++]=node;end=index.leave[u.k][node];}
            mask.cut.resize(kept);
        }
        mask.born=mask.verified=epoch;return mask;
    }
    bool valid(State u,int pid) {return current_mask(u).flags[index.slot[pid]]>0;}
    void observe(const std::vector<Cell>& opens) {
        // Blocks cannot invalidate admissibility. Their collision consequences
        // are checked lazily, including every arc of an MPGAA continuation.
        if(opens.empty() || h.empty())return;
        std::vector<Cell> relevant_opens;for(Cell q:opens)if(relevant(q))relevant_opens.push_back(q);
        if(relevant_opens.empty())return;
        bool scan=mode!=Mode::Stamp && (force_scan || double(learned_arcs)<double(relevant_opens.size())*double(m.groups.size()));
        using Repair=std::pair<double,State>;
        std::priority_queue<Repair,std::vector<Repair>,std::greater<Repair>> queue;
        auto lower_h=[&](State u,double v,State to,int pid) {
            auto old=h.find(u);if(old==h.end() || v>=old->second-EPS)return;
            v=std::max(base(u),v);old->second=v;next.erase(u);support[u]={to,pid};queue.push({v,u});
        };
        auto seed=[&](State u,int pid) {
            ++work.seed_tests;State v=m.head(u,pid);double estimate=m.primitives[pid].cost+lower(v);
            if(estimate<h.at(u)-EPS && valid(u,pid))lower_h(u,estimate,v,pid);
        };
        if(scan) {
            ++work.scan_batches;
            // Sorting makes seed order stable and comparable to the edit join.
            std::vector<State> states;states.reserve(h.size());for(const auto& [u,hu]:h){(void)hu;states.push_back(u);}
            std::sort(states.begin(),states.end());
            for(State u:states)for(int pid:m.by_start[u.k]){++stats.notify_probes;seed(u,pid);}
        } else {
            ++work.edit_batches;
            std::map<State,std::set<int>> affected;
            for(Cell q:relevant_opens)for(const auto& group:m.groups) {
                ++stats.notify_probes;State u{q.i-group.di,q.j-group.dj,group.theta};
                if(grid.inside(u.cell()) && h.count(u))affected[u].insert(group.ids.begin(),group.ids.end());
            }
            for(const auto& [u,ids]:affected)for(int pid:ids)seed(u,pid);
        }
        // The complete predecessor propagation is mandatory in either mode.
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
    bool goal_condition(State u,StateMap<bool>& memo) {
        std::vector<State> chain;StateSet seen;bool good=false;
        while(u!=goal && !memo.count(u)) {
            require(seen.insert(u).second,"lazy MPGAA continuation cycle");chain.push_back(u);
            auto arrow=next.find(u);if(arrow==next.end())goto finish;
            if(std::abs(lower(u)-m.primitives[arrow->second.pid].cost-lower(arrow->second.to))>8*EPS)goto finish;
            ++work.arrow_checks;
            if(!valid(u,arrow->second.pid)){next.erase(arrow);goto finish;}
            u=arrow->second.to;
        }
        good=u==goal || memo.at(u);
    finish:
        for(State v:chain)memo[v]=good;
        return good;
    }
    Path solve(State start) {
        Path failed;if(!grid.free(start.cell()) || !grid.free(goal.cell()))return failed;
        StateMap<double> best,closed;StateMap<Arrow> parent;StateMap<bool> memo;
        best[start]=0;Open queue;queue.push({lower(start),0,0,start,{},-1});std::uint64_t seq=0;
        State join;bool found=false;
        while(!queue.empty()) {
            auto item=queue.top();queue.pop();State u=item.u;if(item.g!=value(best,u))continue;
            if(goal_condition(u,memo)){join=u;found=true;break;}
            if(stats.expansions>=limit){failed.stats.capped=true;return failed;}
            ++stats.expansions;closed[u]=item.g;
            if(!has_box){min_i=max_i=u.i;min_j=max_j=u.j;has_box=true;}
            else{min_i=std::min(min_i,u.i);max_i=std::max(max_i,u.i);min_j=std::min(min_j,u.j);max_j=std::max(max_j,u.j);}
            // Refresh only once per expanded state; flags are packed by pid slot.
            auto& mask=current_mask(u);
            for(int pid:m.by_start[u.k]) {
                State v=m.head(u,pid);double ng=item.g+m.primitives[pid].cost;
                if(ng>=value(best,v)-EPS || !mask.flags[index.slot[pid]])continue;
                best[v]=ng;parent[v]={u,pid};queue.push({ng+lower(v),ng,++seq,v,{},-1});
            }
        }
        if(!found)return failed;
        std::vector<int> ids;State u=join;
        for(std::size_t n=0;u!=start;++n){require(n<=parent.size(),"lazy MPGAA parent cycle");auto a=parent.at(u);ids.push_back(a.pid);u=a.to;}
        std::reverse(ids.begin(),ids.end());u=join;
        for(std::size_t n=0;u!=goal;++n){require(n<=next.size(),"lazy MPGAA suffix cycle");auto a=next.at(u);ids.push_back(a.pid);u=a.to;}
        Path result=path_from_ids(m,start,ids);
        for(auto [v,gu]:closed) {
            double old=lower(v);require(result.cost-gu>=old-1e-7,"lazy adaptive heuristic inconsistency");
            if(!h.count(v))learned_arcs+=m.by_start[v.k].size();
            h[v]=std::max(old,result.cost-gu);
        }
        for(std::size_t k=0;k<ids.size();++k)next[result.states[k]]={result.states[k+1],ids[k]};
        return result;
    }
public:
    LazyMPGAA(const MeshIndex& idx,const Grid& g,State t,Mode variant,std::uint64_t cap,int tile=8,bool scan=false)
        :m(idx.model),index(idx),grid(g),goal(t),mode(variant),limit(cap),tile_side(checked_tile(tile)),tile_cols((g.width+tile_side-1)/tile_side),force_scan(scan),
         stamps(std::size_t((g.height+tile_side-1)/tile_side)*tile_cols,0) {}
    const Work& counters() const {return work;}
    void set_limit(std::uint64_t cap){limit=cap;}
    Path replan(State start,const std::vector<Cell>& blocks={},const std::vector<Cell>& opens={}) override {
        auto [b,o]=net_changes(grid,blocks,opens);stats={};work={};stats.backend_calls=1;
        if(!b.empty() || !o.empty()) {
            require(epoch<std::numeric_limits<std::uint64_t>::max(),"map epoch overflow");++epoch;
            for(const auto* edits:{&b,&o})for(Cell q:*edits){stamps[std::size_t(q.i/tile_side)*tile_cols+q.j/tile_side]=epoch;++work.stamp_writes;}
        }
        for(Cell q:b)grid.set(q,true);
        for(Cell q:o)grid.set(q,false);
        observe(o);
        Path result;if(!(has_no_path && start==no_path && o.empty()))result=solve(start);
        has_no_path=!result.success() && !result.stats.capped;no_path=start;
        bool capped=result.stats.capped;result.stats=stats;result.stats.capped=capped;return result;
    }
    // Read-only audit. Stale masks are intentional; only masks certified by
    // their stamps are required to describe the current occupancy snapshot.
    void audit() const {
        require(std::abs(lower(goal))<EPS,"lazy h(goal) not zero");
        for(auto [u,hu]:h) {
            require(hu>=base(u)-EPS,"lazy heuristic below base");Stats ignored;
            for(int pid:m.by_start[u.k])if(valid_edge(grid,m,u,pid,ignored))
                require(hu<=m.primitives[pid].cost+lower(m.head(u,pid))+1e-7,"inconsistent lazy heuristic");
        }
        for(const auto& [u,mask]:masks) {
            if(!fresh(u,mask,[](){}))continue;
            for(int pid:m.by_start[u.k]) {
                Stats ignored;bool direct=valid_edge(grid,m,u,pid,ignored);
                require(bool(mask.flags[index.slot[pid]])==direct,"stale certified mask");
            }
        }
    }
};
} // namespace ima::mpgaa_lazy
