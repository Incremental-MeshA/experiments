#!/usr/bin/env python3
"""Frozen full-configuration-mesh study; no case selection by timing results."""
import hashlib,json,shlex,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
NATIVE=['mesh_mpgaa','trigger_mesh','cascade_mesh','cascade_scan','cascade_heap','mesh_astar','contour_only']
OLD=['lba_reuse','mesha','mpgaa','batch_mpgaa','md_astar','boundary_mesh','conditional_dstar','cmesh_dstar']
NAV=['mesh_mpgaa','trigger_mesh','cascade_mesh','lba_reuse','batch_mpgaa','md_astar','conditional_dstar','cmesh_dstar']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 dest=HERE/'frozen';dest.mkdir(exist_ok=True);assert not (dest/'manifest.json').exists()
 prior=json.loads((ROOT/'cpp/mesh_symmetric/frozen/manifest.json').read_text());plan=[];contexts={};files={}
 def reg(p):k=str(p.relative_to(ROOT));files[k]=sha(p);return k
 oldctx=json.loads((ROOT/'cpp/mesh_symmetric/frozen/contexts.json').read_text())
 for j in prior['plan']:
  if not j['name'].startswith('replay_'):continue
  methods=NATIVE+OLD+(['octile_reuse'] if j['name'].endswith('grid8') else [])
  plan.append(dict(j,methods=methods));reg(ROOT/j['input'])
 contexts.update({k:dict(v,stage='reused_replay') for k,v in oldctx.items() if v['cohort']=='replay'})
 old=ROOT/'cpp/navigation_sweeps/frozen'
 for source in sorted(old.glob('car16_*.specs.txt')):
  stem=source.name.removesuffix('.specs.txt');kind=stem.rsplit('_',1)[1];lines=[];ids=set()
  for line in source.read_text().splitlines()[1:]:
   f=shlex.split(line);radius,k,cr=map(int,f[2:5])
   if ('s48101' in f[0] or 's48102' in f[0]) and ((kind=='unknown' and radius in [8,16,32,64]) or (kind=='dynamic' and (k,cr) in {(2,5),(8,10),(32,20)})):lines.append(line);ids.add(f[0])
  assert len(ids)==(8 if kind=='unknown' else 6)
  p=dest/(stem+'.specs.txt');p.write_text(f'NAV_SPEC 1 {len(ids)}\n'+'\n'.join(lines)+'\n')
  ctx=old/(stem+'.contexts.json');cs=[c for c in json.loads(ctx.read_text())['cases'] if c['id'] in ids];assert len(cs)==len(ids)
  contexts.update({c['id']:dict(c,cohort='navigation_'+kind,control='car16',stage='closed_loop') for c in cs});reg(source);reg(ctx)
  job=dict(name='navigation_'+stem,mode='navigation',input=reg(old/(stem+'.txt')),specs=reg(p),cases=len(ids),methods=NAV)
  if kind=='dynamic':job['visibility']=reg(old/'car16_visibility.txt')
  plan.append(job)
 p=dest/'contexts.json';p.write_text(json.dumps(contexts,ensure_ascii=False,indent=1)+'\n');reg(p)
 sources=dict(prior['sources'])
 for p in list(HERE.glob('*.hpp'))+[HERE/x for x in ['replay.cpp','navigation.cpp','test.cpp','Makefile','prepare.py','run_all.py']]:sources[str(p.relative_to(ROOT))]=sha(p)
 m=dict(version=1,base_commit='de6c4e93f2ce76500c418fc9fbbdb5026b4c3ff9',repeats=3,cap=1000000,seed=982107,primary_methods=['trigger_mesh','cascade_mesh'],controls=OLD+['mesh_mpgaa','octile_reuse'],ablations=['cascade_scan','cascade_heap','mesh_astar','contour_only'],plan=plan,files=files,sources=sources,contexts_file='cpp/mesh_vertex/frozen/contexts.json',protocol='Freeze before any canonical timings. Search, OPEN, g, learned h and cached policies operate on the full original configuration mesh (412 car configurations,16 boundary headings); positive dyadic reweighting preserves primitive costs. Triggered cell-violation repair; reverse zero-base cascades and forward exact-priority contour continuation. Same-core native MPGAA and component ablations plus eight fresh strong repository controls. All52 previous car replay and96 grid replay inputs, never selected by wins; history4 separated. Closed-loop: all six car maps x both roots, four unknown radii8/16/32/64, dynamic(k,cr)=(2,5),(8,10),(32,20), n=k; balanced exchanges clamped, actualcr reported. These are existing public repository specifications, not hidden or statistically independent validation. Three randomized serial timing repeats; one separate allocation pass. No compilation, instrumentation or analysis during timing. No earlier seconds pooled.')
 m.update(scenarios=sum(j['cases'] for j in plan),timed_runs=sum(j['cases']*len(j['methods'])*3 for j in plan),memory_runs=sum(j['cases']*len(j['methods']) for j in plan))
 assert m['scenarios']==232 and m['timed_runs']==8964 and m['memory_runs']==2988
 (dest/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n');print(m['scenarios'],m['timed_runs'],m['memory_runs'])
if __name__=='__main__':main()
