#!/usr/bin/env python3
"""Serial, resumable 15-method timing cohort and separate allocation passes."""
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


def main(output):
    manifest_path=HERE/'frozen/manifest.json';manifest=json.loads(manifest_path.read_text())
    assert digest(ROOT/manifest['base_manifest'])==manifest['base_manifest_sha256']
    for path,sha in {**manifest['source_sha256'],**manifest['contexts_sha256']}.items():
        if digest(ROOT/path)!=sha:raise RuntimeError('Frozen source/context changed: '+path)
    for r in manifest['records']:assert digest(ROOT/r['path'])==r['sha256']
    subprocess.run(['make','-C',str(HERE),'-j2','all'],check=True)
    output=output.resolve();output.mkdir(parents=True,exist_ok=True)
    plan=[]
    for r in manifest['records']:
        name=Path(r['path']).stem;replay='_replay' in name
        job=dict(name='timing_'+name,input=r['path'],mode='replay' if replay else 'mission',memory=False,repeats=3)
        if not replay:job.update(radius=int(name.rsplit('r',1)[1]),max_steps=160 if name.startswith('car16') else 256)
        plan.append(job)
    plan.sort(key=lambda j:j['mode']=='replay')
    for r in manifest['records']:
        if '_replay' in r['path']:plan.append(dict(name='memory_'+Path(r['path']).stem,input=r['path'],mode='replay',memory=True,repeats=1))
    cpu=next((s.split(':',1)[1].strip() for s in Path('/proc/cpuinfo').read_text().splitlines() if s.startswith('model name')),platform.processor())
    state_path=output/'experiment.json'
    if state_path.exists():
        state=json.loads(state_path.read_text())
        assert state['plan']==plan and state['manifest_sha256']==digest(manifest_path)
        assert state['cpu']==cpu and state['platform']==platform.platform()
    else:
        state=dict(status='running',utc=datetime.now(timezone.utc).isoformat(),cpu=cpu,platform=platform.platform(),python=sys.version.split()[0],workers=1,
                   git_parent=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                   manifest_sha256=digest(manifest_path),source_sha256=manifest['source_sha256'],plan=plan,jobs={},
                   protocol=manifest['protocol']+' Three randomized repeats per case; all caps and step limits retained. Models prepared once outside planner timers; model costs reported separately.')
    state_path.write_text(json.dumps(state,indent=2)+'\n')
    for job in plan:
        target=output/(job['name']+'.csv')
        if job['name'] in state['jobs']:
            old=state['jobs'][job['name']]
            if old['status']=='passed' and digest(target)==old['csv_sha256'] and digest(Path(str(target)+'.json'))==old['completion_sha256']:
                print('cached',job['name'],flush=True);continue
            raise RuntimeError('Incomplete/corrupt job; preserve it and choose a new directory')
        if target.exists():raise RuntimeError('Unregistered output exists: '+str(target))
        binary=HERE/'build'/('experiment_memory' if job['memory'] else 'experiment')
        command=[str(binary),'--input',str(ROOT/job['input']),'--output',str(target),'--mode',job['mode'],
                 '--methods',','.join(manifest['experiment_methods']),'--repeats',str(job['repeats']),'--cap',str(manifest['cap']),'--seed','48101']
        if job['mode']=='mission':command+=['--radius',str(job['radius']),'--max-steps',str(job['max_steps'])]
        record=dict(status='running',command=command,binary_sha256=digest(binary));state['jobs'][job['name']]=record
        state_path.write_text(json.dumps(state,indent=2)+'\n');print('starting',job['name'],flush=True)
        with target.with_suffix('.log').open('w') as log:
            process=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        record.update(status='passed' if process.returncode==0 else 'failed',returncode=process.returncode)
        if not process.returncode:
            completion=json.loads(Path(str(target)+'.json').read_text())
            assert completion['status']=='passed' and completion['memory_profile']==job['memory']
            record.update(csv_sha256=digest(target),completion_sha256=digest(Path(str(target)+'.json')),completion=completion)
        state_path.write_text(json.dumps(state,indent=2)+'\n')
        if process.returncode:raise RuntimeError('Native validation failed: '+job['name'])
        print('passed',job['name'],completion['runs'],'runs',completion['rows'],'rows',flush=True)
    state['status']='passed';state_path.write_text(json.dumps(state,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=HERE/'results/full')
    main(p.parse_args().output)
