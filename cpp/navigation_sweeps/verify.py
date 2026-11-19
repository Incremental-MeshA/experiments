#!/usr/bin/env python3
"""Small real navigation smoke, repeat/allocation/sanitizer decision parity."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
IGNORE={'repeat','time_s','setup_s','planner_s','initial_s','repair_s','sensing_s','reference_s','peak_heap_bytes','retained_heap_bytes'}
def rows(path):
    with path.open() as f:return list(csv.DictReader(f))
def normalized(data):return sorted([{k:v for k,v in r.items() if k not in IGNORE} for r in data],key=lambda r:(r['case'],r['method'],int(r.get('query',0))))
def main(sanitize):
    checks=[]
    subprocess.run(['make','-C',str(HERE),'test'],check=True)
    with tempfile.TemporaryDirectory(prefix='ima_navigation_check_') as tmp:
        d=Path(tmp)
        for control,dataset,substring in [('car16','arena_unknown','arena__unknown__s48101__r8'),('car16','arena_dynamic','arena__dynamic__s48101__k8__cr10__n8'),('grid8','random50_p20_dynamic','random50_p20__dynamic__s68101__k2__cr5__n2')]:
            outputs=[]
            for suffix in ['', '_memory',*(['_sanitize'] if sanitize else [])]:
                prefix=d/(control+dataset+suffix)
                command=[str(HERE/'build'/('experiment'+suffix)),'--input',str(HERE/'frozen'/f'{control}_{dataset}.txt'),
                         '--specs',str(HERE/'frozen'/f'{control}_{dataset}.specs.txt'),'--visibility',str(HERE/'frozen'/f'{control}_visibility.txt'),
                         '--case',substring,'--output',str(prefix),'--repeats','2' if not suffix else '1']
                subprocess.run(command,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=True)
                calls=rows(Path(str(prefix)+'_calls.csv'));runs=rows(Path(str(prefix)+'_runs.csv'))
                assert len({r['method'] for r in runs})==15
                first=[r for r in calls if r['repeat']=='0'];first_runs=[r for r in runs if r['repeat']=='0']
                if not suffix:
                    assert normalized(first)==normalized([r for r in calls if r['repeat']=='1'])
                    assert normalized(first_runs)==normalized([r for r in runs if r['repeat']=='1'])
                outputs.append((normalized(first),normalized(first_runs)))
            assert all(o==outputs[0] for o in outputs)
            checks.append(dict(control=control,case=substring,methods=15,calls=len(outputs[0][0]),repeat_allocation_sanitizer_parity=True))
    result=dict(status='passed',protocol_tests='passed',sanitize=sanitize,checks=checks)
    (HERE/'results').mkdir(exist_ok=True);(HERE/'results/verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sanitize',action='store_true');main(p.parse_args().sanitize)
