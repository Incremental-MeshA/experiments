#!/usr/bin/env python3
"""Paired normal/allocation verification, never a timing result source."""
import json,subprocess,hashlib
from pathlib import Path
import pandas as pd
from pandas.testing import assert_frame_equal
from prepare import NATIVE,NAV
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def main():
 d=HERE/'results/preflight';d.mkdir(parents=True,exist_ok=True);m=json.loads((HERE/'frozen/manifest.json').read_text());jobs=[]
 for job in m['plan']:
  if job['name'].startswith('replay_'):jobs.append((job,NATIVE+['mesha_reuse'],'Berlin' if job['name'].endswith('car16') else ''))
  elif 'arena' in job['name']:jobs.append((job,NAV,''))
 matched=0
 for job,methods,filter in jobs:
  nav=job['mode']=='navigation';frames=[]
  for memory in [False,True]:
   name=job['name']+('_memory' if memory else '_normal');prefix=d/name;target=prefix if nav else prefix.with_suffix('.csv');meta=Path(str(target)+'.json')
   if not meta.exists():
    binary=HERE/'build'/(('navigation' if nav else 'replay')+('_memory' if memory else ''))
    args=[str(binary),'--input',str(ROOT/job['input']),'--output',str(target),'--methods',','.join(methods),'--repeats','1','--cap',str(m['cap'])]
    if filter:args+=['--case',filter]
    if nav:
     args+=['--specs',str(ROOT/job['specs'])]
     if 'visibility' in job:args+=['--visibility',str(ROOT/job['visibility'])]
    with (d/(name+'.log')).open('w') as log:subprocess.run(args,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
   assert json.loads(meta.read_text())['status']=='passed'
   p=Path(str(prefix)+'_calls.csv') if nav else target
   frames.append(pd.read_csv(p,dtype={k:str for k in ['path_hash','world_hash','belief_hash','fingerprint','mv_trace_hash']}))
  a,b=[f.set_index(['case','method','query']).sort_index() for f in frames]
  fields=[x for x in a if not x.endswith('_s') and x not in ['peak_heap_bytes','retained_heap_bytes']]
  assert_frame_equal(a[fields],b[fields],check_dtype=False,check_exact=True);matched+=len(a)
  print('passed',job['name'],len(a),flush=True)
 value=dict(status='passed',matched_rows=matched,binaries={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (HERE/'build').iterdir() if p.name in ['replay','replay_memory','navigation','navigation_memory']})
 (d/'validation.json').write_text(json.dumps(value,indent=2)+'\n');print('PREFLIGHT_PASSED',matched,flush=True)
if __name__=='__main__':main()
