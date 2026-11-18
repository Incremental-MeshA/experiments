#!/usr/bin/env python3
"""Independent heap-Dijkstra oracle for the new grid8 model and dynamic replay."""
import csv
import heapq
import json
import math
import subprocess
import tempfile

import numpy as np

from prepare import HERE, _assemble, write_suite

DIRS=[(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]


def oracle(grid,start,goal):
    s=tuple(start[:2]);t=tuple(goal[:2]);distance={s:0.0};queue=[(0.0,s)]
    while queue:
        cost,u=heapq.heappop(queue)
        if cost!=distance[u]:continue
        if u==t:return cost
        for di,dj in DIRS:
            v=(u[0]+di,u[1]+dj)
            if not (0<=v[0]<grid.shape[0] and 0<=v[1]<grid.shape[1]) or grid[v]:continue
            nxt=cost+(math.sqrt(2) if di and dj else 1.0)
            if nxt<distance.get(v,math.inf):
                distance[v]=nxt;heapq.heappush(queue,(nxt,v))
    return None


def main():
    model=_assemble('grid8_oracle',1,((0,1),),[(0,0,((0,0),d),math.hypot(*d)) for d in DIRS])
    rng=np.random.default_rng(48103);cases=[]
    for ci in range(24):
        grid=(rng.random((8,9))<(.1+.1*(ci%4))).astype(np.uint8)
        s,t=(0,0,0),(7,8,0);grid[s[:2]]=grid[t[:2]]=0;initial=grid.copy();queries=[]
        for qi in range(9):
            blocks=[];opens=[]
            if qi:
                for flat in rng.choice(grid.size,4,replace=False):
                    cell=(int(flat)//grid.shape[1],int(flat)%grid.shape[1])
                    if cell in [s[:2],t[:2]]:continue
                    (opens if grid[cell] else blocks).append(cell);grid[cell]^=1
            queries.append(dict(start=s,goal=t,blocks=blocks,opens=opens,expected=oracle(grid,s,t)))
        cases.append(dict(id=f'oracle_{ci}',family='independent_grid8',_initial=initial,queries=queries))
    from pathlib import Path
    with tempfile.TemporaryDirectory(prefix='ima_grid8_oracle_') as directory:
        d=Path(directory);data=d/'suite.txt';write_suite(data,model,cases)
        outputs=[]
        for name in ['experiment','experiment_memory']:
            path=d/(name+'.csv')
            subprocess.run([str(HERE/'build'/name),'--input',str(data),'--output',str(path),'--repeats','1'],check=True,capture_output=True,text=True)
            with path.open() as f:outputs.append(list(csv.DictReader(f)))
        excluded={'time_s','setup_s','sensing_s','peak_heap_bytes','retained_heap_bytes'}
        assert [{k:v for k,v in r.items() if k not in excluded} for r in outputs[0]]==[{k:v for k,v in r.items() if k not in excluded} for r in outputs[1]]
        assert all(r['status'] in ['ok','no_path'] for r in outputs[0])
        assert len(outputs[0])==24*9*11
    result=dict(status='passed',oracle='Independent Python heap-Dijkstra, destination-only grid8, no shared graph/search classes',
                maps=24,snapshots=216,algorithm_queries=2376,exact_methods=10,approximate_method='mesh_parall',
                memory_decision_parity=True)
    (HERE/'results/grid8_oracle.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
