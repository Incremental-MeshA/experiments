#pragma once
#include "algorithms.hpp"
#include "../mpgaa_mesh/factory.hpp"
namespace ima::mpgaa_lazy {
inline const std::vector<std::string> methods=[](){auto v=mpgaa_mesh::methods;
    for(const auto* name:{"stamp_mpgaa","batch_mpgaa","witness_mpgaa","stamp_cell","batch_scan"})v.emplace_back(name);
    return v;}();
inline std::unique_ptr<Planner> make(const std::string& name,const Grid& grid,const Model& m,const Certificate& c,
    const variants::Prepared& prepared,const MeshIndex& mesh,State s,State t,std::uint64_t cap) {
    if(name=="stamp_mpgaa")return std::make_unique<LazyMPGAA>(mesh,grid,t,Mode::Stamp,cap);
    if(name=="batch_mpgaa")return std::make_unique<LazyMPGAA>(mesh,grid,t,Mode::Batch,cap);
    if(name=="witness_mpgaa")return std::make_unique<LazyMPGAA>(mesh,grid,t,Mode::Witness,cap);
    if(name=="stamp_cell")return std::make_unique<LazyMPGAA>(mesh,grid,t,Mode::Stamp,cap,1);
    if(name=="batch_scan")return std::make_unique<LazyMPGAA>(mesh,grid,t,Mode::Batch,cap,8,true);
    return mpgaa_mesh::make(name,grid,m,c,prepared,mesh,s,t,cap);
}
inline Work counters(const Planner& planner) {
    if(const auto* p=dynamic_cast<const LazyMPGAA*>(&planner))return p->counters();
    Work w;static_cast<mpgaa_mesh::Work&>(w)=mpgaa_mesh::counters(planner);return w;
}
inline void write_work(std::ostream& out,const Work& w) {
    mpgaa_mesh::write_work(out,w);
    out<<','<<w.stamp_writes<<','<<w.tile_reads<<','<<w.mask_refreshes<<','<<w.mask_hits<<','<<w.cut_checks<<','<<w.cut_reuses
       <<','<<w.cut_primitives<<','<<w.edit_batches<<','<<w.scan_batches<<','<<w.seed_tests<<','<<w.arrow_checks<<','<<w.cover_tests;
}
inline const std::string work_columns=std::string(mpgaa_mesh::work_columns)+",stamp_writes,tile_reads,mask_refreshes,mask_hits,cut_checks,cut_reuses,cut_primitives,edit_batches,scan_batches,seed_tests,arrow_checks,cover_tests";
} // namespace ima::mpgaa_lazy
