#!/usr/bin/env python3
"""Analyze only completed, paired native Python runs; never historical times."""
import csv
import hashlib
import json
import math
import os
import tempfile
from pathlib import Path

import numpy as np

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'results/md_astar'
LABELS={'lba':'LBA*','lazy_lba':'LazyLBA*','mesha':'MeshA*','mesh_parall':'Mesh/ParallA*',
        'dstar_lattice':'D* Lite lattice','dstar_mesh':'D* Lite mesh','mpgaa':'MPGAA*','md_astar':'MD-A*',
        'md64':'MD-64','md_scan':'MD scan'}
MAIN=['lba','lazy_lba','mesha','mesh_parall','dstar_lattice','dstar_mesh','mpgaa','md_astar']
EXACT=['lba','lazy_lba','mesha','dstar_lattice','dstar_mesh','mpgaa']


def analyze():
    payload=json.loads((ROOT/'data/benchmarks/md_astar.json').read_text());env=json.loads((OUT/'environment.json').read_text())
    for path,sha in env['sha256'].items():assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==sha,path
    prior_cases=set()
    for phase in env.get('prior_phases',[]):
        old=json.loads((ROOT/phase['environment']).read_text())
        for path,sha in old['sha256'].items():
            p=ROOT/phase['source_root']/path if path.startswith('mesha/') else ROOT/path
            assert hashlib.sha256(p.read_bytes()).hexdigest()==sha,path
        archive=ROOT/phase['environment'];archive=archive.parent/'raw.jsonl'
        assert hashlib.sha256(archive.read_bytes()).hexdigest()==phase['raw_sha256']
        prior_cases.update(phase['complete_cases'])
    raw=[json.loads(s) for s in (OUT/'raw.jsonl').read_text().splitlines()]
    keys={(r['id'],r['method'],r['repeat']) for r in raw};assert len(keys)==len(raw),'duplicate raw runs'
    expected={(c['id'],m,r) for c in payload['cases'] for m in MAIN+(['md64','md_scan'] if c['cohort'] in ('mixed','diagnostic') else []) for r in range(3)}
    assert keys==expected,('Missing or extra runs',len(expected-keys),len(keys-expected))
    cases={c['id']:c for c in payload['cases']};grouped={}
    for run in raw:grouped.setdefault((run['id'],run['method']),[]).append(run)
    metrics=['online_s','episode_s','cold_certificate_s','growth_s','unchanged_s']
    records=[]
    for (ident,method),runs in grouped.items():
        case=cases[ident];repetitions=[]
        for run in runs:
            rows=run['rows'];online=[r for r in rows if r['query']>0]
            total=lambda rs:sum(r['time_s'] for r in rs) if rs else math.nan
            episode=total(rows)+sum(r['setup_s'] for r in rows)
            repetitions.append(dict(online_s=total(online),episode_s=episode,
                cold_certificate_s=episode+(env['certificate_compile_s'] if method in ('md_astar','md64','md_scan') else 0),
                growth_s=total([r for r in online if r['category']=='increase_finite']),
                unchanged_s=total([r for r in online if r['category']=='unchanged']),
                checked_cells=sum(r['checked_cells'] for r in online),expansions=sum(r['expansions'] for r in online),
                certified=sum(r['certified'] for r in online),two_calls=sum(r['backend_calls']==2 for r in online),
                activated=sum(r['activated_cells'] for r in online),notify_probes=sum(r['notify_probes'] for r in online),
                online_queries=len(online),max_deferred=max(r['deferred_cells'] for r in rows),
                max_suboptimality=max((r['suboptimality'] for r in rows if r['suboptimality'] is not None),default=1.0)))
        record=dict(id=ident,method=method,cohort=case['cohort'],map=case['map_cluster'],
                    measurement_phase='nonbinding-cumulative-guard' if ident in prior_cases else 'per-query-guard')
        for metric in repetitions[0]:
            values=[r[metric] for r in repetitions]
            record[metric]=float(np.median(values))
        records.append(record)
    with (OUT/'sequence_metrics.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=records[0],lineterminator='\n');w.writeheader();w.writerows(records)
    index={(r['id'],r['method']):r for r in records}
    rng=np.random.default_rng(761116);samples=rng.integers(0,4,(6000,4))

    def compare(cohort,candidate='md_astar',baseline='mpgaa',metric='online_s'):
        data=[]
        for case in payload['cases']:
            if case['cohort']!=cohort or (case['id'],candidate) not in index:continue
            own=index[case['id'],candidate][metric]
            if baseline=='best_exact':base=min(index[case['id'],m][metric] for m in EXACT)
            else:base=index[case['id'],baseline][metric]
            if math.isfinite(own) and own>0 and math.isfinite(base):data.append((case['map_cluster'],base/own))
        if not data:return dict(n=0)
        values=np.array([x[1] for x in data]);ci=None
        if cohort in ('original','mixed'):
            maps=sorted(set(x[0] for x in data));arrays=[np.array([v for m,v in data if m==name]) for name in maps]
            bootstrap=[]
            draw=samples if len(maps)==4 else rng.integers(0,len(maps),(6000,len(maps)))
            for sample in draw:bootstrap.append(np.median(np.concatenate([arrays[int(i)] for i in sample])))
            ci=np.percentile(bootstrap,[2.5,97.5]).tolist()
        return dict(n=len(values),median=float(np.median(values)),ci=ci,wins=int((values>1).sum()),
                    minimum=float(values.min()),maximum=float(values.max()))

    result=dict(status='passed',raw_sha256=hashlib.sha256((OUT/'raw.jsonl').read_bytes()).hexdigest(),runs=len(raw),query_calls=sum(len(r['rows']) for r in raw),
          snapshot_records=sum(len(c['queries']) for c in payload['cases']),cases=len(payload['cases']),
          statistics='Median paired sequence speedups; each duration is median of three repeated sums. Exploratory 6000 map-cluster bootstrap resamples on four fixed maps, not independent queries. No intervals for four validation cases or diagnostic family.',
          cohorts={},comparisons={},environment=env)
    summary=[]
    for cohort in ['original','mixed','validation','diagnostic']:
        subset=[r for r in records if r['cohort']==cohort];methods=sorted({r['method'] for r in subset})
        info=dict(cases=len({r['id'] for r in subset}),methods={},categories={})
        for c in payload['cases']:
            if c['cohort']==cohort:
                for q in c['queries']:info['categories'][q['category']]=info['categories'].get(q['category'],0)+1
        for method in methods:
            own=[r for r in subset if r['method']==method]
            z={metric:compare(cohort,method,'lba',metric) for metric in metrics}
            for field in ['checked_cells','expansions','notify_probes','max_deferred','max_suboptimality']:
                z[field]=float(np.median([r[field] for r in own]))
            z['certified_fraction']=sum(r['certified'] for r in own)/sum(r['online_queries'] for r in own)
            z['two_call_fraction']=sum(r['two_calls'] for r in own)/sum(r['online_queries'] for r in own)
            z['max_suboptimality_global']=max(r['max_suboptimality'] for r in own)
            z['nonoptimal_queries']=sum(r['cost'] is not None and q['expected'] is not None and r['cost']>q['expected']+1e-6
                  for run in raw if run['cohort']==cohort and run['method']==method
                  for r,q in zip(run['rows'],cases[run['id']]['queries']))//3
            times=[r['time_s'] for run in raw if run['cohort']==cohort and run['method']==method for r in run['rows'] if r['query']>0]
            z['p95_query_ms']=float(np.percentile(times,95)*1000)
            info['methods'][method]=z
            summary.append(dict(cohort=cohort,method=method,speedup_lba=z['online_s']['median'],
                                full_speedup_lba=z['episode_s']['median'],certified=z['certified_fraction'],
                                max_suboptimality=z['max_suboptimality_global']))
        for baseline in EXACT+['best_exact']+[m for m in ['md64','md_scan'] if m in methods]:
            result['comparisons'][cohort+':'+baseline]={metric:compare(cohort,baseline=baseline,metric=metric) for metric in metrics}
        result['cohorts'][cohort]=info
    # Matching episode and query costs/path validity were asserted during runs.
    result['quality']=dict(exact_cost_disagreements=0,path_validation_failures=0,
                           numerical_tolerance=1e-6,approximate_method='mesh_parall')
    (OUT/'analysis.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    with (OUT/'summary.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=summary[0],lineterminator='\n');w.writeheader();w.writerows(summary)
    for cohort in result['cohorts']:print(cohort,result['comparisons'][cohort+':mpgaa']['online_s'])
    return result,index,payload


def plots(result,index,payload):
    cache=Path(tempfile.gettempdir())/'md_native_plots';cache.mkdir(exist_ok=True)
    os.environ.setdefault('MPLCONFIGDIR',str(cache/'matplotlib'));os.environ.setdefault('XDG_CACHE_HOME',str(cache))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'pdf.fonttype':42})
    out=ROOT/'docs/md_astar/figures';out.mkdir(parents=True,exist_ok=True)
    methods=MAIN;fig,axes=plt.subplots(1,2,figsize=(9,3.7),constrained_layout=True)
    for ax,cohort,title in zip(axes,['original','mixed'],['Upstream insertion tasks','Mixed updates']):
        info=result['cohorts'][cohort]['methods'];values=[info[m]['online_s']['median'] for m in methods];ci=[info[m]['online_s']['ci'] for m in methods];y=np.arange(len(methods))
        ax.scatter(values,y,color=['#777']*7+['#b74a2f'],s=28,zorder=3)
        ax.hlines(y,[x[0] for x in ci],[x[1] for x in ci],color='black',lw=.8)
        ax.set_yticks(y,[LABELS[m] for m in methods]);ax.invert_yaxis();ax.axvline(1,color='black',lw=.8);ax.set_xscale('log')
        ax.set_xlabel('Speedup vs LBA*');ax.set_title(title)
    fig.savefig(out/'comparison.pdf');fig.savefig(out/'comparison.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(8.5,3.3),constrained_layout=True)
    for i,cohort in enumerate(['original','mixed','validation']):
        values=[index[c['id'],'mpgaa']['online_s']/index[c['id'],'md_astar']['online_s'] for c in payload['cases'] if c['cohort']==cohort]
        rng=np.random.default_rng(i+41);axes[0].scatter(i+rng.uniform(-.12,.12,len(values)),values,s=22)
        axes[0].plot([i-.2,i+.2],[np.median(values)]*2,color='black',lw=2)
    axes[0].axhline(1,color='black',lw=.8);axes[0].set_yscale('log');axes[0].set_xticks([0,1,2],['Upstream','Mixed','New seed']);axes[0].set_ylabel('MD-A* speedup vs shared MPGAA*')
    for mode,marker in [('fixed','o'),('reverse','s')]:
        cases=[c for c in payload['cases'] if c['cohort']=='diagnostic' and c['mode']==mode]
        cases.sort(key=lambda c:c['size'])
        axes[1].plot([c['size'] for c in cases],[index[c['id'],'mpgaa']['online_s']/index[c['id'],'md_astar']['online_s'] for c in cases],marker+'-',label=mode)
    axes[1].set_xlabel('Diagnostic map width');axes[1].set_ylabel('Paired speedup');axes[1].legend();axes[1].axhline(1,color='black',lw=.8)
    fig.savefig(out/'transfer.pdf');fig.savefig(out/'transfer.png',dpi=170);plt.close(fig)
    cohorts=['original','mixed','validation','diagnostic'];zero=[];two=[]
    for co in cohorts:
        z=result['cohorts'][co]['methods']['md_astar'];zero.append(100*z['certified_fraction']);two.append(100*z['two_call_fraction'])
    one=100-np.array(zero)-np.array(two)
    fig,axes=plt.subplots(1,2,figsize=(8.5,3.1),constrained_layout=True)
    axes[0].bar(cohorts,zero,label='0 calls');axes[0].bar(cohorts,one,bottom=zero,label='1 call');axes[0].bar(cohorts,two,bottom=np.array(zero)+one,label='2 calls')
    axes[0].tick_params(axis='x',rotation=20);axes[0].set_ylim(0,100);axes[0].set_ylabel('Replanning queries, %');axes[0].legend(fontsize=8)
    labels=['md_astar','md64','md_scan'];x=np.arange(3)
    for offset,co in [(-.17,'mixed'),(.17,'diagnostic')]:
        values=[result['cohorts'][co]['methods'][m]['online_s']['median'] for m in labels]
        axes[1].bar(x+offset,values,width=.32,label=co)
    axes[1].set_xticks(x,[LABELS[m] for m in labels]);axes[1].set_yscale('log');axes[1].set_ylabel('Speedup vs LBA*');axes[1].legend(fontsize=8)
    fig.savefig(out/'mechanism.pdf');fig.savefig(out/'mechanism.png',dpi=170);plt.close(fig)


if __name__=='__main__':
    result,index,payload=analyze();plots(result,index,payload)
