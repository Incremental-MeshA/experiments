#!/usr/bin/env python3
"""Export original double costs/mesh and frozen queries; no search in this tool."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mesha.maps import load_map
from mesha.mesh import build_mesh
from mesha.primitives import build_control_set


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export(output, suite='md', control_name='car16'):
    if suite != 'model' and control_name != 'car16':
        raise ValueError('Frozen benchmark queries require car16')
    control = build_control_set(control_name)
    mesh = build_mesh(control)
    sources = [ROOT/'mesha/primitives.py', ROOT/'mesha/mesh.py', Path(__file__).resolve()]
    cases = []
    if suite == 'md':
        path = ROOT/'data/benchmarks/md_astar.json'
        sources.append(path)
        cases = json.loads(path.read_text())['cases']
    elif suite == 'upstream':
        path = ROOT/'data/benchmarks/incremental_mesha.json'
        runs = ROOT/'results/runs.json'
        sources += [path, runs]
        records = json.loads(runs.read_text())['records']
        cost = {(r['id'], r['query']): r['cost'] for r in records
                if r['algorithm'] == 'lba' and r['weight'] == 1}
        for episode in json.loads(path.read_text())['instances']:
            queries = [dict(start=q['start'], goal=q['goal'], blocks=q['new_blocks'], opens=[],
                            expected=cost[episode['id'], i], category='initial' if i == 0 else 'increase_finite',
                            event='original') for i, q in enumerate(episode['queries'])]
            cases.append(dict(id='upstream__'+episode['id'], cohort='upstream', map=episode['map'], queries=queries))
    names = sorted({c['map'] for c in cases})
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    # 17 significant digits round-trip IEEE-754 binary64. No cost quantization.
    def token(x):
        if isinstance(x, str):
            return json.dumps(x, ensure_ascii=True)
        if isinstance(x, float):
            return format(x, '.17g')
        return str(x)
    with output.open('w', newline='\n') as f:
        def row(*items):
            f.write(' '.join(map(token, items))+'\n')
        f.write('IMA_CPP 1\n')
        row(control.name, control.n_theta, len(control), mesh.n_configs)
        row(*mesh.initial_of_theta)
        for p in control.primitives:
            row(p.start_theta, p.end_theta, p.di, p.dj, p.cost, len(p.cells))
            row(*(v for cell in p.cells for v in cell))
        for cfg in range(mesh.n_configs):
            row(mesh.theta_of_config[cfg], *mesh.origin[cfg], mesh.signature[cfg], len(mesh.successors[cfg]), len(mesh.finals[cfg]))
            for edge in mesh.successors[cfg]:
                row(*edge)
            for final in mesh.finals[cfg]:
                row(*final)
        row(len(names))
        for name in names:
            path = ROOT/'data/maps'/name
            sources.append(path)
            grid = load_map(path)
            row(name, *grid.shape)
            for line in grid:
                f.write(''.join('#' if x else '.' for x in line)+'\n')
        row(len(cases))
        for c in cases:
            row(c['id'], c['cohort'], names.index(c['map']), len(c['queries']))
            for q in c['queries']:
                row(*q['start'], *q['goal'], float(q['expected']) if q['expected'] is not None else -1.0,
                    q['category'], q['event'], len(q['blocks']), len(q['opens']))
                row(*(v for cell in q['blocks'] for v in cell))
                row(*(v for cell in q['opens'] for v in cell))
    manifest = dict(format=1, suite=suite, control=control_name, primitives=len(control),
                    mesh_configs=mesh.n_configs, episodes=len(cases), queries=sum(len(c['queries']) for c in cases),
                    input_sha256=sha(output), source_sha256={str(p.relative_to(ROOT)): sha(p) for p in sources},
                    costs='Original IEEE-754 binary64; decimal export uses 17 significant digits; no rounding to microcosts.')
    output.with_suffix(output.suffix+'.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(output, manifest['episodes'], 'episodes;', manifest['queries'], 'queries')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', choices=['md', 'upstream', 'model'], default='md')
    parser.add_argument('--control', choices=['car16', 'legacy8'], default='car16')
    parser.add_argument('--output', type=Path, default=ROOT/'cpp/data/car16_md.txt')
    args = parser.parse_args()
    export(args.output, args.suite, args.control)
