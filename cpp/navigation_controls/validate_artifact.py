#!/usr/bin/env python3
"""Read-only validation of the separate stronger-grid control cohort."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
spec=importlib.util.spec_from_file_location('control_analysis',HERE/'analyze.py');analysis=importlib.util.module_from_spec(spec);spec.loader.exec_module(analysis)
digest=analysis.digest

def validate(directory=HERE/'results/full',primary=HERE.parent/'navigation_sweeps/results/full',smoke=False):
    state,meta,runs,calls,memory,raw,primary_hashes=analysis.load(directory,primary)
    ad=directory/'analysis';a=json.loads((ad/'analysis.json').read_text())
    assert a['status']=='passed' and a['source_sha256']==digest(HERE/'analyze.py')
    assert a['primary_analyzer_sha256']==digest(HERE.parent/'navigation_sweeps/analyze.py')
    assert a['verification_sha256']==digest(HERE/'results/verification.json')
    assert a['experiment_sha256']==digest(directory/'experiment.json') and a['raw_sha256']==raw and a['primary_run_sha256']==primary_hashes
    assert a['timed_runs']==len(runs)==1200 and a['memory_runs']==len(memory)==400 and a['planner_calls']==len(calls)
    assert a['exact_cost_disagreements']==0 and a['primary_decision_parity']==a['allocation_decision_parity']==a['repeat_decision_parity']=='passed'
    for name,sha in a['tables_sha256'].items():assert digest(ad/name)==sha,name
    for path,sha in a['figures_sha256'].items():assert digest(ROOT/path)==sha,path
    assert digest(ROOT/'docs/experiments/navigation_controls_body.md')==a['body_sha256']
    if smoke:subprocess.run(['make','-C',str(HERE),'-j2','all','test','sanitize'],cwd=ROOT,check=True)
    return dict(status='passed',cases=len(meta),timed_runs=len(runs),memory_runs=len(memory),planner_calls=len(calls),primary_decision_parity='passed',smoke=smoke)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,default=HERE/'results/full');p.add_argument('--primary-directory',type=Path,default=HERE.parent/'navigation_sweeps/results/full');p.add_argument('--smoke',action='store_true');p.add_argument('--output',type=Path);a=p.parse_args();result=validate(a.directory.resolve(),a.primary_directory.resolve(),a.smoke);print(json.dumps(result,indent=2))
    if a.output:a.output.write_text(json.dumps(result,indent=2)+'\n')
