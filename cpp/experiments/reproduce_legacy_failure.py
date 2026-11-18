#!/usr/bin/env python3
"""Rebuild the archived original runner and reproduce its D* Lite counterexample."""
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent


def main():
    source=HERE/'results/pre_boundary_fix/source'
    manifest=json.loads((source/'manifest.json').read_text())
    required=['cpp/experiments/bench.cpp','cpp/experiments/memory.hpp',
              *[p for p in manifest['source_sha256'] if p.startswith('cpp/include/ima/')]]
    for name in required:
        p=source/Path(name).name if name.startswith('cpp/experiments/') else ROOT/name
        assert hashlib.sha256(p.read_bytes()).hexdigest()==manifest['source_sha256'][name],name
    with tempfile.TemporaryDirectory(prefix='ima_legacy_failure_') as directory:
        d=Path(directory);binary=d/'legacy'
        subprocess.run(['g++','-O2','-std=c++17','-I'+str(ROOT/'cpp/include'),str(source/'bench.cpp'),'-o',str(binary)],check=True)
        run=subprocess.run([str(binary),'--input',str(HERE/'frozen/car16_missions_r8.txt'),
                            '--output',str(d/'legacy.csv'),'--mode','mission','--methods','dstar_mesh',
                            '--case','car16__MA_room96__mission__s48101__r8','--repeats','1','--radius','8',
                            '--max-steps','160'],capture_output=True,text=True)
        assert run.returncode==1 and 'finite D* Lite label has no path' in run.stderr,run.stderr
    print('Reproduced the archived D* Lite mesh failure; corrected implementation passes the same mission in test_protocols.py.')


if __name__=='__main__':main()
