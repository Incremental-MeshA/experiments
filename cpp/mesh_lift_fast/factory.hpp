#pragma once
#include "algorithms.hpp"
#include "../mesh_lift/factory.hpp"
#include "new_factory.hpp"

namespace ima::mesh_lift_fast {
struct MeshIndex:mesh_lift::MeshIndex {
    Index compact,raw;
    MeshIndex(const Model& m,const variants::Prepared& p):mesh_lift::MeshIndex(m,p),compact(m),raw(m,false){compile_s+=compact.compile_s+raw.compile_s;}
};
inline const std::vector<std::string> new_methods={"zero_lift","zero_cascade","fast_lift","fast_cascade","fast_all_closed","fast_no_depth","fast_trace","fast_raw_finals","fast_recompute_base","fast_slow_policy"};
inline const std::vector<std::string> methods=[](){auto names=mesh_lift::methods;names.insert(names.end(),new_methods.begin(),new_methods.end());return names;}();
inline std::unique_ptr<Planner> make(const std::string& name,const Grid& grid,const Model& m,const Certificate& cert,const variants::Prepared& p,const MeshIndex& index,State s,State goal,std::uint64_t cap) {
    if(name.rfind("zero_",0)==0 || name.rfind("fast_",0)==0)return make_new(name,grid,goal,cap,index.vertex,index.compact,index.raw);
    return mesh_lift::make(name,grid,m,cert,p,index,s,goal,cap);
}
template<class Previous> inline Work copy_work(const Previous& old) {
    Work result;
#define COPY(field) result.field=old.field;
    COPY(boundary_expansions) COPY(interior_expansions) COPY(heap_pushes) COPY(heap_pops) COPY(contour_steps) COPY(learning_updates) COPY(repair_edges) COPY(repair_heap_pushes) COPY(repair_local_steps) COPY(seed_tests) COPY(watch_inserts) COPY(watch_events) COPY(active_watches) COPY(policy_tests) COPY(policy_hits) COPY(interior_joins) COPY(records) COPY(trace_hash) COPY(terminal_tests) COPY(terminal_prunes) COPY(lift_edges) COPY(lift_writes)
#undef COPY
    return result;
}
inline Work counters(const Planner& p) {
    if(auto* q=dynamic_cast<const LiftMPGAA*>(&p))return q->counters();
    if(auto* q=dynamic_cast<const mesh_lift_zero::LiftMPGAA*>(&p))return copy_work(q->counters());
    return copy_work(mesh_lift::counters(p));
}
inline const std::string work_columns=mesh_lift::work_columns+",fast_base_evaluations,fast_closure_seeds,fast_closure_pushes,fast_terminal_cells";
inline void write_work(std::ostream& out,const Work& w) {
    out<<','<<w.boundary_expansions<<','<<w.interior_expansions<<','<<w.heap_pushes<<','<<w.heap_pops<<','<<w.contour_steps<<','<<w.learning_updates<<','<<w.repair_edges<<','<<w.repair_heap_pushes<<','<<w.repair_local_steps<<','<<w.seed_tests<<','<<w.watch_inserts<<','<<w.watch_events<<','<<w.active_watches<<','<<w.policy_tests<<','<<w.policy_hits<<','<<w.interior_joins<<','<<w.records<<','<<w.trace_hash<<','<<w.terminal_tests<<','<<w.terminal_prunes<<','<<w.lift_edges<<','<<w.lift_writes<<','<<w.base_evaluations<<','<<w.closure_seeds<<','<<w.closure_pushes<<','<<w.terminal_cells;
}
}
