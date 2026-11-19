#include <algorithm>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <filesystem>
#include <functional>
#include <iostream>
#include <limits>
#include <memory>
#include <queue>
#include <random>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <tuple>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>
#include <sys/resource.h>

using I = int64_t;
using Id = uint64_t;
constexpr I INF = std::numeric_limits<I>::max()/8;
constexpr Id NONE = std::numeric_limits<Id>::max();
using Clock = std::chrono::steady_clock;
struct RC { int r=0,c=0; bool operator==(const RC& x) const { return r==x.r && c==x.c; } };
struct State { int r=0,c=0,h=0; };
struct Primitive { int id,h,dr,dc,th; I cost; std::vector<RC> trace; };
struct Config { int initial,depth,orr,orc; std::vector<std::pair<int,int>> finals; };
struct Edge { int src,dst,dr,dc,pid; I cost; std::vector<RC> trace; };
struct Dependency { int edge,dr,dc; };
struct Stats {
    uint64_t expanded=0,updates=0,edge_checks=0,cell_checks=0,pushes=0,pops=0,notify_probes=0,affected=0;
};
struct Grid {
    int H=0,W=0; std::vector<uint8_t> blocked;
    explicit Grid(const std::string& path) {
        std::ifstream f(path); if(!f) throw std::runtime_error("Cannot open map: "+path);
        std::string s; std::getline(f,s); f>>s>>H>>s>>W>>s; std::getline(f,s);
        if(H<=0 || W<=0) throw std::runtime_error("Bad map header");
        blocked.reserve(H*W);
        for(int r=0;r<H;++r){ std::getline(f,s); if((int)s.size()<W) throw std::runtime_error("Short map row");
            for(int c=0;c<W;++c) blocked.push_back(s[c]!='.' && s[c]!='G' && s[c]!='S'); }
    }
    bool inside(int r,int c) const {return r>=0 && c>=0 && r<H && c<W;}
    bool free(int r,int c) const {return inside(r,c) && !blocked[r*W+c];}
};
struct Model {
    int headings,Q; I delta,alpha; std::unordered_map<int,Primitive> primitives;
    std::vector<Config> conf; std::vector<Edge> edges;
    std::vector<std::vector<int>> out,in;
    std::vector<Dependency> dep;std::vector<int> edge_slot;
    explicit Model(const std::string& path) {
        std::ifstream f(path); if(!f) throw std::runtime_error("Cannot open model: "+path);
        int P,E; f>>headings>>P>>Q>>E>>delta>>alpha;
        for(int i=0;i<P;++i){Primitive p; int n; f>>p.id>>p.h>>p.dr>>p.dc>>p.th>>p.cost>>n;
            for(int j=0;j<n;++j){RC x;f>>x.r>>x.c;p.trace.push_back(x);} primitives[p.id]=p;}
        for(int i=0;i<Q;++i){Config c;int n;f>>c.initial>>c.depth>>c.orr>>c.orc>>n;
            for(int j=0;j<n;++j){int p,k;f>>p>>k;c.finals.emplace_back(p,k);}conf.push_back(c);}
        out.resize(Q);in.resize(Q);
        for(int i=0;i<E;++i){Edge e;int n;f>>e.src>>e.dst>>e.dr>>e.dc>>e.cost>>e.pid>>n;
            if(e.cost<=0) throw std::runtime_error("Nonpositive edge");
            std::set<std::pair<int,int>> support;
            for(int j=0;j<n;++j){RC x;f>>x.r>>x.c;e.trace.push_back(x);support.emplace(x.r,x.c);}
            edges.push_back(e);edge_slot.push_back(out[e.src].size());out[e.src].push_back(i);in[e.dst].push_back(i);
            for(auto [r,c]:support) dep.push_back({i,r,c});}
        if(!f) throw std::runtime_error("Truncated model");
    }
    I metric(int r,int c) const {I a=std::abs(r),b=std::abs(c);return alpha*(1000*std::max(a,b)+414*std::min(a,b));}
};
struct Graph {
    Model& m; Grid& grid; Stats st;
    int cache_mode=0;std::unique_ptr<Model> batchmesh;
    std::unordered_map<Id,std::vector<int8_t>> cache;
    struct GroupDep {int h,dr,dc;};std::vector<GroupDep> group_dep;
    Graph(Model& model,Grid& map):m(model),grid(map){}
    void enable_cache(int mode,const std::string& meshpath=""){
        cache_mode=mode;if(mode!=2)return;batchmesh=std::make_unique<Model>(meshpath);
        std::set<std::tuple<int,int,int>> unique;
        for(const auto& e:m.edges)for(auto p:e.trace)unique.emplace(e.src,p.r,p.c);
        for(auto [h,r,c]:unique)group_dep.push_back({h,r,c});
    }
    Id id(int r,int c,int q) const {return (Id(r)*grid.W+c)*m.Q+q;}
    Id id(State s) const {return id(s.r,s.c,s.h);}
    void decode(Id x,int& r,int& c,int& q) const {q=x%m.Q;x/=m.Q;r=x/grid.W;c=x%grid.W;}
    RC pos(Id x) const {int r,c,q;decode(x,r,c,q);return {r,c};}
    bool free(Id x) const {auto p=pos(x);return grid.free(p.r,p.c);}
    void evaluate_batch(Id origin,std::vector<int8_t>& flags){
        int r,c,h;decode(origin,r,c,h);std::fill(flags.begin(),flags.end(),0);
        struct Item {int q,dr,dc;};std::vector<Item> stack={{h,0,0}};
        while(!stack.empty()){
            auto a=stack.back();stack.pop_back();++st.cell_checks;
            if(!grid.free(r+a.dr,c+a.dc))continue;
            for(int ei:batchmesh->out[a.q]){const auto& e=batchmesh->edges[ei];
                int nr=a.dr+e.dr,nc=a.dc+e.dc;
                if(e.pid>=0){++st.cell_checks;if(grid.free(r+nr,c+nc)){
                    for(int le:m.out[h])if(m.edges[le].pid==e.pid){flags[m.edge_slot[le]]=1;break;}
                }}else stack.push_back({e.dst,nr,nc});
            }
        }
    }
    void invalidate(const std::vector<RC>& changed){
        if(!cache_mode)return;
        if(cache_mode==2){for(auto p:changed)for(auto d:group_dep){++st.notify_probes;
            int r=p.r-d.dr,c=p.c-d.dc;if(!grid.inside(r,c))continue;
            auto it=cache.find(id(r,c,d.h));if(it!=cache.end())std::fill(it->second.begin(),it->second.end(),-1);}}
        else for(auto p:changed)for(auto d:m.dep){++st.notify_probes;int r=p.r-d.dr,c=p.c-d.dc;
            if(!grid.inside(r,c))continue;
            const auto& e=m.edges[d.edge];auto it=cache.find(id(r,c,e.src));
            if(it!=cache.end())it->second[m.edge_slot[d.edge]]=-1;}
    }
    I cost(Id tail,int ei) {
        ++st.edge_checks;int r,c,q;decode(tail,r,c,q);const auto& e=m.edges[ei];
        std::vector<int8_t>* flags=nullptr;int slot=m.edge_slot[ei];
        if(cache_mode){auto [it,inserted]=cache.try_emplace(tail);if(inserted)it->second.assign(m.out[q].size(),-1);flags=&it->second;
            if(cache_mode==2 && (*flags)[slot]<0)evaluate_batch(tail,*flags);
            if((*flags)[slot]>=0)return (*flags)[slot]?e.cost:INF;
        }
        bool valid=true;for(auto p:e.trace){++st.cell_checks;if(!grid.free(r+p.r,c+p.c)){valid=false;break;}}
        if(flags)(*flags)[slot]=valid;
        return valid?e.cost:INF;
    }
    Id head(Id tail,int ei) const {int r,c,q;decode(tail,r,c,q);const auto& e=m.edges[ei];
        if(!grid.inside(r+e.dr,c+e.dc))return NONE;
        return id(r+e.dr,c+e.dc,e.dst);}
    Id tail(Id head,int ei) const {int r,c,q;decode(head,r,c,q);const auto& e=m.edges[ei];
        if(!grid.inside(r-e.dr,c-e.dc))return NONE;
        return id(r-e.dr,c-e.dc,e.src);}
    template<class F> void succ(Id x,F f) const {int r,c,q;decode(x,r,c,q);for(int ei:m.out[q]){Id y=head(x,ei);if(y!=NONE)f(y,ei);}}
    template<class F> void pred(Id x,F f) const {int r,c,q;decode(x,r,c,q);for(int ei:m.in[q]){Id y=tail(x,ei);if(y!=NONE)f(y,ei);}}
    I heuristic(Id x,Id target,bool reverse,bool zero=false) const {
        if(zero)return 0;
        int r,c,q,tr,tc,tq;decode(x,r,c,q);decode(target,tr,tc,tq);const auto& cf=m.conf[q];
        if(reverse) {
#ifdef IMA_SUFFIX
            // The graph is the reversal of mesh(reverse-primitives). D* Lite
            // therefore uses that mesh's forward Finals heuristic. Its
            // potential has the opposite sign in the forward original graph.
            if(cf.initial>=0)return m.metric(r-tr,c-tc);
            I best=INF;
            for(auto [pid,k]:cf.finals){const auto& p=m.primitives.at(pid);
                const auto& off=p.trace[p.trace.size()-1-k];
                best=std::min(best,p.cost+m.metric(r-off.r-tr,c-off.c-tc));}
            return best-m.delta*cf.depth;
#else
            return m.metric(r-cf.orr-tr,c-cf.orc-tc)+m.delta*cf.depth;
#endif
        }
        if(cf.initial>=0)return m.metric(r-tr,c-tc);
        I best=INF;
        for(auto [pid,k]:cf.finals){const auto& p=m.primitives.at(pid);const auto& off=p.trace[k];
            best=std::min(best,p.cost+m.metric(r+p.dr-off.r-tr,c+p.dc-off.c-tc));}
        return best-m.delta*cf.depth;
    }
};
using Key=std::pair<I,I>;
struct Entry {Key key;Id id;uint64_t ver;bool operator<(const Entry& b)const{return std::tie(key,id,ver)>std::tie(b.key,b.id,b.ver);}};
struct Record {I g=INF,rhs=INF;uint64_t ver=0;Id parent=NONE;int parent_edge=-1;bool closed=false;};
struct Result {I cost=INF;std::vector<int> prims;std::vector<Id> nodes;};
class Planner {
public:
    Graph& g; bool incremental,reverse,zero,scan; Id start,goal,root,target;I km=0;
    std::unordered_map<Id,Record> rec;
    std::priority_queue<Entry> open;
    Planner(Graph& graph,State s,State t,bool inc,bool rev,bool z=false,bool fullscan=false)
      :g(graph),incremental(inc),reverse(rev),zero(z),scan(fullscan),start(g.id(s)),goal(g.id(t)),
       root(rev?goal:start),target(rev?start:goal){rec.reserve(4096);if(inc){rec[root].rhs=0;queue(root);}}
    I val(Id x)const {auto it=rec.find(x);return it==rec.end()?INF:it->second.g;}
    Key key(Id x)const {const auto& v=rec.at(x);I a=std::min(v.g,v.rhs);return {a+g.heuristic(x,target,reverse,zero)+km,a};}
    void queue(Id x){auto& v=rec.at(x);++v.ver;if(v.g!=v.rhs){open.push({key(x),x,v.ver});++g.st.pushes;}}
    void clean(){while(!open.empty()){const auto& e=open.top();auto it=rec.find(e.id);
        if(it!=rec.end() && it->second.ver==e.ver && it->second.g!=it->second.rhs)break;
        open.pop();++g.st.pops;}}
    void update(Id x){++g.st.updates;auto& v=rec[x];if(x!=root){I best=INF;
        if(reverse)g.succ(x,[&](Id y,int ei){I gy=val(y);if(gy<INF)best=std::min(best,gy+g.cost(x,ei));});
        else g.pred(x,[&](Id y,int ei){I gy=val(y);if(gy<INF)best=std::min(best,gy+g.cost(y,ei));});
        v.rhs=std::min(best,INF);}queue(x);}
    void propagate(Id x){ // Register geometric neighbors even when blocked: essential for decreases.
        if(reverse)g.pred(x,[&](Id y,int){update(y);});else g.succ(x,[&](Id y,int){update(y);});}
    void move(State s){Id n=g.id(s);if(n==start)return;
        if(incremental && !reverse)throw std::runtime_error("LPA* requires fixed start");
        if(reverse){auto a=g.pos(start),b=g.pos(n);km+=g.m.metric(a.r-b.r,a.c-b.c);target=n;}
        start=n;}
    void notify(const std::vector<RC>& changed){if(!incremental)return;
        std::unordered_set<Id> dirty;
        if(scan){
            // Reference ablation: inspect every registered tail and every support cell.
            std::set<std::pair<int,int>> cells;for(auto p:changed)cells.emplace(p.r,p.c);
            for(const auto& [u,v]:rec){(void)v;int r,c,q;g.decode(u,r,c,q);
                for(int ei:g.m.out[q]){bool hit=false;for(auto p:g.m.edges[ei].trace){++g.st.notify_probes;
                    if(cells.count({r+p.r,c+p.c})){hit=true;break;}}
                    if(hit){Id x=reverse?u:g.head(u,ei);if(x!=NONE)dirty.insert(x);}}}
        }else if(g.cache_mode==2 && reverse){
            for(auto p:changed)for(auto d:g.group_dep){++g.st.notify_probes;int r=p.r-d.dr,c=p.c-d.dc;
                if(!g.grid.inside(r,c))continue;
                Id u=g.id(r,c,d.h);if(rec.find(u)!=rec.end())dirty.insert(u);}
        }else{
            for(auto p:changed)for(const auto& d:g.m.dep){++g.st.notify_probes;
                int r=p.r-d.dr,c=p.c-d.dc;if(!g.grid.inside(r,c))continue;
                const auto& e=g.m.edges[d.edge];Id u=g.id(r,c,e.src);
                if(rec.find(u)==rec.end())continue;
                Id x=reverse?u:g.head(u,d.edge);if(x!=NONE)dirty.insert(x);}
        }
        g.st.affected+=dirty.size();std::vector<Id> sorted(dirty.begin(),dirty.end());std::sort(sorted.begin(),sorted.end());
        for(Id x:sorted)update(x);
    }
    void repair(){rec.try_emplace(target);clean();
        uint64_t limit=0;
        while(!open.empty() && (open.top().key<key(target) || rec.at(target).g!=rec.at(target).rhs)){
            if(++limit>100000000)throw std::runtime_error("Repair iteration limit");
            Entry e=open.top();open.pop();++g.st.pops;Key now=key(e.id);
            if(e.key<now){queue(e.id);clean();continue;}
            ++g.st.expanded;
            auto& u=rec.at(e.id);
            if(u.g>u.rhs){u.g=u.rhs;++u.ver;propagate(e.id);}
            else{u.g=INF;++u.ver;update(e.id);propagate(e.id);}clean();
        }
    }
    Result extract_incremental(){Result out;out.cost=val(target);if(out.cost>=INF)return out;
        Id x=target;std::vector<int> edge_path;out.nodes.push_back(x);
        while(x!=root){Id next=NONE;int selected=-1;I best=INF;
            auto consider=[&](Id y,int ei){I gy=val(y);if(gy>=INF)return;I c=g.cost(reverse?x:y,ei);
                I v=std::min(INF,c+gy);if(v<best || (v==best && y<next)){best=v;next=y;selected=ei;}};
            if(reverse)g.succ(x,consider);else g.pred(x,consider);
            if(next==NONE || best!=val(x) || val(next)>=val(x))throw std::runtime_error("Invalid incremental parent chain");
            edge_path.push_back(selected);x=next;out.nodes.push_back(x);
            if(out.nodes.size()>rec.size()+1)throw std::runtime_error("Parent cycle");
        }
        if(!reverse){std::reverse(edge_path.begin(),edge_path.end());std::reverse(out.nodes.begin(),out.nodes.end());}
        for(int ei:edge_path)if(g.m.edges[ei].pid>=0)out.prims.push_back(g.m.edges[ei].pid);
        return out;
    }
    Result astar(){rec.clear();open={};root=start;target=goal;rec[start].g=0;
        open.push({{g.heuristic(start,goal,false,zero),0},start,0});++g.st.pushes;
        while(!open.empty()){
            Entry e=open.top();open.pop();++g.st.pops;
            if(e.key.second!=val(e.id)||rec.at(e.id).closed)continue;
            rec.at(e.id).closed=true;
            ++g.st.expanded;
            if(e.id==goal){Result out;out.cost=val(goal);Id x=goal;
                while(x!=start){out.nodes.push_back(x);const auto& r=rec.at(x);
                    int pid=g.m.edges[r.parent_edge].pid;if(pid>=0)out.prims.push_back(pid);x=r.parent;}
                out.nodes.push_back(start);std::reverse(out.prims.begin(),out.prims.end());std::reverse(out.nodes.begin(),out.nodes.end());return out;}
            int nr,nc,nq;g.decode(e.id,nr,nc,nq);const auto& cfg=g.m.conf[nq];
            if(cfg.initial<0){bool redundant=true;
                for(auto [pid,k]:cfg.finals){const auto& prim=g.m.primitives.at(pid);auto off=prim.trace[k];
                    int er=nr+prim.dr-off.r,ec=nc+prim.dc-off.c;if(!g.grid.free(er,ec))continue;
                    auto it=rec.find(g.id(er,ec,prim.th));
                    if(it==rec.end()||!it->second.closed){redundant=false;break;}}
                if(redundant)continue;
            }
            I gu=val(e.id);
            g.succ(e.id,[&](Id v,int ei){I c=g.cost(e.id,ei);if(c>=INF)return;I ng=gu+c;
                if(ng<val(v)){auto& r=rec[v];r.g=ng;r.parent=e.id;r.parent_edge=ei;
                    open.push({{ng+g.heuristic(v,goal,false,zero),ng},v,0});++g.st.pushes;}});
        }return {};
    }
    Result solve(){if(!g.free(start) || !g.free(goal))return {};if(!incremental)return astar();repair();return extract_incremental();}
    void validate(const Result& result)const {
        if(result.cost>=INF)return;
        auto s=g.pos(start);int q=int(start%g.m.Q);int h=g.m.conf[q].initial;I total=0;
        if(h<0)throw std::runtime_error("Noninitial start");
        for(int pid:result.prims){const auto& p=g.m.primitives.at(pid);
            if(p.h!=h)throw std::runtime_error("Wrong heading in reconstruction");
            for(auto off:p.trace)if(!g.grid.free(s.r+off.r,s.c+off.c))throw std::runtime_error("Collision in reconstruction");
            s.r+=p.dr;s.c+=p.dc;h=p.th;total+=p.cost;}
        auto t=g.pos(goal);int th=g.m.conf[goal%g.m.Q].initial;
        if(s.r!=t.r || s.c!=t.c || h!=th || total!=result.cost)throw std::runtime_error("Reconstruction endpoint or cost mismatch");
    }
};

struct Step {State start;std::vector<std::tuple<int,int,int>> changes;};
struct Workload {std::string map;State start,goal;std::vector<Step> steps;};
Workload load_workload(const std::string& path){std::ifstream f(path);if(!f)throw std::runtime_error("Missing workload");
    Workload w;f>>w.map>>w.start.r>>w.start.c>>w.start.h>>w.goal.r>>w.goal.c>>w.goal.h;
    if(!std::filesystem::exists(w.map)){
        auto local=std::filesystem::path(path).parent_path().parent_path()/"maps"/std::filesystem::path(w.map).filename();
        if(std::filesystem::exists(local))w.map=local.string();
    }
    int r,c,h,n;while(f>>r>>c>>h>>n){Step s;s.start={r,c,h};for(int i=0;i<n;++i){int a,b,v;f>>a>>b>>v;s.changes.emplace_back(a,b,v);}w.steps.push_back(s);}return w;}
void save_workload(const Workload& w,const std::string& path){std::ofstream f(path);f<<w.map<<'\n'<<w.start.r<<' '<<w.start.c<<' '<<w.start.h<<' '
    <<w.goal.r<<' '<<w.goal.c<<' '<<w.goal.h<<'\n';for(const auto& s:w.steps){f<<s.start.r<<' '<<s.start.c<<' '<<s.start.h<<' '<<s.changes.size()<<'\n';for(auto [r,c,v]:s.changes)f<<r<<' '<<c<<' '<<v<<'\n';}}
std::vector<RC> apply(Grid& grid,const Step& s){std::vector<RC> changed;
    for(auto [r,c,v]:s.changes){if(!grid.inside(r,c))throw std::runtime_error("Change outside map");
        auto& cell=grid.blocked[r*grid.W+c];if(cell!=v){cell=v;changed.push_back({r,c});}}return changed;}

void generate(const std::string& model_path,const std::string& map_path,const std::string& path,
              int seed,int episodes,const std::string& pattern,bool moving){
    Model m(model_path);Grid base(map_path),grid=base;Graph graph(m,grid);std::mt19937 rng(seed);
    std::vector<State> candidates;std::ifstream scen(map_path+".scen");std::string line;std::getline(scen,line);
    struct Pair {State s,t;};std::vector<Pair> pairs;
    while(std::getline(scen,line)){std::istringstream f(line);int bucket,W,H,sx,sy,tx,ty;std::string name;double dist;
        if(f>>bucket>>name>>W>>H>>sx>>sy>>tx>>ty>>dist){if(dist>=50 && dist<=220)pairs.push_back({{sy,sx,0},{ty,tx,0}});}}
    Workload w;w.map=map_path;Result found;
    for(int attempt=0;attempt<300;++attempt){State s,t;
        if(!pairs.empty()){auto p=pairs[rng()%pairs.size()];s=p.s;t=p.t;}
        else{s={int(rng()%grid.H),int(rng()%grid.W),0};t={int(rng()%grid.H),int(rng()%grid.W),0};
            auto d=m.metric(s.r-t.r,s.c-t.c);if(d<40000000 || d>180000000)continue;}
        s.h=rng()%m.headings;t.h=rng()%m.headings;if(!grid.free(s.r,s.c)||!grid.free(t.r,t.c))continue;
        Planner p(graph,s,t,false,false);auto r=p.solve();
        if(r.cost<INF && r.prims.size()>=6){w.start=s;w.goal=t;found=std::move(r);break;}}
    if(found.cost>=INF)throw std::runtime_error("Could not sample reachable task");
    State s=w.start;std::set<int> overlay;w.steps.push_back({s,{}});
    for(int ep=1;ep<=episodes;++ep){
        if(moving && !found.prims.empty() && ep%2==0){const auto& p=m.primitives.at(found.prims.front());s.r+=p.dr;s.c+=p.dc;s.h=p.th;}
        Planner ref(graph,s,w.goal,false,false);found=ref.solve();
        std::vector<RC> pathcells;State cur=s;
        for(int pid:found.prims){const auto& p=m.primitives.at(pid);for(auto off:p.trace)pathcells.push_back({cur.r+off.r,cur.c+off.c});cur.r+=p.dr;cur.c+=p.dc;}
        int batch=pattern=="churn"?128:(pattern=="path"?8:4);
        Step step;step.start=s;std::set<int> chosen;
        // Alternate additions and removals without consulting any tested planner.
        for(int j=0;j<batch;++j){RC q;bool selected=false;
            if(!overlay.empty() && (rng()%100 < 40 || found.cost>=INF)){
                auto it=overlay.begin();std::advance(it,rng()%overlay.size());q={*it/grid.W,*it%grid.W};selected=true;
            }else if(pattern=="path" && pathcells.size()>8){q=pathcells[pathcells.size()/5+rng()%(pathcells.size()*3/5)];selected=true;}
            else if(pattern=="local" && !pathcells.empty()){q=pathcells[rng()%pathcells.size()];q.r+=int(rng()%17)-8;q.c+=int(rng()%17)-8;selected=true;}
            if(!selected)q={int(rng()%grid.H),int(rng()%grid.W)};
            if(!grid.inside(q.r,q.c)||!base.free(q.r,q.c)||(q.r==s.r&&q.c==s.c)||(q.r==w.goal.r&&q.c==w.goal.c))continue;
            int cell=q.r*grid.W+q.c;if(!chosen.insert(cell).second)continue;
            int v=!grid.blocked[cell];step.changes.emplace_back(q.r,q.c,v);
            if(v)overlay.insert(cell);else overlay.erase(cell);
        }
        apply(grid,step);w.steps.push_back(step);Planner p(graph,s,w.goal,false,false);found=p.solve();
    }
    save_workload(w,path);std::cout<<"generated "<<path<<" steps="<<w.steps.size()<<'\n';
}

void run(const std::string& model_path,const std::string& workload_path,const std::string& algorithm,bool dump){
#ifdef IMA_SUFFIX
    if(algorithm!="dlite" || model_path.find("_suffix.model")==std::string::npos)
        throw std::runtime_error("Suffix build requires suffix model and dlite algorithm");
#endif
    auto setup0=Clock::now();Model m(model_path);auto w=load_workload(workload_path);Grid grid(w.map);Graph graph(m,grid);
    if(algorithm.find("batch")!=std::string::npos){auto mp=model_path;auto pos=mp.rfind("_lattice.model");
        if(pos==std::string::npos)throw std::runtime_error("Batch evaluation requires lattice model");
        mp.replace(pos,std::string("_lattice.model").size(),"_mesh.model");graph.enable_cache(2,mp);
    }else if(algorithm.find("cached")!=std::string::npos)graph.enable_cache(1);
    bool inc=algorithm.find("astar")==std::string::npos && algorithm!="dijkstra";
    bool rev=algorithm.find("dlite")!=std::string::npos;bool zero=algorithm=="dijkstra";
    Planner p(graph,w.start,w.goal,inc,rev,zero,algorithm.find("scan")!=std::string::npos);
    auto setup_us=std::chrono::duration<double,std::micro>(Clock::now()-setup0).count();
    std::cout<<"episode,cost,total_us,update_us,search_us,extract_us,expanded,updates,edge_checks,cell_checks,pushes,pops,notify_probes,affected,records,heap_entries,cache_origins,changes,setup_us,rss_kib\n";
    for(size_t i=0;i<w.steps.size();++i){graph.st={};const auto& step=w.steps[i];auto t0=Clock::now();
        auto changed=apply(grid,step);graph.invalidate(changed);p.move(step.start);p.notify(changed);auto t1=Clock::now();
        Result r;
        if(!graph.free(p.start)||!graph.free(p.goal))r={};else if(inc)p.repair();else r=p.astar();
        auto t2=Clock::now();if(inc&&graph.free(p.start)&&graph.free(p.goal))r=p.extract_incremental();auto t3=Clock::now();
        p.validate(r);auto us=[](auto a,auto b){return std::chrono::duration<double,std::micro>(b-a).count();};
        const auto& st=graph.st;struct rusage usage{};getrusage(RUSAGE_SELF,&usage);
        std::cout<<i<<','<<(r.cost>=INF?-1:r.cost)<<','<<us(t0,t3)<<','<<us(t0,t1)<<','<<us(t1,t2)<<','<<us(t2,t3)<<','
                 <<st.expanded<<','<<st.updates<<','<<st.edge_checks<<','<<st.cell_checks<<','<<st.pushes<<','<<st.pops<<','
                 <<st.notify_probes<<','<<st.affected<<','<<p.rec.size()<<','<<p.open.size()<<','<<graph.cache.size()<<','<<changed.size()<<','<<(i==0?setup_us:0)<<','<<usage.ru_maxrss<<'\n';
        if(dump){std::cerr<<"PATH "<<i;for(int pid:r.prims)std::cerr<<' '<<pid;std::cerr<<'\n';}
    }
}
int main(int argc,char** argv){try{
    std::unordered_map<std::string,std::string> args;
    for(int i=1;i<argc;++i){std::string k=argv[i];if(k=="--dump")args[k]="1";else{if(i+1>=argc)throw std::runtime_error("Missing argument");args[k]=argv[++i];}}
    auto get=[&](const std::string& k,const std::string& def=""){return args.count(k)?args.at(k):def;};
    if(get("--generate")!="")generate(get("--model"),get("--map"),get("--generate"),std::stoi(get("--seed","0")),std::stoi(get("--episodes","20")),get("--pattern","local"),get("--moving","0")=="1");
    else run(get("--model"),get("--workload"),get("--algorithm","astar"),args.count("--dump"));
    return 0;
}catch(const std::exception& e){std::cerr<<"ERROR: "<<e.what()<<'\n';return 1;}}
