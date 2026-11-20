#!/usr/bin/env python3
"""Stage two: symmetric deferral after the negative first-stage findings."""
import hashlib,json,shlex
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
MAIN=['smd_batch','smd_plain','md_batch','batch_mpgaa','md_astar','lba_reuse','boundary_mesh','conditional_dstar']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 dest=HERE/'frozen';dest.mkdir(exist_ok=True);assert not (dest/'manifest.json').exists()
 ready=json.loads((HERE/'validation/build_ready.json').read_text());assert ready['status']=='passed'
 for name,h in ready['sources'].items():assert sha(HERE/name)==h,name
 for name,h in ready['binaries'].items():assert sha(HERE/'build'/name)==h,name

 original=json.loads((ROOT/'cpp/mesh_envelope/frozen/manifest.json').read_text());conditional=json.loads((ROOT/'cpp/mesh_conditional/frozen/manifest.json').read_text())
 files={};contexts={};plan=[]
 def reg(p):k=str(p.relative_to(ROOT));files[k]=sha(p);return k
 cs=json.loads((ROOT/'cpp/mesh_envelope/frozen/contexts.json').read_text())
 for job in original['plan']:
  if not job['name'].startswith('replay_'):continue
  model=job['name'].split('_')[-1];plan.append(dict(job,methods=MAIN+['lazy_blocks_batch']+(['octile_reuse'] if model=='grid8' else [])));reg(ROOT/job['input'])
 contexts.update({k:dict(v,stage='exploratory_replay') for k,v in cs.items() if v['cohort']=='replay'})
 old=ROOT/'cpp/navigation_sweeps/frozen'
 for source in sorted(old.glob('car16_*.specs.txt')):
  stem=source.name.removesuffix('.specs.txt');kind=stem.rsplit('_',1)[1];lines=[];ids=set()
  for line in source.read_text().splitlines()[1:]:
   f=shlex.split(line);r,k,cr=map(int,f[2:5])
   if 's48102' in f[0] and ((kind=='dynamic' and (k,cr) in {(2,5),(32,20)}) or (kind=='unknown' and r in [8,16,32,64])):lines.append(line);ids.add(f[0])
  assert len(ids)==(2 if kind=='dynamic' else 4)
  p=dest/(stem+'.specs.txt');p.write_text(f'NAV_SPEC 1 {len(ids)}\n'+'\n'.join(lines)+'\n')
  context=old/(stem+'.contexts.json');allctx=json.loads(context.read_text())['cases'];selected=[c for c in allctx if c['id'] in ids]
  assert len(selected)==len(ids)
  contexts.update({c['id']:dict(c,cohort='navigation_'+kind,control='car16',stage='holdout_navigation') for c in selected});reg(context);reg(source)
  job=dict(name='holdout_'+stem,mode='navigation',input=reg(old/(stem+'.txt')),specs=reg(p),cases=len(ids),methods=MAIN)
  if kind=='dynamic':job['visibility']=reg(old/'car16_visibility.txt')
  plan.append(job)
 p=dest/'contexts.json';p.write_text(json.dumps(contexts,ensure_ascii=False,indent=1)+'\n');reg(p)
 sources=dict(conditional['sources'])
 for p in list(HERE.glob('*.hpp'))+[HERE/x for x in ['replay.cpp','navigation.cpp','Makefile','test.cpp','prepare.py','run_all.py']]:sources[str(p.relative_to(ROOT))]=sha(p)
 manifest=dict(version=1,base_commit=original['base_commit'],repeats=3,cap=1000000,seed=731039,primary_methods=['smd_batch'],controls=['md_batch','batch_mpgaa','md_astar','lba_reuse','boundary_mesh','conditional_dstar','octile_reuse'],ablations=['smd_plain','lazy_blocks_batch'],plan=plan,files=files,sources=sources,contexts_file=str((dest/'contexts.json').relative_to(ROOT)),protocol='Stage-two algorithm design AFTER first-stage replay showed no useful standard-map mesh-envelope gain. Freeze before all SMD timings. Exploratory replay: all52 car and96 grid cases from stage one, no case selection by wins. Holdout navigation relative to stage one: alternate root s48102 on all six car maps, four discovery radii8/16/32/64 and two dynamic anchors(k,cr)=(2,5),(32,20), n=k and actual clampedcr retained. These maps/specifications already existed in the repository; this is a new-method/alternate-root check, not a claim of a hidden benchmark. Shared Batch backend isolates symmetric vs one-sided deferral; gap-off and eager-open ablations. All comparator times collected afresh, three randomized serial repeats and a separate allocation pass. No seconds pooled with earlier cohorts.')
 manifest.update(scenarios=sum(j['cases'] for j in plan),timed_runs=sum(j['cases']*len(j['methods'])*3 for j in plan),memory_runs=sum(j['cases']*len(j['methods']) for j in plan))
 assert manifest['scenarios']==184 and manifest['timed_runs']==5148 and manifest['memory_runs']==1716
 (dest/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');print(manifest['scenarios'],manifest['timed_runs'],manifest['memory_runs'])
if __name__=='__main__':main()
