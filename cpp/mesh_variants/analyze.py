#!/usr/bin/env python3
"""Validate and analyze the new contemporaneous 15-method native cohort."""
import argparse
import csv
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import tempfile

import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
spec=importlib.util.spec_from_file_location('previous_experiment_analysis',ROOT/'cpp/experiments/analyze.py')
previous=importlib.util.module_from_spec(spec);spec.loader.exec_module(previous)
aggregate,compare,median,digest,in_panel=(getattr(previous,k) for k in ['aggregate','compare','median','digest','in_panel'])
COUNTERS,INTS,FLOATS=previous.COUNTERS,previous.INTS,previous.FLOATS
LABELS={**previous.LABELS,'prefix_positive':'Positive prefix D* Lite','cmesh_dstar':'C-Mesh-D* Lite',
        'suffix_mesh':'Suffix-Mesh D* Lite','boundary_mesh':'Boundary-Mesh D* Lite'}
METHODS=list(LABELS)
NEW=['cmesh_dstar','suffix_mesh','boundary_mesh']
VARIANTS=['prefix_positive',*NEW]
ANCHORS=['lba','lba_reuse','dstar_lattice','dstar_mesh','prefix_positive','mpgaa','md_astar']
FOCUS=['lba_reuse','dstar_lattice','mpgaa','md_astar',*VARIANTS]
EXACT=[m for m in METHODS if m!='mesh_parall']
MAIN=['car16:on_path','car16:off_path','car16:churn','car16:unknown_replay','grid8:paper_dynamic']


def load(directory):
    state=json.loads((directory/'experiment.json').read_text());assert state['status']=='passed','Incomplete experiments'
    manifest_path=HERE/'frozen/manifest.json';assert digest(manifest_path)==state['manifest_sha256']
    manifest=json.loads(manifest_path.read_text());assert manifest['experiment_methods']==METHODS
    assert digest(ROOT/manifest['base_manifest'])==manifest['base_manifest_sha256']
    base=json.loads((ROOT/manifest['base_manifest']).read_text())
    for path,sha in {**base['source_sha256'],**manifest['source_sha256'],**manifest['contexts_sha256']}.items():
        assert digest(ROOT/path)==sha,path
    assert state['source_sha256']==manifest['source_sha256']
    meta={};dataset={};inputs={r['path']:r for r in manifest['records']}
    for item in manifest['records']:
        path=ROOT/item['path'];assert digest(path)==item['sha256']
        for c in json.loads(path.with_suffix('.contexts.json').read_text())['cases']:
            assert c['id'] not in meta
            meta[c['id']]=c;dataset[c['id']]=path.stem
    timing=[];memory=[];hashes={}
    for job in state['plan']:
        record=state['jobs'][job['name']];assert record['status']=='passed'
        path=directory/(job['name']+'.csv');assert digest(path)==record['csv_sha256']
        assert digest(Path(str(path)+'.json'))==record['completion_sha256']
        hashes[path.name]=record['csv_sha256'];hashes[path.name+'.json']=record['completion_sha256']
        with path.open() as f:rows=list(csv.DictReader(f))
        expected=inputs[job['input']];completion=record['completion']
        assert len(rows)==completion['rows'] and completion['runs']==expected['cases']*len(METHODS)*job['repeats']
        assert completion['memory_profile']==job['memory'] and completion['cap']==manifest['cap']
        if job['mode']=='replay':assert len(rows)==expected['snapshots']*len(METHODS)*job['repeats']
        keys=set();runs=set();decisions={}
        for r in rows:
            for k in INTS:r[k]=int(r[k])
            for k in FLOATS:r[k]=float(r[k]) if r[k] else None
            r.update(job=job['name'],mode=job['mode'],control=meta[r['case']]['control'],map=meta[r['case']]['map'])
            assert dataset[r['case']]==Path(job['input']).stem and r['method'] in METHODS
            assert 0<=r['repeat']<job['repeats']
            key=(r['case'],r['method'],r['repeat'],r['query']);assert key not in keys;keys.add(key);runs.add(key[:3])
            if r['planned'] and r['status'] not in ['capped','skipped_after_cap']:
                assert (r['cost'] is None)==(r['expected'] is None)
                if r['cost'] is not None:
                    assert r['cost']>=r['expected']-1e-6
                    if r['method']!='mesh_parall':assert abs(r['cost']-r['expected'])<1e-6,key
            fingerprint=tuple(r[k] for k in ['status','cost','expected','planned','path_hash',*COUNTERS,'certified','deferred_cells',
                                            'start_i','start_j','start_theta','next_i','next_j','next_theta'])
            dkey=(r['case'],r['method'],r['query'])
            if r['repeat']==0:decisions[dkey]=fingerprint
            else:assert fingerprint==decisions[dkey],('Repeat differs',dkey)
        assert len(runs)==completion['runs']
        (memory if job['memory'] else timing).extend(rows)
    normal={(r['case'],r['method'],r['query']):r for r in timing if r['mode']=='replay' and r['repeat']==0}
    parity=['status','cost','expected','planned','path_hash',*COUNTERS,'certified','deferred_cells',
            'start_i','start_j','start_theta','next_i','next_j','next_theta']
    for r in memory:
        other=normal[r['case'],r['method'],r['query']]
        assert all(r[k]==other[k] for k in parity),('Allocation differs',r['case'],r['method'],r['query'])
    assert len(memory)==len(normal)
    # The three non-batched representations collapse to exactly the same
    # automaton for one-step grid8 primitives, hence every decision must agree.
    grid_reference={(r['case'],r['repeat'],r['query']):r for r in timing if r['control']=='grid8' and r['method']=='prefix_positive'}
    for r in timing:
        if r['control']=='grid8' and r['method'] in ['cmesh_dstar','suffix_mesh']:
            reference=grid_reference[r['case'],r['repeat'],r['query']]
            assert all(r[k]==reference[k] for k in parity),('Degenerate grid differs',r['case'],r['method'],r['query'])
        if r['control']=='grid8' and r['method']=='boundary_mesh':
            reference=grid_reference[r['case'],r['repeat'],r['query']]
            assert all(r[k]==reference[k] for k in parity if k!='checked_cells'),('Grid mask changed decisions',r['case'],r['query'])
    return state,manifest,meta,timing,memory,hashes


def paired(index,cases,bootstrap=False):
    return {m:{base:{metric:compare(index,cases,m,base,metric,
                    bootstrap and metric!='peak_heap_bytes' and m in NEW and base in ['dstar_lattice','md_astar','lba_reuse'])
                    for metric in ['episode_s','online_s','peak_heap_bytes']} for base in ANCHORS} for m in VARIANTS}


def method_stats(index,cases,rows):
    ids={c['id'] for c in cases};result={}
    for method in METHODS:
        own=[index[c['id'],method] for c in cases];success=[r for r in own if r['complete']]
        q=[r for r in rows if r['case'] in ids and r['method']==method and r['planned'] and r['query']>0 and r['status'] not in ['capped','skipped_after_cap']]
        z=dict(completed=len(success),total=len(own),episode_ms=median([r['episode_s']*1000 for r in success]),
               online_ms=median([r['online_s']*1000 for r in success]),
               online_ms_per_query=median([1000*r['online_s']/r['online_queries'] for r in success if r['online_queries']]),
               p50_ms=median([r['time_s']*1000 for r in q]),p95_ms=float(np.percentile([r['time_s']*1000 for r in q],95)) if q else None,
               peak_mib=median([r['peak_heap_bytes']/2**20 for r in own]) if own[0]['mode']=='replay' else None,
               retained_mib=median([r['retained_heap_bytes']/2**20 for r in own]) if own[0]['mode']=='replay' else None,
               travel_ratio=median([r['travel_ratio'] for r in success if r['travel_ratio'] is not None]),
               max_plan_ratio=max((r['max_suboptimality'] for r in own if r['max_suboptimality'] is not None),default=None),
               known_fraction=median([r['known_fraction'] for r in success if r['known_fraction'] is not None]),
               repeat_relative_mad=median([r['episode_s_relative_mad'] for r in success]),
               vs_lba=compare(index,cases,method,'lba'),sum_episode_s=sum(r['episode_s'] for r in success),
               terminal_counts={s:sum(r['terminal']==s for r in own) for s in sorted({r['terminal'] for r in own})})
        for counter in COUNTERS:
            z[counter]=median([r[counter] for r in success]);z['online_'+counter]=median([r['online_'+counter] for r in success])
        result[method]=z
    return result


def analyze(directory):
    state,manifest,meta,rows,memory,hashes=load(directory)
    records=aggregate(rows,meta);mi={(r['case'],r['method']):r for r in aggregate(memory,meta)}
    for r in records:
        if (r['case'],r['method']) in mi:
            m=mi[r['case'],r['method']];r.update(peak_heap_bytes=m['peak_heap_bytes'],retained_heap_bytes=m['retained_heap_bytes'])
    index={(r['case'],r['method']):r for r in records}
    groups={};group_cases={}
    for control,family in sorted({(c['control'],c['family']) for c in meta.values()}):
        cases=[c for c in meta.values() if c['control']==control and c['family']==family]
        if control=='car16' and family in ['on_path','off_path','churn','unknown_replay']:cases=[c for c in cases if 'main' in c['panels']]
        if not cases:continue
        key=control+':'+family;group_cases[key]=cases
        groups[key]=dict(cases=len(cases),methods=method_stats(index,cases,rows),comparisons=paired(index,cases,True))
    map_results=[]
    for key,cases in group_cases.items():
        for name in sorted({c['map'] for c in cases}):
            selected=[c for c in cases if c['map']==name]
            eligible=[(sum(index[c['id'],m]['episode_s'] for c in selected),m) for m in EXACT if all(index[c['id'],m]['complete'] for c in selected)]
            map_results.append(dict(group=key,map=name,cases=len(selected),winner=min(eligible)[1] if eligible else None,
                                    methods=method_stats(index,selected,[]),comparisons=paired(index,selected)))
    parameters=[]
    panels=[('batch','car16',[1,8,32,128],'batch'),('frequency','car16',[1,2,4,8],'interval'),
            ('visibility','car16',[8,16,32],'radius'),('closed_loop','car16',[8,16],'radius'),('closed_loop','grid8',[1,4,8],'radius')]
    for panel,control,values,param in panels:
        for family in sorted({c['family'] for c in meta.values() if c['control']==control and in_panel(c,panel)}):
            for value in values:
                cases=[c for c in meta.values() if c['control']==control and c['family']==family and in_panel(c,panel) and c['params'][param]==value]
                if cases:parameters.append(dict(panel=panel,control=control,family=family,value=value,cases=len(cases),
                    methods=method_stats(index,cases,[]),comparisons=paired(index,cases)))
    for k in [2,8,32]:
        for cr in [1,5,10,30]:
            cases=[c for c in meta.values() if c['family']=='paper_dynamic' and c['params']['interval']==k and c['params']['change_rate']==cr]
            parameters.append(dict(panel='literature_dynamic',control='grid8',family='paper_dynamic',value=[k,cr],cases=len(cases),
                                   methods=method_stats(index,cases,[]),comparisons=paired(index,cases)))
    outcomes=[]
    for control in ['car16','grid8']:
        for mode in ['replay','mission']:
            for m in METHODS:
                own=[r for r in records if r['control']==control and r['mode']==mode and r['method']==m]
                outcomes.append(dict(control=control,mode=mode,method=m,total=len(own),completed=sum(r['complete'] for r in own),
                    terminals={s:sum(r['terminal']==s for r in own) for s in sorted({r['terminal'] for r in own})}))
    # Exact performance profiles include every failed case with infinite ratio.
    profiles={}
    for key,cases in {**group_cases,'car16:main':[c for c in meta.values() if c['control']=='car16' and 'main' in c['panels']]}.items():
        profiles[key]={}
        for m in EXACT:
            ratios=[]
            for c in cases:
                best=min((index[c['id'],a]['episode_s'] for a in EXACT if index[c['id'],a]['complete']),default=math.inf)
                own=index[c['id'],m];ratios.append(own['episode_s']/best if own['complete'] and math.isfinite(best) else None)
            profiles[key][m]=ratios
    models={}
    for control in ['car16','grid8']:
        all_jobs=[j for j in state['plan'] if Path(j['input']).name.startswith(control)]
        times=[state['jobs'][j['name']]['completion']['variant_compile_s'] for j in all_jobs if not j['memory']]
        memory_job=next(j for j in all_jobs if j['memory']);mem=state['jobs'][memory_job['name']]['completion']
        models[control]=dict(models=mem['variant_models'],compile_s_median=median(times),compile_s_samples=times,
                             common_retained_bytes=mem['variant_model_heap_retained_bytes'],common_peak_bytes=mem['variant_model_heap_peak_bytes'])
    caps=[{k:r[k] for k in ['case','method','query','repeat','mode','expansions','blocks','opens','backend_calls','expected']} for r in rows if r['status']=='capped']
    snapshots={(r['case'],r['method'],r['repeat'],r['query']):r for r in rows}
    cap_witnesses=[]
    for m in VARIANTS:
        failed=next((r for r in rows if r['method']==m and r['status']=='capped' and r['repeat']==0 and r['mode']=='replay'),None)
        if failed:
            other=snapshots[failed['case'],'dstar_lattice',0,failed['query']];c=meta[failed['case']]
            cap_witnesses.append(dict(method=m,case=failed['case'],map=c['map'],family=c['family'],seed=c['seed'],query=failed['query'],
                                      expected=failed['expected'],variant_expansions=failed['expansions'],
                                      lattice_status=other['status'],lattice_expansions=other['expansions']))
    work_witness=None
    for r in rows:
        if r['method']!='boundary_mesh' or r['repeat']!=0 or r['mode']!='replay' or r['status']!='no_path':continue
        base=snapshots[r['case'],'dstar_lattice',0,r['query']]
        if base['status']!='no_path' or r['checked_cells']>=base['checked_cells']:continue
        times={m:median([snapshots[r['case'],m,rep,r['query']]['time_s'] for rep in range(3)]) for m in ['boundary_mesh','dstar_lattice']}
        if times['boundary_mesh']<=times['dstar_lattice']:continue
        c=meta[r['case']]
        work_witness=dict(case=r['case'],map=c['map'],family=c['family'],seed=c['seed'],query=r['query'],times_s=times,
                          reads={m:snapshots[r['case'],m,0,r['query']]['checked_cells'] for m in times},
                          expansions={m:snapshots[r['case'],m,0,r['query']]['expansions'] for m in times})
        break
    # Separate useful finite-path repair from proofs of disconnection. Keep
    # every cap/skip in coverage; conditional ratios first sum matched query
    # medians inside each case, then take a median across cases.
    partitions={}
    for r in rows:
        if r['mode']!='replay' or r['method']!='lba' or r['repeat']!=0 or r['query']==0:continue
        c=meta[r['case']]
        if c['control']=='car16' and 'main' not in c['panels']:continue
        key=c['control']+(' finite' if r['expected'] is not None else ' no_path')
        partitions.setdefault(key,[]).append((r['case'],r['query']))
    query_times={}
    def query_time(case,method,query):
        key=(case,method,query)
        if key not in query_times:query_times[key]=median([snapshots[case,method,rep,query]['time_s'] for rep in range(3)])
        return query_times[key]
    reachability={}
    for key,keys in partitions.items():
        item=dict(snapshots=len(keys),cases=len({case for case,_ in keys}),methods={},comparisons={})
        for m in METHODS:
            own=[snapshots[case,m,0,q] for case,q in keys]
            item['methods'][m]=dict(completed=sum(r['status'] in ['ok','no_path'] for r in own),
                capped=sum(r['status']=='capped' for r in own),skipped=sum(r['status']=='skipped_after_cap' for r in own))
        for m in VARIANTS:
            item['comparisons'][m]={}
            for base in ANCHORS:
                sums={};count=0
                for case,q in keys:
                    x,y=snapshots[case,m,0,q],snapshots[case,base,0,q]
                    if x['status'] not in ['ok','no_path'] or y['status'] not in ['ok','no_path']:continue
                    own,other=query_time(case,m,q),query_time(case,base,q)
                    if not own or not other:continue
                    pair=sums.setdefault(case,[0.,0.]);pair[0]+=own;pair[1]+=other;count+=1
                ratios=[b/a for a,b in sums.values()]
                item['comparisons'][m][base]=dict(median=median(ratios),n=len(ratios),total=item['cases'],
                                                  paired_snapshots=count,total_snapshots=len(keys))
        reachability[key]=item
    completion_pairs=[]
    car_cases=[c for c in meta.values() if c['control']=='car16' and c['family']!='unknown_mission']
    for m in NEW:
        for base in ['prefix_positive','dstar_mesh']:
            wins=[c for c in car_cases if index[c['id'],m]['complete'] and not index[c['id'],base]['complete']]
            losses=[c for c in car_cases if not index[c['id'],m]['complete'] and index[c['id'],base]['complete']]
            examples=[]
            for c in wins:
                failure=next(r for r in rows if r['case']==c['id'] and r['method']==base and r['repeat']==0 and r['status']=='capped')
                own=snapshots[c['id'],m,0,failure['query']]
                examples.append(dict(case=c['id'],map=c['map'],family=c['family'],query=failure['query'],expected=failure['expected'],
                                      own_status=own['status'],own_expansions=own['expansions'],baseline_expansions=failure['expansions']))
            example=next((e for e in examples if e['expected'] is not None),examples[0] if examples else None)
            completion_pairs.append(dict(method=m,baseline=base,total=len(car_cases),wins=len(wins),losses=len(losses),
                                         won_cases=[c['id'] for c in wins],lost_cases=[c['id'] for c in losses],example=example))
    out=directory/'analysis';out.mkdir(exist_ok=True)
    with (out/'episode_metrics.csv').open('w',newline='') as f:
        keys=list(records[0]);writer=csv.DictWriter(f,fieldnames=keys,lineterminator='\n');writer.writeheader();writer.writerows(records)
    result=dict(status='passed',cpu=state['cpu'],platform=state['platform'],timed_runs=sum(v['completion']['runs'] for k,v in state['jobs'].items() if k.startswith('timing_')),
                timed_rows=len(rows),planner_calls=sum(r['planned'] for r in rows),memory_rows=len(memory),
                memory_runs=sum(v['completion']['runs'] for k,v in state['jobs'].items() if k.startswith('memory_')),
                cap_rows=len(caps),skipped_rows=sum(r['status']=='skipped_after_cap' for r in rows),step_limited=sum(r['status']=='step_limit' for r in rows),
                exact_disagreements=0,allocation_decision_parity='passed',degenerate_grid_decision_parity='passed',
                grid_boundary_path_expansion_parity='passed',groups=groups,map_results=map_results,parameters=parameters,
                outcomes=outcomes,profiles=profiles,models=models,caps=caps,cap_witnesses=cap_witnesses,work_tradeoff_witness=work_witness,
                reachability_panels=reachability,completion_pairs=completion_pairs,
                raw_sha256=hashes,manifest_sha256=digest(HERE/'frozen/manifest.json'),
                analysis_source_sha256=digest(Path(__file__)),shared_analysis_sha256=digest(ROOT/'cpp/experiments/analyze.py'),
                episode_metrics_sha256=digest(out/'episode_metrics.csv'),
                statistics='Median paired ratios of median repeated sums; 2000 map-cluster bootstrap for main comparisons with >=4 map clusters. Conditional ratios have explicit pair counts; profiles retain failures. Map winner: smallest sum of median episode times, exact methods completing every case in the row.')
    (out/'analysis.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print('Validated',result['timed_runs'],'timed runs,',len(rows),'rows,',len(caps),'caps;',len(memory),'allocation rows')
    return result,index,meta,rows,memory


def plots(directory,a,index,meta,rows,memory):
    os.environ.setdefault('MPLCONFIGDIR',str(Path(tempfile.gettempdir())/'ima_mesh_mpl'))
    os.environ.setdefault('XDG_CACHE_HOME',str(Path(tempfile.gettempdir())/'ima_mesh_cache'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import TwoSlopeNorm
    from matplotlib.ticker import LogLocator,FormatStrFormatter
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'pdf.fonttype':42})
    dest=ROOT/'docs/experiments/mesh_figures';dest.mkdir(exist_ok=True)
    colors={m:plt.get_cmap('tab20')(i) for i,m in enumerate(METHODS)}
    colors.update(prefix_positive='#777777',cmesh_dstar='#0072b2',suffix_mesh='#d55e00',boundary_mesh='#009e73',
                  md_astar='#cc79a7',mpgaa='#b59b18',lba_reuse='#5640a0',dstar_lattice='#2f2f2f')
    def save(fig,name):
        fig.savefig(dest/(name+'.pdf'),bbox_inches='tight');fig.savefig(dest/(name+'.png'),dpi=210,bbox_inches='tight');plt.close(fig)
    short={'car16:on_path':'On path','car16:off_path':'Off path','car16:churn':'Blocks + openings','car16:unknown_replay':'Unknown replay','grid8:paper_dynamic':'Grid8 dynamic'}
    # All methods, common episode speedup denominator.
    fig,axes=plt.subplots(2,2,figsize=(7.6,8.3),constrained_layout=True)
    for ax,key in zip(axes.flat,MAIN[:4]):
        for i,m in enumerate(METHODS):
            z=a['groups'][key]['methods'][m]['vs_lba']
            if z['median'] is not None:ax.scatter(z['median'],i,color=colors[m],s=24)
        ax.set_yticks(range(len(METHODS)),[LABELS[m]+f" ({a['groups'][key]['methods'][m]['vs_lba']['n']}/{a['groups'][key]['methods'][m]['vs_lba']['total']})" for m in METHODS],fontsize=8.5);ax.invert_yaxis()
        ax.set_xscale('log');ax.axvline(1,color='black',lw=.7);ax.set_title(short[key]);ax.set_xlabel('Episode speedup\nvs LBA*')
        ax.xaxis.set_major_locator(LogLocator(base=10,subs=(1,2,5)));ax.xaxis.set_major_formatter(FormatStrFormatter('%g'))
    save(fig,'all_methods')
    # Per-map differences with completion counts.
    names=sorted({c['map'] for c in meta.values() if c['control']=='car16' and 'main' in c['panels']})
    heatmaps=[];annotations=[]
    for m in NEW:
        values=np.full((len(names),4),np.nan);texts={}
        for i,name in enumerate(names):
            for j,key in enumerate(MAIN[:4]):
                row=next(r for r in a['map_results'] if r['group']==key and r['map']==name)
                z=row['comparisons'][m]['dstar_lattice']['episode_s']
                if z['median']:values[i,j]=math.log2(z['median'])
                texts[i,j]=('—' if z['median'] is None else f'{z["median"]:.2f}x')+f'\n{z["n"]}/{z["total"]}'
        heatmaps.append(values);annotations.append(texts)
    limit=max([1,*[float(np.nanmax(np.abs(v))) for v in heatmaps if np.any(np.isfinite(v))]])
    fig,axes=plt.subplots(1,3,figsize=(7.6,4.8),sharey=True,constrained_layout=True)
    for ax,m,values,texts in zip(axes,NEW,heatmaps,annotations):
        im=ax.imshow(values,cmap='RdYlGn',norm=TwoSlopeNorm(vmin=-limit,vcenter=0,vmax=limit),aspect='auto')
        for (i,j),text in texts.items():
            rgba=im.cmap(im.norm(values[i,j]));light=.2126*rgba[0]+.7152*rgba[1]+.0722*rgba[2]
            ax.text(j,i,text,ha='center',va='center',fontsize=8.5,color='black' if not math.isfinite(values[i,j]) or light>.5 else 'white')
        ax.set_xticks(range(4),['on','off','mixed','unknown'],rotation=40,ha='right',fontsize=8.5)
        ax.set_yticks(range(len(names)),names,fontsize=8.5);ax.set_title(LABELS[m],fontsize=9.5)
    fig.colorbar(im,ax=list(axes),shrink=.7,label='log2 episode speedup vs lattice D* Lite')
    save(fig,'map_regimes')
    # Model/implementation ablation on common complete cases, not independent medians.
    fig,axes=plt.subplots(1,2,figsize=(7.6,4.2),constrained_layout=True)
    for ax,metric,title in zip(axes,['episode_s','online_s'],['Full episode','Repair only']):
        for k,m in enumerate(NEW):
            values=[a['groups'][key]['comparisons'][m]['prefix_positive'][metric]['median'] for key in MAIN]
            ax.plot(range(5),values,marker='o',label=LABELS[m],color=colors[m])
        ax.axhline(1,color='black',lw=.7);ax.set_yscale('log');ax.set_xticks(range(5),[short[k] for k in MAIN],rotation=35,ha='right',fontsize=8)
        ax.set_ylabel('Speedup vs positive prefix');ax.set_title(title)
    axes[-1].legend(fontsize=8);save(fig,'topology_ablation')
    # Work, memory and failure-aware outcomes, both time and collision work count.
    fig,axes=plt.subplots(2,2,figsize=(7.6,6.5),constrained_layout=True)
    for m in FOCUS:
        z=[a['groups'][key]['methods'][m] for key in MAIN]
        axes[0,0].plot(range(5),[max(x['online_expansions'] or 0,1) for x in z],marker='o',color=colors[m],label=LABELS[m])
        axes[0,1].plot(range(5),[max(x['online_checked_cells'] or 0,1) for x in z],marker='o',color=colors[m])
        axes[1,0].plot(range(5),[max(x['peak_mib'] or 0,1e-6) for x in z],marker='o',color=colors[m])
        axes[1,1].plot(range(5),[x['completed']/x['total'] for x in z],marker='o',color=colors[m])
    for ax in axes.flat:ax.set_xticks(range(5),[short[k] for k in MAIN],rotation=35,ha='right',fontsize=8)
    for ax in [axes[0,0],axes[0,1],axes[1,0]]:ax.set_yscale('log')
    axes[0,0].set_ylabel('Median repair expansions');axes[0,1].set_ylabel('Median repair cell reads')
    axes[1,0].set_ylabel('Median observed peak heap, MiB');axes[1,1].set_ylabel('Completed / all episodes');axes[1,1].set_ylim(0,1.03)
    handles,labels=axes[0,0].get_legend_handles_labels()
    fig.legend(handles,labels,loc='lower center',bbox_to_anchor=(.5,-.1),ncol=4,fontsize=8)
    save(fig,'work_memory_completion')
    # Controlled batch/frequency/visibility. No averaging repeated roots as new tasks.
    fig,axes=plt.subplots(1,3,figsize=(7.6,3.6),constrained_layout=True)
    for ax,panel,family in zip(axes,['batch','frequency','visibility'],['churn','churn','unknown_replay']):
        selected=sorted((p for p in a['parameters'] if p['panel']==panel and p['family']==family),key=lambda p:p['value'])
        for m in FOCUS:
            ax.plot([p['value'] for p in selected],[p['methods'][m]['online_ms_per_query'] for p in selected],marker='o',color=colors[m],label=LABELS[m])
        ax.set_yscale('log');ax.set_xscale('log',base=2);ax.set_xticks([p['value'] for p in selected],[str(p['value']) for p in selected]);ax.set_title(panel);ax.set_xlabel('Requested batch' if panel=='batch' else ('Motion interval' if panel=='frequency' else 'Sensor radius'))
    axes[0].set_ylabel('Median repair ms / query')
    handles,labels=axes[0].get_legend_handles_labels();fig.legend(handles,labels,loc='lower center',bbox_to_anchor=(.5,-.2),ncol=4,fontsize=8)
    save(fig,'parameters')
    fig,axes=plt.subplots(1,2,figsize=(7.6,3.8),constrained_layout=True)
    for ax,control in zip(axes,['car16','grid8']):
        selected=sorted((p for p in a['parameters'] if p['panel']=='closed_loop' and p['control']==control),key=lambda p:p['value'])
        for m in FOCUS:
            ax.plot([p['value'] for p in selected],[p['methods'][m]['online_ms_per_query'] for p in selected],marker='o',color=colors[m],label=LABELS[m])
        ax.set_yscale('log');ax.set_xticks([p['value'] for p in selected]);ax.set_xlabel('Sensor radius');ax.set_title(control+' own navigation');ax.set_ylabel('Completed mission repair ms / query')
    handles,labels=axes[-1].get_legend_handles_labels();fig.legend(handles,labels,loc='lower center',bbox_to_anchor=(.5,-.2),ncol=4,fontsize=8)
    save(fig,'unknown_navigation')
    fig,axes=plt.subplots(1,2,figsize=(7.6,3.8),constrained_layout=True)
    for ax,key,title in zip(axes,['car16:main','grid8:paper_dynamic'],['Car16 main (48 cases)','Grid8 dynamic (96 cases)']):
        x=np.geomspace(1,300,200)
        for m in FOCUS:
            v=np.array([r if r is not None else math.inf for r in a['profiles'][key][m]])
            ax.plot(x,[np.mean(v<=t) for t in x],color=colors[m],label=LABELS[m])
        ax.set_xscale('log');ax.set_ylim(0,1.02);ax.set_title(title);ax.set_xlabel('Factor of fastest exact complete method');ax.set_ylabel('Fraction of all cases')
    handles,labels=axes[-1].get_legend_handles_labels();fig.legend(handles,labels,loc='lower center',bbox_to_anchor=(.5,-.2),ncol=4,fontsize=8)
    save(fig,'performance_profiles')
    # Actual delivered edits, paired per-snapshot timing on a common replay.
    fig,axes=plt.subplots(1,2,figsize=(7.6,3.8),constrained_layout=True)
    for ax,control in zip(axes,['car16','grid8']):
        for m in FOCUS:
            selected=[r for r in rows if r['control']==control and r['mode']=='replay' and r['query']>0 and r['method']==m and r['planned'] and r['status'] not in ['capped','skipped_after_cap']]
            bins=[(0,0),(1,1),(2,7),(8,31),(32,127),(128,10**9)];values=[]
            for lo,hi in bins:
                values.append(median([r['time_s']*1000 for r in selected if lo<=r['blocks']+r['opens']<=hi]))
            ax.plot(range(6),values,marker='o',color=colors[m],label=LABELS[m])
        ax.set_xticks(range(6),['0','1','2–7','8–31','32–127','128+'],rotation=25,ha='right',fontsize=8)
        ax.set_yscale('log');ax.set_title(control);ax.set_xlabel('Delivered changed cells / repair');ax.set_ylabel('Conditional median latency, ms')
    handles,labels=axes[-1].get_legend_handles_labels();fig.legend(handles,labels,loc='lower center',bbox_to_anchor=(.5,-.2),ncol=4,fontsize=8)
    save(fig,'change_scaling')
    figure_manifest=dict(status='passed',analysis_sha256=digest(directory/'analysis/analysis.json'),
                         source_sha256=digest(Path(__file__)),files={str(p.relative_to(ROOT)):digest(p) for p in sorted(dest.iterdir()) if p.suffix in ['.png','.pdf']})
    (directory/'analysis/figures.json').write_text(json.dumps(figure_manifest,indent=2)+'\n')
    print('Wrote eight PNG/PDF figures to',dest)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,default=HERE/'results/full');p.add_argument('--no-plots',action='store_true');args=p.parse_args()
    result=analyze(args.directory)
    if not args.no_plots:plots(args.directory,*result)
