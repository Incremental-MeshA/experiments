#!/usr/bin/env python3
"""Freeze the comparison plan before collecting any candidate timings."""
import hashlib
import json
import shlex
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
PRIMARY=['lba','lba_reuse','mpgaa','md_astar','boundary_mesh','boundary_mpgaa','selective_mpgaa','delta_mpgaa','policy_mpgaa']
ABLATIONS=['selective_no_prune','selective_geom']
ANCHORS={(2,5),(8,10),(32,20),(64,30)}
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    dest=HERE/'frozen';dest.mkdir(exist_ok=True)
    if (dest/'manifest.json').exists():raise RuntimeError('Manifest exists; do not replace frozen inputs')
    plan=[];contexts={};files={}
    def register(p):
        path=str(p.relative_to(ROOT));files[path]=digest(p);return path
    for control in ['car16','grid8']:
        native=ROOT/f'cpp/experiments/frozen/{control}_replay.txt';context=native.with_suffix('.contexts.json')
        methods=PRIMARY+ABLATIONS+(['octile_reuse'] if control=='grid8' else [])
        path=register(native);register(context)
        cs=json.loads(context.read_text())['cases']
        contexts.update({c['id']:dict(c,cohort='replay',control=control) for c in cs})
        plan.append(dict(name='replay_'+control,mode='replay',input=path,methods=methods,cases=len(cs)))
    for control,radii in [('car16',[8,16]),('grid8',[1,4,8])]:
        for radius in radii:
            native=ROOT/f'cpp/experiments/frozen/{control}_missions_r{radius}.txt';context=native.with_suffix('.contexts.json')
            path=register(native);register(context);cs=json.loads(context.read_text())['cases']
            contexts.update({c['id']:dict(c,cohort='mission',control=control) for c in cs})
            plan.append(dict(name=f'mission_{control}_r{radius}',mode='mission',input=path,methods=PRIMARY+(['octile_reuse'] if control=='grid8' else []),
                             radius=radius,max_steps=160 if control=='car16' else 256,cases=len(cs)))
    old=ROOT/'cpp/navigation_sweeps/frozen'
    for source in sorted(old.glob('*.specs.txt')):
        stem=source.name.removesuffix('.specs.txt');control=stem.split('_',1)[0];kind=stem.rsplit('_',1)[1]
        selected=[];ids=set()
        for line in source.read_text().splitlines()[1:]:
            fields=shlex.split(line);radius,k,cr=map(int,fields[2:5])
            if (kind=='dynamic' and (k,cr) in ANCHORS) or (kind=='unknown' and radius in [16,64]):
                selected.append(line);ids.add(fields[0])
        if not selected:continue
        specs=dest/(stem+'.specs.txt');specs.write_text(f'NAV_SPEC 1 {len(selected)}\n'+'\n'.join(selected)+'\n')
        context=old/(stem+'.contexts.json');cs=[c for c in json.loads(context.read_text())['cases'] if c['id'] in ids]
        assert len(cs)==len(ids)
        contexts.update({c['id']:dict(c,cohort='navigation_'+kind,control=control) for c in cs})
        job=dict(name='navigation_'+stem,mode='navigation',input=register(old/(stem+'.txt')),specs=register(specs),cases=len(ids),
                 methods=PRIMARY+(['octile_reuse'] if control=='grid8' else []))
        register(context);register(source)
        if kind=='dynamic':job['visibility']=register(old/(control+'_visibility.txt'))
        plan.append(job)
    (dest/'contexts.json').write_text(json.dumps(contexts,ensure_ascii=False,indent=1)+'\n');register(dest/'contexts.json')
    sources=[]
    for directory in ['cpp/include/ima','cpp/mesh_variants','cpp/navigation_controls','cpp/navigation_sweeps','cpp/mpgaa_mesh']:
        for p in (ROOT/directory).glob('*.hpp'):sources.append(p)
    sources.extend(ROOT/p for p in ['cpp/experiments/memory.hpp','cpp/experiments/dstar_boundary.hpp','cpp/mpgaa_mesh/replay.cpp',
                                   'cpp/mpgaa_mesh/navigation.cpp','cpp/mpgaa_mesh/Makefile','cpp/mpgaa_mesh/test.cpp'])
    manifest=dict(version=1,base_commit='691b8f0',repeats=3,cap=1000000,seed=48101,primary_methods=PRIMARY,ablations=ABLATIONS,
                  anchors=sorted(ANCHORS),plan=plan,files=files,sources={str(p.relative_to(ROOT)):digest(p) for p in sorted(set(sources))},
                  protocol='Complete frozen 186 replay cases and 40 missions; dynamic navigation: all 16 maps, two roots, four prespecified anchors (n=k); unknown car16: all six maps, two roots, radii 16 and 64. Three randomized serial repeats. Separate one-repeat allocation pass on every case. Replay ablations only. No previous timings reused.')
    manifest['timed_runs']=sum(j['cases']*len(j['methods'])*3 for j in plan)
    manifest['memory_runs']=sum(j['cases']*len(j['methods']) for j in plan)
    (dest/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({k:manifest[k] for k in ['timed_runs','memory_runs','protocol']},ensure_ascii=False))

if __name__=='__main__':main()
