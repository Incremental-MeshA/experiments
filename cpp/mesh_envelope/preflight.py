#!/usr/bin/env python3
"""Exercise both harnesses and allocation accounting before official timings."""
import json
import subprocess
import sys
from pathlib import Path
import pandas as pd
from pandas.testing import assert_frame_equal
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
def read(p):return pd.read_csv(p,dtype={k:str for k in ['path_hash','world_hash','belief_hash','fingerprint']})
def main():
    out=HERE/'results/preflight';out.mkdir(exist_ok=True,parents=True)
    methods='lba_reuse,dstar_lattice,cmesh_dstar,batch_mpgaa,mesh_cold,mesh_reuse,cut_mesh,envelope_mesh,dual_mesh,lattice_envelope,circuit_mesh'
    jobs=[('grid',False,['--input','cpp/mesh_envelope/frozen/grid8_separator.txt']),
          ('car',False,['--input','cpp/mesh_envelope/frozen/car16_separator.txt','--case','separator32']),
          ('unknown',True,['--input','cpp/navigation_sweeps/frozen/car16_arena_unknown.txt','--specs','cpp/mesh_envelope/frozen/car16_arena_unknown.specs.txt']),
          ('dynamic',True,['--input','cpp/navigation_sweeps/frozen/car16_arena_dynamic.txt','--specs','cpp/mesh_envelope/frozen/car16_arena_dynamic.specs.txt','--visibility','cpp/navigation_sweeps/frozen/car16_visibility.txt'])]
    matched=0
    for name,nav,args in jobs:
        paths=[]
        for memory in [False,True]:
            prefix=out/(name+('_memory' if memory else '_normal'))
            target=prefix if nav else prefix.with_suffix('.csv')
            binary=HERE/'build'/(('navigation' if nav else 'replay')+('_memory' if memory else ''))
            command=[str(binary),*args,'--output',str(target),'--repeats','1','--methods',methods]
            with prefix.with_suffix('.log').open('w') as f:subprocess.run(command,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,check=True)
            paths.append(Path(str(prefix)+'_calls.csv') if nav else target)
        a,b=map(read,paths);keys=['case','method','query'];a=a.set_index(keys).sort_index();b=b.set_index(keys).sort_index()
        fields=[c for c in a if not c.endswith('_s') and c not in ['peak_heap_bytes','retained_heap_bytes']]
        assert_frame_equal(a[fields],b[fields],check_dtype=False,check_exact=True)
        assert b.peak_heap_bytes.ge(b.retained_heap_bytes).all() and b.retained_heap_bytes.gt(0).all()
        assert b.peak_heap_bytes.lt(2**48).all();matched+=len(a)
    result=dict(status='passed',matched_rows=matched)
    (out/'validation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
