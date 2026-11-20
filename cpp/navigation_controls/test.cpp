#include "memory.hpp"
#include "strong_grid.hpp"
#include "ima/search.hpp"
#include <iostream>
#include <random>
using namespace ima;
int main(int argc,char** argv)try{
    require(argc==2,"provide model");auto model=read_suite(argv[1]).model;std::mt19937 rng(712031);int checked=0;
    for(int trial=0;trial<48;++trial){
        int side=9+trial%16;Grid grid(side,side);
        for(auto& q:grid.cells)q=rng()%100<unsigned(10+10*(trial%4));
        State start{0,0,0},goal{side-1,side-1,0};grid.set(start.cell(),false);grid.set(goal.cell(),false);
        navigation_controls::OctileGrid plain(model,grid,goal,false,1000000),reuse(model,grid,goal,true,1000000);
        Path previous;
        for(int phase=0;phase<12;++phase){
            if(previous.success() && previous.ids.size()>1)start=previous.states[1];
            std::vector<Cell> blocks,opens;std::set<Cell> changed;
            for(int j=0;j<5;++j){Cell q{int(rng()%side),int(rng()%side)};if(q==start.cell() || q==goal.cell())continue;
                if(!changed.insert(q).second)continue;
                if(grid.blocked(q)){grid.set(q,false);opens.push_back(q);}else{grid.set(q,true);blocks.push_back(q);}}
            // Canonical net deltas: do not toggle a cell twice in one phase.
            auto ref=search("lba",grid,model,start,goal,1000000);
            auto a=plain.replan(start,blocks,opens),b=reuse.replan(start,blocks,opens);
            require(!ref.stats.capped && !a.stats.capped && !b.stats.capped,"unexpected test cap");
            for(auto* p:{&a,&b}){require(p->success()==ref.success(),"octile reachability mismatch");if(p->success())require(std::abs(p->cost-ref.cost)<1e-6,"octile nonoptimal");validate_path(grid,model,start,goal,*p);++checked;}
            previous=b;
        }
    }
    Grid free(32,32);navigation_controls::OctileGrid limited(model,free,{31,31,0},false,1);require(limited.replan({0,0,0}).stats.capped,"cap was not retained");
    std::cout<<"passed "<<checked<<" octile/reuse answers with moving starts, increases, decreases and no paths\n";return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
