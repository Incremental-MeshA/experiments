#pragma once
#include "ima/deferred.hpp"

namespace ima::navigation_controls {
// Standard grid A*: an admissible octile heuristic, dense stamped arrays,
// and larger-g tie breaking. This is a strengthened baseline, not a new search
// algorithm. Motion validity still uses the original model and cell probes.
class OctileGrid final:public Planner {
    const Model& model;Grid grid;State goal,last;
    bool reuse,no_path=false;std::uint64_t cap;
    Suffix suffix;
    std::vector<double> g;
    std::vector<std::uint32_t> stamp;
    std::vector<int> parent;
    std::uint32_t epoch=0;
    double cardinal=INF,diagonal=INF;
    struct Item {double f,g;std::uint64_t sequence;int cell;};
    struct Greater {
        bool operator()(const Item& a,const Item& b)const{
            if(a.f!=b.f)return a.f>b.f;
            if(a.g!=b.g)return a.g<b.g;
            return a.sequence>b.sequence;
        }
    };
    int index(Cell c)const{return c.i*grid.width+c.j;}
    double heuristic(Cell c)const{
        int a=std::abs(c.i-goal.i),b=std::abs(c.j-goal.j),lo=std::min(a,b),hi=std::max(a,b);
        return std::nextafter(1.0,0.0)*(cardinal*(hi-lo)+diagonal*lo);
    }
    Path solve(State start){
        Path failed;Stats stats;stats.backend_calls=1;
        if(!grid.free(start.cell()) || !grid.free(goal.cell())){failed.stats=stats;return failed;}
        if(++epoch==0){std::fill(stamp.begin(),stamp.end(),0);epoch=1;}
        auto root=index(start.cell()),target=index(goal.cell());stamp[root]=epoch;g[root]=0;parent[root]=-1;
        std::priority_queue<Item,std::vector<Item>,Greater> open;std::uint64_t sequence=0;
        open.push({heuristic(start.cell()),0,sequence++,root});
        while(!open.empty()){
            auto item=open.top();open.pop();if(stamp[item.cell]!=epoch || item.g!=g[item.cell])continue;
            State u{item.cell/grid.width,item.cell%grid.width,0};
            if(item.cell==target){
                std::vector<int> ids;State v=goal;
                for(std::size_t steps=0;v!=start;++steps){
                    require(steps<grid.cells.size(),"octile parent cycle");int id=parent[index(v.cell())];require(id>=0,"octile missing parent");
                    ids.push_back(id);auto& p=model.primitives[id];v={v.i-p.di,v.j-p.dj,p.start};
                }
                std::reverse(ids.begin(),ids.end());auto path=path_from_ids(model,start,ids);
                require(std::abs(path.cost-item.g)<1e-6,"octile reconstruction mismatch");path.stats=stats;return path;
            }
            if(stats.expansions>=cap){failed.stats=stats;failed.stats.capped=true;return failed;}++stats.expansions;
            for(int id:model.by_start[0]){
                auto v=model.head(u,id);
                if(!grid.inside(v.cell())){(void)valid_edge(grid,model,u,id,stats);continue;}
                int to=index(v.cell());double candidate=item.g+model.primitives[id].cost;
                if(stamp[to]==epoch && candidate>=g[to]-EPS)continue;
                if(!valid_edge(grid,model,u,id,stats))continue;
                stamp[to]=epoch;g[to]=candidate;parent[to]=id;
                open.push({candidate+heuristic(v.cell()),candidate,sequence++,to});
            }
        }
        failed.stats=stats;return failed;
    }
public:
    OctileGrid(const Model& m,const Grid& initial,State target,bool keep,std::uint64_t limit)
        :model(m),grid(initial),goal(target),reuse(keep),cap(limit),suffix(m),g(initial.cells.size()),stamp(initial.cells.size()),parent(initial.cells.size(),-1){
        require(m.name=="grid8" && m.headings==1 && m.primitives.size()==8 && target.k==0,"octile control requires grid8");
        std::set<Cell> displacements;
        for(auto& p:m.primitives){
            require(p.start==0 && p.end==0 && std::max(std::abs(p.di),std::abs(p.dj))==1 && p.cells.size()==2 && p.cells.front()==Cell{0,0} && p.cells.back()==Cell{p.di,p.dj},"unsupported grid primitive");
            require(std::abs(p.cost-std::hypot(p.di,p.dj))<1e-12,"unsupported grid costs");displacements.insert({p.di,p.dj});
            (p.di && p.dj ? diagonal : cardinal)=std::min(p.di && p.dj ? diagonal : cardinal,p.cost);
        }
        require(displacements.size()==8 && cardinal>0 && diagonal>=cardinal && diagonal<=2*cardinal,"invalid grid control");
    }
    Path replan(State start,const std::vector<Cell>& blocks={},const std::vector<Cell>& opens={}) override{
        require(start.k==0,"grid heading mismatch");auto [b,o]=net_changes(grid,blocks,opens);
        if(reuse)suffix.update(b,o);
        for(auto q:b)grid.set(q,true);
        for(auto q:o)grid.set(q,false);
        std::size_t at=0;
        if(reuse && o.empty() && no_path && start==last){Path p;p.stats.certified=true;return p;}
        if(reuse && o.empty() && grid.free(start.cell()) && grid.free(goal.cell()) && suffix.position(start,at)){auto p=suffix.tail(at);p.stats.certified=true;return p;}
        auto path=solve(start);
        if(reuse)suffix.install(path.stats.capped ? Path{} : path);
        last=start;no_path=!path.success() && !path.stats.capped;return path;
    }
};
}
