#!/usr/bin/env python3
"""Wait for serial native jobs, then build and audit the complete artifact."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]

def main(wait,directory=HERE/'results/full',controls_directory=None):
    directory=directory.resolve();state_path=directory/'experiment.json';last=None
    while True:
        try:state=json.loads(state_path.read_text())
        except json.JSONDecodeError:
            if not wait:raise
            time.sleep(1);continue
        failed=[n for n,j in state['jobs'].items() if j['status']=='failed']
        if failed:raise RuntimeError('Native verification failed: '+','.join(failed))
        completed=sum(j['status']=='passed' for j in state['jobs'].values())
        if completed!=last:print('Native jobs completed:',completed,'/',len(state['plan']),flush=True);last=completed
        if state['status']=='passed':break
        if not wait:raise RuntimeError('Native jobs are incomplete')
        time.sleep(30)
    controls=ROOT/'cpp/navigation_controls'
    controls_directory=(controls_directory or controls/'results'/directory.name).resolve()
    commands=[
        [sys.executable,str(controls/'run_all.py'),'--output',str(controls_directory)],
        [sys.executable,str(controls/'analyze.py'),'--directory',str(controls_directory),'--primary-directory',str(directory)],
        [sys.executable,str(HERE/'storage.py'),'--pack','--directory',str(directory)],
        [sys.executable,str(HERE/'analyze.py'),'--directory',str(directory)],
        [sys.executable,str(HERE/'report.py'),'--directory',str(directory),'--controls-directory',str(controls_directory)],
        [os.environ.get('NAV_NOTEBOOK_PYTHON',sys.executable),str(HERE/'notebook.py'),'--directory',str(directory)],
        [sys.executable,str(ROOT/'cpp/experiments/report.py'),'--navigation-directory',str(directory)],
        [sys.executable,str(HERE/'validate_artifact.py'),'--directory',str(directory),'--smoke','--output',str(directory/'validation.json')],
        [sys.executable,str(ROOT/'cpp/mesh_variants/validate_artifact.py')],
    ]
    for command in commands:
        print('Starting',Path(command[1]).name,flush=True);subprocess.run(command,cwd=ROOT,check=True)
    print('Postprocessing and audits passed',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--wait',action='store_true');parser.add_argument('--directory',type=Path,default=HERE/'results/full');parser.add_argument('--controls-directory',type=Path);args=parser.parse_args();main(args.wait,args.directory,args.controls_directory)
