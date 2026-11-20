#pragma once
#include "ima/planners.hpp"
#include "dstar_boundary.hpp"
#include "variants.hpp"

// The same fifteen implementations as mesh_variants/bench.cpp. Only the
// environment/controller is new; no search kernel is modified for this study.
namespace ima::navigation {
inline const std::vector<std::string> methods={"lba","lazy_lba","mesha","mesh_parall","dstar_lattice","dstar_mesh","mpgaa","md_astar","md64","md_scan","lba_reuse","prefix_positive","cmesh_dstar","suffix_mesh","boundary_mesh"};

class Reuse final:public Planner {
    const Model& model;Grid grid;State goal,last;Suffix suffix;std::uint64_t cap;bool no_path=false;
public:
    Reuse(const Model& m,const Grid& g,State t,std::uint64_t limit):model(m),grid(g),goal(t),suffix(m),cap(limit) {}
    Path replan(State s,const std::vector<Cell>& blocks={},const std::vector<Cell>& opens={}) override {
        auto [b,o]=net_changes(grid,blocks,opens);suffix.update(b,o);
        for(auto q:b)grid.set(q,true);
        for(auto q:o)grid.set(q,false);
        std::size_t at=0;
        if(o.empty() && no_path && s==last){Path p;p.stats.certified=true;return p;}
        if(o.empty() && grid.free(s.cell()) && grid.free(goal.cell()) && suffix.position(s,at)){
            auto p=suffix.tail(at);p.stats.certified=true;return p;
        }
        auto p=search("lba",grid,model,s,goal,cap);suffix.install(p.stats.capped ? Path{} : p);
        last=s;no_path=!p.success() && !p.stats.capped;return p;
    }
};

inline std::unique_ptr<Planner> make(const std::string& name,const Grid& grid,const Model& m,const Certificate& c,
                                     const variants::Prepared& prepared,State s,State t,std::uint64_t cap){
    if(name=="prefix_positive" || name=="cmesh_dstar" || name=="suffix_mesh" || name=="boundary_mesh")
        return std::make_unique<variants::MeshVariantPlanner>(prepared,name,grid,s,t,cap);
    if(name=="dstar_lattice" || name=="dstar_mesh")return std::make_unique<BoundaryDStarLite>(m,grid,s,t,name=="dstar_mesh",cap);
    if(name=="lba_reuse")return std::make_unique<Reuse>(m,grid,t,cap);
    return make_planner(name,grid,m,c,s,t,cap);
}
}
