#!/usr/bin/env python3
"""Serial final rebuild after development compiles; gate subsequent timings."""
import json,hashlib,subprocess,time,os
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
# Run this only after all earlier development build sessions have completed.
(HERE/'algorithms.hpp').touch()
with (ROOT.parent/'mesh_symmetric_serial_build.log').open('w') as f:subprocess.run(['make','-C','cpp/mesh_symmetric','-j2','all','test'],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,check=True)
with (ROOT.parent/'mesh_symmetric_serial_asan_build.log').open('w') as f:subprocess.run(['make','-C','cpp/mesh_symmetric','sanitize'],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,check=True)
for model in ['grid8','car16']:
 with (ROOT.parent/f'mesh_symmetric_serial_asan_{model}.log').open('w') as f:subprocess.run([str(HERE/'build/test_sanitize'),str(ROOT/f'cpp/experiments/frozen/{model}_model.txt')],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,check=True)
subprocess.run(['python',str(HERE/'preflight.py')],cwd=ROOT,check=True)
# Only this marker permits the next timing cohort to start.
validation=HERE/'validation';validation.mkdir(exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
record=dict(status='passed',sources={p.name:sha(p) for p in HERE.glob('*.hpp')},binaries={p.name:sha(p) for p in (HERE/'build').iterdir() if p.name in ['replay','replay_memory','navigation','navigation_memory']})
(validation/'build_ready.json').write_text(json.dumps(record,indent=2)+'\n');print('SMD_BUILD_READY',flush=True)
