#!/usr/bin/env python3
"""Preserve complete paired episodes from the nonbinding v1 guard only.

The interrupted episode is repeated in full. Frozen v1 sources, all raw data
and its failure log remain in development/cumulative-budget-v1. This is not a
case selection by speed and never combines two phases within a paired episode.
"""
import hashlib
import json
from pathlib import Path

from mesha.benchmark import environment
from mesha.md_benchmark import MAIN,ABLATIONS,INPUT,MAP_DIR

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'results/md_astar'
OLD=OUT/'development/cumulative-budget-v1'


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    old=json.loads((OLD/'environment.json').read_text());now=environment()
    for key in ['python','numpy','platform','cpu','cpu_count']:assert old[key]==now[key],('Environment changed',key)
    for p,value in old['sha256'].items():
        path=OLD/'source'/p if p.startswith('mesha/') else ROOT/p
        assert sha(path)==value,p
    oldtext=(OLD/'source/mesha/md_benchmark.py').read_text()
    newtext=(ROOT/'mesha/md_benchmark.py').read_text()
    insertion="        # D* Lite's counter is cumulative; give each query the same 3M budget.\n        if method.startswith('dstar'):planner.max_expansions=planner.expansions+3_000_000\n"
    assert newtext.replace(insertion,'',1)==oldtext,'More than the guard changed'
    for path in (ROOT/'mesha').glob('*.py'):
        if path.name!='md_benchmark.py':assert path.read_bytes()==(OLD/'source/mesha'/path.name).read_bytes(),path
    rows=[json.loads(s) for s in (OLD/'raw.jsonl').read_text().splitlines()]
    assert (OUT/'raw.jsonl').read_bytes()==(OLD/'raw.jsonl').read_bytes(),'Already migrated or modified'
    by_key={(r['id'],r['method'],r['repeat']):r for r in rows};assert len(by_key)==len(rows)
    payload=json.loads(INPUT.read_text());complete=[]
    for case in payload['cases']:
        methods=list(MAIN)+(list(ABLATIONS) if case['cohort'] in ('mixed','diagnostic') else [])
        keys={(case['id'],m,r) for m in methods for r in range(3)}
        if keys<=by_key.keys():
            for key in keys:
                if key[1].startswith('dstar'):
                    assert sum(r['expansions'] for r in by_key[key]['rows'])<=3_000_000
            complete.append(case['id'])
    kept=[r for r in rows if r['id'] in complete]
    (OUT/'raw.jsonl').write_text(''.join(json.dumps(r,allow_nan=False)+'\n' for r in kept))
    hashes={str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'mesha').glob('*.py'))}
    hashes[str(INPUT.relative_to(ROOT))]=sha(INPUT)
    for name in {c['map'] for c in payload['cases']}:hashes[str((MAP_DIR/name).relative_to(ROOT))]=sha(MAP_DIR/name)
    old['sha256']=hashes
    old['query_budget']='3,000,000 expansions per D* Lite query; adaptive backend call retains its 3,000,000 guard. No successful final run is capped.'
    old['prior_phases']=[dict(id='cumulative-budget-v1',environment='results/md_astar/development/cumulative-budget-v1/environment.json',
            source_root='results/md_astar/development/cumulative-budget-v1/source',complete_cases=complete,
            reason='D* Lite originally used one cumulative 3M guard for a 13-query episode. Only whole paired episodes that never hit that guard are retained; all partial episodes are repeated under the per-query guard.',
            runner_change='Only the max_expansions assignment before each query, outside its timer. Verified exact source-text diff and identical algorithm sources.',
            raw_sha256=sha(OLD/'raw.jsonl'))]
    old['budget_fix_date']=now['date']
    (OUT/'environment.json').write_text(json.dumps(old,indent=2)+'\n')
    record=dict(status='passed',retained_complete_cases=len(complete),retained_runs=len(kept),
                archived_runs=len(rows),repeated_incomplete_cases=sorted({r['id'] for r in rows}-set(complete)),
                no_within_episode_phase_mixing=True,all_prior_guards_nonbinding=True)
    (OUT/'budget_migration.json').write_text(json.dumps(record,indent=2)+'\n');print(record)


if __name__=='__main__':main()
