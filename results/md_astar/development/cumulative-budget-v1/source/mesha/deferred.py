"""MD-A*: native Python mesh certificates and deferred known cost decreases.

The actual map and a restricted working map share the repository's floating
primitive costs and supercovers. MPGAA* is the same backend as the standalone
control in adaptive.py. See docs/md_astar/method.md for the correctness proof.
"""
from __future__ import annotations

import heapq
import math
import time
from dataclasses import dataclass
from functools import lru_cache

from mesha.adaptive import AdaptiveStats, MPGAA
from mesha.incremental import EPS
from mesha.mesh import build_mesh

INF = math.inf
DIRECTIONS = ((1,math.sqrt(2)-1), (math.sqrt(2)-1,1), (1,1-math.sqrt(2)),
              (math.sqrt(2)-1,-1), (-1,math.sqrt(2)-1), (1-math.sqrt(2),1),
              (-1,1-math.sqrt(2)), (1-math.sqrt(2),-1))


def _octile(i,j):
    a,b=abs(i),abs(j)
    return max(a,b)+(math.sqrt(2)-1)*min(a,b)


@dataclass(frozen=True)
class MeshCertificate:
    alpha: float
    mu: tuple
    correction: float
    compile_s: float

    def distance(self,a,b):
        return self.alpha*_octile(a[0]-b[0],a[1]-b[1])

    def bound(self,s,t,q,full=False):
        if not full:
            return self.distance(s,q)+self.distance(q,t)+self.correction
        return max(self.alpha*(a[0]*(q[0]-s[0])+a[1]*(q[1]-s[1])+
                               b[0]*(t[0]-q[0])+b[1]*(t[1]-q[1]))+self.mu[i][j]
                   for i,a in enumerate(DIRECTIONS) for j,b in enumerate(DIRECTIONS))


@lru_cache(maxsize=None)
def compile_certificate(control):
    """64 min-plus coefficients on one-primitive DAG, not flat enumeration.

    Completing edges go to separate sinks, never back to initial roots. Flat
    primitive enumeration is used only by the independent selfcheck.
    """
    clock=time.perf_counter()
    mesh=build_mesh(control)
    alpha=math.nextafter(min(p.cost/_octile(p.di,p.dj) for p in control.primitives
                             if p.di or p.dj),0.0)
    n=mesh.n_configs
    degree=[0]*n
    for edges in mesh.successors:
        for _di,_dj,v,_cost,pid in edges:
            if pid<0:degree[v]+=1
    order=[v for v in range(n) if not degree[v]]
    for u in order:
        for _di,_dj,v,_cost,pid in mesh.successors[u]:
            if pid<0:
                degree[v]-=1
                if not degree[v]:order.append(v)
    if len(order)!=n:raise ValueError('primitive mesh must be acyclic')
    f=[[INF]*8 for _ in range(n)];b=[[INF]*8 for _ in range(n)]
    for root in mesh.initial_of_theta:f[root]=[0.0]*8
    for u in order:
        for di,dj,v,cost,pid in mesh.successors[u]:
            if pid<0:
                for a,(ai,aj) in enumerate(DIRECTIONS):
                    f[v][a]=min(f[v][a],f[u][a]+cost-alpha*(ai*di+aj*dj))
    for u in reversed(order):
        for di,dj,v,cost,pid in mesh.successors[u]:
            for a,(ai,aj) in enumerate(DIRECTIONS):
                after=0.0 if pid>=0 else b[v][a]
                b[u][a]=min(b[u][a],cost-alpha*(ai*di+aj*dj)+after)
    mu=[[INF]*8 for _ in range(8)]
    for u in range(n):
        for a in range(8):
            for z in range(8):mu[a][z]=min(mu[a][z],f[u][a]+b[u][z])
    for u,edges in enumerate(mesh.successors):
        for di,dj,_v,cost,pid in edges:
            if pid>=0:
                for a,(ai,aj) in enumerate(DIRECTIONS):
                    end=f[u][a]+cost-alpha*(ai*di+aj*dj)
                    for z in range(8):mu[a][z]=min(mu[a][z],end)
    # A conservative fixed rounding margin; ambiguous comparisons below also
    # activate cells instead of certifying equality. No primitive is quantized.
    margin=EPS*(1+max(p.cost for p in control.primitives)+max(len(p.cells) for p in control.primitives))
    mu=tuple(tuple(x-margin for x in row) for row in mu)
    return MeshCertificate(alpha,mu,min(map(min,mu)),time.perf_counter()-clock)


class _Suffix:
    def __init__(self,control):
        self.control=control
        self.states=self.ids=()
        self.index={};self.last={};self.blocked=set();self.bad=[];self.remaining=()

    def install(self,result):
        self.states,self.ids=result.states,result.prim_ids
        self.index={s:i for i,s in enumerate(self.states)}
        self.last={};self.blocked=set();self.bad=[]
        remaining=[0.0]*(len(self.ids)+1)
        for i in range(len(self.ids)-1,-1,-1):remaining[i]=remaining[i+1]+self.control.primitives[self.ids[i]].cost
        self.remaining=tuple(remaining)
        for i,pid in enumerate(self.ids):
            u=self.states[i]
            for a,b in self.control.primitives[pid].cells:self.last[u[0]+a,u[1]+b]=i

    def update(self,blocks,opens):
        for q in blocks:
            if q in self.last and q not in self.blocked:
                self.blocked.add(q);heapq.heappush(self.bad,(-self.last[q],q))
        for q in opens:self.blocked.discard(q)
        if len(self.bad)>2*len(self.blocked)+64:
            self.bad=[(-self.last[q],q) for q in self.blocked];heapq.heapify(self.bad)

    def position(self,start):
        at=self.index.get(start)
        while self.bad and self.bad[0][1] not in self.blocked:heapq.heappop(self.bad)
        return at if at is not None and (not self.bad or -self.bad[0][0]<at) else None


class MeshDeferred:
    """MPGAA* wrapper with zero, one or two backend calls per uncapped query."""
    def __init__(self,grid,control,start,goal,max_expansions=2_000_000,*,variant='md_astar',certificate=None):
        if variant not in ('md_astar','md64','md_scan'):raise ValueError(variant)
        self.grid=grid.copy();self.working=grid.copy()
        self.control=control;self.start=tuple(start);self.goal=tuple(goal)
        self.variant=variant
        self.certificate=certificate or compile_certificate(control)
        self.backend=MPGAA(self.working,control,start,goal,max_expansions,copy_grid=False)
        self.suffix=_Suffix(control)
        self.deferred={};self.waiting=[];self.blocks=set();self.opens=set()
        self.travel=0.0;self.previous=None;self.no_path_start=None

    def _bound(self,s,q):
        return self.certificate.bound(s,self.goal,q,self.variant=='md64')

    def _activate(self,q):
        if q not in self.deferred:return 0
        del self.deferred[q]
        self.working[q]=0
        self.blocks.discard(q);self.opens.add(q)
        return 1

    def _release(self,start,upper):
        activated=refined=0
        if self.variant=='md_scan':
            for q in list(self.deferred):
                refined+=1
                bound=self._bound(start,q)
                if not math.isfinite(upper) or bound<=upper+EPS*(1+abs(upper)+abs(bound)):
                    activated+=self._activate(q)
            return activated,refined
        threshold=upper+self.travel
        while self.waiting:
            key,q=self.waiting[0]
            if self.deferred.get(q)!=key:heapq.heappop(self.waiting);continue
            guard=EPS*(1+abs(key)+abs(threshold)) if math.isfinite(upper) else 0.0
            if math.isfinite(upper) and key>threshold+guard:break
            heapq.heappop(self.waiting)
            if math.isfinite(upper):
                fresh=self._bound(start,q)+self.travel;refined+=1
                guard=EPS*(1+abs(fresh)+abs(threshold))
                if fresh>threshold+guard:
                    self.deferred[q]=fresh;heapq.heappush(self.waiting,(fresh,q));continue
            activated+=self._activate(q)
        return activated,refined

    def _call(self,start):
        result=self.backend.replan(start,sorted(self.blocks),sorted(self.opens))
        self.blocks.clear();self.opens.clear()
        return result

    def plan(self):return self.replan(self.start,(),())

    def replan(self,new_start,new_blocks=(),new_opens=()):
        clock=time.perf_counter();start=tuple(new_start)
        blocks,opens=tuple(map(tuple,new_blocks)),tuple(map(tuple,new_opens))
        if set(blocks)&set(opens):raise ValueError('contradictory cell changes')
        h,w=self.grid.shape
        for q in blocks+opens:
            if not (0<=q[0]<h and 0<=q[1]<w):raise ValueError('cell outside grid')
        blocks=tuple(q for q in blocks if not self.grid[q])
        opens=tuple(q for q in opens if self.grid[q])
        if self.previous is not None and start[:2]!=self.previous[:2]:
            distance=self.certificate.distance(start,self.previous)
            self.travel+=distance+EPS*(1+distance)
        self.previous=start;self.start=start
        self.suffix.update(blocks,opens)
        for q in blocks:
            self.grid[q]=1;self.deferred.pop(q,None)
            self.opens.discard(q)
            if not self.working[q]:self.working[q]=1;self.blocks.add(q)
        for q in opens:
            self.grid[q]=0
            key=self._bound(start,q)+self.travel
            self.deferred[q]=key;heapq.heappush(self.waiting,(key,q))
        if len(self.waiting)>2*len(self.deferred)+64:
            self.waiting=[(key,q) for q,key in self.deferred.items()];heapq.heapify(self.waiting)
        activated=refined=0;calls=[];certified=False
        at=self.suffix.position(start)
        endpoints_free=(0<=start[0]<h and 0<=start[1]<w and not self.grid[start[:2]] and not self.grid[self.goal[:2]])
        if start==self.no_path_start and not opens:
            cost,states,ids=INF,(),();certified=True
        elif at is not None and endpoints_free:
            upper=self.suffix.remaining[at]
            activated,refined=self._release(start,upper)
            if not activated:
                cost,states,ids=upper,self.suffix.states[at:],self.suffix.ids[at:];certified=True
            else:
                for u,pid in zip(self.suffix.states[at:],self.suffix.ids[at:]):
                    for a,b in self.control.primitives[pid].cells:activated+=self._activate((u[0]+a,u[1]+b))
                result=self._call(start);calls.append(result)
                if not result.capped and result.cost>upper+1e-6:raise AssertionError('working map lost incumbent')
                cost,states,ids=result.cost,result.states,result.prim_ids
        else:
            result=self._call(start);calls.append(result)
            if not result.capped:
                activated,refined=self._release(start,result.cost)
                if activated:
                    upper=result.cost;result=self._call(start);calls.append(result)
                    if not result.capped and result.cost>upper+1e-6:raise AssertionError('decreases raised cost')
            cost,states,ids=result.cost,result.states,result.prim_ids
        capped=any(r.capped for r in calls)
        result=AdaptiveStats(cost<INF and not capped,cost,sum(r.expansions for r in calls),
                             sum(r.checked_cells for r in calls),time.perf_counter()-clock,capped,
                             states=states,prim_ids=ids,certified=certified,backend_calls=len(calls),
                             activated_cells=activated,deferred_cells=len(self.deferred),refined_cells=refined,
                             notify_probes=sum(r.notify_probes for r in calls))
        if calls:
            if not capped:self.suffix.install(result)
            else:self.suffix.install(AdaptiveStats(False,INF,0,0,0.0,True))
            self.no_path_start=start if cost==INF and not capped else None
        return result
