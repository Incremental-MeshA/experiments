#include "memory.hpp"
#include "factory.hpp"
#include <iostream>
#include <random>
using namespace ima;
int main(int argc,char** argv)try {
    require(argc==3,"provide model and output CSV");auto suite=read_suite(argv[1]);auto& m=suite.model;
    std::ofstream out(argv[2]);require(bool(out),"cannot open setup CSV");out<<std::setprecision(17)<<"model,method,repeat,time_s,peak_heap_bytes,retained_heap_bytes,allocation_calls,configurations,edges\n";
    std::mt19937 random(882211);std::size_t sink=0;
    for(int repeat=0;repeat<100;++repeat){std::vector<std::string> names={"legacy_templates","direct_raw","direct_dedup"};std::shuffle(names.begin(),names.end(),random);
        for(auto name:names){auto before=allocation_profile::live,events=allocation_profile::events;allocation_profile::reset_peak();auto clock=Clock::now();double elapsed=0;std::size_t peak=0,resident=0,nodes=0,edges=0;
            if(name=="legacy_templates") {
                variants::Prepared prepared(m);mesh_lift::MeshIndex index(m,prepared);elapsed=seconds(clock);peak=allocation_profile::peak-before;resident=allocation_profile::live-before;nodes=index.vertex.graph.nodes.size();edges=index.vertex.graph.edges.size();
            } else {
                mesh_lift_fast::Index index(m,name=="direct_dedup");elapsed=seconds(clock);peak=allocation_profile::peak-before;resident=allocation_profile::live-before;nodes=index.nodes.size();edges=index.edges.size();
            }
            auto allocations=allocation_profile::events-events;
            // Snapshot before constructing require()'s diagnostic std::string.
            bool released=allocation_profile::live==before;
            require(released,"shared index leaked tracked memory");
            sink+=nodes+edges;out<<m.name<<','<<name<<','<<repeat<<','<<elapsed<<','<<peak<<','<<resident<<','<<allocations<<','<<nodes<<','<<edges<<'\n';
        }
    }
    std::cout<<"{\"status\":\"passed\",\"compiler\":\""<<__VERSION__<<"\",\"runs\":300,\"checksum\":"<<sink<<",\"memory_profile\":";
#ifdef IMA_TRACK_ALLOC
    std::cout<<"true";
#else
    std::cout<<"false";
#endif
    std::cout<<"}\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
