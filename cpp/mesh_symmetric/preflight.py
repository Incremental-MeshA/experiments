#!/usr/bin/env python3
import json,subprocess,shlex
from pathlib import Path
import pandas as pd
from pandas.testing import assert_frame_equal
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def main():
 out=HERE/'results/preflight';out.mkdir(parents=True,exist_ok=True)
 methods='smd_batch,smd_plain,md_batch,lazy_blocks_batch,batch_mpgaa,md_astar';old=ROOT/'cpp/navigation_sweeps/frozen'
 jobs=[('grid',False,['--input','cpp/experiments/frozen/grid8_replay.txt']),('history',False,['--input','cpp/experiments/frozen/car16_replay.txt','--case','history'])]
 for kind in ['unknown','dynamic']:
  src=old/f'car16_arena_{kind}.specs.txt';lines=[]
  for line in src.read_text().splitlines()[1:]:
   f=shlex.split(line);r,k,cr=map(int,f[2:5])
   if 's48102' in f[0] and ((kind=='unknown' and r in [8,32]) or (kind=='dynamic' and (k,cr) in {(2,5),(32,20)})):lines.append(line)
  spec=out/(kind+'.specs.txt');spec.write_text(f'NAV_SPEC 1 {len(lines)}\n'+'\n'.join(lines)+'\n')
  args=['--input',str(old/f'car16_arena_{kind}.txt'),'--specs',str(spec)]
  if kind=='dynamic':args+=['--visibility',str(old/'car16_visibility.txt')]
  jobs.append((kind,True,args))
 matched=0
 for name,nav,args in jobs:
  frames=[]
  for memory in [False,True]:
   prefix=out/(name+('_memory' if memory else '_normal'));target=prefix if nav else prefix.with_suffix('.csv');binary=HERE/'build'/(('navigation' if nav else 'replay')+('_memory' if memory else ''))
   with prefix.with_suffix('.log').open('w') as f:subprocess.run([str(binary),*args,'--output',str(target),'--repeats','1','--methods',methods],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,check=True)
   frames.append(pd.read_csv(Path(str(prefix)+'_calls.csv') if nav else target,dtype={k:str for k in ['path_hash','world_hash','belief_hash']}))
  a,b=[d.set_index(['case','method','query']).sort_index() for d in frames];cols=[c for c in a if not c.endswith('_s') and c not in ['peak_heap_bytes','retained_heap_bytes']]
  assert_frame_equal(a[cols],b[cols],check_dtype=False,check_exact=True);assert b.peak_heap_bytes.ge(b.retained_heap_bytes).all();matched+=len(a)
 (out/'validation.json').write_text(json.dumps(dict(status='passed',matched_rows=matched),indent=2)+'\n');print('SMD_PREFLIGHT_PASSED',matched)
if __name__=='__main__':main()
