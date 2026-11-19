#!/usr/bin/env python3
"""Freeze a new native cohort while reusing byte-identical earlier inputs."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
METHODS=['lba','lazy_lba','mesha','mesh_parall','dstar_lattice','dstar_mesh','mpgaa',
         'md_astar','md64','md_scan','lba_reuse','prefix_positive','cmesh_dstar','suffix_mesh','boundary_mesh']


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    original=ROOT/'cpp/experiments/frozen/manifest.json'
    source=json.loads(original.read_text())
    for path,sha in source['source_sha256'].items():assert digest(ROOT/path)==sha,path
    for record in source['records']:assert digest(ROOT/record['path'])==record['sha256']
    paths=[*sorted((ROOT/'cpp/include/ima').glob('*.hpp')),
           ROOT/'cpp/experiments/memory.hpp',ROOT/'cpp/experiments/dstar_boundary.hpp',
           *[HERE/p for p in ['bench.cpp','variants.hpp','Makefile','run_all.py','freeze.py','test_models.cpp','test_variants.py']]]
    target=HERE/'frozen/manifest.json'
    if target.exists():raise RuntimeError('Manifest already exists; preserve any measured cohort before refreezing')
    manifest=dict(status='frozen',base_manifest=str(original.relative_to(ROOT)),base_manifest_sha256=digest(original),
                  records=source['records'],seeds=source['seeds'],experiment_methods=METHODS,
                  cap=source['cap'],repeats=3,memory_repeats=1,total_replay_cases=186,total_missions=40,
                  source_sha256={str(p.relative_to(ROOT)):digest(p) for p in paths},
                  contexts_sha256={str((ROOT/r['path']).with_suffix('.contexts.json').relative_to(ROOT)):
                                  digest((ROOT/r['path']).with_suffix('.contexts.json')) for r in source['records']},
                  protocol='New contemporaneous 15-method cohort. Same immutable worlds, events, references and budgets as the previous 11-method cohort. No pooling of timing measurements across cohorts.')
    target.parent.mkdir(exist_ok=True);target.write_text(json.dumps(manifest,indent=2)+'\n')
    print(target)


if __name__=='__main__':main()
