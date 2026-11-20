#pragma once
#include "search.hpp"
#include "dstar.hpp"
#include "deferred.hpp"

namespace ima {
inline const std::vector<std::string> METHODS={"lba","lazy_lba","mesha","mesh_parall","dstar_lattice","dstar_mesh","mpgaa","md_astar","md64","md_scan"};
inline std::unique_ptr<Planner> make_planner(const std::string& method,const Grid& g,const Model& m,const Certificate& cert,State s,State t,std::uint64_t limit=3000000) {
    require(std::find(METHODS.begin(),METHODS.end(),method)!=METHODS.end(),"unknown planner: "+method);
    if (method=="mpgaa") return std::make_unique<MPGAA>(m,g,t,limit);
    if (method=="md_astar" || method=="md64" || method=="md_scan") return std::make_unique<MeshDeferred>(m,cert,g,t,method,limit);
    if (method=="dstar_lattice" || method=="dstar_mesh") return std::make_unique<DStarLite>(m,g,s,t,method=="dstar_mesh",limit);
    return std::make_unique<Repeated>(m,g,t,method,limit);
}
} // namespace ima
