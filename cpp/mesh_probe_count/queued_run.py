#!/usr/bin/env python3
import json,time,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
while True:
 p=ROOT/'cpp/mesh_conditional/results/full/experiment.json'
 if p.exists():
  s=json.loads(p.read_text())
  if any(j.get('status')=='failed' for j in s['jobs'].values()):raise RuntimeError('Conditional cohort failed')
  if any(k.startswith('memory_') for k in s['jobs']):break
 time.sleep(15)
# Compile only after all regular timing is over; allocation bytes are process-local.
subprocess.run([sys.executable,str(HERE/'run.py'),'--build'],cwd=ROOT,check=True)
while json.loads((ROOT/'cpp/mesh_conditional/results/full/experiment.json').read_text())['status']!='passed':time.sleep(15)
subprocess.run([sys.executable,'-u',str(HERE/'run.py')],cwd=ROOT,check=True)
