#!/usr/bin/env python3
"""Freeze navigation roots, full parameter grids and per-phase budget rules."""
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'cpp/experiments'))
from prepare import write_suite,Reference
from mesha.maps import load_map
from mesha.primitives import build_control_set,_assemble

KS=[2,4,8,16,32,64]
CRS=[1,5,10,15,20,30]
RADII=[8,16,32,64]
ANCHORS={(2,5),(8,10),(32,20),(64,30)}
METHODS=['lba','lazy_lba','mesha','mesh_parall','dstar_lattice','dstar_mesh','mpgaa','md_astar','md64','md_scan','lba_reuse','prefix_positive','cmesh_dstar','suffix_mesh','boundary_mesh']


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def seed_for(*parts):return int(hashlib.sha256(':'.join(map(str,parts)).encode()).hexdigest()[:16],16)


def write_specs(path,cases):
    with path.open('w') as f:
        f.write(f'NAV_SPEC 1 {len(cases)}\n')
        for c in cases:
            p=c['params']
            f.write(' '.join([json.dumps(c['id']),c['kind'],str(p.get('radius',0)),str(p.get('k',0)),str(p.get('cr',0)),str(p.get('n',0)),
                              str(p['max_moves']),str(c['timing_repeats']),str(c['world_seed']),str(int(c['trace']))])+'\n')


def grid_root(grid,server,seed,label):
    rng=np.random.default_rng(seed_for('root',label,seed));free=np.argwhere(grid==0)
    large=min(grid.shape)>=128
    for trial in range(1500):
        a,b=free[rng.integers(len(free),size=2)];span=int(np.max(np.abs(a-b)))
        if not ((144<=span<=260) if large else (25<=span<=max(grid.shape))):continue
        start=(*map(int,a),0);goal=(*map(int,b),0);answer=server.plan(grid,start,goal)
        if answer['cost'] is not None and len(answer['ids'])<=400:
            return start,goal,answer,dict(selection_trial=trial,geometric_chebyshev=span,initial_moves=len(answer['ids']),
                                          long_route_stratum=large,guaranteed_minimum_moves=span)
    raise RuntimeError('No reference-solvable root in prespecified stratum: '+label)


def main():
    out=HERE/'frozen';out.mkdir(exist_ok=True)
    if (out/'manifest.json').exists():raise RuntimeError('Already frozen; do not overwrite measured data')
    old_dir=ROOT/'cpp/experiments/frozen';old=json.loads((old_dir/'car16_replay.contexts.json').read_text())
    car=build_control_set('car16')
    grid8=_assemble('grid8',1,((0,1),),[(0,0,((0,0),(i,j)),math.hypot(i,j)) for i,j in [(0,1),(1,0),(0,-1),(-1,0),(1,1),(1,-1),(-1,1),(-1,-1)]])
    records=[];all_cases=[];maps={};roots={};files=[]
    for c in old['cases']:
        if c['family']=='on_path' and 'main' in c['panels']:
            key=(c['map'],c['seed'])
            if key in roots:continue
            source=ROOT/c['source'];g=load_map(source)
            if c.get('crop'):
                i,j,n=c['crop'];g=g[i:i+n,j:j+n].copy()
            info={k:c[k] for k in ['map','map_family','shape','source','source_sha256','original_shape','crop','truth_density'] if k in c}
            maps[c['map']]=(g,info);roots[key]=(tuple(c['start']),tuple(c['goal']),c['truth_optimum'],len(c['example_ids']))
    for model in [car,grid8]:
        model_path=out/(model.name+'_model.txt');write_suite(model_path,model,[]);files.append(model_path)
    def case(info,grid,control,start,goal,optimum,seed,kind,params,initial_moves,long_stratum=False):
        suffix=f'r{params["radius"]}' if kind=='unknown' else f'k{params["k"]}__cr{params["cr"]}__n{params["n"]}'
        c=dict(**info,control=control.name,seed=seed,start=start,goal=goal,initial_optimum=optimum,initial_moves=initial_moves,
               guaranteed_minimum_moves=max(abs(start[0]-goal[0]),abs(start[1]-goal[1])) if control.name=='grid8' else None,
               long_route_stratum=long_stratum,kind=kind,params=params,
               world_seed=seed_for('world',control.name,info['map'],seed),
               timing_repeats=3 if kind=='unknown' or (params['k'],params['cr']) in ANCHORS else 1,
               trace=seed in [48101,68101] and ((kind=='unknown' and params['radius'] in [8,64]) or (kind=='dynamic' and (params['k'],params['cr']) in {(8,10),(64,30)})),
               family='navigation_'+kind,_initial=grid,
               queries=[dict(start=start,goal=goal,blocks=[],opens=[],expected=optimum,category='truth_only',event=kind)])
        c['id']=f'{control.name}__{info["map"]}__{kind}__s{seed}__{suffix}'
        if kind=='dynamic':
            target=int(math.floor(grid.size*params['cr']/200+.5));actual=min(target,int(grid.sum()),grid.size-int(grid.sum())-2)
            c['requested_half']=target;c['actual_half']=actual;c['potential_actual_cr']=200*actual/grid.size;c['budget_clamped']=actual<target
        return c
    for name,(g,info) in maps.items():
        static=[];dynamic=[]
        for seed in [48101,48102]:
            s,t,opt,initial_moves=roots[name,seed]
            for radius in RADII:static.append(case(info,g,car,s,t,opt,seed,'unknown',dict(radius=radius,max_moves=512),initial_moves))
            for k in KS:
                for cr in CRS:dynamic.append(case(info,g,car,s,t,opt,seed,'dynamic',dict(k=k,n=k,cr=cr,max_moves=384),initial_moves))
        for kind,cases in [('unknown',static),('dynamic',dynamic)]:
            path=out/f'car16_{name}_{kind}.txt';record=write_suite(path,car,cases);spec=path.with_suffix('.specs.txt');write_specs(spec,cases)
            record.update(control='car16',map=name,kind=kind,specs=str(spec.relative_to(ROOT)),specs_sha256=digest(spec),
                          contexts=str(path.with_suffix('.contexts.json').relative_to(ROOT)),timed_runs=sum(c['timing_repeats'] for c in cases)*len(METHODS),
                          memory_cases=[c['id'] for c in cases if c['timing_repeats']==3])
            records.append(record);all_cases+=cases;print('prepared',path.name,record['cases'],flush=True)
    grid_maps=[]
    for name,relative in [('Berlin','data/maps/Berlin_2_256.map'),('AR0700','data/maps/AR0700SR.map'),('arena','cpp/experiments/maps/arena.map'),
                          ('MA_room512','cpp/experiments/maps/16room_000.map'),('MA_random512','cpp/experiments/maps/random512-10-0.map'),('MA_maze512','cpp/experiments/maps/maze512-16-0.map')]:
        path=ROOT/relative;g=load_map(path);grid_maps.append((g,dict(map=name,shape=list(g.shape),truth_density=float(g.mean()),source=relative,source_sha256=digest(path),map_family='published_full')))
    for density in [10,20,30,40]:
        path=ROOT/f'cpp/experiments/maps/random50_p{density}.map';g=load_map(path)
        grid_maps.append((g,dict(map=f'random50_p{density}',shape=list(g.shape),truth_density=float(g.mean()),source=str(path.relative_to(ROOT)),source_sha256=digest(path),map_family='paper_random50')))
    reference=Reference(out/'grid8_model.txt')
    try:
        for g,info in grid_maps:
            cases=[]
            for seed in [68101,68102]:
                s,t,answer,selection=grid_root(g,reference,seed,info['map'])
                for k in KS:
                    for cr in CRS:
                        c=case(info,g,grid8,s,t,answer['cost'],seed,'dynamic',dict(k=k,n=k,cr=cr,max_moves=512),len(answer['ids']),selection['long_route_stratum'])
                        c['root_selection']=selection;cases.append(c)
            path=out/f'grid8_{info["map"]}_dynamic.txt';record=write_suite(path,grid8,cases);spec=path.with_suffix('.specs.txt');write_specs(spec,cases)
            record.update(control='grid8',map=info['map'],kind='dynamic',specs=str(spec.relative_to(ROOT)),specs_sha256=digest(spec),
                          contexts=str(path.with_suffix('.contexts.json').relative_to(ROOT)),timed_runs=sum(c['timing_repeats'] for c in cases)*len(METHODS),
                          memory_cases=[c['id'] for c in cases if c['timing_repeats']==3])
            records.append(record);all_cases+=cases;print('prepared',path.name,record['cases'],flush=True)
    finally:reference.close()
    # Build and freeze the geometric arc-depth stencils before candidate timings.
    for control in ['car16','grid8']:
        model=out/f'{control}_model.txt';visibility=out/f'{control}_visibility.txt'
        if not visibility.exists():subprocess.run([str(HERE/'build/experiment'),'--input',str(model),'--build-visibility',str(visibility)],check=True)
        files.append(visibility)
    sources=[HERE/p for p in ['bench.cpp','factory.hpp','visibility.hpp','environment.hpp','Makefile','prepare.py','run_all.py','test_protocol.cpp']]
    sources += [ROOT/'cpp/experiments/memory.hpp',ROOT/'cpp/experiments/dstar_boundary.hpp',ROOT/'cpp/mesh_variants/variants.hpp',*sorted((ROOT/'cpp/include/ima').glob('*.hpp'))]
    sources += [ROOT/p for p in ['cpp/experiments/prepare.py','mesha/primitives.py','mesha/mesh.py','mesha/maps.py']]
    for r in records:r['contexts_sha256']=digest(ROOT/r['contexts'])
    manifest=dict(status='frozen',methods=METHODS,ks=KS,change_rates=CRS,static_radii=RADII,n_equals_k=True,
                  budget_policy='Clamp equally in both directions to the pre-phase blocked/free pools; report actual cr.',
                  visibility='Obstacle-free primitive-arc depth; union of collision footprints, clipped to map. Grid8 equals a Chebyshev n-ball.',
                  dynamics='Pre-phase pools, protected current cell and fixed goal. Common phase priorities; protection makes worlds policy-coupled.',
                  repeat_policy='Three timing repeats for all static worlds and prespecified dynamic anchors; one broad timing pass elsewhere. One separate allocation repeat on the three-repeat subset.',
                  anchors=sorted(ANCHORS),cap=1000000,records=records,
                  static_cases=sum(c['kind']=='unknown' for c in all_cases),dynamic_cases=sum(c['kind']=='dynamic' for c in all_cases),
                  timed_runs=sum(r['timed_runs'] for r in records),memory_runs=sum(len(r['memory_cases'])*len(METHODS) for r in records),
                  source_sha256={str(p.relative_to(ROOT)):digest(p) for p in sources},
                  auxiliary_sha256={str(p.relative_to(ROOT)):digest(p) for p in files})
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print('Frozen',manifest['timed_runs'],'timed and',manifest['memory_runs'],'allocation runs',flush=True)


if __name__=='__main__':main()
