#include "visibility.hpp"
#include "environment.hpp"
#include <iostream>
using namespace ima;
namespace nav=ima::navigation;

int main(int argc,char** argv)try{
    require(argc==2,"provide a frozen model");auto m=read_suite(argv[1]).model;
    auto visibility=nav::Visibility::compile(m,4);
    for(int h=0;h<m.headings;++h)for(int depth:{1,2,4}){
        StateSet visited;std::vector<std::pair<State,int>> queue{{{0,0,h},0}};visited.insert({0,0,h});CellSet cells;
        for(std::size_t i=0;i<queue.size();++i){auto [s,d]=queue[i];
            for(int id:m.by_start[s.k]){auto& p=m.primitives[id];for(auto c:p.cells)cells.insert({s.i+c.i,s.j+c.j});
                auto t=m.head(s,id);if(d+1<depth && visited.insert(t).second)queue.push_back({t,d+1});}
        }
        CellSet encoded;for(auto run:visibility.runs.at({h,depth}))for(int j=run.lo;j<=run.hi;++j)encoded.insert({run.di,j});
        require(cells==encoded,"compiled arc-depth visibility differs from independent direct BFS");
        if(m.name=="grid8"){require(cells.size()==std::size_t((2*depth+1)*(2*depth+1)),"grid visibility is not Chebyshev ball");for(auto c:cells)require(std::max(std::abs(c.i),std::abs(c.j))<=depth,"grid visibility bound");}
    }
    Grid grid(10,10);for(int j=0;j<7;++j)grid.set({0,j},true);
    nav::World a(grid,true),b(grid,true);nav::Calendar ca{100,123,{}},cb{100,123,{}};
    for(int phase=1;phase<=10;++phase){
        auto old=a.truth.cells;auto event=a.change(ca,phase,30,{5,5},{9,9});auto same=b.change(cb,phase,30,{5,5},{9,9});
        require(event.requested_half==15 && event.actual_half==7 && event.clamped,"balanced clamp");
        require(a.truth.cells==b.truth.cells && event.hash==same.hash,"nonrepeatable phases");
        std::size_t blocks=0,opens=0;for(std::size_t i=0;i<old.size();++i){blocks+=!old[i] && a.truth.cells[i];opens+=old[i] && !a.truth.cells[i];}
        require(blocks==7 && opens==7 && a.blocked==7,"pre-phase pools/density broken");
        require(a.truth.free({5,5}) && a.truth.free({9,9}),"protected endpoints changed");
        auto observation=a.square({5,5,0},10);require(a.mismatch==0 && a.world_hash==a.belief_hash && a.known==100,"observation accounting");
        require(observation.blocks.size()+observation.opens.size()<=14+7,"observation duplication");
    }
    nav::World empty(Grid(4,4),false);nav::Calendar ce{16,9,{}};require(empty.change(ce,1,30,{0,0},{3,3}).actual_half==0,"empty pool not clamped");
    std::cout<<"passed visibility BFS, grid geometry, phase determinism, balanced clamp, density, protected endpoints and observation hashes\n";return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
