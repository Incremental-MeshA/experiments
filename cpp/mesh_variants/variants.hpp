#pragma once
#include "ima/planners.hpp"
#include <iterator>

// Float-cost ports of the earlier C-Mesh, suffix and boundary prototypes.
// Original primitive costs/IDs/traces are preserved. A dyadic potential makes
// every mesh edge positive without quantizing the physical objective.
namespace ima::variants {

struct Node {
    int heading=-1,depth=0;
    Cell origin;
    double potential=0;
    std::vector<Final> finals;
};
struct Edge {
    int from=0,to=0,pid=-1;
    Cell delta;
    double base=0,cost=0;
    std::vector<Cell> cells;
    std::vector<int> members; // projection audit; not consulted by search
};
struct Dependency {
    int configuration=0;
    Cell offset;
    std::vector<int> edges;
};
struct TemplateGraph {
    std::string name;
    bool suffix=false,batch=false;
    double delta=0;
    std::vector<int> roots;
    std::vector<Node> nodes;
    std::vector<Edge> edges;
    std::vector<std::vector<int>> out,in;
    std::vector<Dependency> dependencies;

    void index() {
        out.assign(nodes.size(),{});in.assign(nodes.size(),{});
        std::map<std::tuple<int,int,int>,std::vector<int>> grouped;
        for (std::size_t id=0;id<edges.size();++id) {
            const auto& e=edges[id];
            require(e.cost>0 && std::isfinite(e.cost),"variant edge is not positive");
            require(e.cells.size()>=2 && e.cells.front()==Cell{} && e.cells.back()==e.delta,"invalid macro trace");
            out.at(e.from).push_back(int(id));in.at(e.to).push_back(int(id));
            std::set<Cell> support(e.cells.begin(),e.cells.end());
            for (auto q:support) grouped[{e.from,q.i,q.j}].push_back(int(id));
        }
        dependencies.clear();
        for (auto& [key,ids]:grouped) {
            auto [cfg,i,j]=key;dependencies.push_back({cfg,{i,j},std::move(ids)});
        }
    }
    double heuristic(State u,Cell start) const {
        const auto& n=nodes[u.k];
        if (!suffix || n.heading>=0)
            return distance({u.i+n.origin.i,u.j+n.origin.j},start)+n.potential;
        double result=INF;
        for (auto f:n.finals) result=std::min(result,f.cost+distance({u.i+f.di,u.j+f.dj},start));
        return result+n.potential;
    }
};

using Marker=std::pair<int,int>;
using Bundle=std::vector<Marker>;

inline TemplateGraph prefix(const std::vector<Primitive>& primitives,int headings) {
    TemplateGraph g;g.name="positive_prefix";
    std::vector<Bundle> bundles;
    std::map<Bundle,int> identifiers;
    auto ensure=[&](const Bundle& b,int heading) {
        if (heading<0) { auto found=identifiers.find(b);if (found!=identifiers.end()) return found->second; }
        int id=int(bundles.size());bundles.push_back(b);
        if (!b.empty()) identifiers.emplace(b,id);
        Node n;n.heading=heading;
        if (!b.empty()) {
            n.depth=b.front().second;auto point=primitives[b.front().first].cells[n.depth];n.origin={-point.i,-point.j};
            for (auto [pid,k]:b) {
                const auto& p=primitives[pid];
                require(k==n.depth && p.cells[k]==point,"bundle origin/depth is not unique");
                n.finals.push_back({p.di-point.i,p.dj-point.j,p.end,p.cost});
            }
        }
        g.nodes.push_back(std::move(n));return id;
    };
    for (int h=0;h<headings;++h) {
        Bundle b;for (std::size_t p=0;p<primitives.size();++p) if (primitives[p].start==h) b.push_back({int(p),0});
        g.roots.push_back(ensure(b,h));
    }
    for (std::size_t cfg=0;cfg<bundles.size();++cfg) {
        // ensure() may reallocate bundles; iterate an independent copy.
        Bundle b=bundles[cfg];std::map<Cell,Bundle> groups;
        for (auto [pid,k]:b) {
            const auto& p=primitives[pid];Cell a=p.cells[k],z=p.cells[k+1],d{z.i-a.i,z.j-a.j};
            if (std::size_t(k+1)==p.cells.size()-1)
                g.edges.push_back({int(cfg),g.roots[p.end],pid,d,p.cost,0,{{0,0},d},{pid}});
            else groups[d].push_back({pid,k+1});
        }
        for (const auto& [d,group]:groups) {
            int to=ensure(group,-1);std::vector<int> members;
            for (auto x:group) members.push_back(x.first);
            g.edges.push_back({int(cfg),to,-1,d,0,0,{{0,0},d},std::move(members)});
        }
    }
    int max_depth=0;double minimum=INF;
    for (const auto& n:g.nodes) max_depth=std::max(max_depth,n.depth);
    for (const auto& p:primitives) minimum=std::min(minimum,p.cost);
    int exponent=0;std::frexp(minimum/(4*(max_depth+1)),&exponent);
    g.delta=std::ldexp(1.0,exponent-1);
    for (auto& n:g.nodes) n.potential=g.delta*n.depth;
    for (auto& e:g.edges) e.cost=e.base+g.nodes[e.to].potential-g.nodes[e.from].potential;
    g.index();return g;
}

inline TemplateGraph compress(const TemplateGraph& source) {
    TemplateGraph g;g.name="cmesh";g.delta=source.delta;
    std::vector<int> remap(source.nodes.size(),-1),kept;
    for (std::size_t q=0;q<source.nodes.size();++q)
        if (source.nodes[q].heading>=0 || source.out[q].size()!=1 || source.in[q].size()!=1) {
            remap[q]=int(kept.size());kept.push_back(int(q));g.nodes.push_back(source.nodes[q]);
        }
    for (int q:source.roots) g.roots.push_back(remap[q]);
    for (int q:kept) for (int first:source.out[q]) {
        Edge e; e.from=remap[q];e.cells={{0,0}};e.members=source.edges[first].members;
        int id=first;std::size_t steps=0;
        while (true) {
            require(++steps<=source.nodes.size()+1,"cycle inside contracted chain");
            const auto& part=source.edges[id];
            for (std::size_t k=1;k<part.cells.size();++k) e.cells.push_back({e.delta.i+part.cells[k].i,e.delta.j+part.cells[k].j});
            e.delta.i+=part.delta.i;e.delta.j+=part.delta.j;e.base+=part.base;e.pid=part.pid;
            if (remap[part.to]>=0) { e.to=remap[part.to];break; }
            require(part.pid<0,"primitive boundary removed by compression");
            id=source.out[part.to].front();std::vector<int> intersection;
            const auto& next=source.edges[id].members;
            std::set_intersection(e.members.begin(),e.members.end(),next.begin(),next.end(),std::back_inserter(intersection));
            e.members=std::move(intersection);require(!e.members.empty(),"empty chain projection");
        }
        e.cost=e.base+g.nodes[e.to].potential-g.nodes[e.from].potential;
        g.edges.push_back(std::move(e));
    }
    g.index();return g;
}

inline TemplateGraph suffix(const Model& model) {
    auto reverse=model.primitives;
    for (auto& p:reverse) {
        std::swap(p.start,p.end);int di=p.di,dj=p.dj;p.di=-di;p.dj=-dj;
        std::reverse(p.cells.begin(),p.cells.end());for (auto& c:p.cells) { c.i-=di;c.j-=dj; }
    }
    auto g=prefix(reverse,model.headings);g.name="suffix_mesh";g.suffix=true;
    for (auto& n:g.nodes) n.potential=-n.potential;
    for (auto& e:g.edges) {
        std::swap(e.from,e.to);int di=e.delta.i,dj=e.delta.j;e.delta={-di,-dj};
        std::reverse(e.cells.begin(),e.cells.end());for (auto& c:e.cells) { c.i-=di;c.j-=dj; }
        // Positive cost is inherited from the reversed-primitive prefix graph.
    }
    g.index();return g;
}

inline TemplateGraph boundary(const Model& model) {
    TemplateGraph g;g.name="boundary_mesh";g.batch=true;
    for (int h=0;h<model.headings;++h) { Node n;n.heading=h;g.roots.push_back(h);g.nodes.push_back(n); }
    for (std::size_t id=0;id<model.primitives.size();++id) {
        const auto& p=model.primitives[id];
        g.edges.push_back({p.start,p.end,int(id),{p.di,p.dj},p.cost,p.cost,p.cells,{int(id)}});
    }
    g.index();return g;
}

struct Prepared {
    const Model& original;
    TemplateGraph positive,contracted,reversed,batched;
    std::vector<int> slot;
    double compile_s=0;
    explicit Prepared(const Model& m):original(m) {
        auto begin=Clock::now();positive=prefix(m.primitives,m.headings);
        // Check the port against the exact frozen forward automaton, not just
        // against an equivalent set of boundary paths.
        require(positive.nodes.size()==m.configs.size() && positive.roots==m.initial,"prefix compiler differs from frozen model");
        for (std::size_t q=0;q<m.configs.size();++q) {
            require(positive.out[q].size()==m.configs[q].edges.size(),"prefix edge count differs");
            for (std::size_t k=0;k<positive.out[q].size();++k) {
                const auto& a=positive.edges[positive.out[q][k]];auto b=m.configs[q].edges[k];
                require(a.delta==Cell{b.di,b.dj} && a.to==b.to && a.pid==b.pid && a.base==b.cost,"prefix transition differs");
            }
        }
        contracted=compress(positive);reversed=suffix(m);batched=boundary(m);
        slot.resize(m.primitives.size());for (const auto& ids:m.by_start) for (std::size_t k=0;k<ids.size();++k) slot[ids[k]]=int(k);
        compile_s=seconds(begin);
    }
    const TemplateGraph& graph(const std::string& name) const {
        if (name=="prefix_positive") return positive;
        if (name=="cmesh_dstar") return contracted;
        if (name=="suffix_mesh") return reversed;
        require(name=="boundary_mesh","unknown mesh variant");return batched;
    }
    std::pair<std::size_t,std::size_t> audit() const {
        std::size_t projections=0,heuristics=0;
        for (const auto* g:{&positive,&contracted,&reversed,&batched}) {
            for (std::size_t pid=0;pid<original.primitives.size();++pid) {
                const auto& p=original.primitives[pid];int cfg=g->roots[p.start];Cell position{};
                std::vector<Cell> cells={{0,0}};std::vector<int> tags;long double cost=0;
                for (std::size_t steps=0;;++steps) {
                    require(steps<10000,"projection audit cycle");
                    if (steps && cfg==g->roots[p.end] && position==Cell{p.di,p.dj}) break;
                    int selected=-1;
                    for (int id:g->out[cfg]) {
                        const auto& e=g->edges[id];if (!std::binary_search(e.members.begin(),e.members.end(),int(pid))) continue;
                        require(selected<0,"ambiguous primitive projection");selected=id;
                    }
                    require(selected>=0,"primitive lost by graph transformation");const auto& e=g->edges[selected];
                    for (std::size_t k=1;k<e.cells.size();++k) cells.push_back({position.i+e.cells[k].i,position.j+e.cells[k].j});
                    position.i+=e.delta.i;position.j+=e.delta.j;cfg=e.to;cost+=e.cost;if (e.pid>=0) tags.push_back(e.pid);
                }
                require(cells==p.cells && tags==std::vector<int>{int(pid)} && std::abs(double(cost)-p.cost)<1e-9,"projection/cost not preserved");++projections;
            }
            for (Cell start:std::vector<Cell>{{0,0},{17,31},{-8,11}}) for (const auto& e:g->edges) {
                double a=g->heuristic({0,0,e.from},start),b=g->heuristic({e.delta.i,e.delta.j,e.to},start);
                require(b<=e.cost+a+1e-9,"inconsistent variant heuristic");++heuristics;
            }
        }
        return {projections,heuristics};
    }
    void json(std::ostream& out) const {
        out<<'{';bool first=true;
        for (const auto* g:{&positive,&contracted,&reversed,&batched}) {
            if (!first) out<<',';
            first=false;
            out<<'"'<<g->name<<"\":{\"configurations\":"<<g->nodes.size()<<",\"edges\":"<<g->edges.size()
               <<",\"support_groups\":"<<g->dependencies.size()<<",\"delta\":"<<g->delta<<'}';
        }
        out<<'}';
    }
};

class Graph {
    struct Mask { std::vector<std::uint8_t> flags;bool dirty=true; };
    const Prepared& prepared;
    EdgeCache cache;
    StateMap<Mask> masks;
    void evaluate(State origin,Mask& mask) {
        const auto& m=prepared.original;int theta=definition.nodes[origin.k].heading;
        require(theta>=0,"batch origin is not a primitive boundary");
        mask.flags.assign(m.by_start[theta].size(),0);mask.dirty=false;
        struct Item { int cfg;Cell cell; };
        std::vector<Item> stack={{m.initial[theta],origin.cell()}};
        while (!stack.empty()) {
            auto item=stack.back();stack.pop_back();++stats.checked_cells;
            if (!grid.free(item.cell)) continue;
            for (auto e:m.configs[item.cfg].edges) {
                Cell next{item.cell.i+e.di,item.cell.j+e.dj};
                if (e.pid>=0) { ++stats.checked_cells;if (grid.free(next)) mask.flags[prepared.slot[e.pid]]=1; }
                else stack.push_back({e.to,next});
            }
        }
    }
public:
    const TemplateGraph& definition;
    Grid grid;
    Stats stats;
    Graph(const Prepared& p,const TemplateGraph& d,const Grid& g):prepared(p),definition(d),grid(g) {}
    State vertex(State s) const { s.k=definition.roots.at(s.k);return s; }
    double cost(State u,int id) {
        const auto& e=definition.edges[id];
        if (definition.batch) {
            auto& mask=masks[u];if (mask.dirty) evaluate(u,mask);
            return mask.flags[prepared.slot[e.pid]] ? e.cost : INF;
        }
        EdgeKey key{u,id};auto it=cache.find(key);if (it!=cache.end()) return it->second ? e.cost : INF;
        bool valid=true;
        for (auto d:e.cells) { ++stats.checked_cells;if (!grid.free({u.i+d.i,u.j+d.j})) { valid=false;break; } }
        cache.emplace(key,valid);return valid ? e.cost : INF;
    }
    struct Arc { State to;double cost;int pid; };
    std::vector<Arc> successors(State u) {
        std::vector<Arc> result;
        for (int id:definition.out[u.k]) {
            const auto& e=definition.edges[id];State v{u.i+e.delta.i,u.j+e.delta.j,e.to};
            if (grid.inside(v.cell())) result.push_back({v,cost(u,id),e.pid});
        }
        return result;
    }
    std::vector<State> predecessors(State v) const {
        // Register all geometric predecessors, including infinite-cost edges.
        // Otherwise a later opening can fail to discover a new component.
        std::vector<State> result;
        for (int id:definition.in[v.k]) {
            const auto& e=definition.edges[id];State u{v.i-e.delta.i,v.j-e.delta.j,e.from};
            if (grid.inside(u.cell())) result.push_back(u);
        }
        std::sort(result.begin(),result.end());result.erase(std::unique(result.begin(),result.end()),result.end());return result;
    }
    std::set<State> invalidate(const std::vector<Cell>& changes) {
        std::set<State> dirty;
        for (auto q:changes) for (const auto& d:definition.dependencies) {
            ++stats.notify_probes;State u{q.i-d.offset.i,q.j-d.offset.j,d.configuration};
            if (!grid.inside(u.cell())) continue;
            if (definition.batch) { auto it=masks.find(u);if (it!=masks.end()) it->second.dirty=true; }
            else for (int edge:d.edges) cache.erase({u,edge});
            dirty.insert(u);
        }
        return dirty;
    }
};

class MeshVariantPlanner final : public Planner {
    using Key=std::pair<double,double>;
    struct Record { double g=INF,rhs=INF;std::uint64_t version=0; };
    struct Entry {
        Key key;State u;std::uint64_t version,sequence;
        bool operator>(const Entry& b) const { return std::tie(key,sequence)>std::tie(b.key,b.sequence); }
    };
    const Model& model;
    Graph graph;
    State physical_goal,start,last,goal;
    StateMap<Record> records;
    std::priority_queue<Entry,std::vector<Entry>,std::greater<Entry>> open;
    std::uint64_t sequence=0,limit;
    double km=0;
    double g(State u) const { auto it=records.find(u);return it==records.end() ? INF : it->second.g; }
    Key key(State u) const {
        const auto& r=records.at(u);double a=std::min(r.g,r.rhs);
        return {a+graph.definition.heuristic(u,start.cell())+km,a};
    }
    void queue(State u) {
        auto& r=records.at(u);++r.version;
        if (r.g!=r.rhs) open.push({key(u),u,r.version,++sequence});
    }
    void update(State u) {
        double rhs=0;
        if (u!=goal) { rhs=INF;for (auto e:graph.successors(u)) rhs=std::min(rhs,e.cost+g(e.to)); }
        records[u].rhs=rhs;queue(u);
    }
    void clean() {
        while (!open.empty()) {
            const auto& e=open.top();const auto& r=records.at(e.u);
            if (r.version==e.version && r.g!=r.rhs) break;
            open.pop();
        }
    }
    bool compute() {
        records.try_emplace(start);
        while (true) {
            clean();const auto& target=records.at(start);double boundary=key(start).first;
            if (open.empty() || (target.g==target.rhs && open.top().key.first>boundary+EPS*(1+std::abs(boundary)))) return true;
            auto e=open.top();open.pop();Key now=key(e.u);
            if (e.key<now) { queue(e.u);continue; }
            if (graph.stats.expansions>=limit) { open.push(e);return false; }
            ++graph.stats.expansions;
            // Do not retain references across update(): unordered_map can rehash.
            if (records.at(e.u).g>records.at(e.u).rhs) records.at(e.u).g=records.at(e.u).rhs;
            else { records.at(e.u).g=INF;update(e.u); }
            for (auto pred:graph.predecessors(e.u)) update(pred);
        }
    }
    Path extract(State physical_start) {
        double label=g(start);if (!std::isfinite(label)) return {};
        State u=start;std::vector<int> ids;
        for (std::size_t steps=0;u!=goal;++steps) {
            require(steps<100000,"variant extraction exceeded path limit");
            double best=INF;Graph::Arc selected{};bool found=false;
            for (auto e:graph.successors(u)) {
                double v=e.cost+g(e.to);
                if (v<best-1e-12) { selected=e;best=v;found=true; }
            }
            require(found && std::isfinite(best) && std::abs(best-g(u))<1e-6,"variant finite label has no consistent path");
            require(g(selected.to)<g(u),"positive variant path does not decrease");
            if (selected.pid>=0) ids.push_back(selected.pid);
            u=selected.to;
        }
        auto p=path_from_ids(model,physical_start,ids);
        require(p.states.back()==physical_goal && std::abs(p.cost-label)<1e-6,"variant projection/cost mismatch");return p;
    }
public:
    MeshVariantPlanner(const Prepared& p,const std::string& name,const Grid& grid,State s,State t,std::uint64_t cap)
        :model(p.original),graph(p,p.graph(name),grid),physical_goal(t),start(graph.vertex(s)),last(start),goal(graph.vertex(t)),limit(cap) {
        records[goal].rhs=0;queue(goal);
    }
    Path replan(State s,const std::vector<Cell>& blocks={},const std::vector<Cell>& opens={}) override {
        auto [b,o]=net_changes(graph.grid,blocks,opens);graph.stats={};graph.stats.backend_calls=1;
        start=graph.vertex(s);km+=distance(last.cell(),start.cell());last=start;
        for (auto q:b) graph.grid.set(q,true);
        for (auto q:o) graph.grid.set(q,false);
        std::vector<Cell> changed=b;changed.insert(changed.end(),o.begin(),o.end());
        for (auto u:graph.invalidate(changed)) if (records.count(u)) update(u);
        Path result;
        if (graph.grid.free(s.cell()) && graph.grid.free(physical_goal.cell())) {
            if (!compute()) result.stats.capped=true;else result=extract(s);
        }
        bool capped=result.stats.capped;result.stats=graph.stats;result.stats.capped=capped;return result;
    }
};
} // namespace ima::variants
