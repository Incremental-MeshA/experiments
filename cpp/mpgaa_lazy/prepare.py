#!/usr/bin/env python3
"""Freeze the complete comparison before collecting any candidate timings."""
import hashlib
import json
import shlex
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
NEW=['stamp_mpgaa','batch_mpgaa','witness_mpgaa']
CONTROL=['mpgaa','lba_reuse','md_astar','boundary_mpgaa','selective_mpgaa','delta_mpgaa','policy_mpgaa']
ABLATIONS=['stamp_cell','batch_scan']
ANCHORS={(2,5),(32,20)}
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    dest=HERE/'frozen';dest.mkdir(exist_ok=True)
    if (dest/'manifest.json').exists():raise RuntimeError('Manifest exists; do not overwrite measured inputs')
    plan=[];contexts={};files={}
    def register(p):
        key=str(p.relative_to(ROOT));files[key]=digest(p);return key
    for control in ['car16','grid8']:
        native=ROOT/f'cpp/experiments/frozen/{control}_replay.txt';context=native.with_suffix('.contexts.json')
        methods=CONTROL+NEW+ABLATIONS+(['octile_reuse'] if control=='grid8' else [])
        path=register(native);register(context);cs=json.loads(context.read_text())['cases']
        contexts.update({c['id']:dict(c,cohort='replay',control=control) for c in cs})
        plan.append(dict(name='replay_'+control,mode='replay',input=path,methods=methods,cases=len(cs)))
    old=ROOT/'cpp/navigation_sweeps/frozen'
    for source in sorted(old.glob('*.specs.txt')):
        stem=source.name.removesuffix('.specs.txt');control=stem.split('_',1)[0];kind=stem.rsplit('_',1)[1]
        selected=[];ids=set()
        for line in source.read_text().splitlines()[1:]:
            fields=shlex.split(line);radius,k,cr=map(int,fields[2:5])
            if (kind=='dynamic' and (k,cr) in ANCHORS) or (kind=='unknown' and radius in [8,16,32,64]):
                selected.append(line);ids.add(fields[0])
        if not selected:continue
        specs=dest/(stem+'.specs.txt');specs.write_text(f'NAV_SPEC 1 {len(selected)}\n'+'\n'.join(selected)+'\n')
        context=old/(stem+'.contexts.json');cs=[c for c in json.loads(context.read_text())['cases'] if c['id'] in ids]
        assert len(cs)==len(ids)
        contexts.update({c['id']:dict(c,cohort='navigation_'+kind,control=control) for c in cs})
        job=dict(name='navigation_'+stem,mode='navigation',input=register(old/(stem+'.txt')),specs=register(specs),cases=len(ids),
                 methods=CONTROL+NEW+(['octile_reuse'] if control=='grid8' else []))
        register(context);register(source)
        if kind=='dynamic':job['visibility']=register(old/(control+'_visibility.txt'))
        plan.append(job)
    (dest/'contexts.json').write_text(json.dumps(contexts,ensure_ascii=False,indent=1)+'\n');register(dest/'contexts.json')
    sources=[]
    for directory in ['cpp/include/ima','cpp/mesh_variants','cpp/navigation_controls','cpp/navigation_sweeps','cpp/mpgaa_mesh','cpp/mpgaa_lazy']:
        sources.extend((ROOT/directory).glob('*.hpp'))
    sources.extend(ROOT/p for p in ['cpp/experiments/memory.hpp','cpp/experiments/dstar_boundary.hpp',
        'cpp/mpgaa_lazy/replay.cpp','cpp/mpgaa_lazy/navigation.cpp','cpp/mpgaa_lazy/Makefile','cpp/mpgaa_lazy/test.cpp',
        'cpp/mpgaa_lazy/prepare.py','cpp/mpgaa_lazy/run_all.py'])
    manifest=dict(version=1,base_commit='3b63d6bd55c7f563d784e2290047e514cbbb2584',repeats=3,cap=1000000,seed=48101,
        primary_methods=NEW,controls=CONTROL+['octile_reuse'],ablations=ABLATIONS,anchors=sorted(ANCHORS),tile_side=8,
        plan=plan,files=files,sources={str(p.relative_to(ROOT)):digest(p) for p in sorted(set(sources))},
        protocol='All 186 frozen replay cases. Dynamic closed-loop: all 16 maps, two roots, two prespecified anchors (2,5),(32,20), n=k. Unknown car16: all six maps, two roots, radii 8,16,32,64. Three serial randomized timing repeats and one independent allocation repeat per configuration. Two replay ablations. All comparator times collected anew. No parameter tuning on timings.')
    manifest['scenarios']=sum(j['cases'] for j in plan)
    manifest['timed_runs']=sum(j['cases']*len(j['methods'])*manifest['repeats'] for j in plan)
    manifest['memory_runs']=sum(j['cases']*len(j['methods']) for j in plan)
    (dest/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({k:manifest[k] for k in ['scenarios','timed_runs','memory_runs','protocol']},ensure_ascii=False))
if __name__=='__main__':main()
