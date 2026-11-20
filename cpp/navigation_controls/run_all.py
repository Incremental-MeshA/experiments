#!/usr/bin/env python3
"""Separate, serial matched control of stronger grid baselines at frozen anchors."""
import argparse
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];NAV=HERE.parent/'navigation_sweeps'
sys.path.insert(0,str(NAV))
from study import read_manifest,digest

METHODS=['lba_reuse','mpgaa','md_astar','octile_astar','octile_reuse']

def sources():
    original=(NAV/'bench.cpp').read_text()
    assert (HERE/'bench.cpp').read_text()==original.replace('namespace nav=ima::navigation;','namespace nav=ima::navigation_controls;')
    return {str(p.relative_to(ROOT)):digest(p) for p in [HERE/name for name in ['run_all.py','bench.cpp','factory.hpp','strong_grid.hpp','test.cpp','Makefile']]}

def main(output,plan_only=False):
    m=read_manifest();plan=[]
    for memory in [False,True]:
        for r in sorted((r for r in m['records'] if r['control']=='grid8'),key=lambda r:r['map']):
            count=len(r['memory_cases'])*len(METHODS)*(1 if memory else 3)
            plan.append(dict(name=('memory_' if memory else 'timing_')+Path(r['path']).stem,memory=memory,
                             input=r['path'],specs=r['specs'],contexts=r['contexts'],expected_runs=count))
    assert sum(j['expected_runs'] for j in plan if not j['memory'])==1200
    assert sum(j['expected_runs'] for j in plan if j['memory'])==400
    if plan_only:print(json.dumps(dict(methods=METHODS,cases=80,timed_runs=1200,memory_runs=400,plan=plan),indent=2));return
    subprocess.run(['make','-C',str(HERE),'-j2','all','test'],check=True)
    own=sources();output=output.resolve();output.mkdir(parents=True,exist_ok=True)
    cpu=next((s.split(':',1)[1].strip() for s in Path('/proc/cpuinfo').read_text().splitlines() if s.startswith('model name')),platform.processor())
    state_path=output/'experiment.json'
    if state_path.exists():
        state=json.loads(state_path.read_text())
        assert state['plan']==plan and state['cpu']==cpu and state['platform']==platform.platform()
        assert state['control_source_sha256']==own and state['source_sha256']==m['source_sha256']
        assert state['manifest_sha256']==digest(NAV/'frozen/manifest.json') and state['selection_sha256']==m['selection_sha256']
    else:
        state=dict(status='running',utc=datetime.now(timezone.utc).isoformat(),cpu=cpu,platform=platform.platform(),workers=1,
                   python=sys.version.split()[0],git_parent=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                   manifest_sha256=digest(NAV/'frozen/manifest.json'),selection_sha256=m['selection_sha256'],source_sha256=m['source_sha256'],
                   control_source_sha256=own,methods=METHODS,cases=80,timed_runs=1200,memory_runs=400,plan=plan,jobs={})
    def save():state_path.write_text(json.dumps(state,indent=2)+'\n')
    save()
    for job in plan:
        name=job['name'];prefix=output/name;paths=[Path(str(prefix)+suffix) for suffix in ['_runs.csv','_calls.csv','_traces.csv','.json']]
        if name in state['jobs']:
            old=state['jobs'][name]
            if old['status']=='passed' and all(digest(ROOT/p)==sha for p,sha in old['output_sha256'].items()):print('cached',name,flush=True);continue
            raise RuntimeError('Preserve incomplete/corrupt job and choose another output directory: '+name)
        assert not any(p.exists() for p in paths),'Unregistered output exists'
        binary=HERE/'build'/('experiment_memory' if job['memory'] else 'experiment')
        command=[str(binary),'--input',str(ROOT/job['input']),'--specs',str(ROOT/job['specs']),
                 '--visibility',str(NAV/'frozen/grid8_visibility.txt'),'--output',str(prefix),'--cap',str(m['cap']),
                 '--methods',','.join(METHODS),'--anchors-only']
        if job['memory']:command+=['--repeats','1']
        record=dict(status='running',command=command,binary_sha256=digest(binary));state['jobs'][name]=record;save();print('starting',name,flush=True)
        with prefix.with_suffix('.log').open('w') as log:result=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        record.update(status='passed' if result.returncode==0 else 'failed',returncode=result.returncode)
        if not result.returncode:
            completion=json.loads(paths[-1].read_text());assert completion['status']=='passed' and completion['runs']==job['expected_runs'] and completion['memory_profile']==job['memory']
            record.update(completion=completion,output_sha256={str(p.relative_to(ROOT)):digest(p) for p in paths})
        save()
        if result.returncode:raise RuntimeError('Native verification failed: '+name)
        print('passed',name,completion['runs'],'runs',completion['calls'],'calls',flush=True)
    state['status']='passed';save()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=HERE/'results/full');p.add_argument('--plan',action='store_true');a=p.parse_args();main(a.output,a.plan)
