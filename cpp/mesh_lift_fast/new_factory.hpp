#pragma once
#include "algorithms.hpp"
#include "zero_only.hpp"
namespace ima::mesh_lift_fast {
inline Options options_for(const std::string& name) {
    Options options=name=="fast_lift"?Options::plain():Options::cascading();
        if(name=="fast_all_closed")options.focused=false;
        if(name=="fast_no_depth")options.depth_tie=false;
        if(name=="fast_trace")options.trace=true;
        if(name=="fast_recompute_base")options.cache_base=false;
        if(name=="fast_slow_policy")options.policy_fast=false;
    return options;
}
inline std::unique_ptr<Planner> make_new(const std::string& name,const Grid& grid,State goal,std::uint64_t cap,const mesh_vertex::Index& legacy,const Index& compact,const Index& raw) {
    if(name=="zero_lift" || name=="zero_cascade") {
        bool cascade=name=="zero_cascade";
        return std::make_unique<mesh_lift_zero::LiftMPGAA>(legacy,grid,goal,cap,cascade,cascade,cascade);
    }
    return std::make_unique<LiftMPGAA>(name=="fast_raw_finals"?raw:compact,grid,goal,cap,options_for(name));
}
}
