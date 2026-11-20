#!/usr/bin/env python3
"""Audit the frozen closed-loop study; preserve coverage and map strata."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path

os.environ.setdefault('MPLCONFIGDIR','/tmp/ima_navigation_mpl')
import numpy as np
import pandas as pd

from run_all import HERE,ROOT,digest,verify
from study import read_manifest
from storage import ensure_unpacked

METHODS=['lba','lazy_lba','mesha','mesh_parall','dstar_lattice','dstar_mesh','mpgaa','md_astar','md64','md_scan','lba_reuse','prefix_positive','cmesh_dstar','suffix_mesh','boundary_mesh']
LABELS=dict(zip(METHODS,['LBA*','Lazy LBA*','MeshA*','Mesh/ParallA* ≈','D* lattice','D* mesh','MPGAA*','MD-A*','MD64','MD-scan','LBA* reuse','Positive prefix','C-Mesh','Suffix-Mesh','Boundary-Mesh']))
COUNTERS=['expansions','checked_cells','notify_probes','heuristic_pops','backend_calls','activated_cells','refined_cells']
IGNORE={'repeat','time_s','setup_s','planner_s','initial_s','repair_s','sensing_s','reference_s','peak_heap_bytes','retained_heap_bytes'}
HASHES={'world_hash':'str','belief_hash':'str','path_hash':'str','fingerprint':'str'}

def finite(value):return None if pd.isna(value) else float(value)
def gm(values):
    a=np.asarray(values,dtype=float);a=a[np.isfinite(a)&(a>0)]
    return float(np.exp(np.log(a).mean())) if len(a) else None

def load(directory):
    ensure_unpacked(directory)
    state=json.loads((directory/'experiment.json').read_text());assert state['status']=='passed','Incomplete study'
    for profile in [False,True]:
        own=[state['jobs'][j['name']] for j in state['plan'] if j['memory']==profile]
        assert len({j['binary_sha256'] for j in own})==1,'Mixed native binaries within a measurement pass'
        assert len({(j['completion']['compiler'],j['completion']['flags']) for j in own})==1,'Mixed compiler flags'
    mp=HERE/'frozen/manifest.json';m=read_manifest();assert digest(mp)==state['manifest_sha256'] and state['selection_sha256']==m['selection_sha256']
    for path,sha in state['runner_sha256'].items():assert digest(ROOT/path)==sha,path
    if 'imported_static' in state:
        archived=HERE/'results/pre_car_full_sweep/raw'
        assert digest(archived/'experiment.json')==state['imported_static']['experiment_sha256']
        for files in state['imported_static']['jobs'].values():
            for path,sha in files.items():assert digest(archived/Path(path).name)==sha,path
    meta={};hashes={};runs=[];calls=[];memruns=[];memcalls=[]
    for r in m['records']:
        selected=set(r['selected_cases'])
        for c in json.loads((ROOT/r['contexts']).read_text())['cases']:
            if c['id'] in selected:assert c['id'] not in meta;meta[c['id']]=c
    for job in state['plan']:
        record=state['jobs'][job['name']];assert record['status']=='passed'
        for p,sha in record['output_sha256'].items():assert digest(ROOT/p)==sha,p;hashes[p]=sha
        prefix=directory/job['name'];completion=json.loads(Path(str(prefix)+'.json').read_text())
        a=pd.read_csv(str(prefix)+'_runs.csv',dtype={k:v for k,v in HASHES.items() if k!='path_hash'})
        b=pd.read_csv(str(prefix)+'_calls.csv',dtype={k:v for k,v in HASHES.items() if k!='fingerprint'})
        assert len(a)==completion['runs']==job['expected_runs'] and len(b)==completion['calls']
        assert completion['memory_profile']==job['memory'] and completion['cap']==m['cap']
        assert set(a.method)==set(METHODS) and not a.duplicated(['case','method','repeat']).any()
        assert not b.duplicated(['case','method','repeat','query']).any() and b.planned.eq(1).all()
        assert a.groupby(['case','method']).fingerprint.nunique().eq(1).all()
        cols=[c for c in b.columns if c not in IGNORE]
        reference=b[b.repeat.eq(0)].set_index(['case','method','query'])
        cols=[c for c in cols if c not in ['case','method','query']]
        for rep in sorted(set(b.repeat)-{0}):
            other=b[b.repeat.eq(rep)].set_index(['case','method','query'])
            pd.testing.assert_frame_equal(reference.loc[other.index,cols],other[cols],check_dtype=False,check_exact=True)
        assert (b.n.eq(b.k)|b.kind.eq('unknown')).all()
        ok=b.status.ne('capped');reachable=b.expected.notna();assert b.loc[ok,'cost'].notna().eq(reachable[ok]).all()
        exact=ok&reachable&b.method.ne('mesh_parall');assert ((b.cost-b.expected).abs()[exact]<1e-6).all()
        approximate=ok&reachable&b.method.eq('mesh_parall');assert ((b.cost-b.expected)[approximate]>=-1e-6).all()
        assert (b.time_s>=0).all() and (a.moves>=0).all()
        (memruns if job['memory'] else runs).append(a);(memcalls if job['memory'] else calls).append(b)
    runs=pd.concat(runs,ignore_index=True);calls=pd.concat(calls,ignore_index=True)
    memruns=pd.concat(memruns,ignore_index=True);memcalls=pd.concat(memcalls,ignore_index=True)
    assert len(runs)==m['timed_runs'] and len(memruns)==m['memory_runs']
    initial=calls[calls.kind.eq('dynamic')&calls['query'].eq(0)]
    initial_optimum=initial['case'].map(lambda c:meta[c]['initial_optimum'])
    assert ((initial.expected-initial_optimum).abs()<1e-6).all(),'Frozen initial optimum differs from the fresh true-map reference'
    # Compare every deterministic field, including world/belief/path hashes.
    for normal,memory,keys in [(runs,memruns,['case','method']),(calls,memcalls,['case','method','query'])]:
        normal=normal[normal.repeat.eq(0)].set_index(keys);memory=memory.set_index(keys)
        cols=[c for c in memory.columns if c not in IGNORE]
        pd.testing.assert_frame_equal(normal.loc[memory.index,cols],memory[cols],check_dtype=False,check_exact=True)
    for frame in [runs,calls,memruns,memcalls]:
        frame['control']=frame['case'].map(lambda x:meta[x]['control']);frame['map']=frame['case'].map(lambda x:meta[x]['map'])
    # Saturated nominal cr columns describe the same physical process. With
    # common priorities they must reproduce paths, worlds and work exactly.
    duplicate=runs[runs.repeat.eq(0)&runs.kind.eq('dynamic')].copy()
    duplicate['physical_key']=duplicate['case'].map(lambda c:json.dumps([meta[c]['control'],meta[c]['map'],meta[c]['seed'],meta[c]['params']['k'],meta[c]['actual_half']]))
    duplicate['physical_fingerprint']=duplicate.fingerprint.map(lambda s:' '.join(v for i,v in enumerate(s.split()) if i not in [5,6]))
    assert duplicate.groupby(['physical_key','method']).physical_fingerprint.nunique().eq(1).all(),'Clamped duplicate scenarios differ'
    grid=calls[calls.control.eq('grid8')];reference=grid[grid.method.eq('prefix_positive')].set_index(['case','repeat','query'])
    fields=['status','cost','expected','path_hash','world_hash','belief_hash','step','expansions','checked_cells','notify_probes','heuristic_pops','backend_calls']
    for method in ['cmesh_dstar','suffix_mesh','boundary_mesh']:
        other=grid[grid.method.eq(method)].set_index(['case','repeat','query'])
        own_fields=[c for c in fields if method!='boundary_mesh' or c!='checked_cells']
        pd.testing.assert_frame_equal(reference.loc[other.index,own_fields],other[own_fields],check_dtype=False,check_exact=True)
    return state,m,meta,runs,calls,memruns,hashes

def aggregate(meta,runs,calls,memory):
    keys=['case','method'];numeric=[c for c in runs.select_dtypes('number').columns if c!='repeat']
    episodes=runs.groupby(keys,sort=False)[numeric].median().reset_index()
    first=runs[runs.repeat.eq(0)].set_index(keys)
    episodes['status']=[first.loc[tuple(v),'status'] for v in episodes[keys].values]
    episodes['repeats']=[int(meta[c]['timing_repeats']) for c in episodes['case']]
    med=runs.assign(episode_s=runs.setup_s+runs.planner_s).groupby(keys).episode_s
    mad=med.apply(lambda a:float(np.median(np.abs(a-np.median(a)))/np.median(a)) if np.median(a)>0 else 0)
    episodes['relative_mad']=[mad.loc[tuple(v)] for v in episodes[keys].values]
    for key in ['control','map','kind','seed','initial_moves','long_route_stratum']:
        episodes[key]=episodes['case'].map(lambda c:meta[c].get(key))
    for key in ['k','n','cr','radius','max_moves']:episodes[key]=episodes['case'].map(lambda c:meta[c]['params'].get(key,0))
    episodes['cells']=episodes['case'].map(lambda c:int(np.prod(meta[c]['shape'])))
    episodes['complete']=episodes.status.eq('goal');episodes['episode_s']=episodes.setup_s+episodes.planner_s
    episodes['planner_and_sensor_s']=episodes.episode_s+episodes.sensing_s
    episodes['online_s']=episodes.repair_s;episodes['known_fraction']=episodes.known_cells/episodes.cells
    episodes['belief_accuracy']=1-episodes.belief_mismatches/episodes.cells
    assert episodes.belief_accuracy.between(0,1).all()
    episodes['travel_ratio']=episodes.travel_cost/episodes.initial_optimum
    static_success=episodes[episodes.kind.eq('unknown')&episodes.complete]
    assert (static_success.travel_cost+1e-6>=static_success.initial_optimum).all()
    episodes['phaseful']=episodes.phases.gt(0);episodes['actual_cr']=np.where(episodes.phases.gt(0),100*episodes.actual_changes/(episodes.cells*episodes.phases),np.nan)
    episodes['repeat_relative_mad']=episodes.relative_mad.where(episodes.repeats.eq(3))
    terminal=calls[calls.repeat.eq(0)].sort_values('query').groupby(keys).tail(1).set_index(keys)
    episodes['stale_dead_end']=[bool(first.loc[tuple(v),'status']=='no_path' and pd.notna(terminal.loc[tuple(v),'truth_cost'])) for v in episodes[keys].values]
    mm=memory.set_index(keys)
    for field in ['peak_heap_bytes','retained_heap_bytes']:episodes[field]=[mm.loc[tuple(v),field] if tuple(v) in mm.index else np.nan for v in episodes[keys].values]
    query=calls.groupby(keys).agg(p95_ms=('time_s',lambda a:1000*float(np.quantile(a,.95))),queries_logged=('query','size'),max_deferred_cells=('deferred_cells','max'))
    episodes=episodes.merge(query,on=keys,validate='one_to_one')
    online_latency=calls[calls.step.gt(0)].groupby(keys).time_s.quantile(.95).mul(1000).rename('online_p95_ms')
    episodes=episodes.merge(online_latency,on=keys,how='left',validate='one_to_one')
    # Calendar density and budgets are invariant; zero phases have zero delivered edits.
    normal_counts=calls[calls.repeat.eq(0)].groupby(keys).size()
    for r in episodes.itertuples():
        c=meta[r.case];assert r.plans==normal_counts.loc[r.case,r.method]
        if c['kind']=='dynamic':
            assert r.phases==(max(0,int(r.moves)-1)//r.k if r.status=='goal' else int(r.moves)//r.k if r.status in ['no_path','capped'] else max(0,int(r.moves)-1)//r.k)
            assert r.actual_changes==2*c['actual_half']*r.phases
            assert r.requested_changes==2*c['requested_half']*r.phases
            assert r.clamped_phases==int(c['budget_clamped'])*r.phases
            assert r.observed_changes<=r.actual_changes
            assert r.known_cells==r.cells and r.newly_seen==0
        else:
            assert r.actual_changes==r.phases==0 and r.belief_mismatches>=0 and not r.stale_dead_end
            assert r.observed_changes==round(c['truth_density']*r.cells)-r.belief_mismatches
            assert r.newly_seen==r.known_cells
    return episodes

def summarize(e,keys):
    result=[]
    for values,a in e.groupby(keys,dropna=False,sort=True):
        values=values if isinstance(values,tuple) else (values,);r=dict(zip(keys,values));g=a[a.complete]
        r.update(cases=len(a),goals=int(a.complete.sum()),phaseful=int(a.phaseful.sum()),phaseful_goals=int((a.complete&a.phaseful).sum()),
                 capped=int(a.status.eq('capped').sum()),no_path=int(a.status.eq('no_path').sum()),stale_dead_ends=int(a.stale_dead_end.sum()),
                 step_limits=int(a.status.eq('step_limit').sum()),zero_phase_goals=int((a.complete&~a.phaseful).sum()),
                 requested_cr_min=finite(a.cr.min()),actual_cr_min=finite(a.actual_cr.min()),actual_cr_max=finite(a.actual_cr.max()),
                 median_phases=finite(a.phases.median()),clamped_phases=int(a.clamped_phases.sum()))
        for col in ['episode_s','online_s','planner_and_sensor_s','p95_ms','online_p95_ms','max_deferred_cells','moves','plans','travel_ratio','known_fraction','belief_accuracy','expansions','checked_cells','notify_probes',
                    'online_expansions','online_checked_cells','observed_changes','actual_changes','sensing_s','peak_heap_bytes','retained_heap_bytes','repeat_relative_mad']:
            r[col]=finite(g[col].median())
        # Total computational cost over every attempted episode is also retained.
        r['all_attempts_s']=float(a.episode_s.sum());r['goal_episode_sum_s']=float(g.episode_s.sum())
        result.append(r)
    return pd.DataFrame(result)

def pairs(e,keys):
    result=[]
    for vals,a in e.groupby(keys,sort=True):
        vals=vals if isinstance(vals,tuple) else (vals,);basekeys=dict(zip(keys,vals))
        for baseline in ['lba','lba_reuse','dstar_lattice']:
            b=a[a.method.eq(baseline)].set_index('case')
            for method in METHODS:
                x=a[a.method.eq(method)].set_index('case');common=x.index.intersection(b.index)
                mask=x.loc[common,'complete']&b.loc[common,'complete'];ids=common[mask]
                eligible=(x.loc[ids,'phaseful']&b.loc[ids,'phaseful']) if a.kind.iloc[0]=='dynamic' else x.loc[ids,'plans'].gt(1)&b.loc[ids,'plans'].gt(1)
                online=ids[eligible&x.loc[ids,'online_s'].gt(0)&b.loc[ids,'online_s'].gt(0)]
                result.append(dict(**basekeys,method=method,baseline=baseline,cases=len(common),paired_goals=len(ids),paired_online=len(online),
                                   episode_speedup=gm(b.loc[ids,'episode_s']/x.loc[ids,'episode_s']),online_speedup=gm(b.loc[online,'online_s']/x.loc[online,'online_s']),
                                   episode_min_speedup=finite((b.loc[ids,'episode_s']/x.loc[ids,'episode_s']).min()),
                                   online_min_speedup=finite((b.loc[online,'online_s']/x.loc[online,'online_s']).min()),
                                   expansion_ratio=gm(b.loc[ids,'expansions']/x.loc[ids,'expansions'].replace(0,np.nan)),
                                   cell_read_ratio=gm(b.loc[ids,'checked_cells']/x.loc[ids,'checked_cells'].replace(0,np.nan))))
    return pd.DataFrame(result)

def prior_maps():
    frames=[];hashes={}
    for cohort,path in [('previous11',ROOT/'cpp/experiments/results/expanded/analysis/episode_metrics.csv'),('contemporary15',ROOT/'cpp/mesh_variants/results/full/analysis/episode_metrics.csv')]:
        assert path.exists();hashes[str(path.relative_to(ROOT))]=digest(path);a=pd.read_csv(path);metadata={}
        for p in (ROOT/'cpp/experiments/frozen').glob('*.contexts.json'):
            for c in json.loads(p.read_text())['cases']:metadata[c['id']]=c
        mask=a.apply(lambda r: r.control!='car16' or r.family not in ['on_path','off_path','churn','unknown_replay'] or 'main' in metadata[r['case']].get('panels',[]),axis=1)
        a=a[mask];keys=['control','map','family','mode','method']
        for values,g in a.groupby(keys,sort=True):
            ok=g[g.complete];r=dict(cohort=cohort,**dict(zip(keys,values)),cases=len(g),completed=len(ok),capped=int(g.terminal.eq('capped').sum()))
            for c in ['episode_s','online_s','peak_heap_bytes','travel_ratio','expansions','checked_cells','notify_probes']:
                r[c]=finite(ok[c].median())
            r['sum_episode_s']=float(ok.episode_s.sum());frames.append(r)
    return pd.DataFrame(frames),hashes

def aligned_queries(calls,meta):
    """Common actual inputs within the closed-loop runs, without new timings.

    Matching is restricted to completed online calls with equal start, phase
    step, pre/post belief hashes, world hash, and block/open cardinalities.
    Internal search histories need not be identical; this is a subset control.
    """
    q=calls[calls.repeat.eq(0)].copy()
    q['prior_belief_hash']=q.groupby(['case','method'],sort=False).belief_hash.shift()
    q=q[q.step.gt(0)&q.status.isin(['ok','no_path'])]
    keys=['case','status','step','start_i','start_j','start_theta','world_hash','belief_hash','prior_belief_hash','blocks','opens']
    fields=['query','time_s','expected',*COUNTERS]
    base=q[q.method.eq('dstar_lattice')][keys+fields]
    episodes=[]
    for method in METHODS:
        if method=='dstar_lattice':continue
        own=q[q.method.eq(method)][keys+fields]
        joined=own.merge(base,on=keys,suffixes=('_candidate','_baseline'),validate='one_to_one')
        assert (((joined.expected_candidate-joined.expected_baseline).abs()<1e-6)|(joined.expected_candidate.isna()&joined.expected_baseline.isna())).all()
        for (case,status),group in joined.groupby(['case','status'],sort=True):
            c=meta[case];r=dict(case=case,status=status,method=method,control=c['control'],map=c['map'],kind=c['kind'],queries=len(group))
            for field in ['time_s',*COUNTERS]:
                r[field+'_candidate']=float(group[field+'_candidate'].sum());r[field+'_baseline']=float(group[field+'_baseline'].sum())
            r['speedup']=r['time_s_baseline']/r['time_s_candidate'];episodes.append(r)
    detail=pd.DataFrame(episodes);summary=[]
    for values,group in detail.groupby(['control','map','kind','method','status'],sort=True):
        summary.append(dict(zip(['control','map','kind','method','status'],values))|dict(cases=len(group),queries=int(group.queries.sum()),
                       speedup=gm(group.speedup),time_candidate=float(group.time_s_candidate.sum()),time_baseline=float(group.time_s_baseline.sum()),
                       expansions_candidate=float(group.expansions_candidate.sum()),expansions_baseline=float(group.expansions_baseline.sum()),
                       reads_candidate=float(group.checked_cells_candidate.sum()),reads_baseline=float(group.checked_cells_baseline.sum())))
    return detail,pd.DataFrame(summary)

def main(directory,plots=True):
    state,m,meta,runs,calls,memory,raw=load(directory)
    e=aggregate(meta,runs,calls,memory);out=directory/'analysis';out.mkdir(exist_ok=True)
    e.to_csv(out/'episode_metrics.csv',index=False)
    summaries={
        'map_summary':summarize(e,['control','kind','map','method']),
        'static_radius':summarize(e[e.kind.eq('unknown')],['control','map','radius','method']),
        'dynamic_parameters':summarize(e[e.kind.eq('dynamic')],['control','map','k','cr','method']),
        'map_pairs':pairs(e,['control','kind','map']),
        'dynamic_pairs':pairs(e[e.kind.eq('dynamic')],['control','kind','map','k','cr']),
    }
    prior,prior_hashes=prior_maps();summaries['prior_by_map']=prior
    aligned,aligned_maps=aligned_queries(calls,meta);summaries['aligned_query_cases']=aligned;summaries['aligned_query_maps']=aligned_maps
    for name,a in summaries.items():a.to_csv(out/(name+'.csv'),index=False)
    prior.to_csv(ROOT/'docs/experiments/prior_by_map.csv',index=False)
    c0=calls[calls.repeat.eq(0)].copy();c0['observed_changes']=c0.blocks+c0.opens
    c0['change_bin']=pd.cut(c0.observed_changes,[-1,0,1,4,16,64,256,1024,1e10],labels=['0','1','2–4','5–16','17–64','65–256','257–1024','>1024'])
    work=c0[c0.step.gt(0)].groupby(['control','map','method','change_bin'],observed=True).agg(queries=('time_s','size'),median_ms=('time_s',lambda v:1000*v.median()),
                p95_ms=('time_s',lambda v:1000*v.quantile(.95)),expansions=('expansions','median'),checked_cells=('checked_cells','median'),notify_probes=('notify_probes','median'))
    work.to_csv(out/'work_by_observed_changes.csv')
    approximate=calls[calls.method.eq('mesh_parall')&calls.cost.notna()&calls.expected.gt(0)&calls.status.ne('capped')]
    verification=json.loads((HERE/'results/verification.json').read_text());assert verification['status']=='passed' and verification['sanitize']
    compiler=next(state['jobs'][j['name']]['completion'] for j in state['plan'] if not j['memory'])
    audit=dict(status='passed',cpu=state['cpu'],platform=state['platform'],compiler=compiler['compiler'],compiler_flags=compiler['flags'],timed_runs=len(runs),memory_runs=len(memory),planner_calls=len(calls),
               cases=len(meta),episodes=len(e),goals=int(e.complete.sum()),terminal_counts=e.status.value_counts().to_dict(),
               dynamic_physical_cases=len({(c['control'],c['map'],c['seed'],c['params']['k'],c['actual_half']) for c in meta.values() if c['kind']=='dynamic'}),
               stale_dead_ends=int(e.stale_dead_end.sum()),dynamic_zero_phase_goals=int((e.kind.eq('dynamic')&e.complete&~e.phaseful).sum()),
               exact_cost_disagreements=0,allocation_decision_parity='passed',repeat_decision_parity='passed',
               grid_mesh_projection_parity='passed',clamped_duplicate_decision_parity='passed',
               max_approximate_plan_ratio=finite((approximate.cost/approximate.expected).max()),
               median_three_repeat_relative_mad=finite(e.repeat_relative_mad.median()),
               manifest_sha256=digest(HERE/'frozen/manifest.json'),source_sha256=digest(Path(__file__)),raw_sha256=raw,prior_metrics_sha256=prior_hashes,
               selection_sha256=m['selection_sha256'],orchestration_sha256=state['runner_sha256'],
               tables_sha256={p.name:digest(p) for p in out.glob('*.csv')},verification_sha256=digest(HERE/'results/verification.json'))
    packed=directory/'packed_outputs.json'
    audit['packed_outputs_sha256']=digest(packed) if packed.exists() else None
    (out/'analysis.json').write_text(json.dumps(audit,indent=2)+'\n')
    if plots:
        from figures import generate
        generate(directory,e,summaries)
    print(json.dumps({k:audit[k] for k in ['status','timed_runs','memory_runs','planner_calls','goals','terminal_counts','stale_dead_ends','dynamic_zero_phase_goals','median_three_repeat_relative_mad']},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,default=HERE/'results/full');p.add_argument('--no-plots',action='store_true');a=p.parse_args();main(a.directory,not a.no_plots)
