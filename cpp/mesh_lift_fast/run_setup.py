#!/usr/bin/env python3
"""Separate construction microbenchmark; run after the planner timing phase."""
import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main(output):
    output.mkdir(parents=True, exist_ok=True)
    assert not (output/'experiment.json').exists(), 'Choose a fresh setup output directory'
    state = dict(status='running', utc=datetime.now(timezone.utc).isoformat(),
                 source_sha256=sha(Path(__file__)), outputs={}, jobs={}, binaries={
                     n:sha(HERE/'build'/n) for n in ['setup', 'setup_memory']}, inputs={})
    for profile in [False, True]:
        for model in ['grid8', 'car16']:
            name = model+('_memory' if profile else '')
            source = ROOT/'cpp/experiments/frozen'/(model+'_model.txt')
            state['inputs'][str(source.relative_to(ROOT))] = sha(source)
            command = [str(HERE/'build'/('setup_memory' if profile else 'setup')), str(source), str(output/(name+'.csv'))]
            with (output/(name+'.log')).open('w') as log:
                process = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
            assert process.returncode == 0, name
            meta = json.loads((output/(name+'.log')).read_text())
            assert meta['status'] == 'passed' and meta['runs'] == 300 and meta['memory_profile'] == profile
            state['jobs'][name] = dict(command=command, completion=meta)
            for extension in ['csv', 'log']:
                path = output/(name+'.'+extension)
                state['outputs'][path.name] = sha(path)
    state['status'] = 'passed'
    (output/'experiment.json').write_text(json.dumps(state, indent=2)+'\n')
    print('SETUP_PASSED', 1200)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=HERE/'results/setup')
    main(parser.parse_args().output)
