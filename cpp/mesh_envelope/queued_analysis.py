#!/usr/bin/env python3
"""Run no analysis workload until both serial experiment cohorts finish."""
import json,time,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
while True:
 states=[]
 for name in ['full','frontier','conditional','symmetric']:
  p=(ROOT/f'cpp/mesh_{name}/results/full/experiment.json') if name in ['conditional','symmetric'] else HERE/f'results/{name}/experiment.json'
  if not p.exists():states.append(None);continue
  s=json.loads(p.read_text());states.append(s)
  if any(j.get('status')=='failed' for j in s.get('jobs',{}).values()):raise RuntimeError('Failed measurement cohort '+name)
 if all(s and s['status']=='passed' for s in states):break
 time.sleep(15)
for name in ['analyze.py','analyze_frontier.py','../mesh_conditional/analyze.py','../mesh_symmetric/analyze.py','report.py']:
 print('starting',name,flush=True);subprocess.run([sys.executable,str(HERE/name)],cwd=ROOT,check=True)
venv=ROOT.parent/'md_tools_venv/bin/python'
print('starting notebook',flush=True);subprocess.run([str(venv) if venv.exists() else sys.executable,str(HERE/'notebook.py')],cwd=ROOT,check=True)
print('starting validation',flush=True);subprocess.run([sys.executable,str(HERE/'validate.py')],cwd=ROOT,check=True)
print('ALL_ANALYSIS_PASSED',flush=True)
