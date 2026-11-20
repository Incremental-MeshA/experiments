// Replay harness derived from cpp/mesh_variants/bench.cpp, SHA256 d1877f9db4ce5721d2a26dd958bd816eced695e1bce42e042453283bcb31e018
// Native harness adapted from cpp/experiments/bench.cpp; base SHA256 ce6ae2a30d499d44d703be29cedf066eaee2b4136e5cbac52830da55da00c0e4
#include "memory.hpp"
#include "ima/planners.hpp"
#include <iostream>
#include <random>
#include <sstream>
#include "dstar_boundary.hpp"
#include "variants.hpp"
#include "factory.hpp"

using namespace ima;
#ifndef IMA_EXPERIMENT_FLAGS
#define IMA_EXPERIMENT_FLAGS "sanitizer"
#endif

namespace {
const std::vector<std::string> all_methods=mpgaa_mesh::methods;
const variants::Prepared* common_variants=nullptr;
const mpgaa_mesh::MeshIndex* common_mesh=nullptr;
void quoted(std::ostream& out,const std::string& s) { out<<'"'; for (char c:s) { if (c=='"') out<<'"'; out<<c; } out<<'"'; }
std::uint64_t hash_path(const Path& p) { std::uint64_t h=1469598103934665603ULL; for (int id:p.ids) { h^=std::uint32_t(id); h*=1099511628211ULL; } return h; }
class Reuse final:public Planner {
    const Model& model; Grid grid; State goal,last; Suffix suffix; std::uint64_t cap; bool no_path=false;
public:
    Reuse(const Model& m,const Grid& g,State t,std::uint64_t limit):model(m),grid(g),goal(t),suffix(m),cap(limit) {}
    Path replan(State s,const std::vector<Cell>& blocks={},const std::vector<Cell>& opens={}) override {
        auto [b,o]=net_changes(grid,blocks,opens); suffix.update(b,o);
        for (auto q:b) grid.set(q,true);
        for (auto q:o) grid.set(q,false);
        std::size_t at=0;
        if (o.empty() && no_path && s==last) { Path p; p.stats.certified=true; return p; }
        if (o.empty() && grid.free(s.cell()) && grid.free(goal.cell()) && suffix.position(s,at)) {
            auto p=suffix.tail(at); p.stats.certified=true; return p;
        }
        auto p=search("lba",grid,model,s,goal,cap); suffix.install(p.stats.capped ? Path{} : p);
        last=s; no_path=!p.success() && !p.stats.capped; return p;
    }
};
std::unique_ptr<Planner> planner(const std::string& name,const Grid& grid,const Model& m,const Certificate& c,State s,State t,std::uint64_t cap) {
    return mpgaa_mesh::make(name,grid,m,c,*common_variants,*common_mesh,s,t,cap);
}
void check(const Grid& g,const Model& m,State s,State t,const Path& p,double expected,const std::string& method) {
    if (p.stats.capped) return;
    require(p.success()==std::isfinite(expected),"reachability mismatch "+method);
    if (p.success()) {
        require(p.cost>=expected-1e-6,"answer below reference "+method);
        if (method!="mesh_parall") require(std::abs(p.cost-expected)<1e-6,"nonoptimal exact answer "+method);
    }
    validate_path(g,m,s,t,p);
}
void server(const Model& m) {
    std::cout<<std::setprecision(17);
    std::string cmd;
    while (std::cin>>cmd && cmd!="quit") {
        require(cmd=="plan","unknown reference command"); int h=0,w=0; State s,t;
        std::cin>>h>>w>>s.i>>s.j>>s.k>>t.i>>t.j>>t.k; require(h>0 && w>0,"bad reference dimensions");
        Grid g(h,w); std::string row;
        for (int i=0;i<h;++i) { std::cin>>row; require(int(row.size())==w,"bad reference row"); for (int j=0;j<w;++j) g.set({i,j},row[j]=='#'); }
        require(bool(std::cin),"truncated reference input");
        auto p=search("lba",g,m,s,t,3000000);
        std::cout<<"{\"cost\":"; if (p.success()) std::cout<<p.cost; else std::cout<<"null";
        std::cout<<",\"capped\":"<<(p.stats.capped?"true":"false")<<",\"ids\":[";
        for (std::size_t k=0;k<p.ids.size();++k) { if (k) std::cout<<','; std::cout<<p.ids[k]; }
        std::cout<<"],\"states\":[";
        for (std::size_t k=0;k<p.states.size();++k) { if (k) std::cout<<','; auto u=p.states[k]; std::cout<<'['<<u.i<<','<<u.j<<','<<u.k<<']'; }
        std::cout<<"]}"<<std::endl;
    }
}
struct Row {
    std::string status="ok";
    double time=0,setup=0,expected=INF,cost=INF,travel=0,sensing=0;
    std::size_t blocks=0,opens=0,revealed=0,known=0,peak=0,retained=0;
    std::uint64_t path_hash=0;
    int planned=1,step=0;
    Stats st;mpgaa_mesh::Work mesh;
    State start,next;
};
void write_row(std::ostream& out,const Episode& e,const std::string& method,int repeat,int q,const Row& r) {
    quoted(out,e.id); out<<','; quoted(out,e.cohort); out<<','; quoted(out,method);
    out<<','<<repeat<<','<<q<<','<<r.step<<','<<r.planned<<','; quoted(out,r.status);
    out<<','<<r.time<<','<<r.setup<<',';
    if (std::isfinite(r.cost)) out<<r.cost;
    out<<','; if (std::isfinite(r.expected)) out<<r.expected;
    out<<','<<r.blocks<<','<<r.opens<<','<<r.revealed<<','<<r.known<<','<<r.travel<<','<<r.sensing<<','
       <<r.st.expansions<<','<<r.st.checked_cells<<','<<r.st.notify_probes<<','<<r.st.heuristic_pops<<','
       <<r.st.certified<<','<<r.st.backend_calls<<','<<r.st.activated_cells<<','<<r.st.deferred_cells<<','<<r.st.refined_cells<<','
       <<r.peak<<','<<r.retained<<','<<r.path_hash<<','<<r.start.i<<','<<r.start.j<<','<<r.start.k<<','<<r.next.i<<','<<r.next.j<<','<<r.next.k;mpgaa_mesh::write_work(out,r.mesh);out<<'\n';
}
std::string fingerprint(const Row& r) {
    std::ostringstream out; out<<std::setprecision(17)<<r.status<<' '<<r.cost<<' '<<r.travel<<' '<<r.known<<' '
        <<r.planned<<' '<<r.st.expansions<<' '<<r.st.checked_cells<<' '<<r.st.notify_probes<<' '<<r.st.heuristic_pops<<' '
        <<r.st.certified<<' '<<r.st.backend_calls<<' '<<r.st.activated_cells<<' '<<r.st.deferred_cells<<' '<<r.st.refined_cells<<' '<<r.path_hash<<' '
        <<r.start.i<<' '<<r.start.j<<' '<<r.start.k<<' '<<r.next.i<<' '<<r.next.j<<' '<<r.next.k;
    mpgaa_mesh::write_work(out,r.mesh);return out.str();
}
}

int main(int argc,char** argv) try {
    std::string input,output,mode="replay",filter; int repeats=3,radius=8,max_steps=160;bool explicit_methods=false;
    std::uint64_t cap=1000000,seed=48101; std::vector<std::string> methods=all_methods;
    for (int i=1;i<argc;++i) {
        std::string a=argv[i]; auto take=[&]() { require(i+1<argc,"missing option value"); return std::string(argv[++i]); };
        if (a=="--input") input=take(); else if (a=="--output") output=take(); else if (a=="--mode") mode=take();
        else if (a=="--repeats") repeats=std::stoi(take()); else if (a=="--radius") radius=std::stoi(take());
        else if (a=="--max-steps") max_steps=std::stoi(take()); else if (a=="--cap") cap=std::stoull(take());
        else if (a=="--seed") seed=std::stoull(take()); else if (a=="--case") filter=take();
        else if (a=="--methods") { explicit_methods=true;methods.clear(); std::istringstream in(take()); std::string s; while (std::getline(in,s,',')) methods.push_back(s); }
        else if (a=="--serve") mode="serve";
        else throw std::runtime_error("unknown option "+a);
    }
    require(!input.empty() && repeats>0 && cap>0 && max_steps>0,"invalid arguments");
    require(mode=="serve" || mode=="replay" || mode=="mission" || mode=="models","unknown mode");
    auto prep=Clock::now(); Suite suite=read_suite(input); const auto& m=suite.model;
    if(!explicit_methods && m.name!="grid8")methods.erase(std::remove(methods.begin(),methods.end(),"octile_reuse"),methods.end());
    if (mode=="serve") { server(m); return 0; }
    auto template_before=allocation_profile::live; allocation_profile::reset_peak();
    variants::Prepared prepared(m);common_variants=&prepared;
    auto variant_peak=allocation_profile::peak-template_before;
    auto index_before=allocation_profile::live;allocation_profile::reset_peak();mpgaa_mesh::MeshIndex mesh(m);common_mesh=&mesh;
    auto index_peak=allocation_profile::peak-index_before,index_retained=allocation_profile::live-index_before;
    auto template_peak=std::max(variant_peak,index_before-template_before+index_peak);
    auto template_retained=allocation_profile::live-template_before;
    if (mode=="models") {
        auto [projections,heuristics]=prepared.audit();std::cout<<std::setprecision(17);
        std::cout<<"{\"projection_checks\":"<<projections<<",\"heuristic_checks\":"<<heuristics
                 <<",\"compile_s\":"<<prepared.compile_s<<",\"heap_retained_bytes\":"<<template_retained
                 <<",\"heap_peak_bytes\":"<<template_peak<<",\"models\":";prepared.json(std::cout);std::cout<<"}\n";return 0;
    }

    require(!output.empty() && !std::ifstream(output).good() && !std::ifstream(output+".json").good(),"output already exists or missing");
    if (mode=="mission") require(radius>=std::max(m.reach_i,m.reach_j),"sensor cannot see a full primitive");
    for (const auto& name:methods) require(std::find(all_methods.begin(),all_methods.end(),name)!=all_methods.end(),"unknown method "+name);
    require(!methods.empty() && std::set<std::string>(methods.begin(),methods.end()).size()==methods.size(),"duplicate/empty methods");
    Certificate cert(m); double prep_s=seconds(prep); auto wall=Clock::now();
    std::ofstream csv(output); require(bool(csv),"cannot open output"); csv<<std::setprecision(17);
    csv<<"case,family,method,repeat,query,step,planned,status,time_s,setup_s,cost,expected,blocks,opens,revealed,known,travel_cost,sensing_s,expansions,checked_cells,notify_probes,heuristic_pops,certified,backend_calls,activated_cells,deferred_cells,refined_cells,peak_heap_bytes,retained_heap_bytes,path_hash,start_i,start_j,start_theta,next_i,next_j,next_theta,"<<mpgaa_mesh::work_columns<<"\n";
    std::map<std::tuple<std::string,std::string,int>,std::string> repeat_check;
    std::mt19937_64 random(seed); std::size_t runs=0,rows=0,caps=0,limits=0;
    for (const auto& e:suite.episodes) {
        if (!filter.empty() && e.id.find(filter)==std::string::npos) continue;
        for (int rep=0;rep<repeats;++rep) {
            auto order=methods; std::shuffle(order.begin(),order.end(),random);
            for (const auto& method:order) {
                const auto& first=e.queries.front(); const Grid& base=suite.maps[e.map];
                Grid belief=mode=="replay" ? base : Grid(base.height,base.width);
                std::vector<std::uint8_t> seen(belief.cells.size());
                auto before=allocation_profile::live; allocation_profile::reset_peak(); auto clock=Clock::now();
                auto p=planner(method,belief,m,cert,first.start,first.goal,cap); double setup_s=seconds(clock);
                std::size_t resident=allocation_profile::live-before,setup_peak=allocation_profile::peak-before;
                auto emit=[&](int q,const Row& r) {
                    auto key=std::make_tuple(e.id,method,q); auto fp=fingerprint(r);
                    if (!rep) repeat_check[key]=fp; else require(repeat_check.at(key)==fp,"repeat mismatch "+e.id+" "+method);
                    write_row(csv,e,method,rep,q,r); ++rows;
                };
                bool stopped=false; State s=first.start; Path current; std::size_t at=0,known=0; double travelled=0;
                int n=mode=="replay" ? int(e.queries.size()) : max_steps+1;
                for (int qi=0;qi<n;++qi) {
                    Row row; row.step=qi; row.setup=qi==0 ? setup_s : 0;
                    row.peak=resident;row.retained=resident;
                    std::vector<Cell> blocks,opens;
                    if (mode=="replay") {
                        const auto& q=e.queries[qi]; s=q.start; row.expected=q.expected; blocks=q.blocks; opens=q.opens;
                    } else {
                        clock=Clock::now();
                        for (int i=std::max(0,s.i-radius);i<=std::min(base.height-1,s.i+radius);++i)
                            for (int j=std::max(0,s.j-radius);j<=std::min(base.width-1,s.j+radius);++j) {
                                std::size_t idx=std::size_t(i)*base.width+j;
                                if (!seen[idx]) { seen[idx]=1; ++known; ++row.revealed; }
                                if (base.cells[idx] && !belief.cells[idx]) blocks.push_back({i,j});
                            }
                        row.sensing=seconds(clock); row.known=known; row.travel=travelled;
                        row.planned=qi==0 || !blocks.empty() || s==first.goal;
                    }
                    row.blocks=blocks.size(); row.opens=opens.size();
                    row.start=s; row.next=s;
                    for (auto q:blocks) belief.set(q,true);
                    for (auto q:opens) belief.set(q,false);
                    if (stopped) { row.status="skipped_after_cap"; row.planned=0; emit(qi,row); continue; }
                    if (row.planned) {
                        before=allocation_profile::live; allocation_profile::reset_peak(); clock=Clock::now();
                        Path answer=p->replan(s,blocks,opens); row.time=seconds(clock);row.mesh=mpgaa_mesh::counters(*p);
                        auto after=allocation_profile::live;
                        row.peak=resident+allocation_profile::peak-before;
                        if(qi==0)row.peak=std::max(row.peak,setup_peak);
                        row.retained=resident+after-before; row.cost=answer.cost; row.st=answer.stats; row.path_hash=hash_path(answer);
                        if (mode=="mission") {
                            auto reference=search("lba",belief,m,s,first.goal,3000000);
                            require(!reference.stats.capped,"mission reference capped"); row.expected=reference.cost;
                        }
                        check(belief,m,s,first.goal,answer,row.expected,method);
                        if (answer.stats.capped) { row.status="capped"; ++caps; stopped=true; }
                        else if (!answer.success()) row.status="no_path";
                        if (mode=="mission") {
                            auto release_before=allocation_profile::live;current=std::move(answer);at=0;
#ifdef IMA_TRACK_ALLOC
                            // Snapshot before constructing require's std::string argument:
                            // argument evaluation may itself allocate tracked memory.
                            const auto release_after=allocation_profile::live;
                            require(release_before>=release_after,"mission move unexpectedly allocated");
                            const auto released=release_before-release_after;
                            require(row.retained>=released,"mission heap accounting underflow");
                            resident=row.retained-released;row.retained=resident;
#else
                            require(row.retained>=release_before-allocation_profile::live,"mission heap accounting underflow");
                            resident=row.retained-(release_before-allocation_profile::live);row.retained=resident;
#endif
                        }
                        else {
                            auto release_before=allocation_profile::live; answer=Path{};
                            resident=row.retained-(release_before-allocation_profile::live);
                        }
                    }
                    if (mode=="mission") {
                        if (!row.planned) row.status="follow";
                        if (stopped || row.status=="no_path") { emit(qi,row); break; }
                        if (s==first.goal) { row.status="goal"; emit(qi,row); break; }
                        if (qi==max_steps) { row.status="step_limit"; ++limits; emit(qi,row); break; }
                        require(at<current.ids.size() && current.states[at]==s,"missing mission suffix");
                        int pid=current.ids[at];
                        auto executed=path_from_ids(m,s,{pid});
                        validate_path(base,m,s,executed.states.back(),executed); // actual truth, next primitive only
                        travelled+=m.primitives[pid].cost; s=executed.states.back(); ++at; row.travel=travelled; row.next=s;
                        if (s==first.goal) { row.status="goal"; emit(qi,row); break; }
                    }
                    emit(qi,row);
                }
                ++runs; csv.flush(); require(bool(csv),"write failed");
            }
        }
        std::cerr<<runs<<" runs; "<<e.id<<"; "<<seconds(wall)<<" s\n";
    }
    require(runs>0,"no cases selected");
    std::ofstream meta(output+".json"); require(bool(meta),"cannot write completion");
    meta<<std::setprecision(17)<<"{\"status\":\"passed\",\"mode\":\""<<mode<<"\",\"runs\":"<<runs<<",\"rows\":"<<rows
        <<",\"capped_queries\":"<<caps<<",\"step_limited_missions\":"<<limits<<",\"repeats\":"<<repeats<<",\"cap\":"<<cap<<",\"radius\":"<<radius
        <<",\"max_steps\":"<<max_steps<<",\"preparation_s\":"<<prep_s<<",\"certificate_s\":"<<cert.compile_s
        <<",\"wall_s\":"<<seconds(wall)<<",\"memory_profile\":"
#ifdef IMA_TRACK_ALLOC
        <<"true"
#else
        <<"false"
#endif
        <<",\"compiler\":\""<<__VERSION__<<"\",\"flags\":\""<<IMA_EXPERIMENT_FLAGS
        <<"\",\"mesh_index_compile_s\":"<<mesh.compile_s<<",\"mesh_index_nodes\":"<<mesh.nodes()<<",\"mesh_index_heap_retained_bytes\":"<<index_retained
        <<",\"mesh_index_heap_peak_bytes\":"<<index_peak<<",\"variant_compile_s\":"<<prepared.compile_s<<",\"variant_model_heap_retained_bytes\":"<<template_retained
        <<",\"variant_model_heap_peak_bytes\":"<<template_peak<<",\"variant_models\":";prepared.json(meta);meta<<"}\n";
    std::cout<<"passed "<<runs<<" runs, "<<rows<<" rows, "<<caps<<" capped queries\n";
    return 0;
} catch (const std::exception& e) { std::cerr<<"error: "<<e.what()<<'\n'; return 1; }
