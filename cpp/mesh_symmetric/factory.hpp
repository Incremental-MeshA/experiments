#pragma once
#include "algorithms.hpp"
namespace ima::mesh_symmetric {
inline const std::vector<std::string> methods=[](){auto v=mesh_conditional::methods;v.emplace_back("smd_batch");v.emplace_back("md_batch");v.emplace_back("smd_plain");v.emplace_back("lazy_blocks_batch");return v;}();
inline std::unique_ptr<Planner> make(const std::string& name,const Grid& grid,const Model& m,const Certificate& c,
    const variants::Prepared& prepared,const MeshIndex& mesh,State s,State t,std::uint64_t cap) {
    if(name=="smd_batch" || name=="md_batch" || name=="smd_plain" || name=="lazy_blocks_batch")return std::make_unique<Symmetric>(mesh,c,grid,t,name!="md_batch",cap,name!="smd_plain",name!="lazy_blocks_batch");
    return mesh_conditional::make(name,grid,m,c,prepared,mesh,s,t,cap);
}
inline Work counters(const Planner& p){if(const auto* s=dynamic_cast<const Symmetric*>(&p))return s->counters();Work w;static_cast<mesh_envelope::Work&>(w)=mesh_conditional::counters(p);return w;}
inline void write_work(std::ostream& out,const Work& w){mesh_envelope::write_work(out,w);out<<','<<w.activated_blocks<<','<<w.deferred_block_cells<<','<<w.optimistic_rounds<<','<<w.path_probes<<','<<w.gap_hits;}
inline const std::string work_columns=mesh_envelope::work_columns+",activated_blocks,deferred_block_cells,optimistic_rounds,path_probes,gap_hits";
}
