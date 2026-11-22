#!/usr/bin/env python3
"""Deterministic resource-bounded audit of the Lift optimizations."""
import argparse,hashlib,json,shlex
from pathlib import Path
from datetime import datetime,timezone
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
MAIN=['lift_mesh','cascade_lift','zero_lift','zero_cascade','fast_lift','fast_cascade','mesha_reuse','batch_mpgaa']
ABLATIONS=['fast_cascade','fast_all_closed','fast_no_depth','fast_trace','fast_raw_finals','fast_recompute_base','fast_slow_policy']
NAV=['lift_mesh','cascade_lift','fast_lift','fast_cascade','mesha_reuse','batch_mpgaa']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def split_suite(path):
 t=shlex.split(path.read_text());i=2;nt,np,nc=map(int,t[i+1:i+4]);i+=4+nt
 for _ in range(np):n=int(t[i+5]);i+=6+2*n
 for _ in range(nc):ne,nf=map(int,t[i+4:i+6]);i+=6+ne*5+nf*4
 head=t[:i];nm=int(t[i]);i+=1;maps=[]
 for _ in range(nm):h,w=map(int,t[i+1:i+3]);maps.append(t[i:i+3+h]);i+=3+h
 n=int(t[i]);i+=1;cases={}
 for _ in range(n):
  begin=i;name=t[i];nq=int(t[i+3]);i+=4
  for _ in range(nq):nb,no=map(int,t[i+9:i+11]);i+=11+2*(nb+no)
  cases[name]=t[begin:i]
 assert i==len(t);return head,maps,cases

def inputs():
 dest=HERE/'frozen';dest.mkdir(exist_ok=True);old=json.loads((ROOT/'cpp/mesh_lift/frozen/manifest.json').read_text());ctx=json.loads((ROOT/old['contexts_file']).read_text());contexts={};plan=[];files={}
 def reg(path):key=str(path.relative_to(ROOT));files[key]=sha(path);return key
 for j in old['plan']:
  if j['mode']=='replay':
   model='car16' if j['name'].endswith('car16') else 'grid8';head,maps,cases=split_suite(ROOT/j['input'])
   names=[k for k in cases if ctx[k]['family']!='history' and (model=='car16' or 's48101' in k)]
   assert len(names)==48
   output=dest/(model+'_replay.txt');output.write_text(' '.join(head+[str(len(maps))]+sum(maps,[])+[str(len(names))]+sum([cases[k] for k in names],[]))+'\n')
   plan.append(dict(name=j['name'],mode='replay',input=reg(output),cases=len(names),methods=MAIN+(['octile_reuse'] if model=='grid8' else [])))
   contexts.update({k:dict(ctx[k],panel='main',original_id=k) for k in names});reg(ROOT/j['input'])
   if model=='car16':
    selected=[k for k in names if 's48101' in k and ctx[k]['family'] in ['on_path','churn']];assert len(selected)==12
    aliased=[]
    for k in selected:
     name=k+'__optimization_ablation';tokens=list(cases[k]);tokens[0]=name;aliased+=tokens
     contexts[name]=dict(ctx[k],id=name,cohort='ablation',panel='ablation',original_id=k)
    output=dest/'car16_ablation.txt';output.write_text(' '.join(head+[str(len(maps))]+sum(maps,[])+[str(len(selected))]+aliased)+'\n')
    plan.append(dict(name='ablation_car16',mode='replay',input=reg(output),cases=len(selected),methods=ABLATIONS))
  else:
   lines=[];names=set()
   for line in (ROOT/j['specs']).read_text().splitlines()[1:]:
    f=shlex.split(line);radius=int(f[2]);kind=j['name'].rsplit('_',1)[1]
    if 's48101' in f[0] and (kind=='dynamic' or radius in [8,32,64]):lines.append(line);names.add(f[0])
   assert len(names)==3
   output=dest/Path(j['specs']).name;output.write_text('NAV_SPEC 1 '+str(len(names))+'\n'+'\n'.join(lines)+'\n')
   job=dict(j,specs=reg(output),cases=len(names),methods=NAV);plan.append(job)
   contexts.update({k:dict(ctx[k],panel='navigation',original_id=k) for k in names});reg(ROOT/j['input']);reg(ROOT/j['specs'])
   if 'visibility' in j:reg(ROOT/j['visibility'])
 output=dest/'contexts.json';output.write_text(json.dumps(contexts,ensure_ascii=False,indent=1)+'\n');reg(output)
 # Put the component ablation after the two main replay jobs.
 plan.sort(key=lambda j:(0 if j['name']=='replay_car16' else 1 if j['name']=='replay_grid8' else 2 if j['name']=='ablation_car16' else 3,j['name']))
 value=dict(version=1,base_commit='49b1df9ee952f36cbc240c0a3be713feef690a1b',repeats=3,cap=1000000,seed=882211,primary_methods=['fast_lift','fast_cascade'],controls=['lift_mesh','cascade_lift','zero_lift','zero_cascade','mesha_reuse','batch_mpgaa','octile_reuse'],ablations=ABLATIONS,plan=plan,contexts_file='cpp/mesh_lift_fast/frozen/contexts.json',files=files,unique_scenarios=132,scheduled_scenarios=sum(j['cases'] for j in plan),timed_runs=sum(j['cases']*len(j['methods'])*3 for j in plan),memory_runs=sum(j['cases']*len(j['methods']) for j in plan),protocol='Freeze before canonical timings. Retain all48 balanced car replay cases (six maps,two roots,four families); grid uses one root and the full4-change-rate x3-k grid on each of four density maps (48 cases,n=k). Navigation uses all six car maps,one root,unknown radii8/32/64 and dynamic(k,cr)=(2,5),(8,10),(32,20),visibility n=k; balanced exchanges clamped and actual cr reported. Twelve reused first-root car on-path/churn cases are repeated as a separately named component-ablation panel, not independent additional configurations. 132 unique configurations,144 scheduled cases. Baselines freshly measured jointly. Three randomized serial timing repeats; separate allocation pass with allocation-request counts for replay. No previous timing seconds pooled; no independent holdout claim. Search stays on the original mesh. Zero-only changes arc costs/heuristic/repair keys only; fast removes allocations and redundant work. Every completed answer checked against exact reference; caps and completion retained. No heavy compilation or analysis during timing.')
 assert (value['scheduled_scenarios'],value['timed_runs'],value['memory_runs'])==(144,3348,1116)
 (dest/'input_plan.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');print(value['unique_scenarios'],value['scheduled_scenarios'],value['timed_runs'],value['memory_runs'])
 return value

def freeze():
 dest=HERE/'frozen';assert not (dest/'manifest.json').exists();m=inputs();old=json.loads((ROOT/'cpp/mesh_lift/frozen/manifest.json').read_text());sources=dict(old['sources'])
 for p in list(HERE.glob('*.hpp'))+list(HERE.glob('*.cpp'))+[HERE/name for name in ['Makefile','prepare.py','run_all.py','preflight.py','run_setup.py']]:sources[str(p.relative_to(ROOT))]=sha(p)
 m['sources']=sources;m['frozen_utc']=datetime.now(timezone.utc).isoformat();(dest/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--freeze',action='store_true');a=p.parse_args();freeze() if a.freeze else inputs()
