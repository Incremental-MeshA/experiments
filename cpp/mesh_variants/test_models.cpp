#include "variants.hpp"
#include <iostream>

int main(int argc,char** argv) try {
    ima::require(argc==2,"pass the native model/suite file");
    auto suite=ima::read_suite(argv[1]);const auto& model=suite.model;
    ima::variants::Prepared prepared(model);auto [projections,heuristics]=prepared.audit();
    std::size_t invalidations=0;
    for (const auto* definition:{&prepared.positive,&prepared.contracted,&prepared.reversed,&prepared.batched}) {
        ima::Grid empty(48,48);ima::variants::Graph graph(prepared,*definition,empty);
        for (std::size_t id=0;id<definition->edges.size();++id) {
            const auto& edge=definition->edges[id];ima::State u{24,24,edge.from};
            for (std::size_t k:std::vector<std::size_t>{0,edge.cells.size()/2,edge.cells.size()-1}) {
                auto off=edge.cells[k];ima::Cell cell{u.i+off.i,u.j+off.j};
                ima::require(graph.cost(u,int(id))==edge.cost,"empty edge is invalid");
                graph.grid.set(cell,true);auto dirty=graph.invalidate({cell});
                ima::require(dirty.count(u) && !std::isfinite(graph.cost(u,int(id))),"changed macro support was not invalidated");
                graph.grid.set(cell,false);graph.invalidate({cell});
                ima::require(graph.cost(u,int(id))==edge.cost,"opening did not restore edge");++invalidations;
            }
        }
    }
    std::cout<<"{\"status\":\"passed\",\"projection_checks\":"<<projections<<",\"heuristic_checks\":"<<heuristics
             <<",\"support_close_open_checks\":"<<invalidations<<"}\n";return 0;
} catch (const std::exception& e) { std::cerr<<e.what()<<'\n';return 1; }
