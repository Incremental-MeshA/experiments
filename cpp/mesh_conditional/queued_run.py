#!/usr/bin/env python3
"""Build/test during un-timed allocation; measure after both original cohorts."""
import json,time,subprocess,sys,os
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def run(args,log):
 print('starting',args,flush=True)
 with (ROOT.parent/log).open('w') as f:subprocess.run(args,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,check=True)
while True:
 s=json.loads((ROOT/'cpp/mesh_envelope/results/full/experiment.json').read_text())
 if any(j.get('status')=='failed' for j in s['jobs'].values()):raise RuntimeError('Primary failed')
 if any(k.startswith('memory_') for k in s['jobs']):break
 time.sleep(15)
run(['make','-C','cpp/mesh_conditional','-j2','all','test'],'mesh_conditional_build_test.log')
run(['make','-C','cpp/mesh_conditional','sanitize'],'mesh_conditional_sanitize_build.log')
for model in ['grid8','car16']:
 run([str(HERE/'build/test_sanitize'),str(ROOT/f'cpp/experiments/frozen/{model}_model.txt')],f'mesh_conditional_sanitize_{model}.log')
while True:
 ready=True
 for path in [ROOT/'cpp/mesh_envelope/results/full/experiment.json',ROOT/'cpp/mesh_envelope/results/frontier/experiment.json']:
  if not path.exists():ready=False;continue
  s=json.loads(path.read_text())
  if any(j.get('status')=='failed' for j in s['jobs'].values()):raise RuntimeError('Prior cohort failed')
  ready &= s['status']=='passed'
 if ready:break
 time.sleep(15)
run([sys.executable,str(HERE/'prepare.py')],'mesh_conditional_prepare.log')
print('starting fresh conditional timings',flush=True)
subprocess.run([sys.executable,'-u',str(HERE/'run_all.py')],cwd=ROOT,check=True)
print('CONDITIONAL_PASSED',flush=True)
