#!/usr/bin/env python3
"""Serial main study: all static radii, full grid k/cr, prespecified car anchors."""
import argparse
import copy
import json
import platform
import shutil
import subprocess
import sys
from datetime import datetime,timezone
from pathlib import Path
from study import HERE,ROOT,read_manifest,digest

def main(output,import_static=None,plan_only=False):
    m=read_manifest();plan=[]
    for memory in [False,True]:
        for r in sorted(m['records'],key=lambda r:(r['kind']!='unknown',r['control'],r['map'])):
            plan.append(dict(name=('memory_' if memory else 'timing_')+Path(r['path']).stem,memory=memory,
                             input=r['path'],specs=r['specs'],control=r['control'],kind=r['kind'],anchors_only=memory or r['anchors_only'],
                             expected_runs=len(r['memory_cases'])*len(m['methods']) if memory else r['timed_runs']))
    if plan_only:print(json.dumps(dict(cases=m['cases'],timed_runs=m['timed_runs'],memory_runs=m['memory_runs'],plan=plan),indent=2));return
    subprocess.run(['make','-C',str(HERE),'-j2','all'],check=True)
    output=output.resolve();output.mkdir(parents=True,exist_ok=True)
    cpu=next((s.split(':',1)[1].strip() for s in Path('/proc/cpuinfo').read_text().splitlines() if s.startswith('model name')),platform.processor())
    sources={str(p.relative_to(ROOT)):digest(p) for p in [Path(__file__),HERE/'study.py']}
    state_path=output/'experiment.json'
    if state_path.exists():
        state=json.loads(state_path.read_text());assert state['plan']==plan and state['manifest_sha256']==digest(HERE/'frozen/manifest.json') and state['selection_sha256']==m['selection_sha256']
        assert state['cpu']==cpu and state['platform']==platform.platform() and state['runner_sha256']==sources
    else:
        state=dict(status='running',utc=datetime.now(timezone.utc).isoformat(),cpu=cpu,platform=platform.platform(),workers=1,python=sys.version.split()[0],
                   git_parent=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),manifest_sha256=digest(HERE/'frozen/manifest.json'),
                   selection_sha256=m['selection_sha256'],source_sha256=m['source_sha256'],runner_sha256=sources,plan=plan,jobs={})
        if import_static:
            old=json.loads((import_static/'experiment.json').read_text())
            assert old['manifest_sha256']==state['manifest_sha256'] and old['source_sha256']==state['source_sha256']
            assert old['cpu']==cpu and old['platform']==state['platform'] and old['workers']==1
            imported={}
            for job in plan:
                if job['memory'] or job['kind']!='unknown':continue
                name=job['name'];record=copy.deepcopy(old['jobs'][name]);assert record['status']=='passed' and record['completion']['runs']==job['expected_runs']
                binary=HERE/'build/experiment';assert record['binary_sha256']==digest(binary)
                new_hashes={}
                for path,sha in record['output_sha256'].items():
                    source=import_static/Path(path).name;assert digest(source)==sha
                    target=output/source.name;assert not target.exists();shutil.copy2(source,target);new_hashes[str(target.relative_to(ROOT))]=sha
                log=import_static/(name+'.log')
                if log.exists():shutil.copy2(log,output/log.name)
                imported[name]=record['output_sha256'];record['output_sha256']=new_hashes;state['jobs'][name]=record
            state['imported_static']=dict(experiment_sha256=digest(import_static/'experiment.json'),jobs=imported,
                                          reason='Identical native binaries, source/input hashes, commands, CPU and serial protocol; complete static cohort only.')
    def save():state_path.write_text(json.dumps(state,indent=2)+'\n')
    save()
    for job in plan:
        prefix=output/job['name'];paths=[Path(str(prefix)+suffix) for suffix in ['_runs.csv','_calls.csv','_traces.csv','.json']]
        if job['name'] in state['jobs']:
            old=state['jobs'][job['name']]
            if old['status']=='passed' and all(digest(ROOT/p)==sha for p,sha in old['output_sha256'].items()):print('cached',job['name'],flush=True);continue
            raise RuntimeError('Incomplete/corrupt job; preserve outputs and use a new directory')
        if any(p.exists() for p in paths):raise RuntimeError('Unregistered output: '+str(prefix))
        binary=HERE/'build'/('experiment_memory' if job['memory'] else 'experiment')
        command=[str(binary),'--input',str(ROOT/job['input']),'--specs',str(ROOT/job['specs']),
                 '--visibility',str(HERE/'frozen'/f'{job["control"]}_visibility.txt'),'--output',str(prefix),
                 '--cap',str(m['cap']),'--methods',','.join(m['methods'])]
        if job['anchors_only']:command+=['--anchors-only']
        if job['memory']:command+=['--repeats','1']
        record=dict(status='running',command=command,binary_sha256=digest(binary));state['jobs'][job['name']]=record;save();print('starting',job['name'],flush=True)
        with prefix.with_suffix('.log').open('w') as log:result=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        record.update(status='passed' if result.returncode==0 else 'failed',returncode=result.returncode)
        if not result.returncode:
            completion=json.loads(paths[-1].read_text());assert completion['status']=='passed' and completion['runs']==job['expected_runs'] and completion['memory_profile']==job['memory']
            record.update(completion=completion,output_sha256={str(p.relative_to(ROOT)):digest(p) for p in paths})
        save()
        if result.returncode:raise RuntimeError('Native verification failed: '+job['name'])
        print('passed',job['name'],completion['runs'],'runs',completion['calls'],'calls',flush=True)
    state['status']='passed';save()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=HERE/'results/full');p.add_argument('--import-static',type=Path);p.add_argument('--plan',action='store_true')
    args=p.parse_args();main(args.output,args.import_static,args.plan)
