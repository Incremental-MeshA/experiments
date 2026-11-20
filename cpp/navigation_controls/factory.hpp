#pragma once
#include "../navigation_sweeps/factory.hpp"
#include "../navigation_sweeps/environment.hpp"
#include "../navigation_sweeps/visibility.hpp"
#include "strong_grid.hpp"

namespace ima::navigation_controls {
using ima::navigation::World;
using ima::navigation::Calendar;
using ima::navigation::Visibility;
using ima::navigation::read_specs;
inline const std::vector<std::string> methods={"lba_reuse","mpgaa","md_astar","octile_astar","octile_reuse"};
inline std::unique_ptr<Planner> make(const std::string& name,const Grid& grid,const Model& m,const Certificate& c,
                                   const variants::Prepared& prepared,State s,State t,std::uint64_t cap){
    if(name=="octile_astar" || name=="octile_reuse")return std::make_unique<OctileGrid>(m,grid,t,name=="octile_reuse",cap);
    return ima::navigation::make(name,grid,m,c,prepared,s,t,cap);
}
}
