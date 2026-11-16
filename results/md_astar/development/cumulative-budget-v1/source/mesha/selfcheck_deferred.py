"""Independent Dijkstra, paths, coefficient algebra and dynamic regression tests."""
from __future__ import annotations

import heapq
import json
import math
import random
from pathlib import Path

import numpy as np

from mesha.adaptive import MPGAA
from mesha.deferred import DIRECTIONS, MeshDeferred, compile_certificate
from mesha.incremental import make_planner
from mesha.mesh import build_mesh
from mesha.primitives import _assemble, build_control_set

ROOT=Path(__file__).resolve().parents[1]


def oracle(grid,control,start,goal):
    """Dijkstra with no planner, graph adapter, heuristic or edge cache."""
    h,w=grid.shape
    if any(not (0<=x[0]<h and 0<=x[1]<w) or grid[x[:2]] for x in (start,goal)):
        return math.inf
    distances={start:0.0};heap=[(0.0,start)]
    while heap:
        cost,u=heapq.heappop(heap)
        if cost!=distances[u]:continue
        if u==goal:return cost
        for pid in control.by_theta[u[2]]:
            p=control.primitives[pid]
            cells=[(u[0]+a,u[1]+b) for a,b in p.cells[1:]]
            if any(not (0<=i<h and 0<=j<w) or grid[i,j] for i,j in cells):continue
            v=(u[0]+p.di,u[1]+p.dj,p.end_theta);candidate=cost+p.cost
            if candidate<distances.get(v,math.inf):
                distances[v]=candidate;heapq.heappush(heap,(candidate,v))
    return math.inf


def validate_path(grid,control,start,goal,result):
    if not result.success:
        assert not result.prim_ids
        return
    u=start;states=[u]
    assert not grid[start[:2]] and not grid[goal[:2]]
    for pid in result.prim_ids:
        p=control.primitives[pid];assert p.start_theta==u[2]
        for a,b in p.cells:
            i,j=u[0]+a,u[1]+b
            assert 0<=i<grid.shape[0] and 0<=j<grid.shape[1] and not grid[i,j]
        u=(u[0]+p.di,u[1]+p.dj,p.end_theta);states.append(u)
    assert u==goal and tuple(states)==tuple(result.states)
    assert abs(math.fsum(control.primitives[x].cost for x in result.prim_ids)-result.cost)<1e-6


def coefficient_audit(control):
    cert=compile_certificate(control);mu=cert.mu;directions=DIRECTIONS
    occurrences=[(p.cost,p.di,p.dj,a,b) for p in control.primitives for a,b in p.cells]
    margin=1e-9*(1+max(p.cost for p in control.primitives)+max(len(p.cells) for p in control.primitives))
    for i,a in enumerate(directions):
        for j,b in enumerate(directions):
            direct=min(C-cert.alpha*(a[0]*r+a[1]*c+b[0]*(di-r)+b[1]*(dj-c))
                       for C,di,dj,r,c in occurrences)
            assert abs(mu[i][j]+margin-direct)<1e-8,(control.name,i,j)
    rng=random.Random(761113)
    for _ in range(128):
        s,t,q=[(rng.randrange(-40,41),rng.randrange(-40,41)) for _ in range(3)]
        exact=min(cert.distance(s,(q[0]-a,q[1]-b))+C+cert.distance((q[0]-a+di,q[1]-b+dj),t)
                  for C,di,dj,a,b in occurrences)
        scalar=cert.bound(s,t,q);full=cert.bound(s,t,q,True)
        assert scalar<=full+1e-9 and full<=exact+1e-8
    return dict(configurations=build_mesh(control).n_configs,primitives=len(control),alpha=cert.alpha,
                correction=cert.correction,coefficient_checks=64,random_bound_checks=128)


def episode(control,grid,start,goal,steps,include_dstar=False,audit=True):
    kinds=['mpgaa','md_astar','md64','md_scan']
    if include_dstar:kinds+=['dstar_lattice','dstar_mesh']
    mesh=build_mesh(control);planners={k:make_planner(k,grid,control,mesh,start,goal) for k in kinds}
    current=grid.copy();results=[]
    for qi,(here,blocks,opens) in enumerate(steps):
        for q in blocks:current[q]=1
        for q in opens:current[q]=0
        reference=oracle(current,control,here,goal)
        snapshot={}
        for kind,p in planners.items():
            r=p.plan() if qi==0 else p.replan(here,blocks,opens)
            assert not r.capped
            assert r.success==math.isfinite(reference),(kind,qi,reference,r.cost)
            if r.success:assert abs(r.cost-reference)<1e-6,(kind,qi,reference,r.cost)
            if hasattr(r,'prim_ids'):validate_path(current,control,here,goal,r)
            if audit and isinstance(p,MPGAA):p.audit()
            if audit and isinstance(p,MeshDeferred):p.backend.audit()
            snapshot[kind]=r
        results.append(snapshot)
    return len(steps)*len(kinds),results


def main():
    comparisons=episodes=0;algebra={}
    for name in ['car16','legacy8']:
        control=build_control_set(name);algebra[name]=coefficient_audit(control)
        grid=np.zeros((26,30),dtype=np.uint8)
        for heading in range(control.n_theta):
            s=(12,12,heading);p=control.primitives[control.by_theta[heading][0]]
            t=(12+p.di,12+p.dj,p.end_theta)
            n,_=episode(control,grid,s,t,[(s,(),())]);comparisons+=n;episodes+=1
        s=(12,4,0);t=(12,25,0)
        wall=grid.copy();wall[:,15]=1
        steps=[(s,(),()),(s,(),((12,15),)),((12,5,0),((12,15),),()),
               (s,(),((12,15),)),(s,(),((12,15),))]
        n,_=episode(control,wall,s,t,steps,True);comparisons+=n;episodes+=len(steps)
        rng=random.Random(76116)
        for seed in range(5):
            work=np.zeros((22,28),dtype=np.uint8);work[3:7,13]=1
            s=(12,3,0);t=(12,24,0);steps=[(s,(),())]
            for k in range(9):
                cell=(rng.randrange(2,20),rng.randrange(7,22))
                here=s if k%3 else (12,4,0)
                steps.append((here,(cell,) if k%2==0 else (),() if k%2==0 else (cell,)))
            n,_=episode(control,work,s,t,steps,True);comparisons+=n;episodes+=len(steps)
        # Blocked endpoints and a long lazy-deletion history exercise MD/MPGAA,
        # while the original D* Lite API assumes endpoints are always free.
        steps=[(s,(),()),(s,(s[:2],),()),(s,(),(s[:2],)),(s,(t[:2],),()),(s,(),(t[:2],))]
        n,_=episode(control,work,s,t,steps);comparisons+=n;episodes+=len(steps)
        print('verified',name,comparisons,'comparisons',flush=True)
    raw=[(0,0,((0,0),d),1.0) for d in [(0,1),(1,0),(0,-1),(-1,0)]]
    toy=_assemble('toy',1,((0,1),),raw)
    g=np.ones((12,18),dtype=np.uint8)
    for row in [2,5,10]:g[row,2:16]=0
    for col in [2,15]:g[2:11,col]=0
    g[2,8]=1;s=(5,2,0);t=(5,15,0)
    n,out=episode(toy,g,s,t,[(s,(),()),(s,(),((2,8),)),(s,((5,8),),())],True)
    comparisons+=n;episodes+=3
    assert [r['md_astar'].cost for r in out]==[13.0,13.0,19.0]
    assert out[1]['md_astar'].certified and out[1]['md_astar'].deferred_cells==1
    assert out[2]['md_astar'].backend_calls==2 and out[2]['md_astar'].activated_cells==1
    empty=np.zeros((12,18),dtype=np.uint8);steps=[(s,(),())]
    for i in range(160):
        here=(5,3,0) if i%4<2 else s
        steps.append((here,((10,7),) if i%2==0 else (),() if i%2==0 else ((10,7),)))
    n,_=episode(toy,empty,s,t,steps);comparisons+=n;episodes+=len(steps)
    result=dict(status='passed',oracle_snapshots=episodes,comparisons=comparisons,algebra=algebra,
                checks=['independent Dijkstra','all primitive cells and headings','cuts and reopening unseen D* sources',
                        'MD-A* two-call reactivation counterexample','idempotent updates','blocked endpoints',
                        'moving/reversing start','lazy heap deletion over 160 updates','64 mesh coefficients versus flat enumeration'])
    out=ROOT/'results/md_astar';out.mkdir(parents=True,exist_ok=True)
    (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
