#!/usr/bin/env python3
import json,time,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
while not (HERE/'validation/build_ready.json').exists():time.sleep(15)
while True:
 p=ROOT/'cpp/mesh_probe_count/results/experiment.json'
 if p.exists() and json.loads(p.read_text())['status']=='passed':break
 time.sleep(15)
subprocess.run([sys.executable,str(HERE/'prepare.py')],cwd=ROOT,check=True)
subprocess.run([sys.executable,'-u',str(HERE/'run_all.py')],cwd=ROOT,check=True)
print('SYMMETRIC_PASSED',flush=True)
