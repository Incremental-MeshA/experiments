#!/usr/bin/env python3
"""Import byte-identical normal jobs after the allocation-only diagnostic fix."""
import json
import os
import platform
from pathlib import Path
from run_all import digest,save

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]

def main():
    archive=HERE/'results/pre_instrument_argument_fix';directory=HERE/'results/full'
    old=json.loads((archive/'experiment.json').read_text());manifest=json.loads((archive/'manifest.json').read_text())
    assert old['manifest_sha256']==digest(archive/'manifest.json')
    assert old['platform']==platform.platform()
    cpu=next(s.split(':',1)[1].strip() for s in Path('/proc/cpuinfo').read_text().splitlines() if s.startswith('model name'))
    assert cpu==old['cpu']
    for p,sha in manifest['files'].items():assert digest(ROOT/p)==sha,p
    changed='cpp/mpgaa_mesh/replay.cpp'
    for p,sha in manifest['sources'].items():
        assert digest(archive/'replay.cpp' if p==changed else ROOT/p)==sha,p
    binaries={name:digest(HERE/'build'/name) for name in old['binaries']}
    assert binaries['replay']==old['binaries']['replay']
    assert binaries['navigation']==old['binaries']['navigation']
    assert binaries['navigation_memory']==old['binaries']['navigation_memory']
    assert binaries['replay_memory']!=old['binaries']['replay_memory']
    assert json.loads((HERE/'results/preflight_fixed/check.json').read_text())['status']=='passed'
    timing={name:record for name,record in old['jobs'].items() if name.startswith('timing_')}
    assert len(timing)==len(manifest['plan'])==29
    for name,record in timing.items():
        assert record['status']=='passed'
        for p,sha in record['outputs'].items():assert digest(directory/p)==sha,p
    failed={name:record for name,record in old['jobs'].items() if not name.startswith('timing_')}
    assert list(failed)==['memory_replay_car16'] and failed['memory_replay_car16']['returncode']==-2
    for path in directory.glob('memory_replay_car16*'):
        assert not (archive/path.name).exists();path.replace(archive/path.name)
    manifest['sources'][changed]=digest(ROOT/changed)
    manifest['allocation_revision']=dict(reason='Snapshot live counter before require() message allocation; compiled only under IMA_TRACK_ALLOC.',
        archived_manifest_sha256=digest(archive/'manifest.json'),archived_experiment_sha256=digest(archive/'experiment.json'),
        archived_source_sha256=digest(archive/'replay.cpp'),unchanged_timing_binaries={k:binaries[k] for k in ['replay','navigation']},
        recovery_source_sha256=digest(Path(__file__)))
    save(HERE/'frozen/manifest.json',manifest)
    state={k:v for k,v in old.items() if k not in ['status','binaries','manifest_sha256','jobs']}
    state.update(status='running',binaries=binaries,manifest_sha256=digest(HERE/'frozen/manifest.json'),jobs=timing,
        imported_timing=dict(archived_manifest_sha256=digest(archive/'manifest.json'),archived_experiment_sha256=digest(archive/'experiment.json'),
                             normal_binary_identity='passed',jobs=list(timing)),
        memory_pass_environment=dict(cpu=cpu,platform=platform.platform(),affinity=sorted(os.sched_getaffinity(0))))
    save(directory/'experiment.json',state)
    print('Imported 29 verified normal jobs with identical native binaries; allocation pass ready')

if __name__=='__main__':main()
