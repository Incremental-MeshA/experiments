#!/usr/bin/env python3
"""Demonstrate why naive terminal pruning needs adaptive lifting."""
import hashlib,json,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 d=HERE/'build/mutant';d.mkdir(parents=True,exist_ok=True);original=HERE/'algorithms.hpp';text=original.read_text();assert text.count('            lift(closed);')==1
 text=text.replace('            lift(closed);','            /* deliberate test-only mutant: omit consistency lifting */;').replace('#include "../mesh_vertex/factory.hpp"','#include "'+str(ROOT/'cpp/mesh_vertex/factory.hpp')+'"')
 header=d/'mutant.hpp';header.write_text(text)
 source=d/'mutant.cpp';source.write_text(r'''#include "mutant.hpp"
#include <iostream>
#include <random>
using namespace ima;
int main(int argc,char** argv)try {
    require(argc==2,"model required");auto suite=read_suite(argv[1]);auto& m=suite.model;
    variants::Prepared p(m);mesh_vertex::MeshIndex index(m,p);
    for(int seed=0;seed<100;++seed) {
        std::mt19937 random(982311+seed);Grid g(31,39);State s{5,5,0},t{24,31,seed%m.headings};
        for(int i=0;i<g.height;++i)for(int j=0;j<g.width;++j)if(random()%100<5)g.set({i,j},true);
        g.set(s.cell(),false);g.set(t.cell(),false);
        mesh_lift::LiftMPGAA planner(index.vertex,g,t,1000000,false,false,false);
        auto path=planner.replan(s);if(!path.success())continue;
        try{planner.audit();}catch(const std::runtime_error& e) {
            require(std::string(e.what())=="inconsistent native mesh heuristic","unexpected mutant failure");
            std::cout<<R"({"status":"mutant_detected","seed":)"<<seed
                <<R"(,"terminal_prunes":)"<<planner.counters().terminal_prunes<<"}"<<std::endl;return 0;
        }
    }
    throw std::runtime_error("mutant did not exercise an inconsistency");
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
''')
 binary=d/'mutant';command=['g++','-O2','-DNDEBUG','-std=c++17']+['-I'+str(ROOT/'cpp'/p) for p in ['include','experiments','mesh_variants','navigation_sweeps']]+[str(source),'-o',str(binary)]
 subprocess.run(command,cwd=ROOT,check=True)
 r=subprocess.run([str(binary),str(ROOT/'cpp/experiments/frozen/car16_model.txt')],cwd=ROOT,text=True,capture_output=True,check=True)
 result=json.loads(r.stdout);assert result['status']=='mutant_detected' and result['terminal_prunes']>0
 v=HERE/'validation';v.mkdir(exist_ok=True);(v/'mutation.json').write_text(json.dumps(dict(status='passed',original_source_sha256=sha(original),script_sha256=sha(Path(__file__)),mutant_header_sha256=sha(header),mutant_source_sha256=sha(source),command=command,result=result),indent=2)+'\n');print(r.stdout,flush=True)
if __name__=='__main__':main()
