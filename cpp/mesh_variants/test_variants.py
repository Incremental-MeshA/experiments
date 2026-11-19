#!/usr/bin/env python3
"""Independent primitive-Dijkstra, dynamic macro cells and unknown-world tests."""
import csv
import heapq
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'cpp/experiments'))
from prepare import write_suite,_assemble,build_control_set

NEW=['prefix_positive','cmesh_dstar','suffix_mesh','boundary_mesh']
METHODS=NEW+['lba']


def oracle(grid,model,start,goal):
    if grid[start[:2]] or grid[goal[:2]]:return None
    best={start:0.0};queue=[(0.0,start)]
    while queue:
        d,u=heapq.heappop(queue)
        if d!=best[u]:continue
        if u==goal:return d
        for p in model.by_theta[u[2]]:
            # This oracle uses physical primitives only, never a mesh adapter,
            # transformed edge, cached cost, heuristic, or D* Lite record.
            primitive=model.primitives[p]
            if any(not (0<=u[0]+i<grid.shape[0] and 0<=u[1]+j<grid.shape[1]) or grid[u[0]+i,u[1]+j] for i,j in primitive.cells):continue
            v=(u[0]+primitive.di,u[1]+primitive.dj,primitive.end_theta);nxt=d+primitive.cost
            if nxt<best.get(v,math.inf):best[v]=nxt;heapq.heappush(queue,(nxt,v))
    return None


def run(binary,data,out,methods=METHODS,repeats=2,*extra):
    result=subprocess.run([str(binary),'--input',str(data),'--output',str(out),'--methods',','.join(methods),
                           '--repeats',str(repeats),*extra],capture_output=True,text=True,
                          env={**os.environ,'ASAN_OPTIONS':'detect_leaks=1','UBSAN_OPTIONS':'halt_on_error=1'})
    assert result.returncode==0,(binary,data,result.stderr)
    assert 'ERROR: AddressSanitizer' not in result.stderr and 'runtime error:' not in result.stderr,result.stderr
    with out.open() as f:return list(csv.DictReader(f))


def main():
    HERE.joinpath('results').mkdir(exist_ok=True)
    car=build_control_set('car16');rng=np.random.default_rng(59103);cases=[]
    for h in range(16):
        grid=(rng.random((18,20))<[0,.08,.15,.25][h%4]).astype(np.uint8)
        starts=[(5+q%3,4+2*(q%2),(h+3*q)%16) for q in range(7)];goal=(9,13,(5*h+3)%16)
        protected={s[:2] for s in starts}|{goal[:2]}
        for c in protected:grid[c]=0
        initial=grid.copy();queries=[]
        for qi,start in enumerate(starts):
            blocks=[];opens=[]
            if qi:
                for flat in rng.choice(grid.size,5,replace=False):
                    cell=(int(flat)//grid.shape[1],int(flat)%grid.shape[1])
                    if cell in protected:continue
                    (opens if grid[cell] else blocks).append(cell);grid[cell]^=1
            queries.append(dict(start=start,goal=goal,blocks=blocks,opens=opens,expected=oracle(grid,car,start,goal)))
        cases.append(dict(id=f'heading_{h}',family='independent',_initial=initial,queries=queries))
    directed=_assemble('directed_macro',1,((0,1),),[(0,0,((0,0),(0,1),(0,2)),2.0),(0,0,((0,0),(1,0),(2,0)),2.0)])
    grid=np.ones((8,18),dtype=np.uint8);grid[2,2:16]=0;grid[2,7]=1;s,t=(2,2,0),(2,14,0);initial=grid.copy();queries=[]
    edits=[([],[]),([] ,[(2,7)]),([(2,9)],[]),([],[(2,9)]),([(2,14)],[]),([],[(2,14)]),([(2,2)],[]),([],[(2,2)])]
    for blocks,opens in edits:
        for c in blocks:grid[c]=1
        for c in opens:grid[c]=0
        queries.append(dict(start=s,goal=t,blocks=blocks,opens=opens,expected=oracle(grid,directed,s,t)))
    macro=[dict(id='directed_open_macro',family='macro',_initial=initial,queries=queries)]
    excluded={'time_s','setup_s','sensing_s','peak_heap_bytes','retained_heap_bytes'}
    def decisions(rows):return [{k:v for k,v in r.items() if k not in excluded} for r in rows]
    query_checks=0
    with tempfile.TemporaryDirectory(prefix='ima_mesh_variants_') as directory:
        d=Path(directory)
        for name,model,suite in [('car16',car,cases),('directed',directed,macro)]:
            data=d/(name+'.txt');write_suite(data,model,suite)
            normal=run(HERE/'build/experiment',data,d/(name+'_normal.csv'))
            memory=run(HERE/'build/experiment_memory',data,d/(name+'_memory.csv'))
            assert decisions(normal)==decisions(memory)
            assert all(r['status'] in ['ok','no_path'] for r in normal)
            query_checks+=len(normal)
            sanitizer=HERE/'build/experiment_sanitize'
            if sanitizer.exists():
                checked=run(sanitizer,data,d/(name+'_sanitized.csv'),NEW,1)
                expected={(r['case'],r['method'],r['query']):r for r in normal if r['method'] in NEW and r['repeat']=='0'}
                for r in checked:
                    assert decisions([r])==decisions([expected[r['case'],r['method'],r['query']]])
        # Exact same native model is compiled from the independently stored input.
        model_audits=[]
        for control in ['car16','grid8']:
            data=ROOT/'cpp/experiments/frozen'/f'{control}_model.txt'
            for binary in ['test_models','test_models_sanitize']:
                p=HERE/'build'/binary
                if not p.exists():continue
                result=subprocess.run([str(p),str(data)],capture_output=True,text=True,check=True,
                                      env={**os.environ,'ASAN_OPTIONS':'detect_leaks=1','UBSAN_OPTIONS':'halt_on_error=1'})
                model_audits.append(dict(control=control,binary=binary,**json.loads(result.stdout)))
        # All new variants navigate the original numerical-regression world.
        missions=run(HERE/'build/experiment',ROOT/'cpp/experiments/frozen/car16_missions_r8.txt',d/'mission.csv',NEW,1,
                     '--mode','mission','--radius','8','--max-steps','160','--case','car16__MA_room96__mission__s48101__r8')
        terminal={}
        for r in missions:terminal[r['method']]=r['status']
        assert len(terminal)==4 and set(terminal.values())=={'goal'},terminal
    result=dict(status='passed',independent_oracle='Python heap-Dijkstra on original float-cost physical primitives',
                car16_headings=16,dynamic_snapshots=120,normal_query_checks=query_checks,allocation_path_counter_parity=True,
                model_audits=model_audits,unknown_car_missions=terminal,sanitized=(HERE/'build/experiment_sanitize').exists())
    HERE.joinpath('results/verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
