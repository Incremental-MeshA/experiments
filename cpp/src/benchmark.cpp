#include "ima/planners.hpp"
#include <iostream>
#include <random>
#include <sstream>

using namespace ima;

#ifndef IMA_BUILD_FLAGS
#define IMA_BUILD_FLAGS "not recorded by build system"
#endif

static std::vector<std::string> split(const std::string& s) {
    std::vector<std::string> out; std::stringstream stream(s); std::string part;
    while (std::getline(stream,part,',')) out.push_back(part);
    return out;
}
static void csv_string(std::ostream& out,const std::string& s) {
    out<<'"'; for (char c:s) { if (c=='"') out<<'"'; out<<c; } out<<'"';
}
static std::uint64_t path_hash(const Path& p) {
    std::uint64_t h=1469598103934665603ULL;
    for (int id:p.ids) { h^=std::uint32_t(id); h*=1099511628211ULL; }
    return h;
}
static void json_string(std::ostream& out,const std::string& s) {
    out<<'"'; for (char c:s) { if (c=='"'||c=='\\') out<<'\\'; if (c=='\n') out<<"\\n"; else out<<c; } out<<'"';
}

int main(int argc,char** argv) try {
    std::string input="cpp/data/car16_md.txt",output="cpp/results/raw.csv",cohort="all",case_filter;
    std::vector<std::string> methods=METHODS;
    int repeats=3; std::uint64_t limit=3000000,seed=761116;
    bool verify_only=false;
    for (int i=1;i<argc;++i) {
        std::string arg=argv[i];
        auto take=[&]() { require(i+1<argc,"missing value for "+arg); return std::string(argv[++i]); };
        if (arg=="--input") input=take();
        else if (arg=="--output") output=take();
        else if (arg=="--methods") methods=split(take());
        else if (arg=="--cohort") cohort=take();
        else if (arg=="--case") case_filter=take();
        else if (arg=="--repeats") repeats=std::stoi(take());
        else if (arg=="--max-expansions") limit=std::stoull(take());
        else if (arg=="--seed") seed=std::stoull(take());
        else if (arg=="--verify-only") verify_only=true;
        else if (arg=="--help") {
            std::cout<<"mesh_bench --input FILE --output CSV [--methods lba,mpgaa,md_astar] [--cohort all|original|mixed|validation|diagnostic|upstream] [--case SUBSTRING] [--repeats 3] [--seed 761116] [--max-expansions 3000000] [--verify-only]\n";
            return 0;
        } else throw std::runtime_error("unknown option: "+arg);
    }
    require(repeats>0 && repeats<=10000 && limit>0,"invalid repeat count or expansion limit");
    require(!methods.empty() && std::set<std::string>(methods.begin(),methods.end()).size()==methods.size(),"empty or duplicate methods");
    for (const auto& name:methods) require(std::find(METHODS.begin(),METHODS.end(),name)!=METHODS.end(),"unknown method: "+name);
    if (verify_only) repeats=1;
    auto preparation=Clock::now(); Suite suite=read_suite(input); Certificate certificate(suite.model); double preparation_s=seconds(preparation);
    std::vector<const Episode*> cases;
    for (const auto& e:suite.episodes) if ((cohort=="all" || e.cohort==cohort) && (case_filter.empty() || e.id.find(case_filter)!=std::string::npos)) cases.push_back(&e);
    require(!cases.empty(),"no episodes matched");
    std::ifstream existing(output); require(!existing.good(),"output exists; select a new file to avoid mixing measurements"); existing.close();
    std::ifstream existing_metadata(output+".json"); require(!existing_metadata.good(),"metadata exists; select a new output");
    std::ofstream csv(output); require(bool(csv),"cannot create CSV (create its parent directory first)"); csv<<std::setprecision(17);
    csv<<"case,cohort,map,method,repeat,query,category,event,success,cost,time_s,setup_s,expansions,checked_cells,notify_probes,heuristic_pops,certified,backend_calls,activated_cells,deferred_cells,refined_cells,path_primitives,path_hash,suboptimality\n";
    std::mt19937_64 random(seed); std::uint64_t queries=0,runs=0;
    auto wall=Clock::now();
    using Fingerprint=std::tuple<double,std::uint64_t,std::uint64_t,std::uint64_t,std::uint64_t,bool,int,std::uint64_t,std::uint64_t,std::uint64_t,std::uint64_t>;
    std::map<std::tuple<std::string,std::string,int>,Fingerprint> fingerprints;
    for (const auto* episode:cases) {
        const auto& e=*episode;
        for (int repeat=0;repeat<repeats;++repeat) {
            auto order=methods; std::shuffle(order.begin(),order.end(),random);
            for (const auto& method:order) {
                Grid validation=suite.maps[e.map]; const auto& first=e.queries.front();
                auto clock=Clock::now();
                auto planner=make_planner(method,suite.maps[e.map],suite.model,certificate,first.start,first.goal,limit);
                double setup_s=seconds(clock);
                for (std::size_t qi=0;qi<e.queries.size();++qi) {
                    const auto& q=e.queries[qi]; clock=Clock::now();
                    Path p=planner->replan(q.start,q.blocks,q.opens);
                    double time_s=seconds(clock); // includes changes, repair, extraction and retained-path indexing
                    require(!p.stats.capped,"expansion cap: "+e.id+" "+method+" query "+std::to_string(qi));
                    for (auto c:q.blocks) validation.set(c,true);
                    for (auto c:q.opens) validation.set(c,false);
                    require(p.success()==std::isfinite(q.expected),"reachability mismatch: "+e.id+" "+method);
                    if (p.success()) {
                        if (method!="mesh_parall") require(std::abs(p.cost-q.expected)<1e-6,"nonoptimal exact answer: "+e.id+" "+method+" query "+std::to_string(qi));
                        require(p.cost>=q.expected-1e-6,"answer beat reference cost");
                    }
                    validate_path(validation,suite.model,q.start,q.goal,p); // outside timed region; no planner cache access
                    auto hash=path_hash(p); const auto& st=p.stats;
                    Fingerprint fp{p.cost,st.expansions,st.checked_cells,st.notify_probes,st.heuristic_pops,st.certified,st.backend_calls,st.activated_cells,st.deferred_cells,st.refined_cells,hash};
                    auto key=std::make_tuple(e.id,method,int(qi));
                    if (!repeat) fingerprints.emplace(key,fp);
                    else require(fingerprints.at(key)==fp,"nondeterministic repeat: "+e.id+" "+method);
                    csv_string(csv,e.id); csv<<','; csv_string(csv,e.cohort); csv<<','; csv_string(csv,suite.map_names[e.map]); csv<<','; csv_string(csv,method);
                    csv<<','<<repeat<<','<<qi<<','; csv_string(csv,q.category); csv<<','; csv_string(csv,q.event); csv<<','<<p.success()<<',';
                    if (p.success()) csv<<p.cost;
                    csv<<','<<time_s<<','<<(qi==0 ? setup_s : 0)<<','<<st.expansions<<','<<st.checked_cells<<','<<st.notify_probes<<','<<st.heuristic_pops<<','<<st.certified<<','<<st.backend_calls<<','<<st.activated_cells<<','<<st.deferred_cells<<','<<st.refined_cells<<','<<p.ids.size()<<','<<hash<<',';
                    if (p.success() && q.expected>0) csv<<p.cost/q.expected;
                    csv<<'\n'; ++queries;
                }
                csv.flush(); require(bool(csv),"CSV write failed"); ++runs;
            }
        }
        std::cerr<<runs<<" complete runs; "<<e.id<<"; "<<seconds(wall)<<" s\n";
    }
    csv.close();
    std::ofstream meta(output+".json"); require(bool(meta),"cannot create completion metadata");
    meta<<std::setprecision(17)<<"{\n  \"status\": \"passed\",\n  \"language\": \"C++17\",\n  \"compiler\": "; json_string(meta,__VERSION__);
#ifdef NDEBUG
    meta<<",\n  \"ndebug\": true";
#else
    meta<<",\n  \"ndebug\": false";
#endif
#ifdef __FAST_MATH__
    meta<<",\n  \"fast_math\": true";
#else
    meta<<",\n  \"fast_math\": false";
#endif
    meta<<",\n  \"build_flags\": "; json_string(meta,IMA_BUILD_FLAGS);
    meta<<",\n  \"verify_only\": "<<(verify_only ? "true" : "false")<<",\n  \"input\": "; json_string(meta,input);
    meta<<",\n  \"episodes\": "<<cases.size()<<",\n  \"runs\": "<<runs<<",\n  \"queries\": "<<queries<<",\n  \"repeats\": "<<repeats<<",\n  \"seed\": "<<seed<<",\n  \"max_expansions_per_query\": "<<limit<<",\n  \"preparation_s\": "<<preparation_s<<",\n  \"certificate_compile_s\": "<<certificate.compile_s<<",\n  \"certificate_alpha\": "<<certificate.alpha<<",\n  \"certificate_correction\": "<<certificate.correction<<",\n  \"wall_s\": "<<seconds(wall)<<",\n  \"methods\": [";
    for (std::size_t i=0;i<methods.size();++i) { if (i) meta<<','; json_string(meta,methods[i]); }
    meta<<"]\n}\n"; require(bool(meta),"metadata write failed");
    std::cout<<"passed: "<<runs<<" runs, "<<queries<<" validated query calls\n";
    return 0;
} catch (const std::exception& e) { std::cerr<<"error: "<<e.what()<<'\n'; return 1; }
