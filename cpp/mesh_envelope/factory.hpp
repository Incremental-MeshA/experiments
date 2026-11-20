#pragma once
#include "circuit.hpp"
namespace ima::mesh_envelope {
inline const std::vector<std::string> methods=[](){auto v=mpgaa_lazy::methods;
    for(const auto* name:{"mesh_cold","mesh_reuse","cut_mesh","envelope_mesh","dual_mesh","lattice_envelope","circuit_mesh",
                          "dstar_lattice","dstar_mesh","cmesh_dstar","suffix_mesh","mesha"})
        if(std::find(v.begin(),v.end(),name)==v.end())v.emplace_back(name);
    return v;}();
inline std::unique_ptr<Planner> make(const std::string& name,const Grid& grid,const Model& m,const Certificate& c,
    const variants::Prepared& prepared,const MeshIndex& mesh,State s,State t,std::uint64_t cap) {
    if(name=="circuit_mesh")return std::make_unique<Circuit>(mesh,grid,s,t,cap);
    if(name=="mesh_cold" || name=="mesh_reuse" || name=="cut_mesh" || name=="envelope_mesh" || name=="dual_mesh" || name=="lattice_envelope")
        return std::make_unique<Envelope>(mesh,grid,t,name,cap);
    return mpgaa_lazy::make(name,grid,m,c,prepared,mesh,s,t,cap);
}
inline Work counters(const Planner& planner) {
    if(const auto* p=dynamic_cast<const Envelope*>(&planner))return p->counters();
    if(const auto* p=dynamic_cast<const Circuit*>(&planner))return p->counters();
    Work w;static_cast<mpgaa_lazy::Work&>(w)=mpgaa_lazy::counters(planner);return w;
}
inline void write_work(std::ostream& out,const Work& w) {
    mpgaa_lazy::write_work(out,w);
    out<<','<<w.envelope_hits<<','<<w.envelope_builds<<','<<w.envelope_added<<','<<w.guard_installs<<','<<w.guard_events
       <<','<<w.frontier_tests<<','<<w.endpoint_tests<<','<<w.envelope_goal<<','<<w.circuit_nodes<<','<<w.circuit_stops<<','<<w.circuit_rows;
}
inline const std::string work_columns=mpgaa_lazy::work_columns+",envelope_hits,envelope_builds,envelope_added,guard_installs,guard_events,frontier_tests,endpoint_tests,envelope_goal,circuit_nodes,circuit_stops,circuit_rows";
}
