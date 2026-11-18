#pragma once

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <limits>
#include <map>
#include <memory>
#include <queue>
#include <set>
#include <stdexcept>
#include <string>
#include <tuple>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace ima {
constexpr double INF = std::numeric_limits<double>::infinity();
constexpr double EPS = 1e-9;
using Clock = std::chrono::steady_clock;
inline double seconds(Clock::time_point start) {
    return std::chrono::duration<double>(Clock::now() - start).count();
}
inline void require(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}

struct Cell {
    int i = 0, j = 0;
    bool operator==(Cell b) const { return i == b.i && j == b.j; }
    bool operator!=(Cell b) const { return !(*this == b); }
    bool operator<(Cell b) const { return std::tie(i,j) < std::tie(b.i,b.j); }
};
struct State {
    int i = 0, j = 0, k = 0; // k = heading for lattice, configuration for mesh
    Cell cell() const { return {i,j}; }
    bool operator==(State b) const { return i == b.i && j == b.j && k == b.k; }
    bool operator!=(State b) const { return !(*this == b); }
    bool operator<(State b) const { return std::tie(i,j,k) < std::tie(b.i,b.j,b.k); }
};
inline std::uint64_t mix(std::uint64_t x) {
    x += 0x9e3779b97f4a7c15ULL;
    x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
    x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
    return x ^ (x >> 31);
}
struct Hash {
    std::size_t operator()(Cell x) const { return mix(std::uint32_t(x.i)) ^ mix(std::uint64_t(std::uint32_t(x.j)) << 1); }
    std::size_t operator()(State x) const { return (*this)(x.cell()) ^ mix(std::uint64_t(std::uint32_t(x.k)) << 2); }
};
template<class T> using StateMap = std::unordered_map<State,T,Hash>;
using StateSet = std::unordered_set<State,Hash>;
template<class T> using CellMap = std::unordered_map<Cell,T,Hash>;
using CellSet = std::unordered_set<Cell,Hash>;
template<class M, class K> inline double value(const M& m, const K& k) {
    auto it = m.find(k); return it == m.end() ? INF : it->second;
}
inline double distance(Cell a, Cell b) { return std::hypot(double(a.i-b.i),double(a.j-b.j)); }

struct Grid {
    int height = 0, width = 0;
    std::vector<std::uint8_t> cells;
    Grid() = default;
    Grid(int h, int w) : height(h), width(w), cells(std::size_t(h)*w) {}
    bool inside(Cell c) const { return c.i >= 0 && c.j >= 0 && c.i < height && c.j < width; }
    bool free(Cell c) const { return inside(c) && !cells[std::size_t(c.i)*width+c.j]; }
    bool blocked(Cell c) const { require(inside(c),"cell outside grid"); return cells[std::size_t(c.i)*width+c.j] != 0; }
    void set(Cell c, bool occupied) { require(inside(c),"cell outside grid"); cells[std::size_t(c.i)*width+c.j] = occupied; }
};
struct Primitive {
    int start = 0, end = 0, di = 0, dj = 0;
    double cost = 0;
    std::vector<Cell> cells;
};
struct MeshEdge { int di, dj, to; double cost; int pid; };
struct Final { int di, dj, theta; double cost; };
struct Config {
    int theta = -1, signature = 0;
    Cell origin;
    std::vector<MeshEdge> edges;
    std::vector<Final> finals;
};
struct Group { int theta, di, dj; std::vector<int> ids; };
struct Model {
    std::string name;
    int headings = 0, reach_i = 0, reach_j = 0;
    std::vector<Primitive> primitives;
    std::vector<Config> configs;
    std::vector<int> initial;
    std::vector<std::vector<int>> by_start, by_end;
    std::vector<std::vector<MeshEdge>> predecessors;
    std::vector<Group> groups;

    void prepare() {
        require(headings > 0 && initial.size() == std::size_t(headings),"invalid headings");
        by_start.assign(headings,{}); by_end.assign(headings,{});
        std::map<std::tuple<int,int,int>,std::set<int>> grouped;
        for (std::size_t id=0; id<primitives.size(); ++id) {
            const auto& p=primitives[id];
            require(p.start>=0 && p.start<headings && p.end>=0 && p.end<headings,"invalid primitive heading");
            require(std::isfinite(p.cost) && p.cost>0 && p.cost+EPS>=std::hypot(p.di,p.dj),"invalid primitive cost");
            require(p.cells.size()>=2 && p.cells.front()==Cell{0,0} && p.cells.back()==Cell{p.di,p.dj},"invalid primitive coverage");
            by_start[p.start].push_back(int(id)); by_end[p.end].push_back(int(id));
            for (std::size_t k=1;k<p.cells.size();++k) {
                auto d=p.cells[k]; grouped[{p.start,d.i,d.j}].insert(int(id));
                reach_i=std::max(reach_i,std::abs(d.i)); reach_j=std::max(reach_j,std::abs(d.j));
            }
        }
        groups.clear();
        for (const auto& [key,ids]:grouped) {
            auto [theta,i,j]=key; groups.push_back({theta,i,j,{ids.begin(),ids.end()}});
        }
        predecessors.assign(configs.size(),{});
        for (std::size_t u=0;u<configs.size();++u) for (auto e:configs[u].edges) {
            require(e.to>=0 && std::size_t(e.to)<configs.size() && e.cost>=0,"invalid mesh edge");
            require(e.pid>=-1 && e.pid<int(primitives.size()),"invalid completion");
            predecessors[e.to].push_back({e.di,e.dj,int(u),e.cost,e.pid});
        }
        for (int t=0;t<headings;++t) require(initial[t]>=0 && std::size_t(initial[t])<configs.size() && configs[initial[t]].theta==t,"invalid mesh root");
    }
    State head(State s,int pid) const { const auto& p=primitives.at(pid); return {s.i+p.di,s.j+p.dj,p.end}; }
    int between(State u,State v) const {
        for (int pid:by_start.at(u.k)) if (head(u,pid)==v) return pid;
        throw std::runtime_error("unidentified primitive transition");
    }
};

struct Stats {
    std::uint64_t expansions=0, checked_cells=0, notify_probes=0, heuristic_pops=0;
    std::uint64_t activated_cells=0, deferred_cells=0, refined_cells=0;
    int backend_calls=0;
    bool certified=false, capped=false;
    void add(const Stats& b) {
        expansions+=b.expansions; checked_cells+=b.checked_cells;
        notify_probes+=b.notify_probes; heuristic_pops+=b.heuristic_pops;
        capped=capped||b.capped;
    }
};
struct Path {
    double cost=INF;
    std::vector<State> states;
    std::vector<int> ids;
    Stats stats;
    bool success() const { return std::isfinite(cost) && !stats.capped; }
};
inline Path path_from_ids(const Model& m,State start,const std::vector<int>& ids) {
    Path p; p.cost=0; p.ids=ids; p.states.push_back(start);
    long double total=0;
    for (int id:ids) { total+=m.primitives.at(id).cost; start=m.head(start,id); p.states.push_back(start); }
    p.cost=double(total); return p;
}
inline void validate_path(const Grid& g,const Model& m,State s,State t,const Path& p) {
    if (!p.success()) { require(p.ids.empty() && p.states.empty(),"failed answer has a path"); return; }
    require(g.free(s.cell()) && g.free(t.cell()),"blocked path endpoint");
    require(p.states.size()==p.ids.size()+1 && p.states.front()==s,"invalid path state count");
    long double total=0;
    for (std::size_t k=0;k<p.ids.size();++k) {
        const auto& prim=m.primitives.at(p.ids[k]); require(prim.start==s.k,"invalid heading");
        for (auto d:prim.cells) require(g.free({s.i+d.i,s.j+d.j}),"path intersects obstacle");
        total+=prim.cost; s=m.head(s,p.ids[k]); require(p.states[k+1]==s,"path state mismatch");
    }
    require(s==t && std::abs(double(total)-p.cost)<1e-6,"path cost/goal mismatch");
}
inline std::pair<std::vector<Cell>,std::vector<Cell>> net_changes(const Grid& g,const std::vector<Cell>& blocks,const std::vector<Cell>& opens) {
    std::set<Cell> b(blocks.begin(),blocks.end()),o(opens.begin(),opens.end());
    for (auto q:b) { require(g.inside(q),"block outside grid"); require(!o.count(q),"contradictory changes"); }
    for (auto q:o) require(g.inside(q),"opening outside grid");
    std::vector<Cell> bb,oo;
    for (auto q:b) if (!g.blocked(q)) bb.push_back(q);
    for (auto q:o) if (g.blocked(q)) oo.push_back(q);
    return {bb,oo};
}
struct EdgeKey { State u; int pid; bool operator==(const EdgeKey& b) const { return u==b.u && pid==b.pid; } };
struct EdgeHash { std::size_t operator()(const EdgeKey& e) const { return Hash{}(e.u)^mix(e.pid+0x10000ULL); } };
using EdgeCache=std::unordered_map<EdgeKey,bool,EdgeHash>;
inline bool valid_edge(const Grid& g,const Model& m,State u,int pid,Stats& stats) {
    const auto& p=m.primitives[pid];
    for (std::size_t k=1;k<p.cells.size();++k) { ++stats.checked_cells; auto d=p.cells[k]; if (!g.free({u.i+d.i,u.j+d.j})) return false; }
    return true;
}
struct OpenItem {
    double f,g; std::uint64_t seq; State u,prev; int pid=-1;
    bool operator>(const OpenItem& b) const { return std::tuple(f,-g,seq)>std::tuple(b.f,-b.g,b.seq); }
};
using Open=std::priority_queue<OpenItem,std::vector<OpenItem>,std::greater<OpenItem>>;
struct Arrow { State to; int pid; };
class Planner {
public:
    virtual ~Planner()=default;
    virtual Path replan(State start,const std::vector<Cell>& blocks={},const std::vector<Cell>& opens={})=0;
};
struct Query { State start,goal; std::vector<Cell> blocks,opens; double expected=INF; std::string category,event; };
struct Episode { std::string id,cohort; int map=0; std::vector<Query> queries; };
struct Suite { Model model; std::vector<Grid> maps; std::vector<std::string> map_names; std::vector<Episode> episodes; };
inline Suite read_suite(const std::string& filename) {
    std::ifstream in(filename); require(bool(in),"cannot open input: "+filename);
    std::string tag; int version=0; in>>tag>>version; require(tag=="IMA_CPP" && version==1,"unsupported input format");
    Suite s; auto& m=s.model; int np=0,nc=0;
    in>>std::quoted(m.name)>>m.headings>>np>>nc;
    require(np>0 && np<100000 && nc>0 && nc<100000 && m.headings>0 && m.headings<10000,"invalid model dimensions");
    m.initial.resize(m.headings); for (auto& x:m.initial) in>>x;
    for (int id=0;id<np;++id) {
        Primitive p; int count=0; in>>p.start>>p.end>>p.di>>p.dj>>p.cost>>count; require(count>=2 && count<100000,"invalid coverage length");
        p.cells.resize(count); for (auto& d:p.cells) in>>d.i>>d.j; m.primitives.push_back(std::move(p));
    }
    for (int id=0;id<nc;++id) {
        Config c; int ne=0,nf=0; in>>c.theta>>c.origin.i>>c.origin.j>>c.signature>>ne>>nf;
        require(ne>=0 && ne<100000 && nf>=0 && nf<100000,"invalid mesh dimensions");
        for (int k=0;k<ne;++k) { MeshEdge e{}; in>>e.di>>e.dj>>e.to>>e.cost>>e.pid; c.edges.push_back(e); }
        for (int k=0;k<nf;++k) { Final f{}; in>>f.di>>f.dj>>f.theta>>f.cost; c.finals.push_back(f); }
        m.configs.push_back(std::move(c));
    }
    int nm=0; in>>nm; require(nm>=0 && nm<100000,"invalid map count");
    for (int k=0;k<nm;++k) {
        std::string name,row; int h=0,w=0; in>>std::quoted(name)>>h>>w; require(h>0 && w>0 && std::int64_t(h)*w<100000000,"invalid map dimensions");
        Grid g(h,w); for (int i=0;i<h;++i) { in>>row; require(int(row.size())==w,"invalid map row"); for (int j=0;j<w;++j) { require(row[j]=='.'||row[j]=='#',"invalid map symbol"); g.set({i,j},row[j]=='#'); } }
        s.maps.push_back(std::move(g)); s.map_names.push_back(name);
    }
    int n=0; in>>n; require(n>=0 && n<1000000,"invalid episode count");
    for (int k=0;k<n;++k) {
        Episode e; int nq=0; in>>std::quoted(e.id)>>std::quoted(e.cohort)>>e.map>>nq;
        require(e.map>=0 && e.map<nm && nq>0 && nq<1000000,"invalid episode");
        for (int j=0;j<nq;++j) {
            Query q; int nb=0,no=0;
            in>>q.start.i>>q.start.j>>q.start.k>>q.goal.i>>q.goal.j>>q.goal.k>>q.expected>>std::quoted(q.category)>>std::quoted(q.event)>>nb>>no;
            require(nb>=0 && no>=0 && nb<1000000 && no<1000000,"invalid update size");
            if (q.expected<0) q.expected=INF;
            q.blocks.resize(nb); q.opens.resize(no);
            for (auto& c:q.blocks) in>>c.i>>c.j;
            for (auto& c:q.opens) in>>c.i>>c.j;
            require(q.start.k>=0 && q.start.k<m.headings && q.goal.k>=0 && q.goal.k<m.headings,"invalid query heading");
            if (!e.queries.empty()) require(q.goal==e.queries.front().goal,"incremental goal must stay fixed");
            e.queries.push_back(std::move(q));
        }
        s.episodes.push_back(std::move(e));
    }
    require(bool(in),"truncated input"); in>>std::ws; require(in.eof(),"trailing input"); m.prepare(); return s;
}
} // namespace ima
