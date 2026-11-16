"""Frozen native-language comparison of MD-A* with all repository algorithms.

python -m mesha.md_benchmark --prepare
python -m mesha.md_benchmark --run --cohort original  # then mixed/validation/diagnostic
Every timed process is sequential. Historical costs are references only;
historical Python/C++ timings are never included in paired speedups.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import platform
import random
import sys
import time
from pathlib import Path

import numpy as np

from mesha.benchmark import environment,load_benchmark,load_named_maps,MAP_DIR
from mesha.deferred import compile_certificate
from mesha.incremental import make_planner
from mesha.maps import load_map,save_map
from mesha.mesh import build_mesh
from mesha.primitives import build_control_set
from mesha.search import search,trace_of
from mesha.selfcheck_deferred import validate_path

ROOT=Path(__file__).resolve().parents[1]
INPUT=ROOT/'data/benchmarks/md_astar.json'
OUT=ROOT/'results/md_astar'
MAIN=('lba','lazy_lba','mesha','mesh_parall','dstar_lattice','dstar_mesh','mpgaa','md_astar')
ABLATIONS=('md64','md_scan')
EXACT=set(MAIN)-{'mesh_parall'}
SEED=761116


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def path_result(grid,control,mesh,start,goal):
    result=search('lba',grid,control,start,goal,mesh,max_expansions=3_000_000,return_path=True,record_expanded=False)
    if result.capped:raise RuntimeError('reference search capped')
    if result.success:validate_path(grid,control,tuple(start),tuple(goal),result)
    return result


def select_original(benchmark):
    selected=[]
    for mi,info in enumerate(benchmark['maps']):
        pairs={}
        for x in benchmark['instances']:
            if x['map']==info['file']:pairs.setdefault(x['pair'],[]).append(x)
        ordered=sorted(pairs.values(),key=lambda a:(a[0]['pair_length'],a[0]['pair']))
        for k in range(6):
            variants=sorted(ordered[round(k*(len(ordered)-1)/5)],key=lambda a:a['id'])
            selected.append(variants[(mi+k)%len(variants)])
    assert len({x['id'] for x in selected})==24
    return selected


def prepare():
    if INPUT.exists():raise RuntimeError('Inputs are frozen; do not overwrite them')
    OUT.mkdir(parents=True,exist_ok=True)
    benchmark=load_benchmark();maps=load_named_maps(benchmark);control=build_control_set('car16');mesh=build_mesh(control)
    historical=json.loads((ROOT/'results/runs.json').read_text())
    expected={(x['id'],x['query']):x['cost'] for x in historical['records'] if x['algorithm']=='lba' and x['weight']==1}
    cases=[]
    selected=select_original(benchmark)
    for x in selected:
        queries=[dict(start=q['start'],goal=q['goal'],blocks=q['new_blocks'],opens=[],expected=expected[x['id'],qi],
                      category='initial' if qi==0 else 'increase_finite',event='original') for qi,q in enumerate(x['queries'])]
        cases.append(dict(id='original__'+x['id'],cohort='original',map=x['map'],map_cluster=x['map'],pair=x['pair'],queries=queries))
    for mi,info in enumerate(benchmark['maps']):
        roots=sorted([x for x in benchmark['instances'] if x['map']==info['file']],key=lambda x:(x['pair_length'],x['id']))
        for seed in [SEED,SEED+1]:
            root=roots[len(roots)//3+(seed-SEED)]
            modes=['fixed','reverse'] if seed==SEED else [['fixed','reverse'][mi%2]]
            for mode in modes:
                base=maps[info['file']];grid=base.copy();start=tuple(root['queries'][0]['start']);goal=tuple(root['queries'][0]['goal'])
                first=path_result(grid,control,mesh,start,goal);assert first.success and len(first.states)>2
                anchors=[start,first.states[1]];overlay=set();queries=[];rng=random.Random(seed+mi*101)
                old=first
                for ep in range(13):
                    here=anchors[(ep//3)%2] if mode=='reverse' else start
                    prior=None
                    if old.success and here in old.states:
                        index=old.states.index(here);prior=math.fsum(control.primitives[p].cost for p in old.prim_ids[index:])
                    changes=[];opened=[];event='initial'
                    if ep:
                        event='shock' if ep%4==0 and old.success else 'background'
                        if event=='shock':center=old.trace[len(old.trace)//2]
                        else:
                            while True:
                                center=(rng.randrange(1,grid.shape[0]-1),rng.randrange(1,grid.shape[1]-1))
                                if not base[center]:break
                        patch={(i,j) for i in range(max(0,center[0]-1),min(grid.shape[0],center[0]+2))
                               for j in range(max(0,center[1]-1),min(grid.shape[1],center[1]+2))
                               if not base[i,j] and (i,j) not in {a[:2] for a in anchors}|{goal[:2]}}
                        for q in sorted(overlay|patch):
                            value=q in patch
                            if bool(grid[q])!=value:
                                (changes if value else opened).append(q);grid[q]=value
                        overlay=patch
                    ref=path_result(grid,control,mesh,here,goal)
                    if ref.success and ref.cost==0:raise RuntimeError('finished-goal query')
                    category='initial' if not ep else 'disconnected' if not ref.success else 'off_reference' if old.success and prior is None else 'reconnected' if prior is None else 'increase_finite' if ref.cost>prior+1e-6 else 'improvement' if ref.cost<prior-1e-6 else 'unchanged'
                    queries.append(dict(start=here,goal=goal,blocks=changes,opens=opened,expected=ref.cost if ref.success else None,category=category,event=event))
                    old=ref
                cases.append(dict(id=f'mixed__{Path(info["file"]).stem}__{mode}__{seed}',cohort='mixed' if seed==SEED else 'validation',
                                  map=info['file'],map_cluster=info['file'],mode=mode,seed=seed,pair=root['pair'],queries=queries))
                print('prepared',cases[-1]['id'],flush=True)
    # Diagnostic family: no path selection by MD-A* time. Reverse motions use
    # the first state of a common MPGAA* optimal path, before any timing.
    theta=control.dirs.index((1,1))
    for size in [80,160]:
        grid=np.zeros((size,size),dtype=np.uint8);grid[[0,-1],:]=1;grid[:,[0,-1]]=1
        name=f'md_empty_{size}.map';save_map(MAP_DIR/name,grid)
        s=(12,12,theta);t=(size-13,size-13,theta)
        backend=make_planner('mpgaa',grid,control,mesh,s,t);initial=backend.plan();assert initial.success
        anchors=[s,initial.states[1]]
        for mode in ['fixed','reverse']:
            work=grid.copy();overlay=set();queries=[];rng=random.Random(SEED+size)
            for ep in range(13):
                here=anchors[(ep//3)%2] if mode=='reverse' else s
                blocks=[];opens=[]
                if ep:
                    a=size//6+rng.randrange(-2,3);b=size-size//6+rng.randrange(-2,3)
                    if ep%2:a,b=b,a
                    patch={(a+i,b+j) for i in [-1,0,1] for j in [-1,0,1]}
                    for q in sorted(overlay|patch):
                        value=q in patch
                        if bool(work[q])!=value:(blocks if value else opens).append(q);work[q]=value
                    overlay=patch
                ref=path_result(work,control,mesh,here,t)
                assert ref.success and ref.cost>0
                queries.append(dict(start=here,goal=t,blocks=blocks,opens=opens,expected=ref.cost,category='initial' if not ep else 'diagnostic',event='diagnostic'))
            cases.append(dict(id=f'diagnostic__{size}__{mode}',cohort='diagnostic',map=name,map_cluster=name,mode=mode,size=size,queries=queries))
    payload=dict(base_commit='cc58898',control='car16',selection='Original: six pair-length quantiles per map; one heading variant chosen by map/stratum parity, before MD-A* timings.',
                 shared_language='Python only; original floating primitive costs and maps; no imported C++ times.',
                 seed=SEED,methods=MAIN,ablations=ABLATIONS,repeats=3,cases=cases,
                 upstream_benchmark_sha256=sha(ROOT/'data/benchmarks/incremental_mesha.json'),upstream_results_sha256=sha(ROOT/'results/runs.json'))
    INPUT.write_text(json.dumps(payload,indent=1)+'\n')
    print('Frozen',len(cases),'cases;',sum(len(x['queries']) for x in cases),'snapshot records',flush=True)


def dstar_path(planner,control,mesh):
    cost,vertices=planner.extract_path()
    if not math.isfinite(cost):raise AssertionError('finite D* Lite label has no extractable path')
    ids=[]
    if planner.graph.name=='lattice':
        for u,v in zip(vertices,vertices[1:]):ids.append(control.between[u[2],v[0]-u[0],v[1]-u[1],v[2]])
    else:
        for u,v in zip(vertices,vertices[1:]):
            matches=[(c,pid) for di,dj,cfg,c,pid in mesh.successors[u[0]] if cfg==v[0] and (di,dj)==(v[1]-u[1],v[2]-u[2])]
            if not matches:raise AssertionError('unidentified mesh transition')
            _c,pid=min(matches)
            if pid>=0:ids.append(pid)
    # D* Lite keeps the current start in s_start, not the constructor field.
    if planner.graph.name=='lattice':start=tuple(planner.s_start)
    else:
        cfg,i,j=planner.s_start;start=(i,j,mesh.theta_of_config[cfg])
    states,_=trace_of(start,ids,control,include_trace=False)
    return cost,tuple(states),tuple(ids)


def run_case(case,method,control,mesh,base):
    clock=time.perf_counter()
    if method in ('lba','lazy_lba','mesha','mesh_parall'):
        planner=None;grid=base.copy()
    else:
        q=case['queries'][0];planner=make_planner(method,base,control,mesh,q['start'],q['goal'],max_expansions=3_000_000)
        grid=planner.graph.grid if method.startswith('dstar') else planner.grid
    setup=time.perf_counter()-clock;validation_grid=base.copy();rows=[]
    for qi,q in enumerate(case['queries']):
        start,goal=tuple(q['start']),tuple(q['goal']);blocks=tuple(map(tuple,q['blocks']));opens=tuple(map(tuple,q['opens']))
        c0=planner.graph.checked if method.startswith('dstar') else 0
        clock=time.perf_counter()
        if planner is None:
            for cell in blocks:grid[cell]=1
            for cell in opens:grid[cell]=0
            r=search(method,grid,control,start,goal,mesh,return_path=True,record_expanded=False,return_trace=False,max_expansions=3_000_000)
        else:
            r=planner.plan() if qi==0 else planner.replan(start,blocks,opens)
            if r.success and method.startswith('dstar'):
                path_cost,r.states,r.prim_ids=dstar_path(planner,control,mesh)
                if abs(path_cost-r.cost)>1e-6:raise AssertionError(('D* path cost',case['id'],qi,method,path_cost,r.cost))
                r.checked_cells=planner.graph.checked-c0
        elapsed=time.perf_counter()-clock
        if r.capped:raise RuntimeError(('capped',case['id'],qi,method))
        reference=q['expected']
        if r.success!=(reference is not None):raise AssertionError(('success',case['id'],qi,method))
        if r.success:
            if method!='mesh_parall' and abs(r.cost-reference)>1e-6:raise AssertionError(('cost',case['id'],qi,method,r.cost,reference))
            if r.cost<reference-1e-6:raise AssertionError('approximate method beat exact oracle')
        for cell in blocks:validation_grid[cell]=1
        for cell in opens:validation_grid[cell]=0
        if r.success:validate_path(validation_grid,control,start,goal,r)
        rows.append(dict(query=qi,cost=r.cost if r.success else None,time_s=elapsed,setup_s=setup if qi==0 else 0.0,
                         expansions=r.expansions,checked_cells=r.checked_cells,certified=bool(getattr(r,'certified',False)),
                         backend_calls=getattr(r,'backend_calls',1),activated_cells=getattr(r,'activated_cells',0),
                         deferred_cells=getattr(r,'deferred_cells',0),refined_cells=getattr(r,'refined_cells',0),
                         notify_probes=getattr(r,'notify_probes',0),category=q['category'],event=q['event'],
                         suboptimality=r.cost/reference if reference else None))
    del planner
    return rows


def run(cohort):
    OUT.mkdir(parents=True,exist_ok=True);payload=json.loads(INPUT.read_text());cases=[x for x in payload['cases'] if cohort=='all' or x['cohort']==cohort]
    prep=time.perf_counter();control=build_control_set('car16');mesh=build_mesh(control);certificate=compile_certificate(control)
    # Both adaptive methods use this immutable index. No algorithm-specific
    # mutable search state survives from one repeated episode to the next.
    from mesha.adaptive import dependency_groups
    dependency_groups(control)
    preparation=time.perf_counter()-prep
    hashes={str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'mesha').glob('*.py'))}
    hashes[str(INPUT.relative_to(ROOT))]=sha(INPUT)
    for name in {x['map'] for x in payload['cases']}:hashes[str((MAP_DIR/name).relative_to(ROOT))]=sha(MAP_DIR/name)
    envpath=OUT/'environment.json'
    if envpath.exists():assert json.loads(envpath.read_text())['sha256']==hashes,'Frozen benchmark source changed'
    else:
        env=environment();env.update(sha256=hashes,base_commit=payload['base_commit'],shared_preparation_s=preparation,
            certificate_compile_s=certificate.compile_s,certificate_alpha=certificate.alpha,certificate_correction=certificate.correction,
            workers=1,protocol='Sequential complete episodes; three randomized repeats; paths and edit processing included; validation outside timers; shared immutable model preparation reported separately.')
        envpath.write_text(json.dumps(env,indent=2)+'\n')
    raw=OUT/'raw.jsonl';completed={}
    if raw.exists():
        for line in raw.read_text().splitlines():
            row=json.loads(line);completed[row['id'],row['method'],row['repeat']]=row
    rng=random.Random(SEED+119);rng.shuffle(cases);started=time.perf_counter();runs=queries=0
    for case in cases:
        base=load_map(MAP_DIR/case['map'])
        methods=list(MAIN)+(list(ABLATIONS) if case['cohort'] in ('mixed','diagnostic') else [])
        for rep in range(3):
            order=methods[:];rng.shuffle(order)
            for method in order:
                key=case['id'],method,rep
                if key not in completed:
                    gc.collect()
                    rows=run_case(case,method,control,mesh,base)
                    previous=completed.get((case['id'],method,0))
                    if previous is not None:
                        fields=('cost','expansions','checked_cells','certified','backend_calls','activated_cells','deferred_cells','refined_cells')
                        signature=lambda rs:[tuple(r[k] for k in fields) for r in rs]
                        if signature(rows)!=signature(previous['rows']):
                            raise AssertionError(('non-deterministic counts',case['id'],method,rep))
                    entry=dict(id=case['id'],cohort=case['cohort'],method=method,repeat=rep,map=case['map'],rows=rows)
                    with raw.open('a') as f:f.write(json.dumps(entry,allow_nan=False)+'\n')
                    completed[key]=entry
                runs+=1;queries+=len(case['queries'])
        print(runs,'runs;',round(time.perf_counter()-started,1),'s;',case['id'],flush=True)
    (OUT/f'completion_{cohort}.json').write_text(json.dumps(dict(status='passed',runs=runs,queries=queries,cases=len(cases),cost_disagreements=0,seconds=time.perf_counter()-started),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--prepare',action='store_true');p.add_argument('--run',action='store_true');p.add_argument('--cohort',choices=['original','mixed','validation','diagnostic','all'],default='all');args=p.parse_args()
    if args.prepare:prepare()
    if args.run:run(args.cohort)
