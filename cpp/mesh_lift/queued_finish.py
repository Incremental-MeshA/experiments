#!/usr/bin/env python3
"""Keep all counting, plotting and document work outside the timing window."""
import json,subprocess,sys,time,os
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
env=dict(os.environ,MPLCONFIGDIR='/tmp/mesh-lift-mpl',XDG_CACHE_HOME='/tmp/mesh-lift-cache')
while True:
 p=HERE/'results/full/experiment.json'
 if p.exists():
  state=json.loads(p.read_text())
  if any(j['status']=='failed' for j in state['jobs'].values()):raise RuntimeError('A canonical measurement failed')
  if state['status']=='passed':break
 time.sleep(15)
for name in ['probe.py','analyze.py','report.py','notebook.py','validate.py']:
 print('starting',name,flush=True)
 python=str(ROOT.parent/'md_tools_venv/bin/python') if name=='notebook.py' else sys.executable
 with (ROOT.parent/('mesh_lift_'+name.removesuffix('.py')+'.log')).open('w') as log:subprocess.run([python,str(HERE/name)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
print('ALL_POSTPROCESSING_PASSED',flush=True)
