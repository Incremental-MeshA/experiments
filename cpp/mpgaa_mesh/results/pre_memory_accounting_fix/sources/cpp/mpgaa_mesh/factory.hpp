#pragma once
#include "algorithms.hpp"
#include "../navigation_controls/factory.hpp"

namespace ima::mpgaa_mesh {
inline const std::vector<std::string> methods={"lba","lba_reuse","mpgaa","md_astar","boundary_mesh","octile_reuse",
    "boundary_mpgaa","selective_mpgaa","delta_mpgaa","policy_mpgaa","selective_no_prune","selective_geom"};
inline std::unique_ptr<Planner> make(const std::string& name,const Grid& grid,const Model& m,const Certificate& c,
    const variants::Prepared& prepared,const MeshIndex& mesh,State s,State t,std::uint64_t cap) {
    if(name=="boundary_mpgaa")return std::make_unique<BoundaryMPGAA>(mesh,grid,t,cap);
    if(name=="selective_mpgaa")return std::make_unique<SelectiveMPGAA>(mesh,grid,t,cap);
    if(name=="delta_mpgaa")return std::make_unique<DeltaMPGAA>(mesh,grid,t,cap);
    if(name=="policy_mpgaa")return std::make_unique<PolicyMPGAA>(mesh,grid,t,cap);
    if(name=="selective_no_prune")return std::make_unique<MeshMPGAA>(mesh,grid,t,Mode::Selective,cap,false,true);
    if(name=="selective_geom")return std::make_unique<MeshMPGAA>(mesh,grid,t,Mode::Selective,cap,true,false);
    return navigation_controls::make(name,grid,m,c,prepared,s,t,cap);
}
inline void write_work(std::ostream& out,const Work& w) {
    out<<','<<w.mesh_nodes<<','<<w.bound_evals<<','<<w.pruned_branches<<','<<w.pruned_primitives
       <<','<<w.watch_hits<<','<<w.validity_flips<<','<<w.witness_stops<<','<<w.policy_probes<<','<<w.policy_hits<<','<<w.alternate_uses;
}
inline const char* work_columns="mesh_nodes,bound_evals,pruned_branches,pruned_primitives,watch_hits,validity_flips,witness_stops,policy_probes,policy_hits,alternate_uses";
} // namespace ima::mpgaa_mesh
