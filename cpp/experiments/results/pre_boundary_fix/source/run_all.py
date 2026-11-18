#!/usr/bin/env python3
"""Run the pre-registered native timing and separate allocation experiments."""
import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(output):
    manifest=json.loads((HERE/'frozen/manifest.json').read_text())
    for path,sha in manifest['source_sha256'].items():
        if digest(ROOT/path)!=sha: raise RuntimeError('Frozen source changed: '+path)
    for item in manifest['records']:
        if digest(ROOT/item['path'])!=item['sha256']: raise RuntimeError('Frozen input changed')
    subprocess.run(['make','-C',str(HERE),'-j2','all'],check=True)
    output=output.resolve();output.mkdir(parents=True,exist_ok=True)
    plan=[]
    for item in manifest['records']:
        name=Path(item['path']).stem
        if '_replay' in name:
            plan.append(dict(name='timing_'+name,input=item['path'],mode='replay',memory=False,repeats=3))
        else:
            radius=int(name.rsplit('r',1)[1])
            plan.append(dict(name='timing_'+name,input=item['path'],mode='mission',memory=False,repeats=3,radius=radius,max_steps=160 if name.startswith('car16') else 256))
    for item in manifest['records']:
        if '_replay' in item['path']:
            plan.append(dict(name='memory_'+Path(item['path']).stem,input=item['path'],mode='replay',memory=True,repeats=1))
    cpu=next((s.split(':',1)[1].strip() for s in Path('/proc/cpuinfo').read_text().splitlines() if s.startswith('model name')),platform.processor())
    state_path=output/'experiment.json'
    if state_path.exists():
        state=json.loads(state_path.read_text())
        if state['plan']!=plan: raise RuntimeError('Different plan; select a new output directory')
        for path,sha in state['source_sha256'].items():
            if digest(ROOT/path)!=sha: raise RuntimeError('Source differs from this run')
        if digest(HERE/'frozen/manifest.json')!=state['manifest_sha256']:raise RuntimeError('Different frozen data')
        if state['cpu']!=cpu or state['platform']!=platform.platform():raise RuntimeError('Cannot resume in a different environment')
    else:
        source=[HERE/'bench.cpp',HERE/'memory.hpp',HERE/'Makefile',*sorted((ROOT/'cpp/include/ima').glob('*.hpp'))]
        state=dict(status='running',utc=datetime.now(timezone.utc).isoformat(),cpu=cpu,platform=platform.platform(),python=sys.version.split()[0],workers=1,
            git_parent=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),manifest_sha256=digest(HERE/'frozen/manifest.json'),
            source_sha256={str(p.relative_to(ROOT)):digest(p) for p in source},plan=plan,jobs={},
            protocol='Serial native runs; three randomized timing repeats; one separate C++ heap allocation pass; truth/belief path validation and reference A* outside timers; capped and step-limited outcomes retained.')
    state_path.write_text(json.dumps(state,indent=2)+'\n')
    for job in plan:
        target=output/(job['name']+'.csv')
        if job['name'] in state['jobs']:
            old=state['jobs'][job['name']]
            if old['status']=='passed' and digest(target)==old['csv_sha256'] and digest(Path(str(target)+'.json'))==old['completion_sha256']:
                print('cached',job['name'],flush=True);continue
            raise RuntimeError('Incomplete/corrupted job; preserve it and use a new directory')
        if target.exists():raise RuntimeError('Unregistered output already exists: '+str(target))
        binary=HERE/'build'/('experiment_memory' if job['memory'] else 'experiment')
        command=[str(binary),'--input',str(ROOT/job['input']),'--output',str(target),'--mode',job['mode'],
                 '--repeats',str(job['repeats']),'--cap',str(manifest['cap']),'--seed','48101']
        if job['mode']=='mission':command+=['--radius',str(job['radius']),'--max-steps',str(job['max_steps'])]
        record=dict(status='running',command=command,binary_sha256=digest(binary))
        state['jobs'][job['name']]=record;state_path.write_text(json.dumps(state,indent=2)+'\n')
        print('starting',job['name'],flush=True)
        with target.with_suffix('.log').open('w') as log:
            run=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        record['returncode']=run.returncode
        record['status']='passed' if run.returncode==0 else 'failed'
        if not run.returncode:
            completion=json.loads(Path(str(target)+'.json').read_text())
            assert completion['status']=='passed' and completion['memory_profile']==job['memory']
            record.update(csv_sha256=digest(target),completion_sha256=digest(Path(str(target)+'.json')),completion=completion)
        state_path.write_text(json.dumps(state,indent=2)+'\n')
        if run.returncode:raise RuntimeError('Native validation failed: '+job['name'])
        print('passed',job['name'],record['completion']['runs'],'runs',record['completion']['rows'],'rows',flush=True)
    state['status']='passed';state_path.write_text(json.dumps(state,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=HERE/'results/expanded')
    main(p.parse_args().output)
