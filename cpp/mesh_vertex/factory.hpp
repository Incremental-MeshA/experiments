#pragma once
#include "algorithms.hpp"
#include "../mesh_symmetric/factory.hpp"
namespace ima::mesh_vertex {
struct MeshIndex:mesh_symmetric::MeshIndex {
    Index vertex;
    MeshIndex(const Model& m,const variants::Prepared& p):mesh_symmetric::MeshIndex(m),vertex(m,p){compile_s+=vertex.compile_s;}
    std::size_t nodes() const{return vertex.graph.nodes.size();}
};
inline const std::vector<std::string> native_methods={"mesh_mpgaa","trigger_mesh","cascade_mesh","cascade_scan","cascade_heap","mesh_astar","contour_only"};
inline const std::vector<std::string> methods=[](){auto n=native_methods;for(auto s:{"lba_reuse","mesha","mpgaa","batch_mpgaa","md_astar","boundary_mesh","conditional_dstar","cmesh_dstar","octile_reuse"})n.emplace_back(s);return n;}();
inline std::unique_ptr<Planner> make(const std::string& name,const Grid& grid,const Model& m,const Certificate& c,const variants::Prepared& p,const MeshIndex& index,State s,State t,std::uint64_t cap) {
    if(std::find(native_methods.begin(),native_methods.end(),name)!=native_methods.end())
        return std::make_unique<MeshMPGAA>(index.vertex,grid,t,cap,name=="trigger_mesh" || name=="cascade_mesh" || name=="cascade_heap" || name=="contour_only",name=="cascade_mesh" || name=="cascade_scan" || name=="contour_only",name=="cascade_mesh" || name=="cascade_scan" || name=="cascade_heap",name!="mesh_astar",name!="mesh_astar");
    return mesh_symmetric::make(name,grid,m,c,p,index,s,t,cap);
}
inline Work counters(const Planner& p){auto* q=dynamic_cast<const MeshMPGAA*>(&p);return q?q->counters():Work{};}
inline const std::string work_columns="mv_boundary_expansions,mv_interior_expansions,mv_heap_pushes,mv_heap_pops,mv_contour_steps,mv_learning_updates,mv_repair_edges,mv_repair_heap_pushes,mv_repair_local_steps,mv_seed_tests,mv_watch_inserts,mv_watch_events,mv_active_watches,mv_policy_tests,mv_policy_hits,mv_interior_joins,mv_records,mv_trace_hash";
inline void write_work(std::ostream& out,const Work& w) {
    out<<','<<w.boundary_expansions<<','<<w.interior_expansions<<','<<w.heap_pushes<<','<<w.heap_pops<<','<<w.contour_steps<<','<<w.learning_updates<<','<<w.repair_edges<<','<<w.repair_heap_pushes<<','<<w.repair_local_steps<<','<<w.seed_tests<<','<<w.watch_inserts<<','<<w.watch_events<<','<<w.active_watches<<','<<w.policy_tests<<','<<w.policy_hits<<','<<w.interior_joins<<','<<w.records<<','<<w.trace_hash;
}
}
