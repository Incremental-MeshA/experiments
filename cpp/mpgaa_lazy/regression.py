#!/usr/bin/env python3
"""Untimed endpoint and blocker-frontier regressions with a Python Dijkstra."""
import argparse
import csv
import hashlib
import heapq
import io
import json
import math
import shlex
import subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
METHODS=['boundary_mpgaa','stamp_mpgaa','batch_mpgaa','witness_mpgaa','stamp_cell','batch_scan']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def model(path):
    tokens=shlex.split(path.read_text());at=2;name=tokens[at];at+=1
    headings,np,nc=map(int,tokens[at:at+3]);at+=3+headings;primitives=[]
    for _ in range(np):
        start,end,di,dj=map(int,tokens[at:at+4]);cost=float(tokens[at+4]);count=int(tokens[at+5]);at+=6
        cells=[tuple(map(int,tokens[at+j:at+j+2])) for j in range(0,2*count,2)];at+=2*count
        primitives.append((start,end,di,dj,cost,cells))
    for _ in range(nc):
        ne,nf=map(int,tokens[at+4:at+6]);at+=6+5*ne+4*nf
    assert tokens[at:]==['0','0']
    prefix='IMA_CPP 1\n'+json.dumps(name)+' '+' '.join(tokens[3:at])+'\n'
    return primitives,prefix
def dijkstra(grid,height,width,primitives,start,goal):
    if grid[start[0]*width+start[1]] or grid[goal[0]*width+goal[1]]:return math.inf,[]
    queue=[(0.0,start)];best={start:0.0};parent={}
    while queue:
        cost,u=heapq.heappop(queue)
        if cost!=best[u]:continue
        if u==goal:
            ids=[]
            while u!=start:u,pid=parent[u];ids.append(pid)
            return cost,list(reversed(ids))
        i,j,k=u
        for pid,(heading,end,di,dj,edge_cost,cells) in enumerate(primitives):
            if heading!=k:continue
            if any(not(0<=i+a<height and 0<=j+b<width) or grid[(i+a)*width+j+b] for a,b in cells[1:]):continue
            v=(i+di,j+dj,end);candidate=cost+edge_cost
            if candidate<best.get(v,math.inf):best[v]=candidate;parent[v]=(u,pid);heapq.heappush(queue,(candidate,v))
    return math.inf,[]
def main(output):
    output.mkdir(parents=True,exist_ok=True);comparisons=0;profiled=0;inputs={};decisions={}
    for control in ['grid8','car16']:
        source=ROOT/f'cpp/experiments/frozen/{control}_model.txt';primitives,prefix=model(source)
        height,width=24,25;grid=bytearray(height*width);start=(2,2,0);goal=(20,21,0)
        initial_cost,ids=dijkstra(grid,height,width,primitives,start,goal);assert math.isfinite(initial_cost)
        # Prefer two cells of the SAME long primitive for the car16 frontier.
        u=start;trail=[];pair=None
        for pid in ids:
            _,end,di,dj,_,cells=primitives[pid]
            interior=[]
            for a,b in cells[1:]:
                q=(u[0]+a,u[1]+b)
                if q not in [start[:2],goal[:2]] and q not in interior:interior.append(q)
            trail+=interior
            if pair is None and len(interior)>=2:pair=interior[:2]
            u=(u[0]+di,u[1]+dj,end)
        if pair is None:pair=list(dict.fromkeys(trail))[:2]
        first,second=pair;queries=[];memo={}
        events=[(start,[],[]),(start,[goal[:2]],[]),(start,[],[goal[:2]]),
                (start,[first,second],[]),(start,[],[second]),(start,[],[second]),(start,[],[first]),
                (start,[start[:2]],[]),(start,[],[start[:2]]),(goal,[],[]),(goal,[goal[:2]],[]),(goal,[],[goal[:2]])]
        for s,blocks,opens in events:
            for i,j in blocks:grid[i*width+j]=1
            for i,j in opens:grid[i*width+j]=0
            key=(bytes(grid),s)
            if key not in memo:memo[key]=dijkstra(grid,height,width,primitives,s,goal)[0]
            queries.append((s,blocks,opens,memo[key]))
        assert queries[1][3]==math.inf and queries[2][3]==initial_cost
        assert queries[7][3]==math.inf and queries[8][3]==initial_cost
        assert queries[9][3]==0 and queries[10][3]==math.inf and queries[11][3]==0
        lines=[prefix,'1',f'"endpoint_and_frontier" {height} {width}',*['.'*width]*height,'1',f'"{control}_regression" "targeted" 0 {len(queries)}']
        for s,blocks,opens,cost in queries:
            lines.append(' '.join(map(str,[*s,*goal,cost if math.isfinite(cost) else -1,'"regression"','"regression"',len(blocks),len(opens)])))
            lines.append(' '.join(str(v) for q in blocks for v in q));lines.append(' '.join(str(v) for q in opens for v in q))
        target=output/(control+'.txt');target.write_text('\n'.join(lines)+'\n');inputs[control]=sha(target)
        profiles=[]
        for memory in [False,True]:
            out=output/(control+('_memory' if memory else '_normal')+'.csv')
            command=[str(HERE/'build'/('replay_memory' if memory else 'replay')),'--input',str(target),'--output',str(out),'--methods',','.join(METHODS),'--repeats','1']
            with out.with_suffix('.log').open('w') as f:subprocess.run(command,cwd=ROOT,check=True,stdout=f,stderr=subprocess.STDOUT)
            with out.open() as f:rows=list(csv.DictReader(f))
            assert len(rows)==len(queries)*len(METHODS)
            records=[]
            for row in rows:
                assert row['status']!='capped'
                expected=queries[int(row['query'])][3]
                if math.isfinite(expected):assert abs(float(row['cost'])-expected)<1e-6
                else:assert row['cost']==''
                if memory:assert 0<int(row['retained_heap_bytes'])<=int(row['peak_heap_bytes'])<2**48
                records.append({k:v for k,v in row.items() if not k.endswith('_s') and k not in ['peak_heap_bytes','retained_heap_bytes']})
            profiles.append(records)
        assert profiles[0]==profiles[1]
        decisions[control]=hashlib.sha256(json.dumps(profiles[0],sort_keys=True).encode()).hexdigest()
        comparisons+=len(profiles[0]);profiled+=len(profiles[1])
    result=dict(status='passed',comparisons=comparisons,profiled_rows=profiled,independent_snapshots=24,inputs_sha256=inputs,decisions_sha256=decisions)
    (output/'validation.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps(result))
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=HERE/'results/regression');main(p.parse_args().output)
