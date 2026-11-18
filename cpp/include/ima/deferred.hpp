#pragma once
#include "adaptive.hpp"

namespace ima {
inline double octile(Cell d) {
    int a=std::abs(d.i),b=std::abs(d.j);
    return std::max(a,b)+(std::sqrt(2.0)-1)*std::min(a,b);
}
struct Certificate {
    double alpha=0,correction=INF,compile_s=0;
    std::array<std::array<double,8>,8> mu{};
    std::array<std::pair<double,double>,8> directions;
    explicit Certificate(const Model& m) {
        auto clock=Clock::now(); double k=std::sqrt(2.0)-1;
        directions={{{1,k},{k,1},{1,-k},{k,-1},{-1,k},{-k,1},{-1,-k},{-k,-1}}};
        double ratio=INF,max_cost=0; std::size_t max_cells=0;
        for (const auto& p:m.primitives) {
            if (p.di || p.dj) ratio=std::min(ratio,p.cost/octile({p.di,p.dj}));
            max_cost=std::max(max_cost,p.cost); max_cells=std::max(max_cells,p.cells.size());
        }
        require(std::isfinite(ratio),"certificate requires a moving primitive"); alpha=std::nextafter(ratio,0.0);
        std::size_t n=m.configs.size(); std::vector<int> degree(n),order;
        for (const auto& c:m.configs) for (auto e:c.edges) if (e.pid<0) ++degree[e.to];
        for (std::size_t v=0;v<n;++v) if (!degree[v]) order.push_back(int(v));
        for (std::size_t at=0;at<order.size();++at) for (auto e:m.configs[order[at]].edges) if (e.pid<0 && !--degree[e.to]) order.push_back(e.to);
        require(order.size()==n,"primitive mesh must be acyclic");
        std::vector<std::array<double,8>> f(n),b(n);
        for (std::size_t v=0;v<n;++v) { f[v].fill(INF); b[v].fill(INF); }
        for (int root:m.initial) f[root].fill(0);
        auto projection=[&](int a,MeshEdge e) { return alpha*(directions[a].first*e.di+directions[a].second*e.dj); };
        for (int u:order) for (auto e:m.configs[u].edges) if (e.pid<0)
            for (int a=0;a<8;++a) f[e.to][a]=std::min(f[e.to][a],f[u][a]+e.cost-projection(a,e));
        for (auto it=order.rbegin();it!=order.rend();++it) for (auto e:m.configs[*it].edges)
            for (int a=0;a<8;++a) b[*it][a]=std::min(b[*it][a],e.cost-projection(a,e)+(e.pid>=0 ? 0 : b[e.to][a]));
        for (auto& row:mu) row.fill(INF);
        for (std::size_t u=0;u<n;++u) for (int a=0;a<8;++a) for (int z=0;z<8;++z) mu[a][z]=std::min(mu[a][z],f[u][a]+b[u][z]);
        // Terminal witnesses are separate sinks, never roots of the next primitive.
        for (std::size_t u=0;u<n;++u) for (auto e:m.configs[u].edges) if (e.pid>=0)
            for (int a=0;a<8;++a) for (int z=0;z<8;++z) mu[a][z]=std::min(mu[a][z],f[u][a]+e.cost-projection(a,e));
        double margin=EPS*(1+max_cost+double(max_cells));
        for (auto& row:mu) for (auto& x:row) { x-=margin; correction=std::min(correction,x); }
        compile_s=seconds(clock);
    }
    double distance(Cell a,Cell b) const { return alpha*octile({a.i-b.i,a.j-b.j}); }
    double bound(Cell s,Cell t,Cell q,bool full=false) const {
        if (!full) return distance(s,q)+distance(q,t)+correction;
        double lower=-INF;
        for (int a=0;a<8;++a) for (int b=0;b<8;++b) {
            auto [ai,aj]=directions[a]; auto [bi,bj]=directions[b];
            lower=std::max(lower,alpha*(ai*(q.i-s.i)+aj*(q.j-s.j)+bi*(t.i-q.i)+bj*(t.j-q.j))+mu[a][b]);
        }
        return lower;
    }
};

class Suffix {
    const Model& m;
    StateMap<std::size_t> index;
    CellMap<std::size_t> last;
    CellSet blocked;
    std::priority_queue<std::pair<std::size_t,Cell>> bad;
public:
    Path path;
    std::vector<double> remaining;
    explicit Suffix(const Model& model):m(model) {}
    void install(const Path& p) {
        path=p; index.clear(); last.clear(); blocked.clear(); bad={};
        for (std::size_t k=0;k<p.states.size();++k) index[p.states[k]]=k;
        remaining.assign(p.ids.size()+1,0);
        for (std::size_t k=p.ids.size();k>0;--k) remaining[k-1]=remaining[k]+m.primitives[p.ids[k-1]].cost;
        for (std::size_t k=0;k<p.ids.size();++k) for (auto d:m.primitives[p.ids[k]].cells) last[{p.states[k].i+d.i,p.states[k].j+d.j}]=k;
    }
    void update(const std::vector<Cell>& blocks,const std::vector<Cell>& opens) {
        for (auto q:blocks) { auto it=last.find(q); if (it!=last.end() && blocked.insert(q).second) bad.push({it->second,q}); }
        for (auto q:opens) blocked.erase(q);
        if (bad.size()>2*blocked.size()+64) { bad={}; for (auto q:blocked) bad.push({last.at(q),q}); }
    }
    bool position(State s,std::size_t& at) {
        auto it=index.find(s); if (it==index.end()) return false;
        while (!bad.empty() && !blocked.count(bad.top().second)) bad.pop();
        at=it->second; return bad.empty() || bad.top().first<at;
    }
    Path tail(std::size_t at) const {
        Path p; p.cost=remaining.at(at);
        p.ids.assign(path.ids.begin()+std::ptrdiff_t(at),path.ids.end());
        p.states.assign(path.states.begin()+std::ptrdiff_t(at),path.states.end()); return p;
    }
};

class MeshDeferred final : public Planner {
    const Model& m;
    const Certificate& cert;
    Grid actual,working;
    State goal,previous,no_path;
    bool has_previous=false,has_no_path=false;
    MPGAA backend;
    Suffix suffix;
    std::string variant;
    std::uint64_t limit;
    double travel=0;
    CellMap<double> deferred;
    using Waiting=std::pair<double,Cell>;
    std::priority_queue<Waiting,std::vector<Waiting>,std::greater<Waiting>> waiting;
    std::set<Cell> pending_blocks,pending_opens;
    Stats stats;

    double bound(State s,Cell q) const { return cert.bound(s.cell(),goal.cell(),q,variant=="md64"); }
    bool activate(Cell q) {
        if (!deferred.erase(q)) return false;
        working.set(q,false); pending_blocks.erase(q); pending_opens.insert(q); ++stats.activated_cells; return true;
    }
    bool release(State s,double upper) {
        auto before=stats.activated_cells;
        if (variant=="md_scan") {
            std::vector<Cell> cells; for (auto [q,k]:deferred) { (void)k; cells.push_back(q); } std::sort(cells.begin(),cells.end());
            for (auto q:cells) {
                ++stats.refined_cells; double l=bound(s,q);
                if (!std::isfinite(upper) || l<=upper+EPS*(1+std::abs(l)+std::abs(upper))) activate(q);
            }
        } else {
            double threshold=upper+travel;
            while (!waiting.empty()) {
                auto [key,q]=waiting.top(); auto it=deferred.find(q);
                if (it==deferred.end() || it->second!=key) { waiting.pop(); continue; }
                double guard=std::isfinite(upper) ? EPS*(1+std::abs(key)+std::abs(threshold)) : 0;
                if (std::isfinite(upper) && key>threshold+guard) break;
                waiting.pop();
                if (std::isfinite(upper)) {
                    double fresh=bound(s,q)+travel; ++stats.refined_cells; guard=EPS*(1+std::abs(fresh)+std::abs(threshold));
                    if (fresh>threshold+guard) { deferred[q]=fresh; waiting.push({fresh,q}); continue; }
                }
                activate(q);
            }
        }
        return stats.activated_cells>before;
    }
    Path call(State s) {
        backend.set_limit(limit-stats.expansions);
        Path p=backend.replan(s,{pending_blocks.begin(),pending_blocks.end()},{pending_opens.begin(),pending_opens.end()});
        pending_blocks.clear(); pending_opens.clear(); stats.add(p.stats); ++stats.backend_calls; return p;
    }
public:
    MeshDeferred(const Model& model,const Certificate& certificate,const Grid& grid,State t,std::string name,std::uint64_t cap)
        :m(model),cert(certificate),actual(grid),working(grid),goal(t),backend(model,grid,t,cap),suffix(model),variant(std::move(name)),limit(cap) {}
    Path replan(State start,const std::vector<Cell>& blocks={},const std::vector<Cell>& opens={}) override {
        auto [b,o]=net_changes(actual,blocks,opens); stats={};
        if (has_previous && start.cell()!=previous.cell()) { double d=cert.distance(start.cell(),previous.cell()); travel+=d+EPS*(1+d); }
        previous=start; has_previous=true; suffix.update(b,o);
        for (auto q:b) {
            actual.set(q,true); deferred.erase(q); pending_opens.erase(q);
            if (!working.blocked(q)) { working.set(q,true); pending_blocks.insert(q); }
        }
        for (auto q:o) { actual.set(q,false); double k=bound(start,q)+travel; deferred[q]=k; waiting.push({k,q}); }
        if (waiting.size()>2*deferred.size()+64) { waiting={}; for (auto [q,k]:deferred) waiting.push({k,q}); }
        Path result; std::size_t at=0;
        if (has_no_path && start==no_path && o.empty()) stats.certified=true;
        else if (actual.free(start.cell()) && actual.free(goal.cell()) && suffix.position(start,at)) {
            double upper=suffix.remaining[at];
            if (!release(start,upper)) { result=suffix.tail(at); stats.certified=true; }
            else {
                for (std::size_t k=at;k<suffix.path.ids.size();++k) for (auto d:m.primitives[suffix.path.ids[k]].cells) activate({suffix.path.states[k].i+d.i,suffix.path.states[k].j+d.j});
                result=call(start); require(result.stats.capped || result.cost<=upper+1e-6,"working map lost incumbent");
            }
        } else {
            result=call(start);
            if (!result.stats.capped && release(start,result.cost)) {
                double upper=result.cost; result=call(start); require(result.stats.capped || result.cost<=upper+1e-6,"decreases raised cost");
            }
        }
        stats.deferred_cells=deferred.size(); result.stats=stats;
        if (stats.backend_calls) {
            suffix.install(stats.capped ? Path{} : result);
            has_no_path=!result.success() && !stats.capped; no_path=start;
        }
        return result;
    }
    void audit() { backend.audit(); }
};
} // namespace ima
