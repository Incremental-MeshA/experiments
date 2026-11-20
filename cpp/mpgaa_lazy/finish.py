#!/usr/bin/env python3
"""Run analysis and document generation only after measurements complete."""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
def main(wait):
    while True:
        state=json.loads((HERE/'results/full/experiment.json').read_text())
        if state['status']=='passed':break
        if any(j['status']=='failed' for j in state['jobs'].values()):raise RuntimeError('Measurement failed; preserve raw data')
        if not wait:raise RuntimeError('Measurements still running; use --wait')
        time.sleep(10)
    for script in ['analyze.py','report.py','notebook.py']:
        interpreter=os.environ.get('MPGAA_NOTEBOOK_PYTHON',sys.executable) if script=='notebook.py' else sys.executable
        print('starting',script,flush=True);subprocess.run([interpreter,str(HERE/script)],cwd=ROOT,check=True)
    print('POSTPROCESS_PASSED',flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--wait',action='store_true');main(p.parse_args().wait)
