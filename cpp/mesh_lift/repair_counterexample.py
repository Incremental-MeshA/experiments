#!/usr/bin/env python3
"""An actual-engine opening-repair counterexample, plus two isolated mutants."""
import argparse,hashlib,json,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main(output_path):
 directory=HERE/'build/repair_counterexample';directory.mkdir(parents=True,exist_ok=True)
 original=HERE/'algorithms.hpp';text=original.read_text();include='#include "../mesh_vertex/factory.hpp"'
 assert text.count('            lift(closed);')==1 and text.count('nodes[child].learned=true;')==1
 variants={'no_closure':text.replace('            lift(closed);','            /* test-only: omit closure */;'),
           'no_learned_mark':text.replace('nodes[child].learned=true;','/* test-only: omit learned mark */;')}
 for name,body in variants.items():
  body=body.replace('namespace ima::mesh_lift {','namespace ima::'+name+' {').replace(include,'#include "'+str(ROOT/'cpp/mesh_vertex/factory.hpp')+'"')
  (directory/(name+'.hpp')).write_text(body)
 source=directory/'fixture.cpp';source.write_text(r'''#include "algorithms.hpp"
#include "no_closure.hpp"
#include "no_learned_mark.hpp"
#include <iostream>
using namespace ima;
Model fixture() {
    Model m;m.name="formal_prefix_opening_counterexample";m.headings=4;
    auto add=[&](int start,int end,double cost,std::vector<Cell> cells){m.primitives.push_back({start,end,0,0,cost,std::move(cells)});};
    // Four boundary headings at one cell represent r,s,v,t. The s-v
    // primitive has two distinct internal configurations u,w. Two initially
    // blocked shortcut primitives have private collision cells x,y.
    add(0,1,1,{{0,0},{0,0}}); // r-s
    add(0,2,2,{{0,0},{0,0}}); // r-v
    add(1,2,3,{{0,0},{0,0},{0,0},{0,0}}); // s-u-w-v
    add(2,3,10,{{0,0},{0,0}}); // v-t, expensive and free
    add(2,3,1,{{0,0},{0,1},{0,0}}); // cheap v-t, blocked at x
    add(1,3,5,{{0,0},{1,0},{0,0}}); // s-t, blocked at y
    auto graph=variants::prefix(m.primitives,m.headings);m.initial=graph.roots;
    for(std::size_t i=0;i<graph.nodes.size();++i) {
        const auto& n=graph.nodes[i];Config c;c.theta=n.heading;c.signature=int(i);c.origin=n.origin;c.finals=n.finals;
        for(int id:graph.out[i]){const auto& e=graph.edges[id];c.edges.push_back({e.delta.i,e.delta.j,e.to,e.base,e.pid});}
        m.configs.push_back(std::move(c));
    }
    m.prepare();return m;
}
double oracle(const Grid& grid,const Model& model,State start,State goal) {
    using Item=std::pair<double,State>;std::priority_queue<Item,std::vector<Item>,std::greater<Item>> queue;
    std::map<State,double> d;d[start]=0;queue.push({0,start});
    while(!queue.empty()) {
        auto [g,u]=queue.top();queue.pop();if(g!=d[u])continue;if(u==goal)return g;
        for(int id:model.by_start[u.k]) {
            auto& p=model.primitives[id];bool valid=true;
            for(auto c:p.cells)if(!grid.free({u.i+c.i,u.j+c.j})){valid=false;break;}
            if(!valid)continue;
            auto v=model.head(u,id);double candidate=g+p.cost;auto it=d.find(v);
            if(it==d.end() || candidate<it->second){d[v]=candidate;queue.push({candidate,v});}
        }
    }
    return INF;
}
template<class PlannerType> double run(const mesh_vertex::Index& index,const Grid& old,const Model& model,bool triggered) {
    State r{2,2,0},s{2,2,1},t{2,2,3};PlannerType planner(index,old,t,10000,triggered,triggered,triggered);
    auto first=planner.replan(r);require(first.success() && first.cost==12,"initial cost must be 12");
    require(planner.counters().terminal_prunes>0,"fixture did not prune its internal prefix");
    auto next=planner.replan(s,{},{{2,3},{3,2}});Grid open=old;open.set({2,3},false);open.set({3,2},false);
    validate_path(open,model,s,t,next);return next.cost;
}
int main()try {
    auto m=fixture();variants::Prepared prepared(m);mesh_vertex::Index index(m,prepared);Grid old(5,5);old.set({2,3},true);old.set({3,2},true);
    Grid open=old;open.set({2,3},false);open.set({3,2},false);double expected=oracle(open,m,{2,2,1},{2,2,3});require(expected==4,"fixture oracle must be 4");
    double lift=run<mesh_lift::LiftMPGAA>(index,old,m,false);double cascade=run<mesh_lift::LiftMPGAA>(index,old,m,true);
    double bad=run<no_closure::LiftMPGAA>(index,old,m,false);double unmarked=run<no_learned_mark::LiftMPGAA>(index,old,m,false);
    require(lift==expected && cascade==expected,"actual Lift opening repair failed");
    require(bad==5 && unmarked==5,"mutants must return the valid but suboptimal cost 5");
    std::cout<<"{\"status\":\"passed\",\"model\":\"formal_prefix_opening_counterexample\",\"configurations\":"<<m.configs.size()<<",\"initial_cost\":12,\"oracle_after_openings\":"<<expected<<",\"lift_cost\":"<<lift<<",\"cascade_lift_cost\":"<<cascade<<",\"no_closure_cost\":"<<bad<<",\"no_learned_mark_cost\":"<<unmarked<<"}\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
''')
 binary=directory/'fixture';command=['g++','-O2','-DNDEBUG','-std=c++17']+['-I'+str(ROOT/'cpp'/p) for p in ['include','experiments','mesh_variants','navigation_sweeps']]+['-I'+str(HERE),str(source),'-o',str(binary)]
 subprocess.run(command,cwd=ROOT,check=True)
 r=subprocess.run([str(binary)],cwd=ROOT,text=True,capture_output=True,check=True);result=json.loads(r.stdout);assert result['status']=='passed'
 output=dict(status='passed',original_source_sha256=sha(original),script_sha256=sha(Path(__file__)),binary_sha256=sha(binary),generated_sources_sha256={p.name:sha(p) for p in sorted(directory.glob('*.hpp'))+[source]},command=command,result=result,scope='A formal non-kinematic prefix fixture using repeated cells and heading states; tests exact C++ learning/repair/search. It is not an additional car16 benchmark or a timing sample.')
 output_path.parent.mkdir(parents=True,exist_ok=True);output_path.write_text(json.dumps(output,indent=2)+'\n');print(json.dumps(output,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=HERE/'validation/repair_counterexample.json');main(p.parse_args().output)
