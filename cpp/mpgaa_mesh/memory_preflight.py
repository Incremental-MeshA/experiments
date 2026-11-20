#!/usr/bin/env python3
"""Check mission allocation bookkeeping after timings, before trusting profiles."""
import json
import os
import signal
import subprocess
import time
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]

def main():
    state_path=HERE/'results/full/experiment.json'
    while True:
        state=json.loads(state_path.read_text())
        timing=[j for name,j in state['jobs'].items() if name.startswith('timing_')]
        plan=json.loads((HERE/'frozen/manifest.json').read_text())['plan']
        if len(timing)==len(plan) and all(j['status']=='passed' for j in timing):break
        if any(j['status']=='failed' for j in timing):raise RuntimeError('Timing failed')
        time.sleep(5)
    native=ROOT/'cpp/experiments/frozen/grid8_missions_r1.txt'
    case=json.loads(native.with_suffix('.contexts.json').read_text())['cases'][0]['id']
    output=HERE/'results/preflight';output.mkdir(exist_ok=True)
    paths=[]
    for memory in [False,True]:
        name='allocation_checkpoint'+('_memory' if memory else '')
        target=output/(name+'.csv');paths.append(target)
        command=[str(HERE/'build'/('replay_memory' if memory else 'replay')),'--input',str(native),'--output',str(target),
                 '--case',case,'--mode','mission','--radius','1','--max-steps','256','--repeats','1',
                 '--methods','mpgaa,boundary_mpgaa,selective_mpgaa,delta_mpgaa,policy_mpgaa']
        with (output/(name+'.log')).open('w') as log:p=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        if p.returncode:
            print('MEMORY_PREFLIGHT_FAILED',name,'returncode',p.returncode,flush=True)
            print((output/(name+'.log')).read_text(),flush=True)
            # Only stop this task's allocation child; timing jobs have finished.
            for line in subprocess.check_output(['ps','-eo','pid,args'],text=True).splitlines()[1:]:
                fields=line.strip().split(None,1)
                if len(fields)!=2:continue
                if any(fields[1].startswith(str(HERE/'build'/binary)+' ') for binary in ['replay_memory','navigation_memory']):
                    os.kill(int(fields[0]),signal.SIGINT)
            raise SystemExit(1)
    from analyze import read,check_profile
    timing,memory=map(read,paths);matched=check_profile(timing,memory)
    assert memory.peak_heap_bytes.max()>0
    (output/'allocation_checkpoint.json').write_text(json.dumps(dict(status='passed',matched_rows=matched),indent=2)+'\n')
    print('MEMORY_PREFLIGHT_PASSED',matched,'rows',flush=True)
if __name__=='__main__':main()
