#include "ima/planners.hpp"
#include <iostream>
#include <random>

using namespace ima;

// Deliberately independent: no planner, graph adapter, edge cache or heuristic.
static double oracle(const Grid& grid,const Model& model,State s,State t) {
    if (!grid.free(s.cell()) || !grid.free(t.cell())) return INF;
    using Item=std::pair<double,State>;
    std::priority_queue<Item,std::vector<Item>,std::greater<Item>> open;
    StateMap<double> distance; distance[s]=0; open.push({0,s});
    while (!open.empty()) {
        auto [g,u]=open.top(); open.pop();
        if (g!=value(distance,u)) continue;
        if (u==t) return g;
        for (const auto& p:model.primitives) {
            if (p.start!=u.k) continue;
            bool free=true;
            for (std::size_t k=1;k<p.cells.size();++k) {
                Cell q{u.i+p.cells[k].i,u.j+p.cells[k].j};
                if (!grid.inside(q) || grid.cells[std::size_t(q.i)*grid.width+q.j]) { free=false; break; }
            }
            if (!free) continue;
            State v{u.i+p.di,u.j+p.dj,p.end}; double candidate=g+p.cost;
            if (candidate<value(distance,v)) { distance[v]=candidate; open.push({candidate,v}); }
        }
    }
    return INF;
}
static std::uint64_t comparisons=0,snapshots=0;

static std::vector<std::map<std::string,Path>> episode(const Model& m,Grid grid,State s,State t,const std::vector<Query>& queries,bool endpoints_free=true) {
    Certificate cert(m); std::map<std::string,std::unique_ptr<Planner>> planners;
    for (const auto& name:METHODS) if (endpoints_free || name.find("dstar_")!=0) planners[name]=make_planner(name,grid,m,cert,s,t);
    std::vector<std::map<std::string,Path>> result;
    for (std::size_t k=0;k<queries.size();++k) {
        const auto& q=queries[k];
        for (auto c:q.blocks) grid.set(c,true);
        for (auto c:q.opens) grid.set(c,false);
        double expected=oracle(grid,m,q.start,t); ++snapshots;
        std::map<std::string,Path> answers;
        for (auto& [name,planner]:planners) {
            Path p=planner->replan(q.start,q.blocks,q.opens);
            require(!p.stats.capped,name+" capped in independent selfcheck");
            require(p.success()==std::isfinite(expected),name+" reachability mismatch at query "+std::to_string(k));
            if (p.success()) {
                require(p.cost>=expected-1e-6,name+" undercut independent oracle");
                if (name!="mesh_parall") require(std::abs(p.cost-expected)<1e-6,name+" cost mismatch at query "+std::to_string(k));
            }
            validate_path(grid,m,q.start,t,p); ++comparisons;
            if (auto* pg=dynamic_cast<MPGAA*>(planner.get())) pg->audit();
            if (auto* md=dynamic_cast<MeshDeferred*>(planner.get())) md->audit();
            answers[name]=std::move(p);
        }
        result.push_back(std::move(answers));
    }
    return result;
}
static Query query(State s,std::vector<Cell> blocks={},std::vector<Cell> opens={}) {
    Query q; q.start=s; q.blocks=std::move(blocks); q.opens=std::move(opens); return q;
}
static void algebra(const Model& m) {
    Certificate c(m); double max_cost=0; std::size_t max_cells=0;
    for (const auto& p:m.primitives) { max_cost=std::max(max_cost,p.cost); max_cells=std::max(max_cells,p.cells.size()); }
    double margin=EPS*(1+max_cost+double(max_cells));
    for (int a=0;a<8;++a) for (int b=0;b<8;++b) {
        double direct=INF; auto [ai,aj]=c.directions[a]; auto [bi,bj]=c.directions[b];
        for (const auto& p:m.primitives) for (auto d:p.cells)
            direct=std::min(direct,p.cost-c.alpha*(ai*d.i+aj*d.j+bi*(p.di-d.i)+bj*(p.dj-d.j)));
        require(std::abs(c.mu[a][b]+margin-direct)<1e-8,"mesh coefficient differs from flat enumeration");
    }
    std::mt19937 random(761113);
    auto cell=[&]() { return Cell{int(random()%81)-40,int(random()%81)-40}; };
    for (int k=0;k<128;++k) {
        Cell s=cell(),t=cell(),q=cell(); double exact=INF;
        for (const auto& p:m.primitives) for (auto d:p.cells)
            exact=std::min(exact,c.distance(s,{q.i-d.i,q.j-d.j})+p.cost+c.distance({q.i-d.i+p.di,q.j-d.j+p.dj},t));
        double scalar=c.bound(s,t,q),full=c.bound(s,t,q,true);
        require(scalar<=full+1e-9 && full<=exact+1e-8,"inadmissible cell certificate");
    }
}
static Model toy_model() {
    Model m; m.name="toy"; m.headings=1; m.initial={0}; m.configs.resize(1); m.configs[0].theta=0;
    for (Cell d:std::vector<Cell>{{0,1},{1,0},{0,-1},{-1,0}}) {
        int pid=int(m.primitives.size()); m.primitives.push_back({0,0,d.i,d.j,1,{{0,0},d}});
        m.configs[0].edges.push_back({d.i,d.j,0,1,pid}); m.configs[0].finals.push_back({d.i,d.j,0,1});
    }
    m.prepare(); return m;
}

int main(int argc,char** argv) try {
    require(argc>=2,"usage: mesh_tests car16_md.txt [legacy8.txt]");
    for (int arg=1;arg<argc;++arg) {
        Model m=read_suite(argv[arg]).model; algebra(m); Grid empty(26,30);
        for (int heading=0;heading<m.headings;++heading) {
            State s{12,12,heading}; int pid=m.by_start[heading].front(); State t=m.head(s,pid);
            episode(m,empty,s,t,{query(s)});
        }
        State s{12,4,0},t{12,25,0}; Grid wall=empty;
        for (int i=0;i<wall.height;++i) wall.set({i,15},true);
        episode(m,wall,s,t,{query(s),query(s,{},{{12,15}}),query({12,5,0},{{12,15}}),query(s,{},{{12,15}}),query(s,{},{{12,15}})});
        std::mt19937 random(76116);
        for (int seed=0;seed<4;++seed) {
            Grid grid(22,28); std::vector<Query> steps{query(s)};
            for (int k=0;k<10;++k) {
                Cell c{2+int(random()%18),7+int(random()%15)}; State here=k%3==0 ? State{12,5,0} : s;
                steps.push_back(k%2==0 ? query(here,{c}) : query(here,{}, {c}));
            }
            episode(m,grid,s,t,steps);
        }
        episode(m,empty,s,t,{query(s),query(s,{s.cell()}),query(s,{}, {s.cell()}),query(s,{t.cell()}),query(s,{}, {t.cell()})},false);
        // Every public planner rejects inconsistent/out-of-bounds edit batches.
        Certificate cert(m);
        for (const auto& name:METHODS) {
            auto p=make_planner(name,empty,m,cert,s,t);
            bool caught=false; try { p->replan(s,{{1,1}},{{1,1}}); } catch (const std::runtime_error&) { caught=true; }
            require(caught,name+" accepted contradictory edits");
            caught=false; try { p->replan(s,{{-1,0}}); } catch (const std::runtime_error&) { caught=true; }
            require(caught,name+" accepted outside edits");
            Path answer=p->replan(s); require(answer.success(),"invalid edits mutated the map");
            auto capped=make_planner(name,empty,m,cert,s,t,0)->replan(s);
            require(capped.stats.capped && !capped.success(),"cap confused with no path");
        }
        std::cout<<"verified "<<m.name<<"; "<<comparisons<<" oracle comparisons\n";
    }
    Model toy=toy_model(); algebra(toy); Grid grid(12,18);
    std::fill(grid.cells.begin(),grid.cells.end(),1);
    for (int row:{2,5,10}) for (int col=2;col<=15;++col) grid.set({row,col},false);
    for (int col:{2,15}) for (int row=2;row<=10;++row) grid.set({row,col},false);
    grid.set({2,8},true); State s{5,2,0},t{5,15,0};
    auto results=episode(toy,grid,s,t,{query(s),query(s,{},{{2,8}}),query(s,{{5,8}})});
    require(results[0].at("md_astar").cost==13 && results[1].at("md_astar").cost==13 && results[2].at("md_astar").cost==19,"reactivation counterexample cost");
    require(results[1].at("md_astar").stats.certified && results[2].at("md_astar").stats.backend_calls==2,"MD-A* did not reactivate old opening with two calls");
    std::vector<Query> history{query(s)};
    for (int i=0;i<160;++i) {
        State here=i%4<2 ? State{5,3,0} : s;
        history.push_back(i%2 ? query(here,{},{{10,7}}) : query(here,{{10,7}}));
    }
    episode(toy,Grid(12,18),s,t,history);
    std::cout<<"passed: "<<snapshots<<" independent Dijkstra snapshots, "<<comparisons<<" comparisons; 64 coefficients and 128 bound triples per model\n";
    return 0;
} catch (const std::exception& e) { std::cerr<<"selfcheck failed: "<<e.what()<<'\n'; return 1; }
