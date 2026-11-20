#pragma once
#include "conditional.hpp"
namespace ima::mesh_conditional {
using mesh_envelope::MeshIndex;using mesh_envelope::Work;
inline const std::vector<std::string> methods=[](){auto v=mesh_envelope::methods;v.emplace_back("conditional_dstar");return v;}();
inline std::unique_ptr<Planner> make(const std::string& name,const Grid& grid,const Model& m,const Certificate& c,
    const variants::Prepared& prepared,const MeshIndex& mesh,State s,State t,std::uint64_t cap) {
    if(name=="conditional_dstar")return std::make_unique<Conditional>(m,grid,s,t,cap);
    return mesh_envelope::make(name,grid,m,c,prepared,mesh,s,t,cap);
}
inline Work counters(const Planner& planner){return mesh_envelope::counters(planner);}
inline void write_work(std::ostream& out,const Work& w){mesh_envelope::write_work(out,w);}
inline const std::string work_columns=mesh_envelope::work_columns;
}
