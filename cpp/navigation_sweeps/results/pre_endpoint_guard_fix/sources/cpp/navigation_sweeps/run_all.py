#!/usr/bin/env python3
"""Run the frozen navigation cohort serially, preserving all terminal outcomes."""
import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime,timezone
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def verify(manifest):
    hashes={**manifest['source_sha256'],**manifest['auxiliary_sha256']}
    for r in manifest['records']:
        hashes.update({r['path']:r['sha256'],r['contexts']:r['contexts_sha256'],r['specs']:r['specs_sha256']})
    for path,sha in hashes.items():
        if digest(ROOT/path)!=sha:raise RuntimeError('Frozen file changed: '+path)

def main(output,only=None):
    mp=HERE/'frozen/manifest.json';m=json.loads(mp.read_text());verify(m)
    subprocess.run(['make','-C',str(HERE),'-j2','all'],check=True)
    output=output.resolve();output.mkdir(parents=True,exist_ok=True)
    plan=[]
    for memory in [False,True]:
        for r in sorted(m['records'],key=lambda r:(r['kind']!='unknown',r['control'],r['map'])):
            plan.append(dict(name=('memory_' if memory else 'timing_')+Path(r['path']).stem,memory=memory,
                             input=r['path'],specs=r['specs'],control=r['control'],
                             expected_runs=len(r['memory_cases'])*len(m['methods']) if memory else r['timed_runs']))
    cpu=next((s.split(':',1)[1].strip() for s in Path('/proc/cpuinfo').read_text().splitlines() if s.startswith('model name')),platform.processor())
    state_path=output/'experiment.json'
    if state_path.exists():
        state=json.loads(state_path.read_text());assert state['plan']==plan and state['manifest_sha256']==digest(mp)
        assert state['cpu']==cpu and state['platform']==platform.platform()
    else:
        state=dict(status='running',utc=datetime.now(timezone.utc).isoformat(),cpu=cpu,platform=platform.platform(),workers=1,
                   python=sys.version.split()[0],git_parent=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                   manifest_sha256=digest(mp),source_sha256=m['source_sha256'],plan=plan,jobs={})
    def save():state_path.write_text(json.dumps(state,indent=2)+'\n')
    save()
    for job in plan:
        if only and job['memory']!=(only=='memory'):continue
        prefix=output/job['name'];paths=[Path(str(prefix)+suffix) for suffix in ['_runs.csv','_calls.csv','_traces.csv','.json']]
        if job['name'] in state['jobs']:
            old=state['jobs'][job['name']]
            if old['status']=='passed' and all(digest(ROOT/p)==sha for p,sha in old['output_sha256'].items()):
                print('cached',job['name'],flush=True);continue
            raise RuntimeError('Incomplete/corrupt job; preserve outputs and select a new output directory')
        if any(p.exists() for p in paths):raise RuntimeError('Unregistered output exists: '+str(prefix))
        binary=HERE/'build'/('experiment_memory' if job['memory'] else 'experiment')
        command=[str(binary),'--input',str(ROOT/job['input']),'--specs',str(ROOT/job['specs']),
                 '--visibility',str(HERE/'frozen'/f'{job["control"]}_visibility.txt'),'--output',str(prefix),
                 '--cap',str(m['cap']),'--methods',','.join(m['methods'])]
        if job['memory']:command+=['--anchors-only','--repeats','1']
        record=dict(status='running',command=command,binary_sha256=digest(binary));state['jobs'][job['name']]=record;save()
        print('starting',job['name'],flush=True)
        with prefix.with_suffix('.log').open('w') as log:result=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        record.update(status='passed' if result.returncode==0 else 'failed',returncode=result.returncode)
        if not result.returncode:
            completion=json.loads(paths[-1].read_text());assert completion['status']=='passed' and completion['runs']==job['expected_runs'] and completion['memory_profile']==job['memory']
            record.update(completion=completion,output_sha256={str(p.relative_to(ROOT)):digest(p) for p in paths})
        save()
        if result.returncode:raise RuntimeError('Native verification failed: '+job['name'])
        print('passed',job['name'],completion['runs'],'runs',completion['calls'],'calls',flush=True)
    state['status']='passed' if len(state['jobs'])==len(plan) and all(j['status']=='passed' for j in state['jobs'].values()) else 'running';save()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=HERE/'results/full');p.add_argument('--only',choices=['timing','memory'])
    a=p.parse_args();main(a.output,a.only)
