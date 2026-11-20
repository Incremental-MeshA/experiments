#!/usr/bin/env python3
"""Queue structural control after all primary timing and allocation work."""
import json,time,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
while True:
 p=HERE/'results/full/experiment.json'
 if p.exists():
  s=json.loads(p.read_text())
  if s['status']=='passed':break
  if any(j.get('status')=='failed' for j in s.get('jobs',{}).values()):raise RuntimeError('Primary failed; retain partial data')
 time.sleep(15)
for name in ['prepare_frontier.py','run_frontier.py']:
 print('starting',name,flush=True);subprocess.run([sys.executable,str(HERE/name)],cwd=ROOT,check=True)
print('PRIMARY_AND_FRONTIER_PASSED',flush=True)
