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
EXTRA=['stamp_writes','tile_reads','mask_refreshes','mask_hits','cut_checks','cut_reuses','cut_primitives','edit_batches','scan_batches','seed_tests','arrow_checks','cover_tests']
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
            # Preserve unpaired rows when no control completes. Their ratios
            # stay missing; the failed fallback never enters the speedup.
            base=metrics[metrics.method.isin(CONTROL)].sort_values(['complete','episode_s','method'],ascending=[False,True,True]).drop_duplicates(['case','job']).copy()
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
        if baseline=='best_control':
            lo,hi=ax.get_xlim();ax.set_xlim(min(.2,lo),max(1.05,hi))
    axes[0].set_yticks(range(len(groups)),[a.replace('navigation_','nav ')+' / '+b for a,b in groups]);axes[0].invert_yaxis();axes[1].legend(loc='best');fig.tight_layout();save('episode_speedup',fig)
    fig,axes=plt.subplots(1,3,figsize=(10.8,4.9))
    for ax,cohort,control in zip(axes,['replay','navigation_dynamic','navigation_dynamic'],['car16','car16','grid8']):
        d=maps[maps.cohort.eq(cohort)&maps.control.eq(control)&maps.baseline.eq('best_control')&maps.method.isin(NEW)]
        mat=d.pivot(index='map',columns='method',values='episode_speedup').reindex(columns=NEW)
        values=np.log2(mat.to_numpy(dtype=float));im=ax.imshow(values,aspect='auto',cmap='RdBu',vmin=-2.5,vmax=2.5)
        ax.set_xticks(range(3),[SHORT[c] for c in NEW],rotation=35,ha='right');ax.set_yticks(range(len(mat)),mat.index);ax.set_title(cohort.replace('navigation_','nav ')+' / '+control)
        for (i,j),v in np.ndenumerate(mat.to_numpy(dtype=float)):
            if np.isfinite(v):ax.text(j,i,f'{v:.2f}',ha='center',va='center',fontsize=8,color='white' if abs(math.log2(v))>1.4 else 'black')
    fig.subplots_adjust(left=.11,right=.87,bottom=.15,top=.9,wspace=.8)
    cax=fig.add_axes([.91,.15,.018,.75]);fig.colorbar(im,cax=cax,label='log2 speedup versus fastest previous method');save('map_speedup',fig)
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
            ax.plot(range(len(bins)),v.median_s*1000,'o-',ms=3,label=SHORT[c],color='#777777' if c=='boundary_mpgaa' else COLORS[NEW.index(c)])
        ax.set_xticks(range(len(bins)),bins,rotation=35,ha='right');ax.set_yscale('log');ax.grid(axis='y',alpha=.2);ax.set_title(control)
        ax.set_xlabel('Received blocks + opens');ax.set_ylabel('Median online call, ms')
    axes[0].legend(fontsize=8);fig.tight_layout();save('change_count_latency',fig)
    fig,axes=plt.subplots(1,2,figsize=(8.4,3.6))
    for ax,control in zip(axes,['car16','grid8']):
        for c in NEW:
            d=pair_data[pair_data.control.eq(control)&pair_data.method.eq(c)&pair_data.baseline.eq('best_control')]
            x=np.sort(d.episode_speedup.dropna().to_numpy());ax.step(x,np.arange(1,len(x)+1)/len(x),where='post',label=SHORT[c],color=COLORS[NEW.index(c)])
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
        for i,n in enumerate(total):ax.text(i,min(.98,scan.iloc[i]+.03),str(int(n))+' batches',ha='center',fontsize=8,
            color='white' if scan.iloc[i]>.9 else 'black',va='top' if scan.iloc[i]>.9 else 'bottom')
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
    archive=HERE/'results/pre_witness_cover';prior=json.loads((archive/'manifest.json').read_text())
    assert prior['plan']==manifest['plan'] and prior['repeats']==manifest['repeats'] and prior['seed']==manifest['seed'] and prior['cap']==manifest['cap']
    assert json.loads((archive/'EXCLUDED.json').read_text())['status']=='excluded'
    for name in ['algorithms.hpp','factory.hpp','test.cpp','Makefile','prepare.py','run_all.py']:
        assert digest(archive/name)==prior['sources']['cpp/mpgaa_lazy/'+name]
    prior_state=json.loads((archive/'raw/experiment.json').read_text())
    for job in prior_state['jobs'].values():
        if job['status']=='passed':
            for name,sha in job['outputs'].items():assert digest(archive/'raw'/name)==sha
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
            dynamic=timing[timing.kind.eq('dynamic')]
            assert dynamic.n.eq(dynamic.k).all(),'Requested n=k constraint violated'
            a=native_timing[native_timing.repeat.eq(0)].set_index(['case','method']).sort_index();b=native_memory.set_index(['case','method']).sort_index()
            assert_frame_equal(a[['fingerprint']],b[['fingerprint']],check_dtype=False,check_exact=True)
        timing=decorate(timing,job,contexts);memory=decorate(memory,job,contexts)
        all_calls.append(timing);all_ep.append(episodes(timing,job,native_timing));all_mem.append(episodes(memory,job,native_memory))
    calls=pd.concat(all_calls,ignore_index=True);ep=pd.concat(all_ep,ignore_index=True);mem=pd.concat(all_mem,ignore_index=True)
    assert len(ep)==manifest['timed_runs'] and len(mem)==manifest['memory_runs']
    assert ep['case'].nunique()==manifest['scenarios']
    ad=directory/'analysis';ad.mkdir(exist_ok=True)
    # Witness changes only occupancy evaluation; Batch/Witness must preserve
    # queries, decisions, search/repair work and the exact cache refresh schedule.
    first=calls[calls.repeat.eq(0)]
    wb=first[first.method.eq('witness_mpgaa')].merge(first[first.method.eq('batch_mpgaa')],on=['case','query'],suffixes=('','_base'),validate='one_to_one')
    assert len(wb)==len(first[first.method.eq('witness_mpgaa')])==len(first[first.method.eq('batch_mpgaa')])
    invariant=['status','planned','step','cost','expected','blocks','opens','travel_cost','path_hash','world_hash','belief_hash','start_i','start_j','start_theta',
        'expansions','heuristic_pops','notify_probes','stamp_writes','tile_reads','mask_refreshes','mask_hits','edit_batches','scan_batches','seed_tests','arrow_checks']
    for field in invariant:
        assert (wb[field].eq(wb[field+'_base'])|(wb[field].isna()&wb[field+'_base'].isna())).all(),('Witness changed logical work',field)
    grid_wb=wb[wb.control.eq('grid8')]
    assert grid_wb.checked_cells.ge(grid_wb.checked_cells_base).all(),'Single-cell grid8 traces cannot benefit from witness prefix coverage'
    wb.groupby(['cohort','control'],as_index=False).agg(rows=('query','size'),witness_checks=('checked_cells','sum'),batch_checks=('checked_cells_base','sum'),
        refreshes=('mask_refreshes','sum'),covered_branches=('cut_reuses','sum')).to_csv(ad/'witness_batch_parity.csv',index=False)
    ep.to_csv(ad/'episode_metrics.csv',index=False);mem.to_csv(ad/'memory_metrics.csv',index=False)
    variation=ep.groupby(['case','job','cohort','control','map','method']).episode_s.agg(median_s='median',
        relative_mad=lambda x:float(np.median(np.abs(x-np.median(x)))/np.median(x)) if np.median(x)>0 else math.nan).reset_index()
    variation.to_csv(ad/'repeat_variation.csv',index=False)
    keys=['case','job','cohort','control','map','family','method'];numeric=['episode_s','online_s','initial_s','setup_s','plans','online_plans','travel_cost']+COUNTERS
    metrics=ep.groupby(keys,as_index=False).agg(**{k:(k,'median') for k in numeric},complete=('complete','all'),repeats=('repeat','size'))
    metrics=metrics.merge(mem[keys+['peak_heap_bytes','retained_heap_bytes']],on=keys,validate='one_to_one')
    assert metrics.repeats.eq(3).all();metrics.to_csv(ad/'case_metrics.csv',index=False)
    control_success=metrics[metrics.method.isin(CONTROL)].groupby(['case','job']).complete.any().rename('any_control_complete')
    exclusive=metrics[metrics.method.isin(NEW)].merge(control_success,on=['case','job'],validate='many_to_one')
    exclusive['candidate_only']=exclusive.complete&~exclusive.any_control_complete
    exclusive['control_only']=~exclusive.complete&exclusive.any_control_complete
    exclusive.to_csv(ad/'completion_vs_controls.csv',index=False)
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
    online.groupby(['cohort','control','map','method','status']).time_s.agg(count='size',p50='median',p95=lambda x:x.quantile(.95),p99=lambda x:x.quantile(.99)).reset_index().to_csv(ad/'latency_by_status.csv',index=False)
    online.groupby(['cohort','control','method','status']).time_s.agg(count='size',p50='median',p95=lambda x:x.quantile(.95),p99=lambda x:x.quantile(.99)).reset_index().to_csv(ad/'latency_status_summary.csv',index=False)
    received=calls[calls.repeat.eq(0)&calls.planned.eq(1)&calls.online].copy()
    received['received_bin']=pd.cut(received.blocks+received.opens,[-1,0,1,4,16,64,256,1024,np.inf],labels=['0','1','2–4','5–16','17–64','65–256','257–1024','>1024'])
    received.groupby(['cohort','control','map','method','received_bin'],observed=True).agg(calls=('time_s','size'),median_s=('time_s','median'),p95_s=('time_s',lambda x:x.quantile(.95)),
        capped=('status',lambda x:int(x.eq('capped').sum())),median_notify=('notify_probes','median'),median_checks=('checked_cells','median')).reset_index().to_csv(ad/'received_changes_by_map.csv',index=False)
    received=received.groupby(['cohort','control','method','received_bin'],observed=True).agg(calls=('time_s','size'),median_s=('time_s','median'),
        p95_s=('time_s',lambda x:x.quantile(.95)),capped=('status',lambda x:int(x.eq('capped').sum())),median_notify=('notify_probes','median'),median_checks=('checked_cells','median')).reset_index()
    received.to_csv(ad/'received_changes.csv',index=False)
    work=calls[calls.repeat.eq(0)&calls.planned.eq(1)].groupby(['cohort','control','method'],as_index=False)[COUNTERS].sum();work.to_csv(ad/'work.csv',index=False)
    # Repair work on strictly identical replay queries, broken down by edit kind.
    repair=calls[calls.repeat.eq(0)&calls.cohort.eq('replay')&calls.online&calls.planned.eq(1)].copy()
    repair['edit_kind']=np.select([repair.opens.eq(0)&repair.blocks.gt(0),repair.blocks.eq(0)&repair.opens.gt(0),repair.opens.gt(0)&repair.blocks.gt(0)],['blocks','opens','mixed'],default='none')
    repair.groupby(['control','family','method','edit_kind'],as_index=False)[['time_s','blocks','opens',*COUNTERS]].sum().to_csv(ad/'repair_work.csv',index=False)
    # Conditional replay diagnosis of Batch's adaptive opening-seed choice.
    # The subgroup is selected by algorithm telemetry, never by measured speed.
    replay_all=calls[calls.cohort.eq('replay')&calls.planned.eq(1)&calls.online&calls.method.isin(['stamp_mpgaa','batch_mpgaa'])]
    replay_median=replay_all.groupby(['case','method','query'],as_index=False).time_s.median().rename(columns={'time_s':'median_call_s'})
    replay_first=replay_all[replay_all.repeat.eq(0)].merge(replay_median,on=['case','method','query'],validate='one_to_one')
    adaptive=replay_first[replay_first.method.eq('batch_mpgaa')].merge(replay_first[replay_first.method.eq('stamp_mpgaa')],on=['case','query'],suffixes=('','_base'),validate='one_to_one')
    adaptive=adaptive[~adaptive.status.eq('capped')&~adaptive.status_base.eq('capped')&(adaptive.edit_batches+adaptive.scan_batches).gt(0)].copy()
    adaptive['selection']=np.where(adaptive.scan_batches.gt(0),'scan','edits')
    adaptive['zero_expansion_success']=adaptive.cost.notna()&adaptive.cost_base.notna()&adaptive.expansions.eq(0)&adaptive.expansions_base.eq(0)
    adaptive['query_speedup']=adaptive.median_call_s_base/adaptive.median_call_s
    adaptive[['case','query','control','map','family','selection','zero_expansion_success','blocks','opens','median_call_s','median_call_s_base','query_speedup',
        'notify_probes','notify_probes_base','seed_tests','seed_tests_base','expansions','expansions_base','heuristic_pops','heuristic_pops_base']].to_csv(ad/'batch_repair_calls.csv',index=False)
    def repair_summary(groupby):
        records=[]
        for key,d in adaptive.groupby(groupby):
            if not isinstance(key,tuple):key=(key,)
            for scope,v in [('all_valid',d),('zero_expansion_success',d[d.zero_expansion_success])]:
                if v.empty:continue
                records.append(dict(zip(groupby,key),scope=scope,calls=len(v),cases=v['case'].nunique(),query_speedup=gm(v.query_speedup),
                    sum_speedup=v.median_call_s_base.sum()/v.median_call_s.sum(),stamp_notify=int(v.notify_probes_base.sum()),batch_notify=int(v.notify_probes.sum()),
                    stamp_seed_tests=int(v.seed_tests_base.sum()),batch_seed_tests=int(v.seed_tests.sum())))
        return pd.DataFrame(records)
    repair_summary(['control','selection']).to_csv(ad/'batch_repair_summary.csv',index=False)
    repair_summary(['control','map','selection']).to_csv(ad/'batch_repair_maps.csv',index=False)
    # Exact input equivalence and work comparison are kept separate from speed.
    a=repair[repair.method.eq('boundary_mpgaa')]
    same=[]
    for candidate in NEW:
        joint=repair[repair.method.eq(candidate)].merge(a,on=['case','query'],suffixes=('','_base'),validate='one_to_one')
        for control,d in joint.groupby('control'):
            same.append(dict(method=candidate,control=control,rows=len(d),same_cost=int(((d.cost-d.cost_base).abs().le(1e-6)|(d.cost.isna()&d.cost_base.isna())).sum()),
                same_expansions=int(d.expansions.eq(d.expansions_base).sum()),same_path_hash=int(d.path_hash.eq(d.path_hash_base).sum())))
    pd.DataFrame(same).to_csv(ad/'replay_work_parity.csv',index=False)
    # Additional closed-loop subset: match the actual input snapshot, position,
    # step, before/after belief, world and update cardinalities. Timing uses the
    # three-repeat median of that deterministic call. Histories may still differ.
    nav_calls=calls[calls.cohort.str.startswith('navigation_')&calls.planned.eq(1)].copy()
    median_calls=nav_calls.groupby(['case','method','step'],as_index=False).time_s.median().rename(columns={'time_s':'median_call_s'})
    nav_first=nav_calls[nav_calls.repeat.eq(0)].sort_values(['case','method','step']).copy()
    nav_first['previous_belief_hash']=nav_first.groupby(['case','method']).belief_hash.shift()
    nav_first=nav_first.merge(median_calls,on=['case','method','step'],validate='one_to_one')
    static=nav_first[nav_first.cohort.eq('navigation_unknown')];static_base=static[static.method.eq('boundary_mpgaa')];static_parity=[]
    for candidate in NEW:
        own=static[static.method.eq(candidate)];joint=own.merge(static_base,on=['case','step'],suffixes=('','_base'),validate='one_to_one')
        same_inputs=np.ones(len(joint),dtype=bool)
        for field in ['start_i','start_j','start_theta','world_hash','belief_hash','previous_belief_hash','blocks','opens']:
            same_inputs&=(joint[field].eq(joint[field+'_base'])|(joint[field].isna()&joint[field+'_base'].isna())).to_numpy()
        static_parity.append(dict(method=candidate,candidate_calls=len(own),baseline_calls=len(static_base),joined_steps=len(joint),identical_inputs=int(same_inputs.sum()),
            identical_paths=int((same_inputs&joint.path_hash.eq(joint.path_hash_base)&joint.status.eq(joint.status_base)).sum()),
            identical_search_work=int((same_inputs&joint.expansions.eq(joint.expansions_base)&joint.heuristic_pops.eq(joint.heuristic_pops_base)).sum())))
    pd.DataFrame(static_parity).to_csv(ad/'static_navigation_parity.csv',index=False)
    terminal=nav_first.groupby(['case','method'],sort=False).tail(1).copy()
    native_status=ep[ep.repeat.eq(0)&ep.cohort.str.startswith('navigation_')][['case','method','status']].rename(columns={'status':'episode_status'})
    terminal=terminal.merge(native_status,on=['case','method'],validate='one_to_one')
    terminal['truth_path_at_belief_no_path']=terminal.status.eq('no_path')&terminal.truth_cost.notna()
    terminal[['case','method','cohort','control','map','status','episode_status','truth_cost','truth_path_at_belief_no_path']].to_csv(ad/'navigation_terminal_calls.csv',index=False)
    nav_first=nav_first[nav_first.online]
    aligned=[];base=nav_first[nav_first.method.eq('boundary_mpgaa')]
    align_keys=['case','step','start_i','start_j','start_theta','world_hash','previous_belief_hash','belief_hash','blocks','opens']
    for candidate in NEW:
        own=nav_first[nav_first.method.eq(candidate)]
        joint=own.merge(base,on=align_keys,suffixes=('','_base'),validate='one_to_one')
        for r in joint.itertuples():
            aligned.append(dict(case=r.case,cohort=r.cohort,control=r.control,map=r.map,method=candidate,step=r.step,status=r.status,status_base=r.status_base,
                uncapped=r.status!='capped' and r.status_base!='capped',candidate_s=r.median_call_s,baseline_s=r.median_call_s_base,
                candidate_expansions=r.expansions,baseline_expansions=r.expansions_base,candidate_checks=r.checked_cells,baseline_checks=r.checked_cells_base))
    aligned=pd.DataFrame(aligned);aligned.to_csv(ad/'aligned_calls.csv',index=False)
    aligned_summary=[]
    for (cohort,control,mp,candidate),own in nav_first[nav_first.method.isin(NEW)].groupby(['cohort','control','map','method']):
        d=aligned[aligned.cohort.eq(cohort)&aligned.control.eq(control)&aligned['map'].eq(mp)&aligned.method.eq(candidate)]
        usable=d[d.uncapped];reference=base[base.cohort.eq(cohort)&base.control.eq(control)&base['map'].eq(mp)]
        aligned_summary.append(dict(cohort=cohort,control=control,map=mp,method=candidate,candidate_online_calls=len(own),baseline_online_calls=len(reference),
            matched_calls=len(d),usable_calls=len(usable),candidate_s=usable.candidate_s.sum(),baseline_s=usable.baseline_s.sum(),
            query_sum_speedup=usable.baseline_s.sum()/usable.candidate_s.sum() if usable.candidate_s.sum()>0 else math.nan))
    pd.DataFrame(aligned_summary).to_csv(ad/'aligned_maps.csv',index=False)
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
    regression=json.loads((HERE/'results/regression/validation.json').read_text());assert regression['status']=='passed'
    planned=calls[calls.planned.eq(1)]
    findings=dict(status='passed',timed_runs=len(ep),memory_runs=len(mem),scenarios=metrics['case'].nunique(),timed_planner_calls=len(planned),
        capped_calls=int(planned.status.eq('capped').sum()),exact_cost_disagreements=0,memory_matched_rows=matched,
        median_relative_mad=float(variation.relative_mad.median()),p95_relative_mad=float(variation.relative_mad.quantile(.95)),
        independent_dijkstra_comparisons=sum(r['comparisons'] for r in tests),asan_ubsan='passed',preflight_matched_rows=preflight['matched_rows'],
        targeted_dijkstra_comparisons=regression['comparisons'],targeted_regressions=regression,regression_source_sha256=digest(HERE/'regression.py'),
        excluded_preliminary_manifest_sha256=digest(archive/'manifest.json'),excluded_preliminary_state_sha256=digest(archive/'raw/experiment.json'),
        software=dict(numpy=np.__version__,pandas=pd.__version__,matplotlib=matplotlib.__version__),manifest_sha256=digest(manifest_path),
        experiment_sha256=digest(directory/'experiment.json'),source_sha256=manifest['sources'],analysis_source_sha256=digest(Path(__file__)),
        reused_analysis_sha256=digest(ROOT/'cpp/mpgaa_mesh/analyze.py'),tables_sha256={p.name:digest(p) for p in sorted(ad.glob('*.csv'))},
        verification_sha256={p.name:digest(p) for p in sorted(verification.glob('*.log'))})
    (ad/'analysis.json').write_text(json.dumps(findings,indent=2,ensure_ascii=False,sort_keys=True)+'\n')
    print(json.dumps({k:v for k,v in findings.items() if not k.endswith('sha256')},indent=2,ensure_ascii=False))
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,default=HERE/'results/full');main(p.parse_args().directory)
