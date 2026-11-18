#!/usr/bin/env python3
"""Build outside the timer, record provenance, then run one serial C++ process."""
import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT/'cpp'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args):
    subprocess.run(['make', '-C', str(CPP), 'all'], check=True)
    input_path = args.input.resolve()
    manifest = json.loads(input_path.with_suffix(input_path.suffix+'.json').read_text())
    if digest(input_path) != manifest['input_sha256']:
        raise RuntimeError('Input SHA-256 differs from export manifest')
    for name, sha in manifest['source_sha256'].items():
        if digest(ROOT/name) != sha:
            raise RuntimeError('Export source changed; re-export inputs: '+name)
    binary = CPP/'build/mesh_bench'
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if any(Path(str(output)+suffix).exists() for suffix in ['', '.json', '.provenance.json']):
        raise RuntimeError('Output already exists; use a new filename')
    command = [str(binary), '--input', str(input_path), '--output', str(output), '--repeats', str(args.repeats),
               '--seed', str(args.seed), '--max-expansions', str(args.max_expansions), '--cohort', args.cohort]
    if args.methods:
        command += ['--methods', args.methods]
    if args.case:
        command += ['--case', args.case]
    if args.verify_only:
        command += ['--verify-only']
    cpu = platform.processor()
    cpu_file = Path('/proc/cpuinfo')
    if cpu_file.exists():
        cpu = next((s.split(':', 1)[1].strip() for s in cpu_file.read_text().splitlines() if s.startswith('model name')), cpu)
    sources = sorted([*CPP.glob('include/ima/*.hpp'), *CPP.glob('src/*.cpp'), CPP/'Makefile', CPP/'CMakeLists.txt'])
    provenance = dict(status='running', utc=datetime.now(timezone.utc).isoformat(),
                      platform=platform.platform(), cpu=cpu, python_driver=sys.version.split()[0], workers=1,
                      git_parent=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                      binary_sha256=digest(binary), input_sha256=digest(input_path),
                      input_relative=str(input_path.relative_to(ROOT)) if input_path.is_relative_to(ROOT) else None,
                      source_sha256={str(p.relative_to(ROOT)): digest(p) for p in sources},
                      command=command, protocol='One serial native process; randomized method order; independent full path validation outside timers; constructors separate; no Python solver calls.')
    destination = Path(str(output)+'.provenance.json')
    destination.write_text(json.dumps(provenance, indent=2)+'\n')
    result = subprocess.run(command, cwd=ROOT)
    provenance.update(status='passed' if result.returncode == 0 else 'failed', returncode=result.returncode)
    if result.returncode == 0:
        provenance['csv_sha256'] = digest(output)
        provenance['completion_sha256'] = digest(Path(str(output)+'.json'))
    destination.write_text(json.dumps(provenance, indent=2)+'\n')
    return result.returncode


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=CPP/'data/car16_md.txt')
    parser.add_argument('--output', type=Path, default=CPP/'results/raw.csv')
    parser.add_argument('--methods', default='')
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--seed', type=int, default=761116)
    parser.add_argument('--max-expansions', type=int, default=3_000_000)
    parser.add_argument('--cohort', default='all')
    parser.add_argument('--case', default='')
    parser.add_argument('--verify-only', action='store_true')
    sys.exit(run(parser.parse_args()))
