#pragma once
#include "algorithms.hpp"
namespace ima::mesh_lift {
using MeshIndex=mesh_vertex::MeshIndex;
// Strong cold-mesh control with the same standard suffix certificate as LBA reuse.
class MeshAReuse final:public Planner {
    const Model& model;Grid grid;State goal,last;Suffix suffix;std::uint64_t cap;bool no_path=false;
public:
    MeshAReuse(const Model& m,const Grid& g,State t,std::uint64_t limit):model(m),grid(g),goal(t),suffix(m),cap(limit){}
    Path replan(State s,const std::vector<Cell>& blocks={},const std::vector<Cell>& opens={}) override {
        auto [b,o]=net_changes(grid,blocks,opens);suffix.update(b,o);
        for(auto q:b)grid.set(q,true);
        for(auto q:o)grid.set(q,false);
        std::size_t at=0;
        if(o.empty() && no_path && s==last){Path p;p.stats.certified=true;return p;}
        if(o.empty() && grid.free(s.cell()) && grid.free(goal.cell()) && suffix.position(s,at)){auto p=suffix.tail(at);p.stats.certified=true;return p;}
        auto p=search("mesha",grid,model,s,goal,cap);suffix.install(p.stats.capped?Path{}:p);
        last=s;no_path=!p.success() && !p.stats.capped;return p;
    }
};
inline const std::vector<std::string> native_methods={"lift_mesh","cascade_lift","lift_cold","lift_noprune","cascade_cold"};
inline const std::vector<std::string> methods=[](){auto v=mesh_vertex::methods;v.insert(v.end(),native_methods.begin(),native_methods.end());v.emplace_back("mesha_reuse");return v;}();
inline std::unique_ptr<Planner> make(const std::string& name,const Grid& grid,const Model& m,const Certificate& c,const variants::Prepared& p,const MeshIndex& index,State s,State t,std::uint64_t cap) {
    if(name=="mesha_reuse")return std::make_unique<MeshAReuse>(m,grid,t,cap);
    if(std::find(native_methods.begin(),native_methods.end(),name)!=native_methods.end()) {
        bool learn=name!="lift_cold" && name!="cascade_cold";
        return std::make_unique<LiftMPGAA>(index.vertex,grid,t,cap,name=="cascade_lift" || name=="lift_noprune",name=="cascade_lift" || name=="lift_noprune" || name=="cascade_cold",name=="cascade_lift" || name=="lift_noprune",learn,learn,name!="lift_noprune");
    }
    return mesh_vertex::make(name,grid,m,c,p,index,s,t,cap);
}
inline Work counters(const Planner& p){if(auto* q=dynamic_cast<const LiftMPGAA*>(&p))return q->counters();Work w;static_cast<mesh_vertex::Work&>(w)=mesh_vertex::counters(p);return w;}
inline const std::string work_columns=mesh_vertex::work_columns+",lift_terminal_tests,lift_terminal_prunes,lift_edges,lift_writes";
inline void write_work(std::ostream& out,const Work& w){mesh_vertex::write_work(out,w);out<<','<<w.terminal_tests<<','<<w.terminal_prunes<<','<<w.lift_edges<<','<<w.lift_writes;}
}
