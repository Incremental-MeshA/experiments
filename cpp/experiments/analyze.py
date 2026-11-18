#!/usr/bin/env python3
"""Analyze the complete expanded experiment; caps stay visible as failures."""
import argparse
import csv
import hashlib
import json
import math
import os
import statistics
import shlex
import tempfile
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
LABELS={'lba':'LBA*','lazy_lba':'LazyLBA*','mesha':'MeshA*','mesh_parall':'Mesh/ParallA*','dstar_lattice':'D* Lite lattice','dstar_mesh':'D* Lite mesh','mpgaa':'MPGAA*','md_astar':'MD-A*','md64':'MD-64','md_scan':'MD scan','lba_reuse':'LBA* reuse'}
METHODS=list(LABELS)
EXACT=[m for m in METHODS if m!='mesh_parall']
COUNTERS=['expansions','checked_cells','notify_probes','heuristic_pops','backend_calls','activated_cells','refined_cells']
INTS=['repeat','query','step','planned','blocks','opens','revealed','known','certified','deferred_cells','peak_heap_bytes','retained_heap_bytes','start_i','start_j','start_theta','next_i','next_j','next_theta',*COUNTERS]
FLOATS=['time_s','setup_s','cost','expected','travel_cost','sensing_s']


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def median(xs):return float(statistics.median(xs)) if xs else None


def in_panel(case,panel):
    if panel in case['panels']:return True
    # k=2 is the unchanged main configuration, already measured once. Its
    # frozen panel tags only list main/batch; include that common reference
    # point without editing the immutable inputs or counting it twice.
    return (panel=='frequency' and case['control']=='car16' and case['family']=='churn'
            and case['map'] in ['MA_room96','MA_random96'] and 'main' in case['panels']
            and case['params']['interval']==2 and case['params']['batch']==8 and case['params']['radius']==8)


def initial_maps(path):
    """Read immutable initial grids for figures directly from the measured file."""
    lex=shlex.shlex(path.read_text(),posix=True);lex.whitespace_split=True;lex.commenters=''
    tokens=iter(lex)
    def take():return next(tokens)
    def skip(n):
        for _ in range(n):take()
    assert take()=='IMA_CPP' and take()=='1'
    take();nt,np_,nc=int(take()),int(take()),int(take());skip(nt)
    for _ in range(np_):skip(5);skip(2*int(take()))
    for _ in range(nc):
        skip(4);ne,nf=int(take()),int(take());skip(5*ne+4*nf)
    maps=[]
    for _ in range(int(take())):
        take();h,w=int(take()),int(take());g=np.array([[x=='#' for x in take()] for _ in range(h)],dtype=np.uint8)
        assert g.shape==(h,w);maps.append(g)
    cases={}
    for _ in range(int(take())):
        name=take();take();mi,nq=int(take()),int(take());cases[name]=maps[mi]
        for _ in range(nq):skip(9);nb,no=int(take()),int(take());skip(2*(nb+no))
    return cases


def load(directory):
    state=json.loads((directory/'experiment.json').read_text());assert state['status']=='passed','Experiments still incomplete'
    assert digest(HERE/'frozen/manifest.json')==state['manifest_sha256']
    for path,sha in state['source_sha256'].items():assert digest(ROOT/path)==sha,path
    manifest=json.loads((HERE/'frozen/manifest.json').read_text())
    for path,sha in manifest['source_sha256'].items():assert digest(ROOT/path)==sha,path
    meta={};dataset={}
    for item in manifest['records']:
        path=ROOT/item['path'];assert digest(path)==item['sha256']
        contexts=json.loads(path.with_suffix('.contexts.json').read_text())
        for c in contexts['cases']:
            assert c['id'] not in meta
            meta[c['id']]=c;dataset[c['id']]=path.stem
    timing=[];memory=[];raw_hashes={};inputs={r['path']:r for r in manifest['records']}
    for job in state['plan']:
        record=state['jobs'][job['name']];assert record['status']=='passed'
        path=directory/(job['name']+'.csv');assert digest(path)==record['csv_sha256']
        assert digest(Path(str(path)+'.json'))==record['completion_sha256']
        raw_hashes[path.name]=record['csv_sha256']
        with path.open() as f:rows=list(csv.DictReader(f))
        assert len(rows)==record['completion']['rows']
        expected=inputs[job['input']]
        assert record['completion']['runs']==expected['cases']*len(METHODS)*job['repeats']
        if job['mode']=='replay':assert len(rows)==expected['snapshots']*len(METHODS)*job['repeats']
        keys=set();run_keys=set()
        for row in rows:
            for col in INTS:row[col]=int(row[col])
            for col in FLOATS:row[col]=float(row[col]) if row[col] else None
            row['job']=job['name'];row['mode']=job['mode'];row['control']=meta[row['case']]['control'];row['map']=meta[row['case']]['map']
            assert dataset[row['case']]==Path(job['input']).stem and row['method'] in METHODS
            assert 0<=row['repeat']<job['repeats'];run_keys.add((row['case'],row['method'],row['repeat']))
            key=(row['case'],row['method'],row['repeat'],row['query']);assert key not in keys;keys.add(key)
            if row['planned'] and row['status'] not in ('capped','skipped_after_cap'):
                assert (row['cost'] is None)==(row['expected'] is None)
                if row['cost'] is not None:
                    assert row['cost']>=row['expected']-1e-6
                    if row['method']!='mesh_parall':assert abs(row['cost']-row['expected'])<1e-6
        assert len(run_keys)==record['completion']['runs']
        (memory if job['memory'] else timing).extend(rows)
    # Allocation instrumentation must preserve every decision, path and work count.
    normal={(r['case'],r['method'],r['query']):r for r in timing if r['mode']=='replay' and r['repeat']==0}
    compare=['status','cost','expected','planned','path_hash',*COUNTERS,'certified','deferred_cells','start_i','start_j','start_theta','next_i','next_j','next_theta']
    for r in memory:
        a=normal[r['case'],r['method'],r['query']]
        assert all(r[k]==a[k] for k in compare),(r['case'],r['method'],r['query'])
    return state,manifest,meta,timing,memory,raw_hashes


def aggregate(rows,meta):
    grouped=defaultdict(list)
    for r in rows:grouped[r['case'],r['method'],r['repeat']].append(r)
    records=[];by_pair=defaultdict(list)
    for (case,method,repeat),q in grouped.items():
        q.sort(key=lambda r:r['query']);c=meta[case]
        assert [r['query'] for r in q]==list(range(len(q)))
        mission=q[0]['mode']=='mission';last=q[-1]
        planned=[r for r in q if r['planned']]
        assert planned
        online=[r for r in planned if r['query']>0]
        complete=last['status']=='goal' if mission else not any(r['status'] in ('capped','skipped_after_cap') for r in q)
        z=dict(case=case,method=method,repeat=repeat,control=c['control'],map=c['map'],family=c['family'],mode=q[0]['mode'],
               complete=complete,terminal=last['status'],time_s=sum(r['time_s'] for r in q),episode_s=sum(r['time_s']+r['setup_s'] for r in q),
               online_s=sum(r['time_s'] for r in online),sensor_s=sum(r['sensing_s'] for r in q),
               queries=len(planned),online_queries=len(online),steps=len(q),changes=sum(r['blocks']+r['opens'] for r in q),
               certified=sum(r['certified'] for r in online),two_calls=sum(r['backend_calls']==2 for r in online),
               peak_heap_bytes=max(r['peak_heap_bytes'] for r in q),retained_heap_bytes=max(r['retained_heap_bytes'] for r in q),
               max_deferred=max(r['deferred_cells'] for r in q),travel_cost=last['travel_cost'],
               known_fraction=last['known']/(c['shape'][0]*c['shape'][1]) if mission else None,
               max_suboptimality=max((r['cost']/r['expected'] for r in planned if r['cost'] is not None and r['expected']),default=None))
        if mission and complete:
            z['travel_ratio']=last['travel_cost']/c['truth_optimum'];assert z['travel_ratio']>=1-1e-6
        else:z['travel_ratio']=None
        for col in COUNTERS:
            z[col]=sum(r[col] for r in q)
            z['online_'+col]=sum(r[col] for r in online)
        by_pair[case,method].append(z)
    for (case,method),reps in by_pair.items():
        assert len({(r['complete'],r['terminal'],r['steps'],r['queries']) for r in reps})==1,'Non-repeatable outcome'
        record={k:reps[0][k] for k in ['case','method','control','map','family','mode','complete','terminal']}
        for col in reps[0]:
            if col not in record and col!='repeat':record[col]=median([r[col] for r in reps if r[col] is not None])
        for col in ['episode_s','online_s']:
            center=record[col]
            record[col+'_relative_mad']=median([abs(r[col]-center) for r in reps])/center if center else None
        records.append(record)
    return records


def compare(index,cases,candidate='md_astar',baseline='mpgaa',metric='episode_s',bootstrap=False):
    values=[]
    for c in cases:
        own=index.get((c['id'],candidate));base=index.get((c['id'],baseline))
        if not own or not base or not own['complete'] or not base['complete'] or not own[metric] or not base[metric]:continue
        values.append((c['map'],base[metric]/own[metric]))
    if not values:return dict(n=0,total=len(cases),median=None,wins=0)
    v=[x[1] for x in values];ci=None
    maps=sorted({x[0] for x in values})
    if bootstrap and len(maps)>=4:
        rng=np.random.default_rng(48101);groups=[[x[1] for x in values if x[0]==name] for name in maps]
        boot=[np.median([x for k in rng.integers(0,len(maps),len(maps)) for x in groups[int(k)]]) for _ in range(2000)]
        ci=np.percentile(boot,[2.5,97.5]).tolist()
    return dict(n=len(v),total=len(cases),median=median(v),minimum=min(v),maximum=max(v),wins=sum(x>1 for x in v),ci=ci)


def analyze(directory):
    state,manifest,meta,rows,memory,hashes=load(directory)
    records=aggregate(rows,meta);mem_records=aggregate(memory,meta)
    index={(r['case'],r['method']):r for r in records};mi={(r['case'],r['method']):r for r in mem_records}
    for r in records:
        m=mi.get((r['case'],r['method']))
        if m:r['peak_heap_bytes']=m['peak_heap_bytes'];r['retained_heap_bytes']=m['retained_heap_bytes']
    out=directory/'analysis';out.mkdir(exist_ok=True)
    with (out/'episode_metrics.csv').open('w',newline='') as f:
        keys=list(records[0]);extra=sorted(set().union(*(r.keys() for r in records))-set(keys))
        writer=csv.DictWriter(f,fieldnames=keys+extra,lineterminator='\n');writer.writeheader();writer.writerows(records)
    groups={}
    for control in ['car16','grid8']:
        families=sorted({c['family'] for c in meta.values() if c['control']==control})
        for family in families:
            cases=[c for c in meta.values() if c['control']==control and c['family']==family]
            if control=='car16' and family in ['on_path','off_path','churn','unknown_replay']:
                cases=[c for c in cases if 'main' in c['panels']]
            ids={c['id'] for c in cases};info=dict(cases=len(cases),methods={})
            for method in METHODS:
                own=[index[c,method] for c in ids];succeeded=[r for r in own if r['complete']]
                qs=[r for r in rows if r['case'] in ids and r['method']==method and r['planned'] and r['query']>0 and r['status'] not in ('capped','skipped_after_cap')]
                z=dict(completed=len(succeeded),total=len(own),completion_fraction=len(succeeded)/len(own),
                       episode_s_success=median([r['episode_s'] for r in succeeded]),
                       online_s_success=median([r['online_s'] for r in succeeded]),
                       query_p50_ms=float(np.percentile([r['time_s']*1000 for r in qs],50)) if qs else None,
                       query_p95_ms=float(np.percentile([r['time_s']*1000 for r in qs],95)) if qs else None,
                       query_p99_ms=float(np.percentile([r['time_s']*1000 for r in qs],99)) if qs else None,
                       certified_fraction=sum(r['certified'] for r in own)/max(1,sum(r['online_queries'] for r in own)),
                       two_call_fraction=sum(r['two_calls'] for r in own)/max(1,sum(r['online_queries'] for r in own)),
                       max_suboptimality=max((r['max_suboptimality'] for r in own if r['max_suboptimality'] is not None),default=None),
                       peak_heap_mib=median([r['peak_heap_bytes']/2**20 for r in own]) if own[0]['mode']=='replay' else None,
                       travel_ratio=median([r['travel_ratio'] for r in succeeded if r['travel_ratio'] is not None]),
                       queries=median([r['queries'] for r in own]))
                z['repeat_relative_mad_median']=median([r['episode_s_relative_mad'] for r in succeeded if r['episode_s_relative_mad'] is not None])
                for col in COUNTERS:
                    z[col]=median([r[col] for r in succeeded])
                    z['online_'+col]=median([r['online_'+col] for r in succeeded])
                z['vs_lba']=compare(index,cases,method,'lba','episode_s',True)
                info['methods'][method]=z
            info['md_vs_mpgaa']={metric:compare(index,cases,metric=metric,bootstrap=True) for metric in ['online_s','episode_s']}
            info['md_vs_reuse']={metric:compare(index,cases,baseline='lba_reuse',metric=metric,bootstrap=True) for metric in ['online_s','episode_s']}
            groups[control+':'+family]=info
    map_results=[]
    for control,name,family in sorted({(c['control'],c['map'],c['family']) for c in meta.values()}):
        cases=[c for c in meta.values() if c['control']==control and c['map']==name and c['family']==family]
        if control=='car16' and family in ['on_path','off_path','churn','unknown_replay']:
            cases=[c for c in cases if 'main' in c['panels']]
        if not cases:continue
        eligible=[]
        for method in EXACT:
            own=[index[c['id'],method] for c in cases]
            if all(r['complete'] for r in own):eligible.append((sum(r['episode_s'] for r in own),method))
        winner=min(eligible)[1] if eligible else None
        map_results.append(dict(control=control,map=name,family=family,cases=len(cases),best_complete_exact=winner,
                                md_vs_mpgaa=compare(index,cases),md_vs_reuse=compare(index,cases,baseline='lba_reuse'),
                                md_vs_mpgaa_online=compare(index,cases,metric='online_s'),
                                md_vs_lba=compare(index,cases,baseline='lba')))
    paper=[c for c in meta.values() if c['family']=='paper_dynamic']
    balanced=[c for c in paper if c['params']['change_rate']<=200*c['density_parameter']]
    sensitivity=dict(all=compare(index,paper),availability_feasible_subset=compare(index,balanced),
                     note='Main analysis retains all cases; supplementary subset excludes nominal requests exceeding the initial balanced-pool capacity.')
    literature_parameters=[]
    for k in [2,8,32]:
        for rate in [1,5,10,30]:
            cases=[c for c in paper if c['params']['interval']==k and c['params']['change_rate']==rate]
            methods={}
            for m in METHODS:
                own=[index[c['id'],m] for c in cases if index[c['id'],m]['complete']]
                methods[m]=dict(completed=len(own),median_online_queries=median([r['online_queries'] for r in own]),
                                online_ms_per_query=median([r['online_s']*1000/r['online_queries'] for r in own if r['online_queries']]))
            literature_parameters.append(dict(interval=k,change_rate=rate,cases=len(cases),methods=methods,
                                              md_vs_mpgaa=compare(index,cases),md_vs_mpgaa_online=compare(index,cases,metric='online_s'),
                                              md_vs_reuse=compare(index,cases,baseline='lba_reuse')))
    outcomes=[]
    for control in ['car16','grid8']:
        for mode in ['replay','mission']:
            for method in METHODS:
                own=[r for r in records if r['control']==control and r['mode']==mode and r['method']==method]
                if not own:continue
                terminal={s:sum(r['terminal']==s for r in own) for s in sorted({r['terminal'] for r in own})}
                outcomes.append(dict(control=control,mode=mode,method=method,total=len(own),completed=sum(r['complete'] for r in own),
                                     capped=sum(r['terminal'] in ('capped','skipped_after_cap') for r in own),
                                     step_limit=terminal.get('step_limit',0),no_path=terminal.get('no_path',0),terminals=terminal))
    parameters=[]
    panels=[('batch','car16',[1,8,32,128],'batch'),('frequency','car16',[1,2,4,8],'interval'),
            ('visibility','car16',[8,16,32],'radius'),('closed_loop','car16',[8,16],'radius'),
            ('closed_loop','grid8',[1,4,8],'radius')]
    for panel,control,values,param in panels:
        families=sorted({c['family'] for c in meta.values() if c['control']==control and in_panel(c,panel)})
        for family in families:
            for value in values:
                cases=[c for c in meta.values() if c['control']==control and c['family']==family and in_panel(c,panel) and c['params'][param]==value]
                if not cases:continue
                parameters.append(dict(panel=panel,control=control,family=family,parameter=param,value=value,cases=len(cases),
                                       md_vs_mpgaa=compare(index,cases),md_vs_reuse=compare(index,cases,baseline='lba_reuse'),
                                       md_vs_mpgaa_online=compare(index,cases,metric='online_s'),
                                       methods={m:dict(completed=sum(index[c['id'],m]['complete'] for c in cases),
                                            online_ms_per_query=median([1000*index[c['id'],m]['online_s']/index[c['id'],m]['online_queries'] for c in cases if index[c['id'],m]['complete'] and index[c['id'],m]['online_queries']]),
                                            travel_ratio=median([index[c['id'],m]['travel_ratio'] for c in cases if index[c['id'],m]['travel_ratio'] is not None]),
                                            known_fraction=median([index[c['id'],m]['known_fraction'] for c in cases if index[c['id'],m]['complete'] and index[c['id'],m]['known_fraction'] is not None])) for m in METHODS}))
    events={}
    for control in ['car16','grid8']:
        for family in sorted({c['family'] for c in meta.values() if c['control']==control and c['family']!='unknown_mission'}):
            cases=[c for c in meta.values() if c['control']==control and c['family']==family]
            if control=='car16' and family in ['on_path','off_path','churn','unknown_replay']:cases=[c for c in cases if 'main' in c['panels']]
            queries=[q for c in cases for q in c['queries'][1:]]
            events[control+':'+family]=dict(queries=len(queries),damaging_reference=sum(q.get('on_path_blocks',0)>0 for q in queries),
                                            with_openings=sum(bool(q['opens']) for q in queries),
                                            delivered=sum(q.get('changes',len(q['blocks'])+len(q['opens'])) for q in queries),
                                            categories={s:sum(q['category']==s for q in queries) for s in sorted({q['category'] for q in queries})})
    mechanisms=[]
    for control in ['car16','grid8']:
        for opening in [False,True]:
            subset=[r for r in rows if r['mode']=='replay' and r['control']==control and r['query']>0 and bool(r['opens'])==opening and r['planned']]
            for method in ['mpgaa','md_astar','md64','md_scan','lba_reuse']:
                own=[r for r in subset if r['method']==method];done=[r for r in own if r['status']!='capped']
                mechanisms.append(dict(control=control,with_openings=opening,method=method,attempts=len(own),capped=sum(r['status']=='capped' for r in own),
                                       certified_fraction=sum(r['certified'] for r in own)/max(1,len(own)),
                                       two_call_fraction=sum(r['backend_calls']==2 for r in own)/max(1,len(own)),
                                       query_p50_ms=median([r['time_s']*1000 for r in done]),
                                       median_activated=median([r['activated_cells'] for r in done]),
                                       maximum_deferred=max((r['deferred_cells'] for r in own),default=0)))
    certificate_controls=[]
    for key in events:
        control,family=key.split(':');ids={c['id'] for c in meta.values() if c['control']==control and c['family']==family}
        if control=='car16' and family in ['on_path','off_path','churn','unknown_replay']:ids={c['id'] for c in meta.values() if c['id'] in ids and 'main' in c['panels']}
        own=[r for r in rows if r['case'] in ids and r['method']=='md_astar' and r['repeat']==0 and r['query']>0 and r['certified'] and r['opens'] and r['cost'] is not None]
        gaps=[r['cost']-math.hypot(r['start_i']-meta[r['case']]['goal'][0],r['start_j']-meta[r['case']]['goal'][1]) for r in own]
        certificate_controls.append(dict(group=key,certified_queries_with_new_openings=len(own),
                                          coinciding_with_global_euclidean_lb=sum(abs(x)<=1e-7 for x in gaps),
                                          positive_geometric_gap=sum(x>1e-7 for x in gaps),maximum_gap=max(gaps,default=None)))
    result=dict(status='passed',cpu=state['cpu'],platform=state['platform'],raw_sha256=hashes,
                timed_episode_runs=sum(x['completion']['runs'] for n,x in state['jobs'].items() if n.startswith('timing_')),
                timed_rows=len(rows),actual_planner_calls=sum(r['planned'] for r in rows),memory_rows=len(memory),
                replay_cases=manifest['total_replay_cases'],mission_cases=manifest['total_missions'],
                cap_rows=sum(r['status']=='capped' for r in rows),skipped_rows=sum(r['status']=='skipped_after_cap' for r in rows),
                step_limited=sum(r['status']=='step_limit' for r in rows),exact_disagreements=0,allocation_decision_parity='passed',
                groups=groups,map_results=map_results,rate_sensitivity=sensitivity,outcomes=outcomes,parameters=parameters,events=events,mechanisms=mechanisms,certificate_controls=certificate_controls,literature_parameters=literature_parameters,
                analysis_source_sha256=digest(Path(__file__)),contexts_sha256={str(p.relative_to(ROOT)):digest(p) for p in sorted((HERE/'frozen').glob('*.contexts.json'))},
                map_winner_criterion='Smallest sum of median episode times among exact methods completing every case in that map/regime; independent of LBA completion.',
                statistics='Median of paired ratios after median repeated sums; descriptive 2000 map-cluster bootstrap only with >=4 map clusters. Queries/repeats are not independent tasks. Completion and failed outcomes are always reported.')
    (out/'analysis.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    with (out/'map_regimes.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['control','map','family','cases','best_complete_exact','md_vs_mpgaa','md_vs_mpgaa_online','md_vs_reuse','md_vs_lba'],lineterminator='\n');writer.writeheader()
        for r in map_results:writer.writerow({**r,**{k:json.dumps(r[k]) for k in ['md_vs_mpgaa','md_vs_mpgaa_online','md_vs_reuse','md_vs_lba']}})
    print('Analyzed',len(rows),'timed rows;',sum(r['planned'] for r in rows),'planner calls;',result['cap_rows'],'caps')
    return result,index,meta,rows,memory


def plots(directory,result,index,meta,rows,memory):
    os.environ.setdefault('MPLCONFIGDIR',str(Path(tempfile.gettempdir())/'ima_exp_mpl'))
    os.environ.setdefault('XDG_CACHE_HOME',str(Path(tempfile.gettempdir())/'ima_exp_cache'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import TwoSlopeNorm
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'pdf.fonttype':42})
    dest=ROOT/'docs/experiments/figures';dest.mkdir(exist_ok=True)
    colors={m:plt.get_cmap('tab20')(i) for i,m in enumerate(METHODS)}
    colors['md_astar']='#c23b23';colors['mpgaa']='#207a35';colors['lba_reuse']='#51349a'
    def save(fig,name):
        fig.savefig(dest/(name+'.pdf'),bbox_inches='tight');fig.savefig(dest/(name+'.png'),dpi=220,bbox_inches='tight');plt.close(fig)
    def contrast(im,value):
        if not math.isfinite(value):return 'black'
        r,g,b,_=im.cmap(im.norm(value))
        return 'black' if .2126*r+.7152*g+.0722*b>.5 else 'white'
    main=[c for c in meta.values() if c['control']=='car16' and 'main' in c['panels']]
    families=['on_path','off_path','churn','unknown_replay'];names=sorted({c['map'] for c in main})
    grids={}
    for control in ['car16','grid8']:
        frozen=initial_maps(HERE/'frozen'/f'{control}_replay.txt')
        for c in meta.values():
            if c['id'] in frozen and c['family'] in ('on_path','paper_dynamic','history'):
                grids.setdefault(c['map'],frozen[c['id']])
    fig,axes=plt.subplots(2,3,figsize=(7.6,6.4),constrained_layout=True)
    for ax,name in zip(axes.flat,names):
        grid=grids[name];ax.imshow(grid,cmap='gray_r',vmin=0,vmax=1)
        for i,c in enumerate(sorted((c for c in main if c['map']==name and c['family']=='on_path'),key=lambda c:c['seed'])):
            path=c['example_states'];ax.plot([s[1] for s in path],[s[0] for s in path],lw=1.3,label='root '+str(i+1))
            s,t=c['start'],c['goal'];ax.scatter([s[1]],[s[0]],marker='o',s=20);ax.scatter([t[1]],[t[0]],marker='*',s=45)
            if len(c['queries'])>1:
                cells=c['queries'][1]['blocks'];ax.scatter([q[1] for q in cells],[q[0] for q in cells],s=10,color='red')
        ax.set_title(name+f' / {grid.shape[0]}x{grid.shape[1]}');ax.set_xticks([]);ax.set_yticks([])
    axes.flat[0].legend(fontsize=7);save(fig,'maps_workloads')
    fig,axes=plt.subplots(1,2,figsize=(7.6,4.6),constrained_layout=True)
    for ax,base,title in zip(axes,['mpgaa','lba_reuse'],['MD-A* vs MPGAA*','MD-A* vs LBA* suffix reuse']):
        values=np.full((len(names),4),np.nan)
        labels={}
        for i,name in enumerate(names):
            for j,family in enumerate(families):
                cases=[c for c in main if c['map']==name and c['family']==family]
                z=compare(index,cases,baseline=base)
                if z['median'] is not None:values[i,j]=np.log2(z['median'])
                labels[i,j]=('—' if z['median'] is None else f'{z["median"]:.2f}x')+f'\n{z["n"]}/{z["total"]}'
        finite=np.abs(values[np.isfinite(values)]);limit=max(1,float(finite.max())) if len(finite) else 1
        im=ax.imshow(values,cmap='RdYlGn',norm=TwoSlopeNorm(vmin=-limit,vcenter=0,vmax=limit),aspect='auto')
        for (i,j),label in labels.items():ax.text(j,i,label,ha='center',va='center',fontsize=8,color=contrast(im,values[i,j]))
        ax.set_xticks(range(4),['on path','off path','mixed','unknown'],rotation=30,ha='right',fontsize=8);ax.set_yticks(range(len(names)),names);ax.set_title(title)
        fig.colorbar(im,ax=ax,label='log2 paired episode speedup',shrink=.75)
    save(fig,'map_regimes')
    fig,axes=plt.subplots(2,2,figsize=(7.4,7.0),constrained_layout=True)
    for ax,family in zip(axes.flat,families):
        cases=[c for c in main if c['family']==family]
        for i,m in enumerate(METHODS):
            z=compare(index,cases,m,'lba',bootstrap=True)
            if z['median'] is not None:
                ax.scatter(z['median'],i,color=colors[m],s=24)
                if z['ci']:ax.hlines(i,*z['ci'],color=colors[m],lw=1)
        ax.axvline(1,color='black',lw=.7);ax.set_xscale('log');ax.set_yticks(range(len(METHODS)),[LABELS[m] for m in METHODS]);ax.invert_yaxis();ax.set_title(family);ax.set_xlabel('Episode speedup vs LBA*')
    save(fig,'all_methods')
    # Exact performance profiles; a cap/unfinished mission has ratio infinity.
    fig,axes=plt.subplots(1,2,figsize=(7.4,3.8),constrained_layout=True)
    for ax,cases,title in [(axes[0],main,'Common replay'),(axes[1],[c for c in meta.values() if c['family']=='unknown_mission'],'Own navigation')]:
        x=np.geomspace(1,100,160)
        for m in EXACT:
            ratios=[]
            for c in cases:
                best=min((index[c['id'],a]['episode_s'] for a in EXACT if index[c['id'],a]['complete']),default=math.inf)
                own=index[c['id'],m]
                ratios.append(own['episode_s']/best if own['complete'] and math.isfinite(best) else math.inf)
            ax.plot(x,[np.mean(np.array(ratios)<=v) for v in x],label=LABELS[m],color=colors[m])
        ax.set_xscale('log');ax.set_ylim(0,1.02);ax.set_xlabel('Factor of fastest exact method');ax.set_ylabel('Fraction of all scenarios');ax.set_title(title)
    axes[1].legend(fontsize=7.5,ncol=2,loc='lower right');save(fig,'performance_profiles')
    fig,axes=plt.subplots(2,2,figsize=(7.4,6.5),constrained_layout=True)
    for ax,family in zip(axes.flat,families):
        ids={c['id'] for c in main if c['family']==family}
        for m in METHODS:
            times=sorted(r['time_s']*1000 for r in rows if r['case'] in ids and r['method']==m and r['query']>0 and r['planned'] and r['status'] not in ('capped','skipped_after_cap'))
            if times:ax.plot(times,np.arange(1,len(times)+1)/len(times),label=LABELS[m],color=colors[m])
        ax.set_xscale('log');ax.set_xlabel('Completed repair latency, ms');ax.set_title(family);ax.set_ylim(0,1)
    axes.flat[0].set_ylabel('Conditional empirical CDF');axes.flat[-1].legend(fontsize=7.5,ncol=2);save(fig,'latency_ecdf')
    # Delivered changes, not nominal requested rate; initial planning excluded.
    fig,axes=plt.subplots(1,2,figsize=(7.4,4.0),constrained_layout=True)
    bounds=[0,1,4,16,64,256,100000];labels=['0','1–3','4–15','16–63','64–255','256+']
    for ax,control in zip(axes,['car16','grid8']):
        for m in METHODS:
            vals=[]
            for a,b in zip(bounds,bounds[1:]):
                times=[r['time_s']*1000 for r in rows if r['control']==control and r['mode']=='replay' and r['method']==m and r['query']>0 and r['status'] not in ('capped','skipped_after_cap') and a<=r['blocks']+r['opens']<b]
                vals.append(median(times) if times else math.nan)
            ax.plot(range(6),vals,'o-',color=colors[m],label=LABELS[m],ms=3)
        ax.set_xticks(range(6),labels);ax.set_yscale('log');ax.set_xlabel('Delivered changed cells / query');ax.set_ylabel('Median completed repair, ms');ax.set_title(control)
    axes[1].legend(fontsize=7.5,ncol=2);save(fig,'change_scaling')
    fig,axes=plt.subplots(2,3,figsize=(7.6,7.8),constrained_layout=True)
    for i,name in enumerate(['MA_room96','MA_random96']):
        for j,family in enumerate(['on_path','off_path','churn']):
            ax=axes[i,j]
            for m in METHODS:
                vals=[]
                for b in [1,8,32,128]:
                    cases=[c for c in meta.values() if c['map']==name and c['family']==family and 'batch' in c['panels'] and c['params']['batch']==b]
                    own=[index[c['id'],m] for c in cases if index[c['id'],m]['complete']]
                    vals.append(median([r['online_s']*1000/max(1,r['online_queries']) for r in own]) if own else math.nan)
                ax.plot([1,8,32,128],vals,'o-',color=colors[m],label=LABELS[m],ms=3)
            ax.set_xscale('log',base=2);ax.set_xticks([1,8,32,128],[1,8,32,128]);ax.set_yscale('log');ax.set_title(name+' / '+family);ax.set_xlabel('Requested batch cells');ax.set_ylabel('Repair ms/query, completed cases')
    fig.legend(*axes[0,2].get_legend_handles_labels(),loc='outside lower center',ncol=4,fontsize=7.5);save(fig,'batch_size')
    fig,axes=plt.subplots(1,2,figsize=(7.4,4.0),constrained_layout=True)
    for ax,name in zip(axes,['MA_room96','MA_random96']):
        for m in METHODS:
            values=[]
            for k in [1,2,4,8]:
                cases=[c for c in meta.values() if c['map']==name and in_panel(c,'frequency') and c['params']['interval']==k]
                done=[index[c['id'],m] for c in cases if index[c['id'],m]['complete'] and index[c['id'],m]['online_queries']]
                values.append(median([r['online_s']*1000/r['online_queries'] for r in done]) if done else math.nan)
            ax.plot([1,2,4,8],values,'o-',color=colors[m],label=LABELS[m],ms=3)
        ax.set_xscale('log',base=2);ax.set_yscale('log');ax.set_xticks([1,2,4,8],[1,2,4,8]);ax.set_title(name+' / mixed changes')
        ax.set_xlabel('Reference primitives between change events');ax.set_ylabel('Mean repair per completed episode, ms/query')
    axes[1].legend(fontsize=7.5,ncol=2);save(fig,'update_frequency')
    fig,axes=plt.subplots(3,4,figsize=(7.6,6.4),constrained_layout=True)
    for ax,m in zip(axes.flat,METHODS):
        a=np.full((3,4),np.nan)
        for i,k in enumerate([2,8,32]):
            for j,rate in enumerate([1,5,10,30]):
                cases=[c for c in meta.values() if c['family']=='paper_dynamic' and c['params']['interval']==k and c['params']['change_rate']==rate]
                a[i,j]=median([index[c['id'],m]['episode_s']*1000 for c in cases if index[c['id'],m]['complete']]) or math.nan
        im=ax.imshow(a,aspect='auto',cmap='viridis')
        for (i,j),v in np.ndenumerate(a):ax.text(j,i,'—' if not math.isfinite(v) else f'{v:.1f}',ha='center',va='center',color=contrast(im,v),fontsize=7)
        ax.set_xticks(range(4),[1,5,10,30]);ax.set_yticks(range(3),[2,8,32]);ax.set_title(LABELS[m]);ax.set_xlabel('Requested cr, %');ax.set_ylabel('k = radius')
    axes.flat[-1].axis('off');axes.flat[-1].text(.05,.5,'Median episode planning, ms\nIncluding first plan + setup\nEach panel has its own color range\nInitial density 10/20/30/40%',va='center')
    save(fig,'paper_rate_frequency')
    fig,axes=plt.subplots(2,2,figsize=(7.5,6.8),constrained_layout=True)
    for j,control in enumerate(['car16','grid8']):
        radii=[8,16] if control=='car16' else [1,4,8]
        for m in METHODS:
            times=[];quality=[]
            for radius in radii:
                cases=[c for c in meta.values() if c['control']==control and c['family']=='unknown_mission' and c['params']['radius']==radius]
                done=[index[c['id'],m] for c in cases if index[c['id'],m]['complete']]
                times.append(median([r['episode_s']*1000 for r in done]) if done else math.nan)
                quality.append(median([r['travel_ratio'] for r in done]) if done else math.nan)
            axes[0,j].plot(radii,times,'o-',label=LABELS[m],color=colors[m],ms=3)
            axes[1,j].plot(radii,quality,'o-',color=colors[m],ms=3)
        axes[0,j].set_yscale('log');axes[0,j].set_title(control+' / successful missions');axes[0,j].set_ylabel('Episode planning, ms')
        axes[1,j].set_xlabel('Sensor radius');axes[1,j].set_ylabel('Travel / clairvoyant optimum');axes[1,j].axhline(1,color='black',lw=.5)
    axes[0,1].legend(fontsize=7.5,ncol=2);save(fig,'unknown_visibility')
    # Actual missions, not reference-replay trajectories. Fog is per algorithm.
    samples=[next(c for c in meta.values() if c['control']=='car16' and c['map']=='MA_maze96' and c['family']=='unknown_mission' and c['seed']==48101 and c['params']['radius']==8),
             next(c for c in meta.values() if c['control']=='grid8' and c['map']=='random50_p40' and c['family']=='unknown_mission' and c['seed']==48101 and c['params']['radius']==1)]
    fig,axes=plt.subplots(2,3,figsize=(7.5,6.6),constrained_layout=True)
    for i,c in enumerate(samples):
        grid=grids[c['map']];radius=c['params']['radius']
        for j,m in enumerate(['lba','dstar_lattice','md_astar']):
            ax=axes[i,j];q=sorted((r for r in rows if r['case']==c['id'] and r['method']==m and r['repeat']==0),key=lambda r:r['step'])
            seen=np.zeros_like(grid,dtype=bool)
            for r in q:
                a,b=r['start_i'],r['start_j'];seen[max(0,a-radius):min(grid.shape[0],a+radius+1),max(0,b-radius):min(grid.shape[1],b+radius+1)]=True
            assert int(seen.sum())==q[-1]['known'],'Figure fog disagrees with native sensor log'
            picture=np.where(seen,np.where(grid,0.0,1.0),0.65)
            ax.imshow(picture,cmap='gray',vmin=0,vmax=1)
            ax.plot([q[0]['start_j']]+[r['next_j'] for r in q],[q[0]['start_i']]+[r['next_i'] for r in q],color=colors[m],lw=1.4)
            ax.scatter([c['start'][1],c['goal'][1]],[c['start'][0],c['goal'][0]],marker='*',color=['#2266cc','#cc3322'],s=45)
            z=index[c['id'],m];quality='unfinished' if z['travel_ratio'] is None else f'travel={z["travel_ratio"]:.2f}x'
            ax.set_title(c['map']+' / '+LABELS[m]+f'\n{z["terminal"]}, {quality}, {1000*z["episode_s"]:.1f} ms',fontsize=8)
            ax.set_xticks([]);ax.set_yticks([])
    save(fig,'navigation_examples')
    fig,axes=plt.subplots(1,2,figsize=(7.4,4.0),constrained_layout=True)
    for ax,c in zip(axes,samples):
        for m in METHODS:
            q=sorted((r for r in rows if r['case']==c['id'] and r['method']==m and r['repeat']==0),key=lambda r:r['step'])
            ax.plot([r['step'] for r in q],[r['known']/(c['shape'][0]*c['shape'][1]) for r in q],color=colors[m],label=LABELS[m])
        ax.set_xlabel('Executed primitive index');ax.set_ylabel('Known cells / all cells');ax.set_title(c['map']+f' / radius {c["params"]["radius"]}')
    axes[1].legend(fontsize=7.5,ncol=2);save(fig,'knowledge_progress')
    fig,axes=plt.subplots(1,2,figsize=(7.4,4.0),constrained_layout=True)
    for ax,reverse in zip(axes,[False,True]):
        c=next(c for c in meta.values() if c['family']=='history' and c['params']['updates']==64 and c['params']['reverse']==reverse)
        for m in METHODS:
            repeats=[]
            for rep in range(3):
                q=sorted((r for r in rows if r['case']==c['id'] and r['method']==m and r['repeat']==rep),key=lambda r:r['query'])
                repeats.append(np.cumsum([r['time_s'] for r in q]))
            x=[q['cumulative_changes'] for q in c['queries']]
            y=np.median(repeats,axis=0)*1000
            ax.plot(x,y,label=LABELS[m],color=colors[m])
        ax.set_yscale('log');ax.set_xlabel('Cumulative delivered changes');ax.set_ylabel('Cumulative planning, ms');ax.set_title('History: '+('reversing start' if reverse else 'fixed start'))
    axes[1].legend(fontsize=7.5,ncol=2);save(fig,'cumulative_history')
    fig,axes=plt.subplots(2,2,figsize=(7.4,6.0),constrained_layout=True)
    for i,reverse in enumerate([False,True]):
        c=next(c for c in meta.values() if c['family']=='history' and c['params']['updates']==64 and c['params']['reverse']==reverse)
        x=[q['cumulative_changes'] for q in c['queries']]
        for m in ['md_astar','md64','md_scan']:
            q=sorted((r for r in rows if r['case']==c['id'] and r['method']==m and r['repeat']==0),key=lambda r:r['query'])
            axes[i,0].plot(x,[r['deferred_cells'] for r in q],label=LABELS[m],color=colors[m])
            axes[i,1].plot(x,np.cumsum([r['refined_cells'] for r in q]),label=LABELS[m],color=colors[m])
        for ax in axes[i]:ax.set_xlabel('Cumulative delivered changes');ax.set_title('Reversing start' if reverse else 'Fixed start')
        axes[i,0].set_ylabel('Deferred cells retained');axes[i,1].set_ylabel('Cumulative bound evaluations')
    axes[0,1].legend(fontsize=8);save(fig,'certificate_history')
    group_names=['car16:on_path','car16:off_path','car16:churn','car16:unknown_replay','grid8:paper_dynamic']
    fig,axes=plt.subplots(1,2,figsize=(7.6,4.8),constrained_layout=True)
    for i,key in enumerate(group_names):
        for j,m in enumerate(METHODS):
            z=result['groups'][key]['methods'][m]
            axes[0].scatter(i+(j-5)*.06,max(z['peak_heap_mib'],1e-6),s=15,color=colors[m],label=LABELS[m] if i==0 else None)
            axes[1].scatter(i+(j-5)*.06,z['completion_fraction'],s=15,color=colors[m])
    for ax in axes:ax.set_xticks(range(5),['on path','off path','mixed','unknown','paper grid'],rotation=15)
    axes[0].set_yscale('log');axes[0].set_ylabel('Median observed peak C++ heap, MiB');axes[0].legend(fontsize=7.5,ncol=2)
    axes[1].set_ylabel('Completed computational episodes / all');axes[1].set_ylim(-.03,1.05);save(fig,'memory_completion')
    fig,axes=plt.subplots(1,2,figsize=(7.6,4.6),constrained_layout=True)
    for j,(column,title) in enumerate([('expansions','Search/repair expansions'),('checked_cells','Collision cell reads')]):
        for i,m in enumerate(METHODS):
            values=[result['groups'][key]['methods'][m][column] for key in group_names]
            axes[j].plot(range(5),[max(v,1) if v is not None else math.nan for v in values],'o-',label=LABELS[m],color=colors[m],ms=3)
        axes[j].set_xticks(range(5),['on path','off path','mixed','unknown','paper grid'],rotation=15);axes[j].set_yscale('log');axes[j].set_ylabel('Median total per completed episode');axes[j].set_title(title+' (zero shown at 1)')
    axes[1].legend(fontsize=7.5,ncol=2);save(fig,'work_metrics')
    print('Wrote figures to',dest)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,default=HERE/'results/expanded');args=p.parse_args()
    r,i,m,q,mem=analyze(args.directory);plots(args.directory,r,i,m,q,mem)
