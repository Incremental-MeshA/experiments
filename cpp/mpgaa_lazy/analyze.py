#!/usr/bin/env python3
"""Validate new matched runs and derive tables and scientific figures."""
import argparse
import importlib.util
import json
import math
import os
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR','/tmp/mpgaa-lazy-mpl')
os.environ.setdefault('XDG_CACHE_HOME','/tmp/mpgaa-lazy-cache')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter,LogLocator,NullFormatter
import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal
from run_all import digest
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
DEST=ROOT/'docs/mpgaa_lazy'
spec=importlib.util.spec_from_file_location('previous_analysis',ROOT/'cpp/mpgaa_mesh/analyze.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
NEW=['stamp_mpgaa','batch_mpgaa','witness_mpgaa']
CONTROL=['mpgaa','lba_reuse','md_astar','boundary_mpgaa','selective_mpgaa','delta_mpgaa','policy_mpgaa','octile_reuse']
ABLATIONS=['stamp_cell','batch_scan']
LABELS={**old.LABELS,'stamp_mpgaa':'Stamp-Mesh-MPGAA*','batch_mpgaa':'Batch-Mesh-MPGAA*','witness_mpgaa':'Witness-Mesh-MPGAA*',
        'stamp_cell':'Stamp / cell epochs','batch_scan':'Batch / forced scan','best_control':'fastest previous method'}
SHORT={**{k:v.replace('-Mesh','').replace('-MPGAA*','') for k,v in LABELS.items()},
       'stamp_mpgaa':'Stamp','batch_mpgaa':'Batch','witness_mpgaa':'Witness','boundary_mpgaa':'Boundary','mpgaa':'MPGAA*',
       'stamp_cell':'Stamp, tile=1','batch_scan':'Batch, always scan'}
EXTRA=['stamp_writes','tile_reads','mask_refreshes','mask_hits','cut_checks','cut_reuses','cut_primitives','edit_batches','scan_batches','seed_tests','arrow_checks']
WORK=old.WORK+EXTRA
COUNTERS=[c for c in old.COUNTERS if c not in old.WORK]+WORK
old.COUNTERS=COUNTERS
read,check_profile,decorate,episodes,gm,summarize=(getattr(old,n) for n in ['read','check_profile','decorate','episodes','gm','summarize'])
COLORS=['#167ba1','#c67220','#368351']

def pairs(metrics):
    rows=[];keys=['case','job','cohort','control','map','family']
    for baseline in CONTROL+['stamp_mpgaa','batch_mpgaa','stamp_cell','batch_scan','best_control']:
        base=metrics[metrics.method.eq(baseline)].copy()
        if baseline=='best_control':
            base=metrics[metrics.method.isin(CONTROL)&metrics.complete].sort_values(['episode_s','method']).drop_duplicates(['case','job']).copy()
            base['selected_control']=base.method;base['method']='best_control'
        for candidate in NEW+ABLATIONS:
            if candidate==baseline:continue
            joint=metrics[metrics.method.eq(candidate)].merge(base,on=keys,suffixes=('','_base'),validate='one_to_one')
            for r in joint.itertuples():
                complete=bool(r.complete and r.complete_base)
                row=dict(case=r.case,job=r.job,cohort=r.cohort,control=r.control,map=r.map,family=r.family,method=candidate,baseline=baseline,
                    paired=complete,candidate_complete=bool(r.complete),baseline_complete=bool(r.complete_base),
                    selected_control=getattr(r,'selected_control',''))
                for field,source in [('episode_speedup','episode_s'),('online_speedup','online_s'),('memory_ratio','peak_heap_bytes'),
                                     ('checked_ratio','checked_cells'),('notify_ratio','notify_probes'),('travel_ratio','travel_cost'),('plans_ratio','plans')]:
                    own=getattr(r,source);reference=getattr(r,source+'_base')
                    row[field]=reference/own if complete and own>0 and reference>0 else math.nan
                rows.append(row)
    return pd.DataFrame(rows)

def plots(metrics,pair_data,summary,maps,latency,received,work,ad):
    dest=DEST/'figures';dest.mkdir(parents=True,exist_ok=True);outputs=[]
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42,'savefig.bbox':'tight'})
    def save(name,fig):
        for ext in ['png','pdf']:
            path=dest/(name+'.'+ext)
            fig.savefig(path,dpi=165,**({'metadata':{'CreationDate':None,'ModDate':None}} if ext=='pdf' else {}));outputs.append(str(path.relative_to(ROOT)))
        plt.close(fig)
    groups=list(metrics[['cohort','control']].drop_duplicates().itertuples(index=False,name=None))
    fig,axes=plt.subplots(1,2,figsize=(8.4,4.3),sharey=True)
    for ax,baseline in zip(axes,['boundary_mpgaa','best_control']):
        for j,c in enumerate(NEW):
            values=[]
            for cohort,control in groups:
                d=summary[summary.cohort.eq(cohort)&summary.control.eq(control)&summary.method.eq(c)&summary.baseline.eq(baseline)]
                values.append(d.episode_speedup.iloc[0] if len(d) else math.nan)
            ax.plot(values,np.arange(len(groups))+(j-1)*.14,'o',color=COLORS[j],label=SHORT[c])
        ax.set_xscale('log');ax.axvline(1,color='gray',lw=.8);ax.grid(axis='x',alpha=.25)
        ax.xaxis.set_major_locator(LogLocator(base=10,subs=[1,2,5]));ax.xaxis.set_major_formatter(FuncFormatter(lambda x,_:f'{x:g}'));ax.xaxis.set_minor_formatter(NullFormatter())
        ax.set_title('Baseline: '+('Boundary' if baseline=='boundary_mpgaa' else 'fastest previous method'))
        ax.set_xlabel('Full-episode speedup (baseline / candidate)')
    axes[0].set_yticks(range(len(groups)),[a.replace('navigation_','nav ')+' / '+b for a,b in groups]);axes[0].invert_yaxis();axes[1].legend(loc='best');fig.tight_layout();save('episode_speedup',fig)
    fig,axes=plt.subplots(1,3,figsize=(10,4.9))
    for ax,cohort,control in zip(axes,['replay','navigation_dynamic','navigation_dynamic'],['car16','car16','grid8']):
        d=maps[maps.cohort.eq(cohort)&maps.control.eq(control)&maps.baseline.eq('best_control')&maps.method.isin(NEW)]
        mat=d.pivot(index='map',columns='method',values='episode_speedup').reindex(columns=NEW)
        values=np.log2(mat.to_numpy(dtype=float));im=ax.imshow(values,aspect='auto',cmap='RdBu',vmin=-2.5,vmax=2.5)
        ax.set_xticks(range(3),[SHORT[c] for c in NEW],rotation=35,ha='right');ax.set_yticks(range(len(mat)),mat.index);ax.set_title(cohort.replace('navigation_','nav ')+' / '+control)
        for (i,j),v in np.ndenumerate(mat.to_numpy(dtype=float)):
            if np.isfinite(v):ax.text(j,i,f'{v:.2f}',ha='center',va='center',fontsize=8,color='white' if abs(math.log2(v))>1.4 else 'black')
    fig.colorbar(im,ax=axes.ravel().tolist(),fraction=.025,pad=.025,label='log2 speedup versus fastest previous method');fig.subplots_adjust(left=.11,right=.91,bottom=.15,top=.9,wspace=.8);save('map_speedup',fig)
    r=pair_data[pair_data.cohort.eq('navigation_unknown')&pair_data.baseline.eq('boundary_mpgaa')&pair_data.method.isin(NEW)].copy()
    if len(r):
        r['radius']=r['case'].map(lambda x:CONTEXTS[x]['params']['radius'])
        fig,axes=plt.subplots(2,3,figsize=(9,5.3),sharex=True,sharey=True)
        for ax,mp in zip(axes.flat,sorted(r['map'].unique())):
            for j,c in enumerate(NEW):
                d=r[r['map'].eq(mp)&r.method.eq(c)].groupby('radius').episode_speedup.agg(gm)
                ax.plot(d.index,d.values,'o-',ms=4,color=COLORS[j],label=SHORT[c])
            ax.axhline(1,color='gray',lw=.8);ax.set_title(mp);ax.set_xscale('log',base=2);ax.set_xticks([8,16,32,64],['8','16','32','64']);ax.grid(alpha=.2)
        for ax in axes[:,0]:ax.set_ylabel('Full speedup versus Boundary')
        for ax in axes[-1]:ax.set_xlabel('Observation radius, cells')
        axes[0,0].legend(fontsize=8);fig.tight_layout();save('unknown_radius',fig)
    fig,axes=plt.subplots(1,2,figsize=(8.4,3.7))
    for ax,control in zip(axes,['car16','grid8']):
        d=received[received.cohort.eq('replay')&received.control.eq(control)]
        bins=['0','1','2–4','5–16','17–64','65–256','257–1024','>1024']
        for c in ['boundary_mpgaa',*NEW]:
            v=d[d.method.eq(c)].set_index('received_bin').reindex(bins)
            ax.plot(range(len(bins)),v.median_s*1000,'o-',ms=3,label=SHORT[c])
        ax.set_xticks(range(len(bins)),bins,rotation=35,ha='right');ax.set_yscale('log');ax.grid(axis='y',alpha=.2);ax.set_title(control)
        ax.set_xlabel('Received blocks + opens');ax.set_ylabel('Median online call, ms')
    axes[0].legend(fontsize=8);fig.tight_layout();save('change_count_latency',fig)
    fig,axes=plt.subplots(1,2,figsize=(8.4,3.6))
    for ax,control in zip(axes,['car16','grid8']):
        for c in NEW:
            d=pair_data[pair_data.control.eq(control)&pair_data.method.eq(c)&pair_data.baseline.eq('best_control')]
            x=np.sort(d.episode_speedup.dropna().to_numpy());ax.step(x,np.arange(1,len(x)+1)/len(x),where='post',label=SHORT[c])
        ax.set_xscale('log');ax.axvline(1,color='gray',lw=.8);ax.set_title(control);ax.set_ylim(0,1.02);ax.grid(alpha=.2)
        ax.set_xlabel('Full speedup versus fastest previous method');ax.set_ylabel('Fraction of paired configurations')
    axes[0].legend(fontsize=8);fig.tight_layout();save('paired_distribution',fig)
    fig,axes=plt.subplots(1,2,figsize=(8.4,3.8))
    for ax,metric,label in zip(axes,['memory_ratio','online_speedup'],['Peak heap reduction','Online speedup']):
        for j,c in enumerate(NEW):
            values=[]
            for cohort,control in groups:
                d=summary[summary.cohort.eq(cohort)&summary.control.eq(control)&summary.method.eq(c)&summary.baseline.eq('boundary_mpgaa')]
                values.append(d[metric].iloc[0] if len(d) else math.nan)
            ax.plot(range(len(groups)),values,'o-',ms=4,color=COLORS[j],label=SHORT[c])
        ax.axhline(1,color='gray',lw=.8);ax.set_yscale('log');ax.set_xticks(range(len(groups)),[a.replace('navigation_','nav ')+'\n'+b for a,b in groups],rotation=20,ha='right')
        ax.set_ylabel(label+' (Boundary / candidate)');ax.grid(axis='y',alpha=.2)
    axes[1].legend(fontsize=8);fig.tight_layout();save('memory_online',fig)
    fig,axes=plt.subplots(1,2,figsize=(8.4,3.5))
    for ax,control in zip(axes,['car16','grid8']):
        d=work[work.control.eq(control)&work.method.isin(NEW)].groupby('method')[['edit_batches','scan_batches']].sum().reindex(NEW)
        total=d.sum(axis=1);scan=d.scan_batches/total.replace(0,np.nan)
        ax.bar(range(3),scan,color=COLORS);ax.set_xticks(range(3),[SHORT[c] for c in NEW]);ax.set_ylim(0,1);ax.set_title(control)
        ax.set_ylabel('Fraction of opening batches using state scan')
        for i,n in enumerate(total):ax.text(i,min(.98,scan.iloc[i]+.03),str(int(n))+' batches',ha='center',fontsize=8)
    fig.tight_layout();save('batch_choice',fig)
    fig,ax=plt.subplots(figsize=(7.2,3.6));labels=[];values=[]
    for control in ['car16','grid8']:
        for candidate,baseline,label in [('stamp_mpgaa','stamp_cell','tile 8 / cell epochs'),('batch_mpgaa','stamp_mpgaa','adaptive / edit join'),
                ('batch_mpgaa','batch_scan','adaptive / forced scan'),('witness_mpgaa','batch_mpgaa','witness cut / no cut')]:
            d=pair_data[pair_data.cohort.eq('replay')&pair_data.control.eq(control)&pair_data.method.eq(candidate)&pair_data.baseline.eq(baseline)]
            labels.append(control+' / '+label);values.append(gm(d.episode_speedup))
    ax.barh(range(len(values)),values,color=['#167ba1']*4+['#c67220']*4);ax.set_yticks(range(len(values)),labels);ax.invert_yaxis();ax.axvline(1,color='black',lw=.8)
    ax.set_xlabel('Full-episode speedup (comparison / candidate)');ax.grid(axis='x',alpha=.2);fig.tight_layout();save('ablations',fig)
    (ad/'figures.json').write_text(json.dumps({p:digest(ROOT/p) for p in outputs},indent=2,sort_keys=True)+'\n')

CONTEXTS={}
def main(directory):
    global CONTEXTS
    directory=directory.resolve();manifest_path=HERE/'frozen/manifest.json';manifest=json.loads(manifest_path.read_text())
    experiment=json.loads((directory/'experiment.json').read_text());assert experiment['status']=='passed'
    assert experiment['manifest_sha256']==digest(manifest_path)
    for path,sha in {**manifest['files'],**manifest['sources']}.items():assert digest(ROOT/path)==sha,path
    for job in experiment['jobs'].values():
        assert job['status']=='passed'
        for path,sha in job['outputs'].items():assert digest(directory/path)==sha,path
    contexts=json.loads((HERE/'frozen/contexts.json').read_text());CONTEXTS=contexts
    all_calls=[];all_ep=[];all_mem=[];matched=0
    for job in manifest['plan']:
        nav=job['mode']=='navigation';suffix='_calls.csv' if nav else '.csv'
        timing=read(directory/('timing_'+job['name']+suffix));memory=read(directory/('memory_'+job['name']+suffix))
        for rep in [1,2]:check_profile(timing,timing[timing.repeat.eq(rep)])
        matched+=check_profile(timing,memory)
        assert memory.peak_heap_bytes.ge(memory.retained_heap_bytes).all() and memory.retained_heap_bytes.ge(0).all() and memory.peak_heap_bytes.lt(2**48).all()
        for frame in [timing,memory]:
            assert len(frame.groupby(['case','method','repeat']))==job['cases']*len(job['methods'])*(3 if frame is timing else 1)
            planned=frame[frame.planned.eq(1)&~frame.status.eq('capped')]
            assert (planned.cost.notna()==planned.expected.notna()).all()
            assert (planned.cost-planned.expected).abs().dropna().le(1e-6).all()
        native_timing=read(directory/('timing_'+job['name']+'_runs.csv')) if nav else None
        native_memory=read(directory/('memory_'+job['name']+'_runs.csv')) if nav else None
        if nav:
            a=native_timing[native_timing.repeat.eq(0)].set_index(['case','method']).sort_index();b=native_memory.set_index(['case','method']).sort_index()
            assert_frame_equal(a[['fingerprint']],b[['fingerprint']],check_dtype=False,check_exact=True)
        timing=decorate(timing,job,contexts);memory=decorate(memory,job,contexts)
        all_calls.append(timing);all_ep.append(episodes(timing,job,native_timing));all_mem.append(episodes(memory,job,native_memory))
    calls=pd.concat(all_calls,ignore_index=True);ep=pd.concat(all_ep,ignore_index=True);mem=pd.concat(all_mem,ignore_index=True)
    assert len(ep)==manifest['timed_runs'] and len(mem)==manifest['memory_runs']
    ad=directory/'analysis';ad.mkdir(exist_ok=True)
    ep.to_csv(ad/'episode_metrics.csv',index=False);mem.to_csv(ad/'memory_metrics.csv',index=False)
    variation=ep.groupby(['case','job','cohort','control','map','method']).episode_s.agg(median_s='median',
        relative_mad=lambda x:float(np.median(np.abs(x-np.median(x)))/np.median(x)) if np.median(x)>0 else math.nan).reset_index()
    variation.to_csv(ad/'repeat_variation.csv',index=False)
    keys=['case','job','cohort','control','map','family','method'];numeric=['episode_s','online_s','initial_s','setup_s','plans','online_plans','travel_cost']+COUNTERS
    metrics=ep.groupby(keys,as_index=False).agg(**{k:(k,'median') for k in numeric},complete=('complete','all'),repeats=('repeat','size'))
    metrics=metrics.merge(mem[keys+['peak_heap_bytes','retained_heap_bytes']],on=keys,validate='one_to_one')
    assert metrics.repeats.eq(3).all();metrics.to_csv(ad/'case_metrics.csv',index=False)
    pair_data=pairs(metrics);pair_data.to_csv(ad/'paired_cases.csv',index=False)
    strong=pair_data[pair_data.method.isin(NEW)&pair_data.baseline.eq('best_control')&pair_data.episode_speedup.ge(1.1)]
    strong.to_csv(ad/'strong_control_wins.csv',index=False)
    summary=summarize(pair_data,['cohort','control','method','baseline'],bootstrap=True);summary.to_csv(ad/'summary.csv',index=False)
    map_pairs=summarize(pair_data,['cohort','control','map','method','baseline']);map_pairs.to_csv(ad/'map_pairs.csv',index=False)
    summarize(pair_data,['cohort','control','family','method','baseline']).to_csv(ad/'family_pairs.csv',index=False)
    for cohort,params,filename in [('navigation_unknown',['radius'],'radius_pairs.csv'),('navigation_dynamic',['k','cr'],'dynamic_pairs.csv')]:
        d=pair_data[pair_data.cohort.eq(cohort)].copy()
        for field in params:d[field]=d['case'].map(lambda x:contexts[x]['params'][field])
        summarize(d,['control','map',*params,'method','baseline']).to_csv(ad/filename,index=False)
    completion=metrics.groupby(['cohort','control','map','method'],as_index=False).agg(cases=('case','size'),completed=('complete','sum'));completion.to_csv(ad/'completion.csv',index=False)
    calls[calls.planned.eq(1)].groupby(['cohort','control','method','status']).size().rename('calls').reset_index().to_csv(ad/'statuses.csv',index=False)
    online=calls[calls.planned.eq(1)&calls.online&~calls.status.eq('capped')]
    latency=online.groupby(['cohort','control','map','method']).time_s.agg(count='size',p50='median',p95=lambda x:x.quantile(.95),p99=lambda x:x.quantile(.99)).reset_index();latency.to_csv(ad/'latency.csv',index=False)
    online.groupby(['cohort','control','method']).time_s.agg(count='size',p50='median',p95=lambda x:x.quantile(.95),p99=lambda x:x.quantile(.99)).reset_index().to_csv(ad/'latency_summary.csv',index=False)
    received=calls[calls.repeat.eq(0)&calls.planned.eq(1)&calls.online].copy()
    received['received_bin']=pd.cut(received.blocks+received.opens,[-1,0,1,4,16,64,256,1024,np.inf],labels=['0','1','2–4','5–16','17–64','65–256','257–1024','>1024'])
    received=received.groupby(['cohort','control','method','received_bin'],observed=True).agg(calls=('time_s','size'),median_s=('time_s','median'),
        p95_s=('time_s',lambda x:x.quantile(.95)),capped=('status',lambda x:int(x.eq('capped').sum())),median_notify=('notify_probes','median'),median_checks=('checked_cells','median')).reset_index()
    received.to_csv(ad/'received_changes.csv',index=False)
    work=calls[calls.repeat.eq(0)&calls.planned.eq(1)].groupby(['cohort','control','method'],as_index=False)[COUNTERS].sum();work.to_csv(ad/'work.csv',index=False)
    # Repair work on strictly identical replay queries, broken down by edit kind.
    repair=calls[calls.repeat.eq(0)&calls.cohort.eq('replay')&calls.online&calls.planned.eq(1)].copy()
    repair['edit_kind']=np.select([repair.opens.eq(0)&repair.blocks.gt(0),repair.blocks.eq(0)&repair.opens.gt(0),repair.opens.gt(0)&repair.blocks.gt(0)],['blocks','opens','mixed'],default='none')
    repair.groupby(['control','family','method','edit_kind'],as_index=False)[['time_s','blocks','opens',*COUNTERS]].sum().to_csv(ad/'repair_work.csv',index=False)
    # Exact input equivalence and work comparison are kept separate from speed.
    a=repair[repair.method.eq('boundary_mpgaa')]
    same=[]
    for candidate in NEW:
        joint=repair[repair.method.eq(candidate)].merge(a,on=['case','query'],suffixes=('','_base'),validate='one_to_one')
        for control,d in joint.groupby('control'):
            same.append(dict(method=candidate,control=control,rows=len(d),same_cost=int(((d.cost-d.cost_base).abs().le(1e-6)|(d.cost.isna()&d.cost_base.isna())).sum()),
                same_expansions=int(d.expansions.eq(d.expansions_base).sum()),same_path_hash=int(d.path_hash.eq(d.path_hash_base).sum())))
    pd.DataFrame(same).to_csv(ad/'replay_work_parity.csv',index=False)
    # Both-root filter for dynamic points. This is descriptive, not a p-value.
    nav=pair_data[pair_data.cohort.eq('navigation_dynamic')&pair_data.baseline.eq('best_control')&pair_data.method.isin(NEW)].copy()
    for field in ['k','cr']:nav[field]=nav['case'].map(lambda x:contexts[x]['params'][field])
    points=nav.groupby(['control','map','k','cr','method'],as_index=False).agg(roots=('case','size'),paired=('paired','sum'),
        paired_online=('online_speedup','count'),min_episode_speedup=('episode_speedup','min'),min_online_speedup=('online_speedup','min'))
    points.to_csv(ad/'navigation_points.csv',index=False)
    nav_changes=[]
    for job in manifest['plan']:
        if job['mode']!='navigation':continue
        d=read(directory/('timing_'+job['name']+'_runs.csv'));d=d[d.repeat.eq(0)]
        for row in d.itertuples():
            c=contexts[row.case];cells=math.prod(c['shape'])
            nav_changes.append(dict(case=row.case,method=row.method,control=c['control'],map=c['map'],kind=row.kind,phases=row.phases,
                requested_cr=c['params'].get('cr',0),actual_cr=100*row.actual_changes/(cells*row.phases) if row.phases else math.nan,
                clamped_phases=row.clamped_phases,observed_changes=row.observed_changes,actual_changes=row.actual_changes))
    pd.DataFrame(nav_changes).to_csv(ad/'actual_changes.csv',index=False)
    plots(metrics,pair_data,summary,map_pairs,latency,received,work,ad)
    verification=HERE/'results/verification'
    records=lambda name:[json.loads(l) for l in (verification/name).read_text().splitlines() if l.startswith('{')]
    tests=records('tests.log');sanitized=records('sanitize.log');assert len(tests)==2 and tests==sanitized
    preflight=json.loads((HERE/'results/preflight/validation.json').read_text());assert preflight['status']=='passed'
    planned=calls[calls.planned.eq(1)]
    findings=dict(status='passed',timed_runs=len(ep),memory_runs=len(mem),scenarios=metrics['case'].nunique(),timed_planner_calls=len(planned),
        capped_calls=int(planned.status.eq('capped').sum()),exact_cost_disagreements=0,memory_matched_rows=matched,
        median_relative_mad=float(variation.relative_mad.median()),p95_relative_mad=float(variation.relative_mad.quantile(.95)),
        independent_dijkstra_comparisons=sum(r['comparisons'] for r in tests),asan_ubsan='passed',preflight_matched_rows=preflight['matched_rows'],
        software=dict(numpy=np.__version__,pandas=pd.__version__,matplotlib=matplotlib.__version__),manifest_sha256=digest(manifest_path),
        experiment_sha256=digest(directory/'experiment.json'),source_sha256=manifest['sources'],analysis_source_sha256=digest(Path(__file__)),
        reused_analysis_sha256=digest(ROOT/'cpp/mpgaa_mesh/analyze.py'),tables_sha256={p.name:digest(p) for p in sorted(ad.glob('*.csv'))},
        verification_sha256={p.name:digest(p) for p in sorted(verification.glob('*.log'))})
    (ad/'analysis.json').write_text(json.dumps(findings,indent=2,ensure_ascii=False,sort_keys=True)+'\n')
    print(json.dumps({k:v for k,v in findings.items() if not k.endswith('sha256')},indent=2,ensure_ascii=False))
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,default=HERE/'results/full');main(p.parse_args().directory)
