#!/usr/bin/env python3
"""Freeze a fresh joint validation against textbook conditional edge updates."""
import hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 dest=HERE/'frozen';dest.mkdir(exist_ok=True);assert not (dest/'manifest.json').exists()
 primary=json.loads((ROOT/'cpp/mesh_envelope/frozen/manifest.json').read_text());frontier=json.loads((ROOT/'cpp/mesh_envelope/frozen/frontier/manifest.json').read_text())
 methods=['conditional_dstar',*primary['primary_methods']];plan=[];files={};contexts={}
 for m,ctx in [(primary,ROOT/'cpp/mesh_envelope/frozen/contexts.json'),(frontier,ROOT/'cpp/mesh_envelope/frozen/frontier/contexts.json')]:
  cs=json.loads(ctx.read_text())
  for job in m['plan']:
   if job['mode']!='replay':continue
   plan.append(dict(job,methods=methods));files[job['input']]=sha(ROOT/job['input'])
  contexts.update({k:v for k,v in cs.items() if not v['cohort'].startswith('navigation')})
 p=dest/'contexts.json';p.write_text(json.dumps(contexts,indent=1)+'\n');files[str(p.relative_to(ROOT))]=sha(p)
 src=dict(primary['sources'])
 for p in list(HERE.glob('*.hpp'))+[HERE/n for n in ['Makefile','replay.cpp','navigation.cpp','test.cpp','prepare.py','run_all.py']]:src[str(p.relative_to(ROOT))]=sha(p)
 m=dict(version=1,base_commit=primary['base_commit'],repeats=3,cap=primary['cap'],seed=831015,primary_methods=primary['primary_methods'],controls=['conditional_dstar'],plan=plan,files=files,sources=src,contexts_file=str((dest/'contexts.json').relative_to(ROOT)),protocol='Additional fresh randomized joint timing cohort specified from source review, before aggregate primary comparisons. Conditional D* Lite handles map-edge decreases directly and backs up on increases only when the changed edge can support rhs; g propagation is conditional, queue synchronization suppresses identical keys. All three unchanged candidates remeasured in the SAME binary on all 184 replay configurations (52 car,96 grid,24 separators,12 width complement). No navigation in this validation cohort. Three timing repeats and one separate allocation pass. These are repeated inputs, not additional independent maps; times are not mixed with primary.')
 m.update(scenarios=sum(j['cases'] for j in plan),timed_runs=sum(j['cases']*len(methods)*3 for j in plan),memory_runs=sum(j['cases']*len(methods) for j in plan))
 assert m['scenarios']==184
 (dest/'manifest.json').write_text(json.dumps(m,indent=2)+'\n');print(m['scenarios'],m['timed_runs'],m['memory_runs'])
if __name__=='__main__':main()
