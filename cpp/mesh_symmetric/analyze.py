#!/usr/bin/env python3
"""Separate second-stage timing cohort; no earlier seconds are imported."""
import argparse,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];DEST=ROOT/'docs/mesh_symmetric'
sys.path.insert(0,str(ROOT/'cpp/mesh_envelope'))
import analyze as base
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pandas.testing import assert_frame_equal
NEW='smd_batch';LABEL={**base.LABEL,'smd_batch':'SMD-A*','smd_plain':'SMD no gap','md_batch':'MD + Batch','lazy_blocks_batch':'Lazy blocks, eager opens','conditional_dstar':'Conditional D* Lite'}
COLORS={**base.COLORS,'smd_batch':'#0072b2','smd_plain':'#56b4e9','md_batch':'#e69f00','lazy_blocks_batch':'#cc79a7','batch_mpgaa':'#009e73','conditional_dstar':'#332288','md_astar':'#999999'}
EXTRA=['activated_blocks','deferred_block_cells','optimistic_rounds','path_probes','gap_hits']
COUNTERS=list(dict.fromkeys([*base.COUNTERS,'activated_cells','deferred_cells','refined_cells',
 'mesh_nodes','bound_evals','pruned_branches','pruned_primitives','watch_hits','validity_flips',
 'witness_stops','policy_probes','policy_hits','alternate_uses','stamp_writes','tile_reads',
 'mask_refreshes','mask_hits','cut_checks','cut_reuses','cut_primitives','edit_batches',
 'scan_batches','seed_tests','arrow_checks','cover_tests',*EXTRA]))
def figure(fig,name,manifest):
 old=base.DEST;base.DEST=DEST
 try:base.figure(fig,name,manifest)
 finally:base.DEST=old

def main(directory):
 manifest=json.loads((HERE/'frozen/manifest.json').read_text());state=json.loads((directory/'experiment.json').read_text());assert state['status']=='passed'
 assert state['manifest_sha256']==base.sha(HERE/'frozen/manifest.json')
 for p,h in {**manifest['files'],**manifest['sources']}.items():assert base.sha(ROOT/p)==h,p
 for job in state['jobs'].values():
  assert job['status']=='passed'
  for p,h in job['outputs'].items():assert base.sha(directory/p)==h,p
 ctx=json.loads((ROOT/manifest['contexts_file']).read_text());meta=pd.DataFrame([dict(case=k,cohort=v['cohort'],control=v['control'],map=v['map'],family=v['family'],stage=v['stage'],panel='history' if v['family']=='history' else ('main' if v['cohort']=='replay' else 'holdout'),radius=v.get('params',{}).get('radius',0),k=v.get('params',{}).get('k',0),cr=v.get('params',{}).get('cr',0),truth_optimum=v.get('initial_optimum',v.get('truth_optimum',np.nan))) for k,v in ctx.items()]);runs=[];calls=[];mem=[];matched=0
 for job in manifest['plan']:
  name=job['name'];nav=job['mode']=='navigation';tp=directory/('timing_'+name);mp=directory/('memory_'+name)
  a=base.read(Path(str(tp)+'_calls.csv') if nav else tp.with_suffix('.csv'));b=base.read(Path(str(mp)+'_calls.csv') if nav else mp.with_suffix('.csv'));first=a[a.repeat.eq(0)].set_index(['case','method','query']).sort_index();profile=b.set_index(['case','method','query']).sort_index();fields=[c for c in first if not c.endswith('_s') and c not in ['repeat','peak_heap_bytes','retained_heap_bytes']]
  assert_frame_equal(first[fields],profile[fields],check_exact=True,check_dtype=False);matched+=len(first);assert b.peak_heap_bytes.ge(b.retained_heap_bytes).all();calls.append(a)
  if nav:
   r=base.read(Path(str(tp)+'_runs.csv'));memory=base.read(Path(str(mp)+'_runs.csv'));mem.append(memory[['case','method','peak_heap_bytes','retained_heap_bytes']])
   for _,v in r.iterrows():
    x=v.to_dict();x.update(full_s=v.setup_s+v.planner_s,complete=v.status=='goal');runs.append(x)
  else:
   mem.append(b.groupby(['case','method'],as_index=False).agg(peak_heap_bytes=('peak_heap_bytes','max'),retained_heap_bytes=('retained_heap_bytes','last')))
   for key,g in a.groupby(['case','method','repeat']):
    x=dict(zip(['case','method','repeat'],key));x.update(full_s=g.time_s.sum()+g.setup_s.sum(),repair_s=g.loc[g['query'].gt(0),'time_s'].sum(),initial_s=g.loc[g['query'].eq(0),'time_s'].sum(),complete=not g.status.isin(['capped','skipped_after_cap']).any(),moves=0,travel_cost=0,plans=g.planned.sum())
    for c in COUNTERS:x[c]=g[c].sum()
    runs.append(x)
 r=pd.DataFrame(runs);calls=pd.concat(calls,ignore_index=True).merge(meta,on='case',suffixes=('','_context'));out=directory/'analysis';out.mkdir(exist_ok=True)
 fields=[c for c in ['full_s','repair_s','initial_s','travel_cost','moves','plans',*COUNTERS] if c in r]
 metrics=r.groupby(['case','method'],as_index=False)[fields].median().merge(r.groupby(['case','method'],as_index=False).complete.all()).merge(pd.concat(mem),on=['case','method']).merge(meta,on='case');base.save(metrics,out/'case_metrics.csv')
 finite=calls.cost.notna()&calls.expected.notna();bad=int((calls.loc[finite,'cost']-calls.loc[finite,'expected']).abs().gt(1e-6).sum());bad+=int(((calls.cost.notna()!=calls.expected.notna())&~calls.status.isin(['capped','skipped_after_cap'])).sum());assert not bad
 pairs=[]
 for case,g in metrics.groupby('case'):
  a=g[g.method.eq(NEW)].iloc[0];old=g[g.method.isin(manifest['controls'])&g.complete];best=old.sort_values('full_s').iloc[0] if len(old) else None
  for method in dict.fromkeys([*manifest['controls'],*manifest['ablations'],'best_control']):
   b=best if method=='best_control' else (g[g.method.eq(method)].iloc[0] if g.method.eq(method).any() else None)
   if b is None and method!='best_control':continue
   ok=bool(a.complete and b is not None and b.complete)
   pairs.append(dict(case=case,baseline=method,selected_control=b.method if b is not None else 'none',cohort=a.cohort,control=a.control,map=a['map'],family=a.family,stage=a.stage,panel=a.panel,complete=ok,full_speedup=b.full_s/a.full_s if ok else np.nan,repair_speedup=b.repair_s/a.repair_s if ok and a.repair_s>0 else np.nan,memory_multiplier=a.peak_heap_bytes/b.peak_heap_bytes if ok else np.nan))
 pairs=pd.DataFrame(pairs);base.save(pairs,out/'paired_cases.csv')
 def aggregate(keys,path):
  rows=[]
  for key,d in pairs.groupby(keys):
   if not isinstance(key,tuple):key=(key,)
   rows.append(dict(zip(keys,key))|dict(configurations=len(d),pairs=int(d.complete.sum()),full_speedup=base.gm(d.full_speedup),repair_speedup=base.gm(d.repair_speedup),memory_multiplier=base.gm(d.memory_multiplier),wins10=int(d.full_speedup.ge(1.1).sum())))
  frame=pd.DataFrame(rows);base.save(frame,out/path);return frame
 summary=aggregate(['cohort','control','panel','baseline'],'summary.csv');maps=aggregate(['cohort','control','map','baseline'],'map_pairs.csv');families=aggregate(['cohort','control','family','baseline'],'family_pairs.csv')
 base.save(metrics.groupby(['cohort','control','method'],as_index=False).agg(configurations=('complete','size'),complete=('complete','sum')),out/'completion.csv')
 base.save(calls[calls.status.eq('capped')][['case','method','repeat','query','expansions']],out/'caps.csv')
 q=calls[calls.repeat.eq(0)].copy();q['observed_edits']=q.blocks+q.opens
 work=q.groupby(['cohort','control','map','method'],as_index=False)[['blocks','opens','observed_edits',*COUNTERS]].sum();base.save(work,out/'work.csv')
 maxpending=q.groupby(['case','method'],as_index=False).deferred_block_cells.max();base.save(maxpending,out/'max_deferred_blocks.csv')
 query=q[q['query'].gt(0)].copy();query['edit_bin']=pd.cut(query.observed_edits,[-1,0,2,8,32,128,1e12],labels=['0','1–2','3–8','9–32','33–128','>128'])
 latency=[]
 medcalls=calls[~calls.status.isin(['capped','skipped_after_cap'])&calls.planned.eq(1)].groupby(['case','method','query'],as_index=False).time_s.median().merge(meta,on='case')
 for key,d in medcalls[medcalls['query'].gt(0)].groupby(['cohort','control','map','method']):latency.append(dict(zip(['cohort','control','map','method'],key))|dict(p50_ms=d.time_s.quantile(.5)*1000,p95_ms=d.time_s.quantile(.95)*1000,p99_ms=d.time_s.quantile(.99)*1000,queries=len(d)))
 base.save(pd.DataFrame(latency),out/'latency.csv')
 quality=metrics[metrics.stage.eq('holdout_navigation')][['case','method','cohort','map','radius','k','cr','complete','travel_cost','moves','plans','truth_optimum']].copy();quality['static_stretch']=np.where(quality.cohort.eq('navigation_unknown')&quality.complete,quality.travel_cost/quality.truth_optimum,np.nan);assert quality.static_stretch.dropna().ge(1-1e-6).all();base.save(quality,out/'navigation_quality.csv')
 changes=[]
 for job in manifest['plan']:
  if job['mode']!='navigation' or not job['name'].endswith('dynamic'):continue
  df=base.read(directory/('timing_'+job['name']+'_runs.csv'));df=df[df.repeat.eq(0)]
  for _,v in df.iterrows():
   c=ctx[v['case']];n=int(np.prod(c['shape']));changes.append(dict(case=v['case'],method=v.method,map=c['map'],k=c['params']['k'],n=c['params']['n'],requested_cr=c['params']['cr'],phases=v.phases,clamped=v.clamped_phases,actual_cr=100*v.actual_changes/(n*v.phases) if v.phases else 0))
 base.save(pd.DataFrame(changes),out/'actual_changes.csv')
 failures=q[q.stage.eq('holdout_navigation')&q.status.eq('no_path')].copy();failures['truth_reachable']=failures.truth_cost.notna();assert not failures.loc[failures.cohort.eq('navigation_unknown'),'truth_reachable'].any();base.save(failures[['case','method','cohort','map','step','truth_reachable','truth_cost']],out/'failure_diagnostics.csv')

 figs={};plt.rcParams.update({'font.size':9,'pdf.fonttype':42,'axes.spines.top':False,'axes.spines.right':False})
 fig,axes=plt.subplots(1,2,figsize=(11,4))
 for ax,control in zip(axes,['car16','grid8']):
  for b in ['best_control','md_batch','batch_mpgaa','conditional_dstar','lazy_blocks_batch']:
   v=np.sort(pairs[pairs.control.eq(control)&pairs.baseline.eq(b)].full_speedup.dropna());ax.step(v,np.arange(1,len(v)+1)/len(v),where='post',label=LABEL.get(b,b))
  ax.set(xscale='log',title=control,xlabel='Episode speedup of SMD-A*',ylabel='Fraction of completed pairs');ax.axvline(1,color='.5',ls=':');ax.legend(fontsize=7)
 figure(fig,'profile',figs)
 fig,axes=plt.subplots(1,2,figsize=(11,4))
 for ax,control in zip(axes,['car16','grid8']):
  names=sorted(metrics[metrics.control.eq(control)]['map'].unique());vals=[];labels=[]
  for name in names:
   d=pairs[pairs.control.eq(control)&pairs['map'].eq(name)&pairs.baseline.eq('best_control')];vals.append(base.gm(d.full_speedup));labels.append(name)
  ax.barh(labels,vals,color=COLORS[NEW]);ax.axvline(1,color='.5',ls=':');ax.set(xscale='log',xlabel='Episode speedup vs fastest control',title=control)
 figure(fig,'by_map',figs)
 fig,axes=plt.subplots(1,2,figsize=(11,4))
 for ax,control in zip(axes,['car16','grid8']):
  d=work[work.control.eq(control)&work.method.eq(NEW)&work.cohort.eq('replay')];x=np.arange(len(d));b=np.divide(d.activated_blocks,d.blocks,out=np.zeros(len(d)),where=d.blocks.gt(0));o=np.divide(d.activated_cells,d.opens,out=np.zeros(len(d)),where=d.opens.gt(0))
  ax.bar(x-.18,b,.36,label='Activated blocks / observed blocks');ax.bar(x+.18,o,.36,label='Activated openings / observed openings');ax.set_xticks(x,d['map'],rotation=35,ha='right');ax.set(title=control,ylabel='Fraction delivered to the backend');ax.legend(fontsize=7)
 figure(fig,'activation',figs)
 fig,axes=plt.subplots(2,3,figsize=(12,7),sharex=True)
 for ax,(name,d) in zip(axes.flat,metrics[metrics.cohort.eq('navigation_unknown')].groupby('map')):
  for method in [NEW,'md_batch','batch_mpgaa','lba_reuse','conditional_dstar']:
   v=d[d.method.eq(method)].sort_values('radius');ax.plot(v.radius,np.where(v.complete,1000*v.full_s,np.nan),'o-',label=LABEL[method],color=COLORS.get(method));f=v[~v.complete];ax.scatter(f.radius,1000*f.full_s,marker='x',color=COLORS.get(method))
  ax.set(yscale='log',title=name,xlabel='Discovery radius, cells',ylabel='Planner time, ms');ax.set_xticks([8,16,32,64])
 axes[0,0].legend(fontsize=7);figure(fig,'holdout_radius',figs)
 fig,axes=plt.subplots(1,2,figsize=(11,4))
 for ax,control in zip(axes,['car16','grid8']):
  methods=[NEW,'md_batch','batch_mpgaa','conditional_dstar','lba_reuse']+(['octile_reuse'] if control=='grid8' else []);a=metrics[metrics.control.eq(control)]
  ax.boxplot([a[a.method.eq(m)].peak_heap_bytes/2**20 for m in methods],tick_labels=[LABEL[m] for m in methods],showfliers=False);ax.tick_params(axis='x',rotation=40,labelsize=8);ax.set(yscale='log',ylabel='Requested peak heap, MiB',title=control)
 figure(fig,'memory',figs)
 dispersion=[]
 for key,d in r.groupby(['case','method']):
  median=d.full_s.median();dispersion.append(dict(case=key[0],method=key[1],relative_mad=float((d.full_s-median).abs().median()/median)))
 dispersion=pd.DataFrame(dispersion);base.save(dispersion,out/'dispersion.csv')
 result=dict(status='passed',scenarios=manifest['scenarios'],timed_runs=len(r),memory_runs=len(metrics),timed_calls=len(calls),allocation_matched_rows=matched,exact_cost_disagreements=bad,capped_calls=int(calls.status.eq('capped').sum()),relative_mad_median=float(dispersion.relative_mad.median()),relative_mad_p95=float(dispersion.relative_mad.quantile(.95)),manifest_sha256=base.sha(HERE/'frozen/manifest.json'),source_sha256=base.sha(Path(__file__)),tables_sha256={p.name:base.sha(p) for p in sorted(out.glob('*.csv'))},figures_sha256=figs)
 assert len(r)==manifest['timed_runs'] and len(metrics)==manifest['memory_runs'];(out/'analysis.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if not k.endswith('sha256')}))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,default=HERE/'results/full');main(p.parse_args().directory)
