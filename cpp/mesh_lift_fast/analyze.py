#!/usr/bin/env python3
"""Validate the frozen cohort and analyze paired Lift simplifications."""
import argparse
import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault('MPLCONFIGDIR', '/tmp/lift_fast_mpl')
os.environ.setdefault('XDG_CACHE_HOME', '/tmp/lift_fast_cache')
import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DEST = ROOT / 'docs/mesh_lift_fast'
HASH = ['path_hash', 'world_hash', 'belief_hash', 'fingerprint', 'mv_trace_hash']
NATIVE = ['lift_mesh', 'cascade_lift', 'zero_lift', 'zero_cascade', 'fast_lift', 'fast_cascade']
LABEL = {
    'lift_mesh': 'Lift (weighted)', 'cascade_lift': 'Cascade (weighted)',
    'zero_lift': 'Lift, zero only', 'zero_cascade': 'Cascade, zero only',
    'fast_lift': 'Lift, simplified', 'fast_cascade': 'Cascade, simplified',
    'mesha_reuse': 'MeshA* reuse', 'batch_mpgaa': 'Batch-MPGAA*',
    'octile_reuse': 'Octile reuse', 'fast_all_closed': 'Scan all CLOSED',
    'fast_no_depth': 'No depth tie', 'fast_trace': 'Enable trace hash',
    'fast_raw_finals': 'Repeated finals', 'fast_recompute_base': 'Recompute base',
    'fast_slow_policy': 'Allocate policy chains',
}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read(path):
    return pd.read_csv(path, dtype={k: str for k in HASH})

def gm(values):
    a = np.asarray(values, dtype=float)
    a = a[np.isfinite(a) & (a > 0)]
    return float(np.exp(np.log(a).mean())) if len(a) else np.nan

def save(frame, path):
    frame.to_csv(path, index=False, float_format='%.17g')

def equivalent(a, b, keys, ignored=()):
    a, b = [d.set_index(keys).sort_index() for d in (a, b)]
    columns = [c for c in a if not c.endswith('_s') and c not in
               ['repeat', 'peak_heap_bytes', 'retained_heap_bytes', 'allocation_calls', *ignored]]
    assert_frame_equal(a[columns], b[columns], check_exact=True, check_dtype=False)
    return len(a)

def main(directory, setup_directory):
    manifest_path = HERE / 'frozen/manifest.json'
    manifest = json.loads(manifest_path.read_text())
    state = json.loads((directory / 'experiment.json').read_text())
    assert state['status'] == 'passed' and state['manifest_sha256'] == sha(manifest_path)
    for path, digest in {**manifest['files'], **manifest['sources']}.items():
        assert sha(ROOT / path) == digest, path
    for name, digest in state['binaries'].items():
        assert sha(HERE / 'build' / name) == digest, name
    for job in state['jobs'].values():
        assert job['status'] == 'passed'
        for name, digest in job['outputs'].items():
            assert sha(directory / name) == digest, name
    contexts = json.loads((ROOT / manifest['contexts_file']).read_text())
    meta = pd.DataFrame([dict(
        case=key, cohort=v['cohort'], control=v['control'], map=v['map'],
        family=v['family'], panel=v['panel'], original_id=v['original_id'],
        seed=v.get('seed', 0), radius=v.get('params', {}).get('radius', 0),
        k=v.get('params', {}).get('k', 0), cr=v.get('params', {}).get('cr', 0),
        truth_optimum=v.get('initial_optimum', v.get('truth_optimum', np.nan)),
    ) for key, v in contexts.items()])
    out = directory / 'analysis'
    out.mkdir(exist_ok=True)
    calls, profiled, episodes, heaps, qualities, changes = [], [], [], [], [], []
    matched_calls = matched_runs = 0
    for job in manifest['plan']:
        nav = job['mode'] == 'navigation'
        tp, mp = [directory / (prefix + job['name']) for prefix in ['timing_', 'memory_']]
        a = read(Path(str(tp) + '_calls.csv') if nav else tp.with_suffix('.csv'))
        b = read(Path(str(mp) + '_calls.csv') if nav else mp.with_suffix('.csv'))
        first = a[a.repeat.eq(0)]
        matched_calls += equivalent(first, b, ['case', 'method', 'query'])
        assert b.peak_heap_bytes.ge(b.retained_heap_bytes).all()
        calls.append(a.drop(columns=['family', 'radius', 'k', 'cr'], errors='ignore'))
        profiled.append(b.drop(columns=['family', 'radius', 'k', 'cr'], errors='ignore'))
        if nav:
            runs, memory_runs = [read(Path(str(p) + '_runs.csv')) for p in [tp, mp]]
            matched_runs += equivalent(runs[runs.repeat.eq(0)], memory_runs, ['case', 'method'])
            heaps.append(memory_runs[['case', 'method', 'peak_heap_bytes', 'retained_heap_bytes']])
            for _, v in runs.iterrows():
                episodes.append(dict(case=v['case'], method=v.method, repeat=v['repeat'],
                                     full_s=v.setup_s + v.planner_s, initial_s=v.setup_s + v.initial_s,
                                     repair_s=v.repair_s, complete=v.status == 'goal', status=v.status,
                                     travel_cost=v.travel_cost, moves=v.moves, plans=v.plans))
            qualities.append(runs[runs.repeat.eq(0)][['case', 'method', 'status', 'travel_cost', 'moves', 'plans']])
            if job['name'].endswith('dynamic'):
                for _, v in runs[runs.repeat.eq(0)].iterrows():
                    c = contexts[v['case']]
                    changes.append(dict(case=v['case'], method=v.method, map=c['map'], k=c['params']['k'],
                                        n=c['params']['n'], requested_cr=c['params']['cr'], phases=v.phases,
                                        clamped=v.clamped_phases,
                                        actual_cr=100*v.actual_changes/(np.prod(c['shape'])*v.phases)
                                        if v.phases else np.nan))
        else:
            heaps.append(b.groupby(['case', 'method'], as_index=False).agg(
                peak_heap_bytes=('peak_heap_bytes', 'max'), retained_heap_bytes=('retained_heap_bytes', 'last')))
            for key, g in a.groupby(['case', 'method', 'repeat']):
                capped = g.status.isin(['capped', 'skipped_after_cap']).any()
                episodes.append(dict(zip(['case', 'method', 'repeat'], key)) | dict(
                    full_s=g.time_s.sum()+g.setup_s.sum(),
                    initial_s=g.loc[g['query'].eq(0), ['time_s', 'setup_s']].sum().sum(),
                    repair_s=g.loc[g['query'].gt(0), 'time_s'].sum(), complete=not capped,
                    status='capped' if capped else 'complete', travel_cost=0, moves=0, plans=g.planned.sum()))
    calls = pd.concat(calls, ignore_index=True).merge(meta, on='case', validate='many_to_one')
    profiled = pd.concat(profiled, ignore_index=True).merge(meta, on='case', validate='many_to_one')
    runs = pd.DataFrame(episodes)
    assert len(runs) == manifest['timed_runs']
    # Native binaries validate every uncapped returned path and its cost.
    done = ~calls.status.isin(['capped', 'skipped_after_cap'])
    finite = calls.cost.notna() & calls.expected.notna() & done
    bad = int((calls.loc[finite, 'cost']-calls.loc[finite, 'expected']).abs().gt(1e-6).sum())
    bad += int(((calls.cost.notna() != calls.expected.notna()) & done).sum())
    assert bad == 0
    q = calls[calls.repeat.eq(0)].copy()
    native = q[q.method.isin(NATIVE) | q.method.str.startswith('fast_')]
    assert native.expansions.eq(native.mv_boundary_expansions+native.mv_interior_expansions).all()
    assert native[native.control.eq('car16')].mv_interior_expansions.sum() > 0
    counters = ['expansions', 'checked_cells', 'notify_probes', 'heuristic_pops', 'backend_calls', 'certified']
    counters += [c for c in q if (c.startswith('mv_') or c.startswith('lift_') or c.startswith('fast_'))
                 and c not in ['mv_trace_hash', 'mv_records', 'mv_active_watches']]
    q['phase'] = np.where(q['query'].eq(0), 'initial', 'repair')
    work = q.groupby(['case', 'method', 'phase'], as_index=False)[['blocks', 'opens', *counters]].sum().merge(meta, on='case')
    save(work, out / 'work.csv')
    allocations = profiled[profiled.panel.isin(['main', 'ablation'])].copy()
    allocations['phase'] = np.where(allocations['query'].eq(0), 'initial', 'repair')
    alloc = allocations.groupby(['case', 'method', 'phase'], as_index=False).allocation_calls.sum().merge(meta, on='case')
    save(alloc, out / 'allocation_requests.csv')
    metrics = runs.groupby(['case', 'method'], as_index=False)[['full_s', 'initial_s', 'repair_s', 'travel_cost', 'moves', 'plans']].median()
    metrics = metrics.merge(runs.groupby(['case', 'method'], as_index=False).complete.all())
    metrics = metrics.merge(pd.concat(heaps), on=['case', 'method'], validate='one_to_one').merge(meta, on='case')
    assert len(metrics) == manifest['memory_runs']
    save(metrics, out / 'case_metrics.csv')
    save(metrics.groupby(['cohort', 'control', 'panel', 'method'], as_index=False).agg(
        configurations=('case', 'size'), complete=('complete', 'sum')), out / 'completion.csv')
    save(q[q.status.eq('capped')][['case', 'method', 'query', 'phase', 'expansions']], out / 'caps.csv')
    baselines = {
        'fast_lift': ['lift_mesh', 'zero_lift', 'fast_cascade', 'mesha_reuse', 'batch_mpgaa', 'octile_reuse'],
        'fast_cascade': ['cascade_lift', 'zero_cascade', 'fast_lift', 'mesha_reuse', 'batch_mpgaa', 'octile_reuse'],
        'zero_lift': ['lift_mesh'], 'zero_cascade': ['cascade_lift'],
    }
    pairs = []
    for case, group in metrics.groupby('case'):
        g = group.set_index('method')
        for method, controls in baselines.items():
            if method not in g.index:
                continue
            a = g.loc[method]
            if a.panel == 'ablation':
                if method != 'fast_cascade':
                    continue
                controls = [b for b in manifest['ablations'] if b != method]
            for baseline in controls:
                if baseline not in g.index:
                    continue
                b = g.loc[baseline]
                ok = bool(a.complete and b.complete)
                row = dict(case=case, method=method, baseline=baseline, complete=ok)
                row.update({c: a[c] for c in ['cohort', 'control', 'map', 'family', 'panel', 'seed', 'radius', 'k', 'cr']})
                for phase in ['full', 'initial', 'repair']:
                    row[phase+'_speedup'] = b[phase+'_s']/a[phase+'_s'] if ok and a[phase+'_s'] > 0 else np.nan
                row['memory_multiplier'] = a.peak_heap_bytes/b.peak_heap_bytes if ok and b.peak_heap_bytes else np.nan
                pairs.append(row)
    pairs = pd.DataFrame(pairs)
    save(pairs, out / 'paired_cases.csv')
    def aggregate(keys, name):
        rows = []
        for key, d in pairs.groupby(keys):
            if not isinstance(key, tuple):
                key = (key,)
            rows.append(dict(zip(keys, key)) | dict(
                configurations=len(d), pairs=int(d.complete.sum()), wins10=int(d.full_speedup.ge(1.1).sum()),
                full_speedup=gm(d.full_speedup), initial_speedup=gm(d.initial_speedup),
                repair_speedup=gm(d.repair_speedup), memory_multiplier=gm(d.memory_multiplier)))
        result = pd.DataFrame(rows)
        save(result, out / name)
        return result
    summary = aggregate(['cohort', 'control', 'panel', 'method', 'baseline'], 'summary.csv')
    maps = aggregate(['cohort', 'control', 'panel', 'map', 'method', 'baseline'], 'map_pairs.csv')
    aggregate(['cohort', 'control', 'panel', 'family', 'method', 'baseline'], 'family_pairs.csv')
    aggregate(['cohort', 'control', 'panel', 'map', 'radius', 'k', 'cr', 'method', 'baseline'], 'parameter_pairs.csv')
    # A failed later repair does not erase a completed initial-search comparison.
    initial = metrics.merge(q[q['query'].eq(0)][['case', 'method', 'status']], on=['case', 'method'])
    initial['initial_complete'] = ~initial.status.isin(['capped', 'skipped_after_cap'])
    save(initial, out / 'initial_cases.csv')
    initial_pairs = []
    for case, group in initial.groupby('case'):
        g = group.set_index('method')
        for method, baseline in [('fast_lift', 'lift_mesh'), ('fast_cascade', 'cascade_lift'),
                                 ('zero_lift', 'lift_mesh'), ('zero_cascade', 'cascade_lift')]:
            if method in g.index and baseline in g.index:
                a, b = g.loc[method], g.loc[baseline]
                ok = bool(a.initial_complete and b.initial_complete)
                initial_pairs.append(dict(case=case, method=method, baseline=baseline, cohort=a.cohort,
                                          control=a.control, panel=a.panel, complete=ok,
                                          speedup=b.initial_s/a.initial_s if ok else np.nan))
    save(pd.DataFrame(initial_pairs), out / 'initial_pairs.csv')
    # Only the tie-breaking ablation may deliberately change paths/expansions.
    ablation = q[q.panel.eq('ablation')]
    deterministic_matches = 0
    for method in ['fast_all_closed', 'fast_trace', 'fast_raw_finals', 'fast_recompute_base', 'fast_slow_policy']:
        a, b = [ablation[ablation.method.eq(m)].set_index(['case', 'query']).sort_index()
                for m in ['fast_cascade', method]]
        assert_frame_equal(a[['path_hash', 'expansions', 'cost', 'status']],
                           b[['path_hash', 'expansions', 'cost', 'status']], check_exact=True)
        deterministic_matches += len(a)
    query_medians = calls[calls.planned.eq(1) & done].groupby(['case', 'method', 'query'], as_index=False).agg(
        time_s=('time_s', 'median'), blocks=('blocks', 'first'), opens=('opens', 'first')).merge(meta, on='case')
    query_medians['edits'] = query_medians.blocks+query_medians.opens
    query_medians['edit_bin'] = pd.cut(query_medians.edits, [-1, 0, 4, 16, 64, 1e12], labels=['0', '1-4', '5-16', '17-64', '>64'])
    repair_queries = query_medians[query_medians['query'].gt(0)]
    save(repair_queries.groupby(['cohort', 'control', 'panel', 'method', 'edit_bin'], observed=True).agg(
        queries=('time_s', 'size'), median_ms=('time_s', lambda v: 1000*v.median()),
        p95_ms=('time_s', lambda v: 1000*v.quantile(.95))).reset_index(), out / 'edits_latency.csv')
    save(repair_queries.groupby(['cohort', 'control', 'panel', 'map', 'method'], observed=True).agg(
        queries=('time_s', 'size'), p50_ms=('time_s', lambda v: 1000*v.median()),
        p95_ms=('time_s', lambda v: 1000*v.quantile(.95))).reset_index(), out / 'latency.csv')
    quality = pd.concat(qualities).merge(meta, on='case')
    quality['static_stretch'] = np.where(quality.cohort.eq('navigation_unknown') & quality.status.eq('goal'),
                                         quality.travel_cost/quality.truth_optimum, np.nan)
    assert quality.static_stretch.dropna().ge(1-1e-6).all()
    save(quality, out / 'navigation_quality.csv')
    save(pd.DataFrame(changes), out / 'actual_changes.csv')
    failures = q[q.panel.eq('navigation') & q.status.eq('no_path')]
    assert not failures.loc[failures.cohort.eq('navigation_unknown'), 'truth_cost'].notna().any()
    save(failures[['case', 'method', 'cohort', 'map', 'step', 'truth_cost']], out / 'no_path_diagnostics.csv')
    dispersion = runs.groupby(['case', 'method']).full_s.apply(
        lambda v: float((v-v.median()).abs().median()/v.median())).rename('relative_mad').reset_index()
    save(dispersion, out / 'dispersion.csv')
    setup_state = json.loads((setup_directory / 'experiment.json').read_text())
    assert setup_state['status'] == 'passed'
    for name, digest in setup_state['outputs'].items():
        assert sha(setup_directory / name) == digest
    for name, digest in setup_state['binaries'].items():
        assert sha(HERE / 'build' / name) == digest
    setups = pd.concat([read(setup_directory / (m+'.csv')) for m in ['grid8', 'car16']])
    setup_memory = pd.concat([read(setup_directory / (m+'_memory.csv')) for m in ['grid8', 'car16']])
    setup_summary = setups.groupby(['model', 'method'], as_index=False).time_s.median().merge(
        setup_memory.groupby(['model', 'method'], as_index=False)[['peak_heap_bytes', 'retained_heap_bytes', 'allocation_calls']].median())
    save(setup_summary, out / 'setup.csv')
    figures = {}
    plt.rcParams.update({'font.size': 13, 'pdf.fonttype': 42, 'axes.spines.top': False, 'axes.spines.right': False})
    colors = {'fast_lift': '#D55E00', 'fast_cascade': '#0072B2', 'zero_cascade': '#009E73',
              'lift_mesh': '#E69F00', 'cascade_lift': '#56B4E9', 'mesha_reuse': '#882255', 'batch_mpgaa': '#777777'}
    def figure(fig, name):
        path = DEST / 'figures'
        path.mkdir(exist_ok=True)
        fig.tight_layout()
        for extension in ['png', 'pdf']:
            target = path / (name+'.'+extension)
            fig.savefig(target, dpi=170, bbox_inches='tight')
            figures[str(target.relative_to(ROOT))] = sha(target)
        plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    d = maps[maps.cohort.eq('replay') & maps.control.eq('car16') & maps.panel.eq('main')]
    names = sorted(d['map'].unique())
    for ax, column, title in zip(axes, ['full_speedup', 'repair_speedup'], ['Whole episode', 'Repairs only']):
        for i, (method, baseline) in enumerate([('fast_lift', 'lift_mesh'), ('fast_cascade', 'cascade_lift'), ('zero_cascade', 'cascade_lift')]):
            values = [d[d['map'].eq(n) & d.method.eq(method) & d.baseline.eq(baseline)].iloc[0][column] for n in names]
            ax.barh(np.arange(len(names))+(i-1)*.24, values, .23, label=LABEL[method], color=colors[method])
        ax.axvline(1, ls=':', color='.4')
        ax.set_yticks(range(len(names)), names)
        ax.set(xscale='log', xlabel='Speedup vs matching weighted Lift', title=title)
    axes[0].legend(fontsize=10, loc='best')
    figure(fig, 'maps')
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    d = summary[summary.panel.eq('ablation')]
    names = [m for m in manifest['ablations'] if m != 'fast_cascade']
    values = [d[d.baseline.eq(m)].iloc[0].full_speedup for m in names]
    axes[0].barh(range(len(names)), values, color='#0072B2')
    axes[0].set_yticks(range(len(names)), [LABEL[m] for m in names])
    axes[0].axvline(1, ls=':', color='.4')
    axes[0].set(xlabel='Ablation time / simplified Cascade time', title='One component changed at a time')
    allocation_lookup = alloc[alloc.panel.eq('ablation')].groupby('method').allocation_calls.sum()
    allocation_values = [allocation_lookup[m]/allocation_lookup['fast_cascade'] for m in names]
    axes[1].barh(range(len(names)), allocation_values, color='#009E73')
    axes[1].set_yticks(range(len(names)), [LABEL[m] for m in names])
    axes[1].axvline(1, ls=':', color='.4')
    axes[1].set(xlabel='Ablation requests / simplified requests', title='Replay allocation requests')
    figure(fig, 'ablation')
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.8))
    methods = NATIVE
    for ax, frame, column, title in [
        (axes[0], work, 'lift_edges', 'Closure arcs inspected'),
        (axes[1], work, 'mv_policy_tests', 'Policy-node tests'),
        (axes[2], alloc, 'allocation_calls', 'Allocation requests')]:
        d = frame[frame.control.eq('car16') & frame.panel.eq('main') & frame.phase.eq('repair')]
        values = d.groupby('method')[column].sum()
        ax.bar(range(len(methods)), [values[m]+1 for m in methods], color=['#E69F00', '#56B4E9', '#999999', '#009E73', '#D55E00', '#0072B2'])
        ax.set_xticks(range(len(methods)), [LABEL[m] for m in methods], rotation=50, ha='right', fontsize=10)
        ax.set(yscale='log', ylabel='Events + 1', title=title)
    figure(fig, 'work')
    fig, axes = plt.subplots(2, 3, figsize=(13, 8), sharex=True)
    for ax, (name, d) in zip(axes.flat, metrics[metrics.cohort.eq('navigation_unknown')].groupby('map')):
        for method in ['lift_mesh', 'cascade_lift', 'fast_lift', 'fast_cascade', 'mesha_reuse', 'batch_mpgaa']:
            g = d[d.method.eq(method)].sort_values('radius')
            good = g[g.complete]
            ax.plot(good.radius, 1000*good.full_s, 'o-', label=LABEL[method], color=colors[method], ms=4)
            bad_cases = g[~g.complete]
            ax.scatter(bad_cases.radius, 1000*bad_cases.full_s, marker='x', color=colors[method])
        ax.set(yscale='log', xlabel='Discovery radius, cells', ylabel='Planner episode, ms', title=name)
        ax.set_xticks([8, 32, 64])
    axes[0, 0].legend(fontsize=9)
    figure(fig, 'radius')
    methods = ['lift_mesh', 'cascade_lift', 'zero_lift', 'zero_cascade', 'fast_lift', 'fast_cascade', 'mesha_reuse', 'batch_mpgaa']
    cohorts = ['replay', 'navigation_unknown', 'navigation_dynamic']
    image = np.full((len(methods), len(cohorts)), np.nan)
    counts = {}
    for i, method in enumerate(methods):
        for j, cohort in enumerate(cohorts):
            d = metrics[metrics.control.eq('car16') & metrics.panel.ne('ablation') & metrics.cohort.eq(cohort) & metrics.method.eq(method)]
            if len(d):
                image[i, j] = d.complete.mean()
                counts[i, j] = (int(d.complete.sum()), len(d))
    fig, ax = plt.subplots(figsize=(8.5, 5))
    heat = ax.imshow(image, cmap='Blues', vmin=0, vmax=1, aspect='auto')
    for i in range(len(methods)):
        for j in range(len(cohorts)):
            text = '/'.join(map(str, counts[i, j])) if (i, j) in counts else 'not run'
            ax.text(j, i, text, ha='center', va='center', color='white' if image[i, j] > .65 else 'black', fontsize=11)
    ax.set_xticks(range(3), ['Replay', 'Unknown', 'Dynamic'])
    ax.set_yticks(range(len(methods)), [LABEL[m] for m in methods], fontsize=11)
    ax.set_title('car16: completed episodes / scheduled configurations')
    fig.colorbar(heat, ax=ax, shrink=.9, label='Completed fraction')
    figure(fig, 'completion')
    value = dict(status='passed', source_sha256=sha(Path(__file__)), manifest_sha256=sha(manifest_path),
                 unique_scenarios=manifest['unique_scenarios'], scheduled_scenarios=manifest['scheduled_scenarios'],
                 timed_runs=len(runs), memory_runs=len(metrics), timed_calls=len(calls),
                 allocation_matched_rows=matched_calls, allocation_matched_episodes=matched_runs,
                 ablation_identical_path_rows=deterministic_matches, exact_cost_disagreements=bad,
                 capped_calls=int(q.status.eq('capped').sum()), terminal_prunes=int(native.lift_terminal_prunes.sum()),
                 lift_writes=int(native.lift_writes.sum()), repeat_relative_mad_median=dispersion.relative_mad.median(),
                 repeat_relative_mad_p95=dispersion.relative_mad.quantile(.95),
                 tables_sha256={p.name: sha(p) for p in sorted(out.glob('*.csv'))}, figures_sha256=figures)
    (out/'analysis.json').write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n')
    print(json.dumps({k:v for k,v in value.items() if not k.endswith('sha256')}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=HERE/'results/full')
    parser.add_argument('--setup-directory', type=Path, default=HERE/'results/setup')
    args = parser.parse_args()
    main(args.directory, args.setup_directory)
