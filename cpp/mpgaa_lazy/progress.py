#!/usr/bin/env python3
"""Read serial experiment progress without loading the measurement CSVs."""
import argparse
import csv
import json
import re
import time
from pathlib import Path
HERE=Path(__file__).resolve().parent
def progress(directory):
    state=json.loads((directory/'experiment.json').read_text());manifest=json.loads((HERE/'frozen/manifest.json').read_text())
    done=sum(j.get('completion',{}).get('runs',0) for j in state['jobs'].values() if j['status']=='passed')
    current=[]
    for name,j in state['jobs'].items():
        if j['status']=='running':
            path=directory/(name+'.log');lines=path.read_text().splitlines() if path.exists() else []
            last=next((line for line in reversed(lines) if re.match(r'^\d+ runs;',line)),None)
            if last:done+=int(last.split()[0])
            record=dict(job=name,last_completed_case=last)
            nav='_navigation_' in name
            calls=directory/(name+('_calls.csv' if nav else '.csv'))
            if calls.exists() and calls.stat().st_size:
                with calls.open('rb') as f:
                    f.seek(max(0,calls.stat().st_size-16384));tail=f.read().decode()
                full=tail.splitlines()[:-1] if not tail.endswith('\n') else tail.splitlines()
                if full:
                    row=next(csv.reader([full[-1]]))
                    if len(row)>=8 and row[0]!='case':
                        record['last_written_call']=dict(case=row[0],method=row[1 if nav else 2],repeat=row[2 if nav else 3],step=row[4 if nav else 5],status=row[7])
            current.append(record)
    return dict(status=state['status'],completed_jobs=sum(j['status']=='passed' for j in state['jobs'].values()),
        total_jobs=2*len(manifest['plan']),completed_episodes=done,total_episodes=manifest['timed_runs']+manifest['memory_runs'],current=current,
        failed_jobs=[n for n,j in state['jobs'].items() if j['status']=='failed'])
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,default=HERE/'results/full')
    p.add_argument('--watch',action='store_true');p.add_argument('--interval',type=float,default=45)
    args=p.parse_args();assert 1<=args.interval<=60
    while True:
        value=progress(args.directory);print(json.dumps(value,ensure_ascii=False),flush=True)
        if not args.watch or value['status']=='passed' or value['failed_jobs']:break
        time.sleep(args.interval)
