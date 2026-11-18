#!/usr/bin/env python3
"""Regression tests for replay, partial observability, caps and allocation pass."""
import csv
import json
import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from prepare import write_suite, _assemble, ROOT, HERE


def run(binary, data, out, *options):
    result=subprocess.run([str(binary), '--input', str(data), '--output', str(out), '--repeats', '2', *options], check=True, capture_output=True, text=True,
                          env={**os.environ,'ASAN_OPTIONS':'detect_leaks=1','UBSAN_OPTIONS':'halt_on_error=1'})
    assert 'runtime error:' not in result.stderr and 'ERROR: AddressSanitizer' not in result.stderr
    with out.open() as f:
        return list(csv.DictReader(f))


def main():
    model = _assemble('toy', 1, ((0,1),), [(0,0,((0,0),d),1.0) for d in [(0,1),(1,0),(0,-1),(-1,0)]])
    grid = np.ones((12,18), dtype=np.uint8)
    for r in [2,5,10]: grid[r,2:16]=0
    for c in [2,15]: grid[2:11,c]=0
    grid[2,8]=1
    grid[0,0]=0  # disconnected free cell: a genuine irrelevant insertion
    s,t=(5,2,0),(5,15,0)
    def query(blocks,opens,cost):
        return dict(start=s,goal=t,blocks=blocks,opens=opens,expected=cost)
    case=dict(id='two_call',family='test',_initial=grid,queries=[query([],[],13),query([(0,0)],[],13),query([],[(2,8)],13),query([(5,8)],[],19)])
    excluded={'time_s','setup_s','sensing_s','peak_heap_bytes','retained_heap_bytes'}
    with tempfile.TemporaryDirectory(prefix='ima_protocols_') as directory:
        d=Path(directory);data=d/'replay.txt';write_suite(data,model,[case])
        normal=run(HERE/'build/experiment',data,d/'normal.csv')
        memory=run(HERE/'build/experiment_memory',data,d/'memory.csv')
        assert len(normal)==len(memory)==88
        assert [{k:v for k,v in r.items() if k not in excluded} for r in normal]==[{k:v for k,v in r.items() if k not in excluded} for r in memory]
        assert all(int(r['peak_heap_bytes'])>0 for r in memory)
        assert all(r['peak_heap_bytes']=='0' for r in normal)
        assert any(r['method']=='md_astar' and r['backend_calls']=='2' for r in normal)
        assert any(r['method']=='lba_reuse' and r['backend_calls']=='0' for r in normal)
        capped=run(HERE/'build/experiment',data,d/'capped.csv','--cap','1')
        assert {r['status'] for r in capped}=={'capped','skipped_after_cap'}
        truth=grid.copy();truth[2,8]=0;truth[5,8]=1
        mission=d/'mission.txt';write_suite(mission,model,[dict(id='unknown',family='unknown',_initial=truth,queries=[query([],[],19)])])
        trajectories=run(HERE/'build/experiment',mission,d/'mission.csv','--mode','mission','--radius','1','--max-steps','80')
        groups={}
        for row in trajectories:
            groups.setdefault((row['method'],row['repeat']),[]).append(row)
            a=(int(row['start_i']),int(row['start_j']));b=(int(row['next_i']),int(row['next_j']))
            assert not truth[a] and not truth[b]
            if a!=b: assert abs(a[0]-b[0])+abs(a[1]-b[1])==1
        assert len(groups)==22 and all(rows[-1]['status']=='goal' and float(rows[-1]['travel_cost'])>=19 for rows in groups.values())
        sanitized=HERE/'build/experiment_sanitize'
        if sanitized.exists():
            checked=run(sanitized,data,d/'sanitizer.csv')
            assert [{k:v for k,v in r.items() if k not in excluded} for r in checked]==[{k:v for k,v in r.items() if k not in excluded} for r in normal]
        boundary=run(HERE/'build/experiment',HERE/'frozen/car16_missions_r8.txt',d/'boundary.csv',
                     '--mode','mission','--radius','8','--max-steps','160',
                     '--case','car16__MA_room96__mission__s48101__r8','--methods','dstar_lattice,dstar_mesh')
        endings={}
        for r in boundary:endings[r['method'],r['repeat']]=r['status']
        assert len(endings)==4 and set(endings.values())=={'goal'},endings
    result=dict(status='passed',methods=11,replay_rows=88,mission_runs=22,allocation_answers_identical=True,
                checks=['two-call reactivation','LBA suffix-reuse control','cap is not no-path','skipped queries retained',
                        'independent truth collision checks','unknown-map mission reaches goal','repeat trajectory identity','separate memory pass matches timed path/counters',
                        'D* Lite floating-key mesh-boundary regression: four real car16 missions reach goal'],
                sanitized=sanitized.exists())
    (HERE/'results/protocol_checks.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
