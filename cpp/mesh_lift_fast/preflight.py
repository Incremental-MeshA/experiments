#!/usr/bin/env python3
"""Check normal/profile logical equivalence before the timing cohort."""
import hashlib,json,subprocess
from pathlib import Path
import pandas as pd
from pandas.testing import assert_frame_equal
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
HASH=['path_hash','world_hash','belief_hash','fingerprint','mv_trace_hash']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 m=json.loads((HERE/'frozen/input_plan.json').read_text());directory=HERE/'results/preflight';directory.mkdir(parents=True,exist_ok=True);matched=0
 for job in m['plan']:
  if job['name']=='ablation_car16':continue
  if job['mode']=='navigation' and 'arena' not in job['name']:continue
  if job['mode']=='replay' and job['name'] not in ['replay_car16','replay_grid8']:continue
  frames=[]
  for profile in [False,True]:
   name=job['name']+('_memory' if profile else '_normal');prefix=directory/name;nav=job['mode']=='navigation';output=prefix if nav else prefix.with_suffix('.csv');metadata=Path(str(output)+'.json')
   if not metadata.exists():
    binary=HERE/'build'/(('navigation' if nav else 'replay')+('_memory' if profile else ''))
    cmd=[str(binary),'--input',str(ROOT/job['input']),'--output',str(output),'--methods',','.join(job['methods']),'--repeats','1','--cap',str(m['cap'])]
    if nav:
     cmd+=['--specs',str(ROOT/job['specs'])]
     if 'visibility' in job:cmd+=['--visibility',str(ROOT/job['visibility'])]
    elif job['name'].endswith('car16'):cmd+=['--case','arena']
    with (directory/(name+'.log')).open('w') as f:subprocess.run(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,check=True)
   assert json.loads(metadata.read_text())['status']=='passed'
   file=Path(str(prefix)+'_calls.csv') if nav else output;frames.append(pd.read_csv(file,dtype={k:str for k in HASH}))
  a,b=[f.set_index(['case','method','query']).sort_index() for f in frames];fields=[c for c in a if not c.endswith('_s') and c not in ['peak_heap_bytes','retained_heap_bytes','allocation_calls']]
  assert_frame_equal(a[fields],b[fields],check_dtype=False,check_exact=True);matched+=len(a);print('passed',job['name'],len(a),flush=True)
 value=dict(status='passed',matched_rows=matched,binaries={name:sha(HERE/'build'/name) for name in ['replay','replay_memory','navigation','navigation_memory']})
 (directory/'validation.json').write_text(json.dumps(value,indent=2)+'\n');print('PREFLIGHT_PASSED',matched)
if __name__=='__main__':main()
