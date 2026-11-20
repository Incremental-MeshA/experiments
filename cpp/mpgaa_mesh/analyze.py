#!/usr/bin/env python3
"""Validate the entire new cohort, then produce paired tables and vector plots."""
import argparse
import json
import math
import os
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR','/tmp/mpgaa-mesh-matplotlib')
os.environ.setdefault('XDG_CACHE_HOME','/tmp/mpgaa-mesh-cache')
Path(os.environ['XDG_CACHE_HOME']).mkdir(parents=True,exist_ok=True)
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal
from run_all import digest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
DEST=ROOT/'docs/mpgaa_mesh'
NEW=['boundary_mpgaa','selective_mpgaa','delta_mpgaa','policy_mpgaa']
CONTROL=['lba','lba_reuse','mpgaa','md_astar','boundary_mesh','octile_reuse']
LABELS={'boundary_mpgaa':'Boundary-MPGAA*','selective_mpgaa':'Selective-Mesh-MPGAA*','delta_mpgaa':'Delta-Mesh-MPGAA*',
        'policy_mpgaa':'Policy-Mesh-MPGAA*','mpgaa':'MPGAA*','lba':'LBA*','lba_reuse':'LBA* reuse','md_astar':'MD-A*',
        'boundary_mesh':'Boundary-Mesh','octile_reuse':'Octile A* reuse','selective_no_prune':'Selective / no pruning','selective_geom':'Selective / geometric bounds'}
WORK=['mesh_nodes','bound_evals','pruned_branches','pruned_primitives','watch_hits','validity_flips','witness_stops','policy_probes','policy_hits','alternate_uses']
COUNTERS=['expansions','checked_cells','notify_probes','heuristic_pops','backend_calls','certified','activated_cells','refined_cells']+WORK
COLORS=['#166e90','#d57c20','#37834e','#964872']

def read(path):
    return pd.read_csv(path,dtype={k:str for k in ['path_hash','world_hash','belief_hash','fingerprint']})

def check_profile(timing,memory):
    keys=['case','method','query']
    a=timing[timing.repeat.eq(0)].set_index(keys).sort_index()
    b=memory.set_index(keys).sort_index()
    fields=[c for c in ['status','planned','cost','expected','blocks','opens','known','known_cells','newly_seen','belief_mismatches',
            'travel_cost','path_hash','world_hash','belief_hash','start_i','start_j','start_theta','next_i','next_j','next_theta','deferred_cells']+COUNTERS if c in a and c in b]
    assert not a.index.has_duplicates and not b.index.has_duplicates
    assert_frame_equal(a[fields],b[fields],check_dtype=False,check_exact=True)
    return len(a)

def decorate(frame,job,contexts):
    frame=frame.copy();frame['job']=job['name'];frame['cohort']=job['mode']
    for name in ['control','map','family']:
        frame[name]=frame['case'].map(lambda x:contexts[x].get(name,'unknown' if job['mode']=='mission' else 'dynamic'))
    if job['mode']=='navigation':frame['cohort']='navigation_'+frame['kind'];frame['family']=frame['kind']
    frame['online']=frame['query'].gt(0)
    return frame

def episodes(calls,job,native=None):
    records=[]
    for (case,method,rep),d in calls.groupby(['case','method','repeat'],sort=False):
        d=d.sort_values('query');p=d[d.planned.eq(1)];online=p[p.online];last=d.iloc[-1]
        complete=not d.status.isin(['capped','skipped_after_cap','step_limit']).any()
        if job['mode']!='replay':complete=complete and last.status=='goal'
        r=dict(case=case,method=method,repeat=rep,job=job['name'],cohort=d.cohort.iloc[0],control=d.control.iloc[0],
               map=d['map'].iloc[0],family=d.family.iloc[0],complete=bool(complete),status=last.status,
               episode_s=float((p.time_s+p.setup_s).sum()),online_s=float(online.time_s.sum()),initial_s=float(p.time_s.iloc[0]),
               setup_s=float(p.setup_s.sum()),plans=len(p),online_plans=len(online),travel_cost=float(last.travel_cost),
               peak_heap_bytes=int(d.peak_heap_bytes.max()),retained_heap_bytes=int(last.retained_heap_bytes))
        for field in COUNTERS:r[field]=int(p[field].sum())
        if native is not None:
            row=native[(native['case']==case)&native.method.eq(method)&native.repeat.eq(rep)].iloc[0]
            r.update(complete=bool(row.status=='goal'),status=row.status,episode_s=float(row.planner_s+row.setup_s),online_s=float(row.repair_s),
                     initial_s=float(row.initial_s),peak_heap_bytes=int(row.peak_heap_bytes),retained_heap_bytes=int(row.retained_heap_bytes),
                     travel_cost=float(row.travel_cost),moves=int(row.moves))
            assert math.isclose(p.time_s.sum(),row.planner_s,rel_tol=1e-12,abs_tol=1e-12)
            assert math.isclose(online.time_s.sum(),row.repair_s,rel_tol=1e-12,abs_tol=1e-12)
            for field in COUNTERS:assert int(p[field].sum())==int(row[field]),(case,method,field)
        records.append(r)
    return pd.DataFrame(records)

def gm(x):
    x=np.asarray(x,dtype=float);x=x[np.isfinite(x)&(x>0)]
    return float(np.exp(np.log(x).mean())) if len(x) else math.nan

def map_bootstrap(d,field):
    # Cluster bootstrap is descriptive: repeated configurations are NOT IID.
    grouped=d.groupby(['control','map'])[field].agg(lambda x:(float(np.log(x).sum()),len(x)))
    if len(grouped)<2:return math.nan,math.nan
    sums=np.array([v[0] for v in grouped]);sizes=np.array([v[1] for v in grouped])
    rng=np.random.default_rng(819013);idx=rng.integers(len(sums),size=(3000,len(sums)))
    values=np.exp(sums[idx].sum(axis=1)/sizes[idx].sum(axis=1));lo,hi=np.quantile(values,[.025,.975])
    return float(lo),float(hi)

def pairs(case_metrics):
    rows=[]
    keys=['case','job','cohort','control','map','family']
    for baseline in ['mpgaa','boundary_mpgaa','lba_reuse','md_astar','boundary_mesh','octile_reuse','selective_no_prune','selective_geom','best_control']:
        base=case_metrics[case_metrics.method.eq(baseline)]
        if baseline=='best_control':
            eligible=case_metrics[case_metrics.method.isin(CONTROL)&case_metrics.complete]
            if eligible.empty:continue
            base=eligible.sort_values('episode_s').drop_duplicates(['case','job']).copy()
            base['selected_control']=base['method'];base['method']='best_control'
        for candidate in NEW+['selective_no_prune','selective_geom']:
            if candidate==baseline:continue
            joint=case_metrics[case_metrics.method.eq(candidate)].merge(base,on=keys,suffixes=('','_base'))
            for r in joint.itertuples():
                full=bool(r.complete and r.complete_base)
                rows.append(dict(case=r.case,job=r.job,cohort=r.cohort,control=r.control,map=r.map,family=r.family,method=candidate,baseline=baseline,
                    paired=full,episode_speedup=r.episode_s_base/r.episode_s if full and r.episode_s>0 else math.nan,
                    online_speedup=r.online_s_base/r.online_s if full and r.online_s_base>0 and r.online_s>0 else math.nan,
                    memory_ratio=r.peak_heap_bytes_base/r.peak_heap_bytes if full and r.peak_heap_bytes>0 else math.nan,
                    checked_ratio=r.checked_cells_base/r.checked_cells if full and r.checked_cells>0 else math.nan,
                    notify_ratio=r.notify_probes_base/r.notify_probes if full and r.notify_probes>0 else math.nan,
                    travel_ratio=r.travel_cost_base/r.travel_cost if full and r.travel_cost>0 and r.travel_cost_base>0 else math.nan,
                    plans_ratio=r.plans_base/r.plans if full and r.plans>0 else math.nan,
                    candidate_complete=bool(r.complete),baseline_complete=bool(r.complete_base),
                    selected_control=getattr(r,'selected_control','')))
    return pd.DataFrame(rows)

def summarize(pair_data,groupby,bootstrap=False):
    records=[]
    for key,d in pair_data.groupby(groupby,dropna=False,sort=False):
        if not isinstance(key,tuple):key=(key,)
        row=dict(zip(groupby,key));row.update(configurations=len(d),candidate_complete=int(d.candidate_complete.sum()),
                                            baseline_complete=int(d.baseline_complete.sum()),paired=int(d.paired.sum()))
        for field in ['episode_speedup','online_speedup','memory_ratio','checked_ratio','notify_ratio','travel_ratio','plans_ratio']:
            valid=d[np.isfinite(d[field])&d[field].gt(0)];row[field]=gm(valid[field]);row[field+'_pairs']=len(valid)
            if field in ['episode_speedup','online_speedup']:
                row[field+'_median']=float(valid[field].median()) if len(valid) else math.nan
                row[field+'_wins10pct']=int(valid[field].ge(1.1).sum())
                if bootstrap:row[field+'_lo'],row[field+'_hi']=map_bootstrap(valid,field)
        records.append(row)
    return pd.DataFrame(records)

def figures(ad,metrics,pair_data,summary,map_pairs,latency,received):
    dest=DEST/'figures';dest.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.spines.top':False,'axes.spines.right':False,
                         'pdf.fonttype':42,'savefig.bbox':'tight'})
    outputs=[]
    def save(name,fig):
        for ext in ['pdf','png']:
            path=dest/(name+'.'+ext);fig.savefig(path,dpi=160,**({'metadata':{'CreationDate':None,'ModDate':None}} if ext=='pdf' else {}));outputs.append(str(path.relative_to(ROOT)))
        plt.close(fig)
    groups=list(metrics[['cohort','control']].drop_duplicates().itertuples(index=False,name=None))
    labels=[a.replace('navigation_','nav / ')+' / '+b for a,b in groups]
    fig,axes=plt.subplots(1,2,figsize=(11,4.5),sharey=True)
    for ax,base in zip(axes,['mpgaa','best_control']):
        for k,candidate in enumerate(NEW):
            values=[]
            for a,b in groups:
                s=summary[summary.cohort.eq(a)&summary.control.eq(b)&summary.method.eq(candidate)&summary.baseline.eq(base)]
                values.append(s.episode_speedup.iloc[0] if len(s) else math.nan)
            ax.plot(values,np.arange(len(groups))+(k-1.5)*.13,'o',color=COLORS[k],label=LABELS[candidate].split('-Mesh')[0])
        ax.axvline(1,color='gray',lw=.9);ax.set_xscale('log');ax.set_title('Baseline: '+('MPGAA*' if base=='mpgaa' else 'fastest completed control'))
        ax.set_xlabel('Full-episode speedup (>1 favors candidate)');ax.grid(axis='x',alpha=.2)
    axes[0].set_yticks(range(len(groups)),labels);axes[0].invert_yaxis();axes[1].legend(fontsize=7,loc='lower right');fig.tight_layout();save('episode_speedup',fig)
    car=pair_data[pair_data.cohort.eq('replay')&pair_data.control.eq('car16')&pair_data.baseline.eq('mpgaa')]
    families=sorted(car.family.unique());fig,ax=plt.subplots(figsize=(8,3.5))
    for k,c in enumerate(NEW):
        x=[gm(car[car.family.eq(f)&car.method.eq(c)].episode_speedup) for f in families]
        ax.plot(x,np.arange(len(families))+(k-1.5)*.14,'o',color=COLORS[k],label=LABELS[c].split('-Mesh')[0])
    ax.set_yticks(range(len(families)),families);ax.axvline(1,color='gray');ax.set_xscale('log');ax.set_xlabel('Full-episode speedup vs MPGAA*; completed pairs');ax.legend(fontsize=7);fig.tight_layout();save('replay_families',fig)
    nav=map_pairs[map_pairs.cohort.eq('navigation_dynamic')&map_pairs.baseline.eq('best_control')]
    pivot=nav[nav.method.isin(NEW)].pivot(index=['control','map'],columns='method',values='episode_speedup').reindex(columns=NEW)
    fig,ax=plt.subplots(figsize=(8,6.5));values=pivot.to_numpy();valid=np.isfinite(values)&(values>0)
    show=np.full(values.shape,np.nan);show[valid]=np.log2(values[valid]);im=ax.imshow(show,aspect='auto',cmap='RdBu',vmin=-2,vmax=2)
    for i in range(len(pivot)):
        for j in range(4):ax.text(j,i,f'{values[i,j]:.2f}' if valid[i,j] else '—',ha='center',va='center',fontsize=8)
    ax.set_xticks(range(4),['Boundary','Selective','Delta','Policy']);ax.set_yticks(range(len(pivot)),[' / '.join(v) for v in pivot.index]);fig.colorbar(im,ax=ax,label='log2(full-episode speedup vs fastest control)');fig.tight_layout();save('navigation_maps',fig)
    fig,axes=plt.subplots(2,2,figsize=(9,6.2))
    for ax,candidate,color in zip(axes.flat,NEW,COLORS):
        d=pair_data[pair_data.baseline.eq('mpgaa')&pair_data.method.eq(candidate)]
        for control,marker in [('car16','o'),('grid8','x')]:
            v=d[d.control.eq(control)];ax.scatter(v.episode_speedup,v.online_speedup,s=11,alpha=.5,c=color,marker=marker,label=control)
        ax.set_xscale('log');ax.set_yscale('log');ax.axhline(1,color='gray',lw=.7);ax.axvline(1,color='gray',lw=.7)
        ax.set_title(LABELS[candidate],fontsize=9);ax.set_xlabel('Full episode / MPGAA*');ax.set_ylabel('Online / MPGAA*');ax.legend(fontsize=7)
    fig.tight_layout();save('online_vs_episode',fig)
    mem=summary[summary.baseline.eq('mpgaa')&summary.method.isin(NEW)].copy()
    fig,ax=plt.subplots(figsize=(9,4))
    for k,c in enumerate(NEW):
        vals=[]
        for a,b in groups:
            d=mem[mem.cohort.eq(a)&mem.control.eq(b)&mem.method.eq(c)];vals.append(d.memory_ratio.iloc[0] if len(d) else math.nan)
        ax.plot(np.arange(len(groups))+(k-1.5)*.13,vals,'o',color=COLORS[k],label=LABELS[c].split('-Mesh')[0])
    ax.set_xticks(range(len(groups)),labels,rotation=30,ha='right');ax.axhline(1,color='gray');ax.set_yscale('log');ax.set_ylabel('MPGAA* peak heap / candidate peak heap');ax.legend(fontsize=7);fig.tight_layout();save('memory',fig)
    ab=pair_data[pair_data.cohort.eq('replay')&pair_data.method.eq('selective_mpgaa')&pair_data.baseline.isin(['boundary_mpgaa','selective_no_prune','selective_geom'])]
    fig,axes=plt.subplots(1,2,figsize=(9,3.5),sharey=True)
    bases=['boundary_mpgaa','selective_no_prune','selective_geom']
    for ax,control in zip(axes,['car16','grid8']):
        data=[ab[ab.control.eq(control)&ab.baseline.eq(b)].episode_speedup.dropna().to_numpy() for b in bases]
        ax.boxplot(data,tick_labels=['Boundary','No pruning','Geometric'],showfliers=False);ax.axhline(1,color='gray');ax.set_yscale('log');ax.set_title(control);ax.set_ylabel('Selective full-episode speedup')
    fig.tight_layout();save('selective_ablation',fig)
    mission=metrics[metrics.cohort.ne('replay')].groupby(['control','map','method']).complete.mean().reset_index()
    comp=mission[mission.method.isin(['mpgaa','lba_reuse']+NEW)].pivot(index=['control','map'],columns='method',values='complete').reindex(columns=['mpgaa','lba_reuse']+NEW)
    fig,ax=plt.subplots(figsize=(9,6.5));im=ax.imshow(comp.to_numpy(),aspect='auto',cmap='Blues',vmin=0,vmax=1)
    for i in range(len(comp)):
        for j in range(len(comp.columns)):
            value=comp.iloc[i,j];ax.text(j,i,f'{value:.0%}' if pd.notna(value) else '—',ha='center',va='center',fontsize=8)
    ax.set_xticks(range(6),['MPGAA*','LBA* reuse','Boundary','Selective','Delta','Policy']);ax.set_yticks(range(len(comp)),[' / '.join(v) for v in comp.index]);fig.colorbar(im,ax=ax,label='Goal fraction (configured scenarios)');fig.tight_layout();save('completion',fig)
    # case_metrics already contains one row per case/method, with deterministic
    # work counters aggregated across repeats; it has no repeat column.
    first=metrics[metrics.cohort.eq('replay')]
    fig,axes=plt.subplots(1,2,figsize=(9,3.5))
    for ax,field,title in zip(axes,['checked_cells','notify_probes'],['Collision-cell probes','Instrumented notifications']):
        for k,control in enumerate(['car16','grid8']):
            sums=first[first.control.eq(control)].groupby('method')[field].sum();base=sums.get('mpgaa',math.nan)
            vals=[sums.get(c,math.nan)/base if base else math.nan for c in NEW]
            ax.plot(range(4),vals,'o-',label=control)
        ax.axhline(1,color='gray');ax.set_yscale('log');ax.set_xticks(range(4),['Boundary','Selective','Delta','Policy']);ax.set_title(title);ax.set_ylabel('Candidate / MPGAA* (sum of replay work)');ax.legend(fontsize=8)
    fig.tight_layout();save('mechanisms',fig)
    fig,axes=plt.subplots(1,2,figsize=(10,4))
    bins=['0','1','2–4','5–16','17–64','65–256','257–1024','>1024']
    shown=['mpgaa','lba_reuse']+NEW
    for ax,control,mp in zip(axes,['car16','grid8'],['Berlin','MA_maze512']):
        d=received[received.cohort.eq('navigation_dynamic')&received.control.eq(control)&received['map'].eq(mp)]
        for method in shown:
            v=d[d.method.eq(method)].set_index('received_bin').reindex(bins)
            ax.plot(range(len(bins)),1000*v.median_s,'o-',ms=3,label=LABELS[method].replace('-Mesh',''))
        ax.set_xticks(range(len(bins)),bins,rotation=35,ha='right');ax.set_yscale('log');ax.set_title(control+' / '+mp)
        ax.set_xlabel('Received blocks + opens');ax.set_ylabel('Median online latency, ms');ax.grid(axis='y',alpha=.2)
    axes[1].legend(fontsize=6.5);fig.tight_layout();save('received_changes',fig)
    (ad/'figures.json').write_text(json.dumps({path:digest(ROOT/path) for path in outputs},indent=2)+'\n')

def main(directory):
    directory=directory.resolve();manifest_path=HERE/'frozen/manifest.json';manifest=json.loads(manifest_path.read_text())
    experiment=json.loads((directory/'experiment.json').read_text());assert experiment['status']=='passed'
    assert experiment['manifest_sha256']==digest(manifest_path)
    revision=manifest.get('allocation_revision')
    if revision:
        retired=HERE/'results/pre_instrument_argument_fix'
        assert digest(retired/'manifest.json')==revision['archived_manifest_sha256']
        assert digest(retired/'experiment.json')==revision['archived_experiment_sha256']
        assert digest(retired/'replay.cpp')==revision['archived_source_sha256']
        assert digest(HERE/'resume_allocation.py')==revision['recovery_source_sha256']
        original=json.loads((retired/'experiment.json').read_text())
        assert experiment['imported_timing']['normal_binary_identity']=='passed'
        assert {name:original['binaries'][name] for name in ['replay','navigation']}==revision['unchanged_timing_binaries']
        assert {name:experiment['binaries'][name] for name in ['replay','navigation']}==revision['unchanged_timing_binaries']
        for name in experiment['imported_timing']['jobs']:
            assert original['jobs'][name]['outputs']==experiment['jobs'][name]['outputs']
    for path,sha in {**manifest['files'],**manifest['sources']}.items():assert digest(ROOT/path)==sha,path
    for job in experiment['jobs'].values():
        assert job['status']=='passed'
        for path,sha in job['outputs'].items():assert digest(directory/path)==sha,path
    contexts=json.loads((HERE/'frozen/contexts.json').read_text());all_calls=[];all_episodes=[];all_memory=[];matched=0
    for job in manifest['plan']:
        nav=job['mode']=='navigation';suffix='_calls.csv' if nav else '.csv'
        timing=read(directory/('timing_'+job['name']+suffix));memory=read(directory/('memory_'+job['name']+suffix))
        matched+=check_profile(timing,memory)
        for frame in [timing,memory]:
            assert len(frame.groupby(['case','method','repeat']))==job['cases']*len(job['methods'])*(3 if frame is timing else 1)
            p=frame[frame.planned.eq(1)&~frame.status.eq('capped')]
            assert (p.cost.notna()==p.expected.notna()).all(),job['name']
            assert ((p.cost-p.expected).abs().dropna()<=1e-6).all(),job['name']
        native_timing=read(directory/('timing_'+job['name']+'_runs.csv')) if nav else None
        native_memory=read(directory/('memory_'+job['name']+'_runs.csv')) if nav else None
        if nav:
            ta=native_timing[native_timing.repeat.eq(0)].set_index(['case','method']).sort_index()
            ma=native_memory.set_index(['case','method']).sort_index()
            assert_frame_equal(ta[['fingerprint']],ma[['fingerprint']],check_dtype=False,check_exact=True)
        timing=decorate(timing,job,contexts);memory=decorate(memory,job,contexts)
        all_calls.append(timing);all_episodes.append(episodes(timing,job,native_timing));all_memory.append(episodes(memory,job,native_memory))
    calls=pd.concat(all_calls,ignore_index=True);ep=pd.concat(all_episodes,ignore_index=True);mem=pd.concat(all_memory,ignore_index=True)
    assert len(ep)==manifest['timed_runs'] and len(mem)==manifest['memory_runs']
    # Boundary changes collision evaluation, not the MPGAA* search order.
    replay_first=calls[calls.cohort.eq('replay')&calls.repeat.eq(0)]
    parity_fields=['status','planned','cost','expansions','heuristic_pops','path_hash']
    base=replay_first[replay_first.method.eq('mpgaa')].set_index(['case','query']).sort_index()
    boundary=replay_first[replay_first.method.eq('boundary_mpgaa')].set_index(['case','query']).sort_index()
    assert_frame_equal(base[parity_fields],boundary[parity_fields],check_dtype=False,check_exact=True)
    ad=directory/'analysis';ad.mkdir(exist_ok=True);ep.to_csv(ad/'episode_metrics.csv',index=False);mem.to_csv(ad/'memory_metrics.csv',index=False)
    variation=ep.groupby(['case','job','cohort','control','map','method']).episode_s.agg(
        median_s='median',relative_mad=lambda x:float(np.median(np.abs(x-np.median(x)))/np.median(x)) if np.median(x)>0 else math.nan).reset_index()
    variation.to_csv(ad/'repeat_variation.csv',index=False)
    keys=['case','job','cohort','control','map','family','method']
    numeric=['episode_s','online_s','initial_s','setup_s','plans','online_plans','travel_cost']+COUNTERS
    metrics=ep.groupby(keys,as_index=False).agg(**{k:(k,'median') for k in numeric},complete=('complete','all'),repeats=('repeat','size'))
    metrics=metrics.merge(mem[keys+['peak_heap_bytes','retained_heap_bytes']],on=keys,validate='one_to_one')
    assert metrics.repeats.eq(3).all();metrics.to_csv(ad/'case_metrics.csv',index=False)
    control_success=metrics[metrics.method.isin(CONTROL)].groupby(['case','job']).complete.any().rename('any_control_complete')
    exclusive=metrics[metrics.method.isin(NEW)].merge(control_success,on=['case','job'],validate='many_to_one')
    exclusive['candidate_only']=exclusive.complete&~exclusive.any_control_complete
    exclusive['control_only']=~exclusive.complete&exclusive.any_control_complete
    exclusive.to_csv(ad/'completion_vs_controls.csv',index=False)
    pair_data=pairs(metrics);pair_data.to_csv(ad/'paired_cases.csv',index=False)
    summary=summarize(pair_data,['cohort','control','method','baseline'],bootstrap=True);summary.to_csv(ad/'summary.csv',index=False)
    map_pairs=summarize(pair_data,['cohort','control','map','method','baseline']);map_pairs.to_csv(ad/'map_pairs.csv',index=False)
    families=summarize(pair_data,['cohort','control','family','method','baseline']);families.to_csv(ad/'family_pairs.csv',index=False)
    completion=metrics.groupby(['cohort','control','map','method'],as_index=False).agg(cases=('case','size'),completed=('complete','sum'))
    completion['completion_fraction']=completion.completed/completion.cases;completion.to_csv(ad/'completion.csv',index=False)
    completed_calls=calls[calls.planned.eq(1)&calls.online&~calls.status.eq('capped')]
    latency=completed_calls.groupby(['cohort','control','map','method']).time_s.agg(count='size',p50='median',p95=lambda x:x.quantile(.95),p99=lambda x:x.quantile(.99)).reset_index()
    latency.to_csv(ad/'latency.csv',index=False)
    received=calls[calls.repeat.eq(0)&calls.planned.eq(1)&calls.online].copy()
    received['received_bin']=pd.cut(received.blocks+received.opens,bins=[-1,0,1,4,16,64,256,1024,np.inf],
                                    labels=['0','1','2–4','5–16','17–64','65–256','257–1024','>1024'])
    received=received.groupby(['cohort','control','map','method','received_bin'],observed=True).agg(
        calls=('time_s','size'),median_s=('time_s','median'),p95_s=('time_s',lambda x:x.quantile(.95)),
        capped=('status',lambda x:int(x.eq('capped').sum())),median_notify=('notify_probes','median'),
        median_flips=('validity_flips','median'),median_checks=('checked_cells','median'),median_expansions=('expansions','median')).reset_index()
    received.to_csv(ad/'received_changes.csv',index=False)
    work=calls[calls.repeat.eq(0)&calls.planned.eq(1)].groupby(['cohort','control','method'],as_index=False)[COUNTERS].sum();work.to_csv(ad/'work.csv',index=False)
    status=ep.groupby(['cohort','control','method','status']).size().rename('runs').reset_index();status.to_csv(ad/'statuses.csv',index=False)
    models=[]
    for job in manifest['plan']:
        t=experiment['jobs']['timing_'+job['name']]['completion'];m=experiment['jobs']['memory_'+job['name']]['completion']
        models.append(dict(job=job['name'],control=Path(job['input']).name.split('_',1)[0],mesh_index_nodes=t['mesh_index_nodes'],
                           mesh_compile_s=t['mesh_index_compile_s'],shared_preparation_s=t['preparation_s'],
                           index_heap_peak_bytes=m['mesh_index_heap_peak_bytes'],index_heap_retained_bytes=m['mesh_index_heap_retained_bytes']))
    pd.DataFrame(models).to_csv(ad/'model_costs.csv',index=False)
    replay=calls[calls.cohort.eq('replay')&calls.repeat.eq(0)&calls.online&calls.planned.eq(1)]
    policy=replay[replay.method.eq('policy_mpgaa')].merge(replay[replay.method.eq('boundary_mpgaa')],on=['case','query'],suffixes=('','_boundary'))
    policy_extra=policy[policy.expansions.eq(0)&policy.expansions_boundary.gt(0)&policy.cost.notna()]
    policy_extra[['case','query','control','map','expansions_boundary','alternate_uses']].to_csv(ad/'policy_extra_certificates.csv',index=False)
    nav=pair_data[pair_data.cohort.eq('navigation_dynamic')&pair_data.baseline.eq('best_control')&pair_data.method.isin(NEW)].copy()
    for field in ['k','cr','seed']:nav[field]=nav['case'].map(lambda x:contexts[x].get('params',{}).get(field,contexts[x].get(field)))
    points=nav.groupby(['control','map','k','cr','method'],as_index=False).agg(roots=('case','size'),paired=('paired','sum'),paired_online=('online_speedup','count'),
                    min_episode_speedup=('episode_speedup','min'),min_online_speedup=('online_speedup','min'))
    points.to_csv(ad/'navigation_points.csv',index=False)
    figures(ad,metrics,pair_data,summary,map_pairs,latency,received)
    planned=calls[calls.planned.eq(1)]
    verification=directory.parent/'verification'
    test_records=[json.loads(line) for line in (verification/'tests.log').read_text().splitlines() if line.startswith('{')]
    sanitized=[json.loads(line) for line in (verification/'sanitize.log').read_text().splitlines() if line.startswith('{')]
    assert len(test_records)==2 and len(sanitized)==2 and test_records==sanitized
    assert all(r['status']=='passed' for r in test_records)
    findings=dict(status='passed',timed_runs=len(ep),memory_runs=len(mem),scenarios=metrics['case'].nunique(),
                  timed_planner_calls=len(planned),exact_completed_calls=int((~planned.status.eq('capped')).sum()),
                  capped_calls=int(planned.status.eq('capped').sum()),exact_cost_disagreements=0,memory_matched_rows=matched,
                  boundary_search_parity_rows=len(base),
                  median_relative_mad=float(variation.relative_mad.median()),p95_relative_mad=float(variation.relative_mad.quantile(.95)),
                  software=dict(numpy=np.__version__,pandas=pd.__version__,matplotlib=matplotlib.__version__),
                  independent_dijkstra_comparisons=sum(r['comparisons'] for r in test_records),asan_ubsan='passed',policy_extra_zero_expansion_replay_calls=len(policy_extra),
                  verification_sha256={p.name:digest(p) for p in verification.glob('*.log')},
                  primary_methods=NEW,manifest_sha256=digest(manifest_path),experiment_sha256=digest(directory/'experiment.json'),
                  source_sha256=manifest['sources'],tables_sha256={p.name:digest(p) for p in ad.glob('*.csv')})
    findings['analysis_source_sha256']=digest(Path(__file__))
    findings['allocation_revision']=revision
    (ad/'analysis.json').write_text(json.dumps(findings,indent=2,ensure_ascii=False)+'\n');print(json.dumps(findings,ensure_ascii=False,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,default=HERE/'results/full');main(p.parse_args().directory)
