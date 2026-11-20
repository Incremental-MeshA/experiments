#!/usr/bin/env python3
"""Serial new timing cohort; immutable inputs, source hashes, and native checks."""
import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime,timezone
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,value):
    temp=p.with_suffix('.tmp');temp.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n');temp.replace(p)

def main(output):
    manifest_path=HERE/'frozen/frontier/manifest.json';manifest=json.loads(manifest_path.read_text())
    for path,sha in {**manifest['files'],**manifest['sources']}.items():
        if digest(ROOT/path)!=sha:raise RuntimeError('Frozen file changed: '+path)
    output=output.resolve();output.mkdir(parents=True,exist_ok=True);state_path=output/'experiment.json'
    binary_hashes={p.name:digest(p) for p in (HERE/'build').iterdir() if p.name in ['replay','replay_memory','navigation','navigation_memory']}
    assert len(binary_hashes)==4
    if state_path.exists():
        state=json.loads(state_path.read_text());assert state['manifest_sha256']==digest(manifest_path) and state['binaries']==binary_hashes
    else:
        state=dict(status='running',utc=datetime.now(timezone.utc).isoformat(),platform=platform.platform(),python=sys.version,
                   cpu=next(l.split(':',1)[1].strip() for l in Path('/proc/cpuinfo').read_text().splitlines() if l.startswith('model name')),
                   affinity=sorted(os.sched_getaffinity(0)),workers=1,binaries=binary_hashes,manifest_sha256=digest(manifest_path),jobs={})
    save(state_path,state)
    for memory in [False,True]:
        for job in manifest['plan']:
            name=('memory_' if memory else 'timing_')+job['name'];old=state['jobs'].get(name)
            if old:
                if old['status']=='passed' and all(digest(output/p)==sha for p,sha in old['outputs'].items()):
                    print('cached',name,flush=True);continue
                raise RuntimeError('Incomplete/corrupt job; preserve it and choose a new output: '+name)
            binary=HERE/'build'/('navigation' if job['mode']=='navigation' else 'replay')
            if memory:binary=binary.with_name(binary.name+'_memory')
            prefix=output/name;is_nav=job['mode']=='navigation';target=prefix if is_nav else prefix.with_suffix('.csv')
            command=[str(binary),'--input',str(ROOT/job['input']),'--output',str(target),'--methods',','.join(job['methods']),
                     '--repeats','1' if memory else str(manifest['repeats']),'--cap',str(manifest['cap'])]
            if is_nav:
                command+=['--specs',str(ROOT/job['specs'])]
                if 'visibility' in job:command+=['--visibility',str(ROOT/job['visibility'])]
            else:
                command+=['--mode',job['mode'],'--seed',str(manifest['seed'])]
                if job['mode']=='mission':command+=['--radius',str(job['radius']),'--max-steps',str(job['max_steps'])]
            record=dict(status='running',command=command,expected_runs=job['cases']*len(job['methods'])*(1 if memory else manifest['repeats']))
            state['jobs'][name]=record;save(state_path,state);print('starting',name,record['expected_runs'],'runs',flush=True)
            with (output/(name+'.log')).open('w') as log:process=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
            record.update(status='passed' if process.returncode==0 else 'failed',returncode=process.returncode)
            if not process.returncode:
                completion=Path(str(target)+'.json');meta=json.loads(completion.read_text())
                assert meta['status']=='passed' and meta['runs']==record['expected_runs'] and meta['memory_profile']==memory
                paths=[completion]+([Path(str(prefix)+s) for s in ['_runs.csv','_calls.csv','_traces.csv']] if is_nav else [target])
                record.update(completion=meta,outputs={p.name:digest(p) for p in paths})
            save(state_path,state)
            if process.returncode:raise RuntimeError('Native validation failed: '+name)
            print('passed',name,meta['runs'],'runs',round(meta['wall_s'],2),'s',flush=True)
    state['status']='passed';save(state_path,state);print('ALL_PASSED',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=HERE/'results/frontier');main(p.parse_args().output)
