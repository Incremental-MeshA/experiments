#pragma once
#include "new_factory.hpp"
namespace ima::mesh_lift_fast {
struct MeshIndex {
    mesh_vertex::Index vertex;Index compact,raw;
    MeshIndex(const Model& m,const variants::Prepared& p):vertex(m,p),compact(m),raw(m,false){}
};
inline std::unique_ptr<Planner> make(const std::string& name,const Grid& grid,const Model&,const Certificate&,const variants::Prepared&,const MeshIndex& index,State,State goal,std::uint64_t cap){return make_new(name,grid,goal,cap,index.vertex,index.compact,index.raw);}
inline Work counters(const Planner& p) {
    if(auto* q=dynamic_cast<const LiftMPGAA*>(&p))return q->counters();
    const auto w=dynamic_cast<const mesh_lift_zero::LiftMPGAA&>(p).counters();Work result;
#define COPY(field) result.field=w.field;
    COPY(boundary_expansions) COPY(interior_expansions) COPY(heap_pushes) COPY(heap_pops) COPY(contour_steps) COPY(learning_updates) COPY(repair_edges) COPY(repair_heap_pushes) COPY(repair_local_steps) COPY(seed_tests) COPY(watch_inserts) COPY(watch_events) COPY(active_watches) COPY(policy_tests) COPY(policy_hits) COPY(interior_joins) COPY(records) COPY(trace_hash) COPY(terminal_tests) COPY(terminal_prunes) COPY(lift_edges) COPY(lift_writes)
#undef COPY
    return result;
}
}
