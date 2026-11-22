// Navigation harness derived from cpp/navigation_sweeps/bench.cpp, SHA256 01dbbe2b3d62e2967631694b0a5c95198bd7b6fe32a5b5be56484b52d6859f1c
#include "memory.hpp"
#include "factory.hpp"
#include "visibility.hpp"
#include "environment.hpp"
#include <iostream>
#include <random>
#include <sstream>

using namespace ima;
namespace nav=ima::navigation;
namespace hybrid=ima::mesh_lift_fast;
#ifndef NAV_FLAGS
#define NAV_FLAGS "sanitizer"
#endif
namespace {
void quote(std::ostream& out,const std::string& value){out<<'"';for(char c:value){if(c=='"')out<<'"';out<<c;}out<<'"';}
void finite(std::ostream& out,double value){if(std::isfinite(value))out<<value;}
std::uint64_t path_hash(const Path& p){std::uint64_t h=1469598103934665603ULL;for(int id:p.ids){h^=std::uint32_t(id);h*=1099511628211ULL;}return h;}
void add(Stats& a,const Stats& b){a.expansions+=b.expansions;a.checked_cells+=b.checked_cells;a.notify_probes+=b.notify_probes;a.heuristic_pops+=b.heuristic_pops;a.backend_calls+=b.backend_calls;a.activated_cells+=b.activated_cells;a.refined_cells+=b.refined_cells;a.certified=a.certified||b.certified;}
void accounting(std::size_t& resident,std::size_t before,std::size_t after){
    if(after>=before)resident+=after-before;else{require(resident>=before-after,"algorithm heap accounting underflow");resident-=before-after;}
}
struct Run {
    std::string status;double setup=0,planner=0,initial=0,repair=0,sensing=0,reference=0,travel=0;
    int moves=0,plans=0,phases=0,clamped=0;std::size_t requested=0,actual=0,observed=0,probes=0,newly=0,peak=0,retained=0,certified=0;
    Stats total,online;hybrid::Work mesh_work,online_mesh_work;
    std::uint64_t trajectory=1469598103934665603ULL;
};
std::string fingerprint(const Run& r,const nav::World& w){
    std::ostringstream s;s<<std::setprecision(17)<<r.status<<' '<<r.travel<<' '<<r.moves<<' '<<r.plans<<' '<<r.phases<<' '<<r.clamped<<' '<<r.requested<<' '<<r.actual<<' '<<r.observed<<' '<<r.probes<<' '<<r.newly<<' '<<r.certified<<' '<<r.trajectory<<' '<<w.world_hash<<' '<<w.belief_hash<<' '<<w.known<<' '<<w.mismatch;
    for(const auto* st:{&r.total,&r.online})s<<' '<<st->expansions<<' '<<st->checked_cells<<' '<<st->notify_probes<<' '<<st->heuristic_pops<<' '<<st->backend_calls<<' '<<st->activated_cells<<' '<<st->refined_cells;
    hybrid::write_work(s,r.mesh_work);hybrid::write_work(s,r.online_mesh_work);return s.str();
}
}

int main(int argc,char** argv)try{
    std::string input,spec_file,visibility_file,output,filter,build_visibility;int repeats_override=0,max_depth=64;bool anchors_only=false,explicit_methods=false;
    std::uint64_t cap=1000000;auto names=hybrid::methods;
    for(int i=1;i<argc;++i){std::string a=argv[i];auto take=[&](){require(i+1<argc,"missing option");return std::string(argv[++i]);};
        if(a=="--input")input=take();else if(a=="--specs")spec_file=take();else if(a=="--visibility")visibility_file=take();
        else if(a=="--output")output=take();else if(a=="--case")filter=take();else if(a=="--cap")cap=std::stoull(take());
        else if(a=="--repeats")repeats_override=std::stoi(take());else if(a=="--anchors-only")anchors_only=true;else if(a=="--build-visibility")build_visibility=take();else if(a=="--max-depth")max_depth=std::stoi(take());
        else if(a=="--methods"){explicit_methods=true;names.clear();std::istringstream ss(take());std::string v;while(std::getline(ss,v,','))names.push_back(v);}
        else throw std::runtime_error("unknown option "+a);
    }
    require(!input.empty() && cap>0,"missing input/invalid cap");auto prep=Clock::now();auto suite=read_suite(input);const auto& model=suite.model;
    if(!explicit_methods && model.name!="grid8")names.erase(std::remove(names.begin(),names.end(),"octile_reuse"),names.end());
    if(!build_visibility.empty()){auto visibility=nav::Visibility::compile(model,max_depth);visibility.write(build_visibility);std::cout<<"visibility compiled in "<<visibility.compilation_s<<" s\n";return 0;}
    require(!spec_file.empty() && !output.empty(),"missing output/specifications");
    for(auto suffix:{"_runs.csv","_calls.csv","_traces.csv",".json"})require(!std::ifstream(output+suffix).good(),"existing output");
    auto specs=nav::read_specs(spec_file);nav::Visibility visibility;if(!visibility_file.empty()){visibility=nav::Visibility::read(visibility_file);require(visibility.headings==model.headings,"visibility/model mismatch");}
    for(auto& name:names)require(std::find(hybrid::methods.begin(),hybrid::methods.end(),name)!=hybrid::methods.end(),"unknown method");
    require(!names.empty() && std::set<std::string>(names.begin(),names.end()).size()==names.size(),"empty/duplicate methods");
    variants::Prepared prepared(model);Certificate certificate(model);
    auto index_before=allocation_profile::live;allocation_profile::reset_peak();hybrid::MeshIndex mesh(model,prepared);
    auto index_peak=allocation_profile::peak-index_before,index_retained=allocation_profile::live-index_before;
    double preparation=seconds(prep);auto wall=Clock::now();
    std::ofstream runs(output+"_runs.csv"),calls(output+"_calls.csv"),traces(output+"_traces.csv");require(bool(runs)&&bool(calls)&&bool(traces),"cannot open outputs");
    runs<<std::setprecision(17);calls<<std::setprecision(17);traces<<std::setprecision(17);
    runs<<"case,method,repeat,kind,status,setup_s,planner_s,initial_s,repair_s,sensing_s,reference_s,moves,plans,phases,clamped_phases,requested_changes,actual_changes,observed_changes,observation_probes,newly_seen,known_cells,belief_mismatches,travel_cost,initial_optimum,peak_heap_bytes,retained_heap_bytes,certified,expansions,checked_cells,notify_probes,heuristic_pops,backend_calls,activated_cells,refined_cells,online_expansions,online_checked_cells,online_notify_probes,online_heuristic_pops,online_backend_calls,online_activated_cells,online_refined_cells,world_hash,belief_hash,fingerprint,"<<hybrid::work_columns<<"\n";
    calls<<"case,method,repeat,kind,step,query,planned,status,time_s,setup_s,sensing_s,reference_s,cost,expected,travel_cost,phase,k,n,radius,cr,global_changes,blocks,opens,observed_cells,newly_seen,known_cells,belief_mismatches,world_hash,belief_hash,expansions,checked_cells,notify_probes,heuristic_pops,backend_calls,certified,activated_cells,deferred_cells,refined_cells,peak_heap_bytes,retained_heap_bytes,path_hash,start_i,start_j,start_theta,truth_cost,"<<hybrid::work_columns<<"\n";
    traces<<"case,method,repeat,step,start_i,start_j,start_theta,pid,next_i,next_j,next_theta,travel_cost,phase,known_cells,status\n";
    std::map<std::pair<std::string,std::string>,std::string> expected;std::size_t run_count=0,call_count=0,cap_count=0;
    for(auto& episode:suite.episodes){
        if(!specs.count(episode.id))continue;
        if(!filter.empty() && episode.id.find(filter)==std::string::npos)continue;
        const auto& spec=specs.at(episode.id);if(anchors_only && spec.repeats!=3)continue;
        const auto& first=episode.queries.front();const auto& base=suite.maps[episode.map];
        require(first.start!=first.goal,"zero-length initial mission");
        if(spec.kind=="unknown")require(spec.radius>=std::max(model.reach_i,model.reach_j),"static sensor cannot see a whole primitive");
        if(spec.kind=="dynamic")require(visibility.runs.count({first.start.k,spec.n}),"missing visibility depth");
        nav::Calendar calendar{base.cells.size(),spec.seed,{}};int repeats=repeats_override?repeats_override:spec.repeats;
        for(int rep=0;rep<repeats;++rep){
            auto order=names;std::mt19937_64 rng(mix(spec.seed^mix(std::uint64_t(rep)+0x1289)));std::shuffle(order.begin(),order.end(),rng);
            for(const auto& name:order){
                nav::World world(base,spec.kind=="unknown");State s=first.start;Run result;Path current;std::size_t at=0,resident=0,pending_global=0;
                auto before=allocation_profile::live;allocation_profile::reset_peak();auto clock=Clock::now();
                auto p=hybrid::make(name,world.belief,model,certificate,prepared,mesh,s,first.goal,cap);result.setup=seconds(clock);
                accounting(resident,before,allocation_profile::live);result.peak=allocation_profile::peak-before;result.retained=resident;
                for(int step=0;step<spec.max_moves;++step){
                    if(spec.kind=="dynamic" && step && step%spec.k==0){
                        auto event=world.change(calendar,++result.phases,spec.cr,s.cell(),first.goal.cell());
                        result.requested+=2*event.requested_half;result.actual+=2*event.actual_half;result.clamped+=event.clamped;pending_global+=2*event.actual_half;
                    }
                    clock=Clock::now();auto observation=spec.kind=="unknown" ? world.square(s,spec.radius) : world.stencil(s,visibility.runs.at({s.k,spec.n}));double sensing=seconds(clock);
                    result.sensing+=sensing;result.observed+=observation.blocks.size()+observation.opens.size();result.probes+=observation.probes;result.newly+=observation.newly;
                    bool planned=step==0 || !observation.blocks.empty() || !observation.opens.empty();
                    double elapsed=0,reference_s=0,expected_cost=INF,answer_cost=INF,truth_cost=INF;Stats stats;hybrid::Work mesh_work;std::uint64_t hash=0;std::size_t peak=resident;
                    std::string status=planned?"ok":"follow";
                    if(planned){
                        before=allocation_profile::live;allocation_profile::reset_peak();clock=Clock::now();
                        Path answer=p->replan(s,observation.blocks,observation.opens);elapsed=seconds(clock);mesh_work=hybrid::counters(*p);result.mesh_work.add(mesh_work);if(step)result.online_mesh_work.add(mesh_work);
                        peak=resident+allocation_profile::peak-before;accounting(resident,before,allocation_profile::live);
                        result.peak=std::max(result.peak,peak);stats=answer.stats;answer_cost=answer.cost;hash=path_hash(answer);
                        result.planner+=elapsed;if(!step)result.initial=elapsed;else{result.repair+=elapsed;add(result.online,stats);}add(result.total,stats);result.certified+=stats.certified;++result.plans;
                        clock=Clock::now();{
                            auto reference=search("lba",world.belief,model,s,first.goal,3000000);require(!reference.stats.capped,"reference capped");expected_cost=reference.cost;
                            if(!answer.stats.capped){require(answer.success()==reference.success(),"reachability mismatch "+name);
                                if(answer.success()){require(answer.cost>=reference.cost-1e-6,"below reference "+name);if(name!="mesh_parall")require(std::abs(answer.cost-reference.cost)<1e-6,"nonoptimal "+name);}
                                validate_path(world.belief,model,s,first.goal,answer);
                            }
                            if(!answer.success() && !answer.stats.capped){auto actual=search("lba",world.truth,model,s,first.goal,3000000);require(!actual.stats.capped,"truth reference capped");truth_cost=actual.cost;}
                        }reference_s=seconds(clock);result.reference+=reference_s;
                        before=allocation_profile::live;current=std::move(answer);at=0;accounting(resident,before,allocation_profile::live);
                        if(stats.capped){status="capped";result.status=status;++cap_count;}
                        else if(!current.success()){status="no_path";result.status=status;}
                    }
                    result.retained=resident;
                    bool terminal=!result.status.empty();
                    if(planned || terminal){
                        quote(calls,episode.id);calls<<',';quote(calls,name);calls<<','<<rep<<','<<spec.kind<<','<<step<<','<<result.plans-1<<','<<planned<<','<<status<<','<<elapsed<<','<<(step?0:result.setup)<<','<<sensing<<','<<reference_s<<',';finite(calls,answer_cost);calls<<',';finite(calls,expected_cost);
                        calls<<','<<result.travel<<','<<result.phases<<','<<spec.k<<','<<spec.n<<','<<spec.radius<<','<<spec.cr<<','<<pending_global<<','<<observation.blocks.size()<<','<<observation.opens.size()<<','<<observation.probes<<','<<observation.newly<<','<<world.known<<','<<world.mismatch<<','<<world.world_hash<<','<<world.belief_hash<<','<<stats.expansions<<','<<stats.checked_cells<<','<<stats.notify_probes<<','<<stats.heuristic_pops<<','<<stats.backend_calls<<','<<stats.certified<<','<<stats.activated_cells<<','<<stats.deferred_cells<<','<<stats.refined_cells<<','<<peak<<','<<resident<<','<<hash<<','<<s.i<<','<<s.j<<','<<s.k<<',';finite(calls,truth_cost);hybrid::write_work(calls,mesh_work);calls<<'\n';++call_count;pending_global=0;
                    }
                    if(terminal)break;
                    require(at<current.ids.size() && current.states[at]==s,"missing path suffix");int pid=current.ids[at];const auto& primitive=model.primitives[pid];
                    for(auto off:primitive.cells){Cell q{s.i+off.i,s.j+off.j};require(world.truth.free(q),"executed primitive hit truth obstacle");require(world.belief.free(q) && world.seen[world.index(q)],"executed primitive was not observed");}
                    State next=model.head(s,pid);result.travel+=primitive.cost;++at;++result.moves;
                    result.trajectory^=std::uint32_t(pid);result.trajectory*=1099511628211ULL;
                    if(next==first.goal)result.status="goal";
                    if(spec.trace && !rep){quote(traces,episode.id);traces<<',';quote(traces,name);traces<<','<<rep<<','<<step<<','<<s.i<<','<<s.j<<','<<s.k<<','<<pid<<','<<next.i<<','<<next.j<<','<<next.k<<','<<result.travel<<','<<result.phases<<','<<world.known<<','<<(result.status.empty()?"move":result.status)<<'\n';}
                    s=next;if(!result.status.empty())break;
                }
                if(result.status.empty())result.status="step_limit";
                auto signature=fingerprint(result,world);auto key=std::make_pair(episode.id,name);
                if(!rep)expected[key]=signature;else require(expected.at(key)==signature,"non-repeatable navigation "+episode.id+" "+name);
                quote(runs,episode.id);runs<<',';quote(runs,name);runs<<','<<rep<<','<<spec.kind<<','<<result.status<<','<<result.setup<<','<<result.planner<<','<<result.initial<<','<<result.repair<<','<<result.sensing<<','<<result.reference<<','<<result.moves<<','<<result.plans<<','<<result.phases<<','<<result.clamped<<','<<result.requested<<','<<result.actual<<','<<result.observed<<','<<result.probes<<','<<result.newly<<','<<world.known<<','<<world.mismatch<<','<<result.travel<<',';finite(runs,first.expected);
                runs<<','<<result.peak<<','<<result.retained<<','<<result.certified;
                for(const auto* st:{&result.total,&result.online})runs<<','<<st->expansions<<','<<st->checked_cells<<','<<st->notify_probes<<','<<st->heuristic_pops<<','<<st->backend_calls<<','<<st->activated_cells<<','<<st->refined_cells;
                runs<<','<<world.world_hash<<','<<world.belief_hash<<',';quote(runs,signature);hybrid::write_work(runs,result.mesh_work);runs<<'\n';++run_count;runs.flush();calls.flush();traces.flush();
            }
        }
        std::cerr<<run_count<<" runs; "<<episode.id<<"; "<<seconds(wall)<<" s\n";
    }
    require(run_count>0,"no selected scenarios");std::ofstream meta(output+".json");
    meta<<std::setprecision(17)<<"{\"status\":\"passed\",\"runs\":"<<run_count<<",\"calls\":"<<call_count<<",\"caps\":"<<cap_count<<",\"wall_s\":"<<seconds(wall)<<",\"preparation_s\":"<<preparation<<",\"cap\":"<<cap<<",\"memory_profile\":"
#ifdef IMA_TRACK_ALLOC
        <<"true"
#else
        <<"false"
#endif
        <<",\"compiler\":\""<<__VERSION__<<"\",\"flags\":\""<<NAV_FLAGS<<"\",\"mesh_index_compile_s\":"<<mesh.compile_s<<",\"mesh_index_nodes\":"<<mesh.nodes()
        <<",\"mesh_index_heap_retained_bytes\":"<<index_retained<<",\"mesh_index_heap_peak_bytes\":"<<index_peak<<"}\n";
    std::cout<<"passed "<<run_count<<" navigation runs; "<<cap_count<<" query caps\n";return 0;
}catch(const std::exception& e){std::cerr<<"error: "<<e.what()<<'\n';return 1;}
