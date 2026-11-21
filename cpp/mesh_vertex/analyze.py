#!/usr/bin/env python3
"""Validate and aggregate only this study's fresh joint measurements."""
import argparse,json,sys
from pathlib import Path
import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];DEST=ROOT/'docs/mesh_vertex'
sys.path.insert(0,str(ROOT/'cpp/mesh_envelope'))
import analyze as common
import matplotlib.pyplot as plt
NATIVE=['mesh_mpgaa','trigger_mesh','cascade_mesh','cascade_scan','cascade_heap','mesh_astar','contour_only']
LABEL={**common.LABEL,'mesh_mpgaa':'Mesh-MPGAA*','trigger_mesh':'Trigger-Mesh','cascade_mesh':'Cascade-Mesh','cascade_scan':'Cascade, no watches','cascade_heap':'Cascade, no forward contour','contour_only':'Trigger + forward contour','mesh_astar':'Mesh A*, same core','conditional_dstar':'Conditional D* Lite'}
NEW=['trigger_mesh','cascade_mesh'];CORE=['expansions','checked_cells','notify_probes','heuristic_pops','backend_calls','certified']
SNAP=['mv_active_watches','mv_records'];HASH=['path_hash','world_hash','belief_hash','fingerprint','mv_trace_hash']
def read(p):return pd.read_csv(p,dtype={k:str for k in HASH})
def figure(fig,name,manifest):
 old=common.DEST;common.DEST=DEST
 try:common.figure(fig,name,manifest)
 finally:common.DEST=old
def main(directory):
 manifest=json.loads((HERE/'frozen/manifest.json').read_text());state=json.loads((directory/'experiment.json').read_text());assert state['status']=='passed'
 assert state['manifest_sha256']==common.sha(HERE/'frozen/manifest.json')
 for p,h in {**manifest['files'],**manifest['sources']}.items():assert common.sha(ROOT/p)==h,p
 for p,h in state['binaries'].items():assert common.sha(HERE/'build'/p)==h,p
 for job in state['jobs'].values():
  assert job['status']=='passed'
  for p,h in job['outputs'].items():assert common.sha(directory/p)==h,p
 ctx=json.loads((ROOT/manifest['contexts_file']).read_text())
 meta=pd.DataFrame([dict(case=k,cohort=v['cohort'],control=v['control'],map=v['map'],family=v['family'],seed=v.get('seed',0),panel='history' if v['family']=='history' else ('main' if v['cohort']=='replay' else 'navigation'),radius=v.get('params',{}).get('radius',0),k=v.get('params',{}).get('k',0),cr=v.get('params',{}).get('cr',0),truth_optimum=v.get('initial_optimum',v.get('truth_optimum',np.nan))) for k,v in ctx.items()])
 frames=[];memory=[];episodes=[];matched=0
 for job in manifest['plan']:
  nav=job['mode']=='navigation';name=job['name'];tp=directory/('timing_'+name);mp=directory/('memory_'+name)
  a=read(Path(str(tp)+'_calls.csv') if nav else tp.with_suffix('.csv'));b=read(Path(str(mp)+'_calls.csv') if nav else mp.with_suffix('.csv'))
  first=a[a.repeat.eq(0)].set_index(['case','method','query']).sort_index();prof=b.set_index(['case','method','query']).sort_index();fields=[c for c in first if not c.endswith('_s') and c not in ['repeat','peak_heap_bytes','retained_heap_bytes']]
  assert_frame_equal(first[fields],prof[fields],check_exact=True,check_dtype=False);matched+=len(first);assert b.peak_heap_bytes.ge(b.retained_heap_bytes).all();frames.append(a)
  if nav:
   r=read(Path(str(tp)+'_runs.csv'));mm=read(Path(str(mp)+'_runs.csv'));memory.append(mm[['case','method','peak_heap_bytes','retained_heap_bytes']])
   for _,v in r.iterrows():episodes.append(dict(case=v['case'],method=v.method,repeat=v['repeat'],full_s=v.setup_s+v.planner_s,initial_s=v.setup_s+v.initial_s,repair_s=v.repair_s,complete=v.status=='goal',status=v.status,travel_cost=v.travel_cost,moves=v.moves,plans=v.plans))
  else:
   memory.append(b.groupby(['case','method'],as_index=False).agg(peak_heap_bytes=('peak_heap_bytes','max'),retained_heap_bytes=('retained_heap_bytes','last')))
   for key,g in a.groupby(['case','method','repeat']):episodes.append(dict(zip(['case','method','repeat'],key))|dict(full_s=g.time_s.sum()+g.setup_s.sum(),initial_s=g.loc[g['query'].eq(0),['time_s','setup_s']].sum().sum(),repair_s=g.loc[g['query'].gt(0),'time_s'].sum(),complete=not g.status.isin(['capped','skipped_after_cap']).any(),status='capped' if g.status.eq('capped').any() else 'complete',travel_cost=0,moves=0,plans=g.planned.sum()))
 calls=pd.concat(frames,ignore_index=True).drop(columns=['family'],errors='ignore').merge(meta,on='case');r=pd.DataFrame(episodes);out=directory/'analysis';out.mkdir(exist_ok=True)
 counters=CORE+[c for c in calls if c.startswith('mv_') and c not in SNAP+['mv_trace_hash']]
 q=calls[calls.repeat.eq(0)].copy();q['observed_edits']=q.blocks+q.opens
 finite=calls.cost.notna()&calls.expected.notna();bad=int((calls.loc[finite,'cost']-calls.loc[finite,'expected']).abs().gt(1e-6).sum());bad+=int(((calls.cost.notna()!=calls.expected.notna())&~calls.status.isin(['capped','skipped_after_cap'])).sum());assert bad==0
 native=q[q.method.isin(NATIVE)];assert native.expansions.eq(native.mv_boundary_expansions+native.mv_interior_expansions).all()
 assert native[native.control.eq('car16')].mv_interior_expansions.sum()>0
 replay=q[q.cohort.eq('replay')]
 # Exact-priority contour continuation must preserve the full extraction trace.
 aa=replay[replay.method.eq('trigger_mesh')].set_index(['case','query']).sort_index();bb=replay[replay.method.eq('contour_only')].set_index(['case','query']).sort_index()
 trace_fields=['status','cost','expansions','path_hash','mv_trace_hash'];assert_frame_equal(aa[trace_fields],bb[trace_fields],check_dtype=False,check_exact=True)
 work=q.groupby(['case','method'],as_index=False)[['blocks','opens','observed_edits',*counters]].sum().merge(meta,on='case');common.save(work,out/'work.csv')
 snapshots=q.groupby(['case','method'],as_index=False)[SNAP].max();common.save(snapshots.merge(meta,on='case'),out/'max_state.csv')
 metrics=r.groupby(['case','method'],as_index=False)[['full_s','initial_s','repair_s','travel_cost','moves','plans']].median().merge(r.groupby(['case','method'],as_index=False).complete.all()).merge(pd.concat(memory),on=['case','method']).merge(meta,on='case');common.save(metrics,out/'case_metrics.csv')
 common.save(metrics.groupby(['cohort','control','method'],as_index=False).agg(configurations=('case','size'),complete=('complete','sum')),out/'completion.csv')
 common.save(calls[calls.status.eq('capped')][['case','method','repeat','query','expansions']],out/'caps.csv')
 pairs=[]
 for case,g in metrics.groupby('case'):
  old=g[g.method.isin(manifest['controls'])&g.complete];best=old.sort_values('full_s').iloc[0] if len(old) else None
  for method in NEW:
   a=g[g.method.eq(method)].iloc[0]
   for baseline in dict.fromkeys([*manifest['controls'],*manifest['ablations'],*NEW,'best_control']):
    if method==baseline:continue
    b=best if baseline=='best_control' else (g[g.method.eq(baseline)].iloc[0] if g.method.eq(baseline).any() else None)
    if b is None and baseline!='best_control':continue
    ok=bool(a.complete and b is not None and b.complete)
    pairs.append(dict(case=case,method=method,baseline=baseline,selected_control='none' if b is None else b.method,cohort=a.cohort,control=a.control,map=a['map'],family=a.family,panel=a.panel,seed=a.seed,radius=a.radius,k=a.k,cr=a.cr,complete=ok,full_speedup=b.full_s/a.full_s if ok else np.nan,repair_speedup=b.repair_s/a.repair_s if ok and a.repair_s>0 else np.nan,memory_multiplier=a.peak_heap_bytes/b.peak_heap_bytes if ok else np.nan))
 pairs=pd.DataFrame(pairs);common.save(pairs,out/'paired_cases.csv')
 def aggregate(keys,name):
  rows=[]
  for key,d in pairs.groupby(keys):
   if not isinstance(key,tuple):key=(key,)
   rows.append(dict(zip(keys,key))|dict(configurations=len(d),pairs=int(d.complete.sum()),full_speedup=common.gm(d.full_speedup),repair_speedup=common.gm(d.repair_speedup),memory_multiplier=common.gm(d.memory_multiplier),wins10=int(d.full_speedup.ge(1.1).sum())))
  frame=pd.DataFrame(rows);common.save(frame,out/name);return frame
 summary=aggregate(['cohort','control','panel','method','baseline'],'summary.csv');maps=aggregate(['cohort','control','map','method','baseline'],'map_pairs.csv');aggregate(['cohort','control','family','method','baseline'],'family_pairs.csv');aggregate(['cohort','control','map','radius','k','cr','method','baseline'],'parameter_pairs.csv')
 querytimes=calls[~calls.status.isin(['capped','skipped_after_cap'])&calls.planned.eq(1)].groupby(['case','method','query'],as_index=False).agg(time_s=('time_s','median'),blocks=('blocks','first'),opens=('opens','first')).merge(meta,on='case');latency=[]
 for key,d in querytimes[querytimes['query'].gt(0)].groupby(['cohort','control','map','method']):latency.append(dict(zip(['cohort','control','map','method'],key))|dict(queries=len(d),p50_ms=1000*d.time_s.quantile(.5),p95_ms=1000*d.time_s.quantile(.95),p99_ms=1000*d.time_s.quantile(.99)))
 common.save(pd.DataFrame(latency),out/'latency.csv')
 querytimes['edits']=querytimes.blocks+querytimes.opens;querytimes['edit_bin']=pd.cut(querytimes.edits,[-1,0,4,16,64,1e12],labels=['0','1–4','5–16','17–64','>64'])
 edit= querytimes[querytimes['query'].gt(0)].groupby(['cohort','control','method','edit_bin'],observed=True).agg(queries=('time_s','size'),median_ms=('time_s',lambda x:1000*x.median()),p95_ms=('time_s',lambda x:1000*x.quantile(.95))).reset_index();common.save(edit,out/'edits_latency.csv')
 # Prefixes are dependent observations of the same episode, not extra maps.
 amort=[]
 for key,d in calls[calls.cohort.eq('replay')].groupby(['case','method','repeat']):
  for repairs in [0,1,2,4,8]:
   if d['query'].max()<repairs:continue
   p=d[d['query'].le(repairs)];amort.append(dict(zip(['case','method','repeat'],key))|dict(repairs=repairs,seconds=p.time_s.sum()+p.setup_s.sum(),complete=not p.status.isin(['capped','skipped_after_cap']).any()))
 amort=pd.DataFrame(amort);amort=amort.groupby(['case','method','repairs'],as_index=False).agg(seconds=('seconds','median'),complete=('complete','all')).merge(meta,on='case');common.save(amort,out/'amortization.csv')
 quality=metrics[metrics.cohort.ne('replay')][['case','method','cohort','map','seed','radius','k','cr','complete','travel_cost','moves','plans','truth_optimum']].copy();quality['static_stretch']=np.where(quality.cohort.eq('navigation_unknown')&quality.complete,quality.travel_cost/quality.truth_optimum,np.nan);assert quality.static_stretch.dropna().ge(1-1e-6).all();common.save(quality,out/'navigation_quality.csv')
 changes=[]
 for job in manifest['plan']:
  if job['mode']!='navigation' or not job['name'].endswith('dynamic'):continue
  d=read(directory/('timing_'+job['name']+'_runs.csv'));d=d[d.repeat.eq(0)]
  for _,v in d.iterrows():
   c=ctx[v['case']];n=int(np.prod(c['shape']));changes.append(dict(case=v['case'],method=v.method,map=c['map'],k=c['params']['k'],n=c['params']['n'],requested_cr=c['params']['cr'],phases=v.phases,clamped=v.clamped_phases,actual_cr=100*v.actual_changes/(n*v.phases) if v.phases else 0))
 common.save(pd.DataFrame(changes),out/'actual_changes.csv')
 failures=q[q.cohort.ne('replay')&q.status.eq('no_path')].copy();failures['truth_reachable']=failures.truth_cost.notna();assert not failures.loc[failures.cohort.eq('navigation_unknown'),'truth_reachable'].any();common.save(failures[['case','method','cohort','map','step','truth_reachable','truth_cost']],out/'failure_diagnostics.csv')
 # A separate counter binary measures every Grid.free API invocation for all
 # replay methods. Its timing columns are never imported as performance data.
 ps=json.loads((HERE/'results/probes/experiment.json').read_text());assert ps['status']=='passed' and ps['source_sha256']==common.sha(HERE/'probe.py');probe=[];probe_matches=0
 for job in ps['jobs']:
  p=HERE/'results/probes'/(job['name']+'.csv');assert common.sha(p)==job['csv_sha256'] and common.sha(Path(str(p)+'.json'))==job['metadata_sha256'];actual=read(p).set_index(['case','method','query']).sort_index();reference=read(directory/('timing_'+job['name']+'.csv'));reference=reference[reference.repeat.eq(0)].set_index(['case','method','query']).sort_index();fields=[c for c in reference if not c.endswith('_s') and c not in ['peak_heap_bytes','retained_heap_bytes']];assert_frame_equal(actual[fields],reference[fields],check_exact=True,check_dtype=False);probe_matches+=len(actual)
  assert actual[actual.index.get_level_values('method').isin(NATIVE)].all_free_calls.eq(actual.loc[actual.index.get_level_values('method').isin(NATIVE),'checked_cells']).all()
  probe.append(actual.reset_index())
 probe=pd.concat(probe,ignore_index=True);probe['online_calls']=np.where(probe['query'].gt(0),probe.all_free_calls,0);pw=probe.groupby(['case','method'],as_index=False)[['all_free_calls','online_calls']].sum().merge(meta,on='case');common.save(pw,out/'collision_probes.csv')
 dispersion=[]
 for key,d in r.groupby(['case','method']):
  v=d.full_s.median();dispersion.append(dict(case=key[0],method=key[1],relative_mad=float((d.full_s-v).abs().median()/v)))
 dispersion=pd.DataFrame(dispersion);common.save(dispersion,out/'dispersion.csv')
 figs={};plt.rcParams.update({'font.size':9,'pdf.fonttype':42,'axes.spines.top':False,'axes.spines.right':False})
 colors={'mesh_mpgaa':'#777777','trigger_mesh':'#e69f00','cascade_mesh':'#0072b2','lba_reuse':'#444444','batch_mpgaa':'#009e73','conditional_dstar':'#cc79a7','cmesh_dstar':'#d55e00','contour_only':'#56b4e9','cascade_heap':'#882255'}
 fig,axes=plt.subplots(1,2,figsize=(11,4))
 for ax,control in zip(axes,['car16','grid8']):
  for method in NEW:
   for baseline,ls in [('best_control','-'),('mesh_mpgaa','--')]:
    v=np.sort(pairs[pairs.control.eq(control)&pairs.cohort.eq('replay')&pairs.panel.eq('main')&pairs.method.eq(method)&pairs.baseline.eq(baseline)].full_speedup.dropna());ax.step(v,np.arange(1,len(v)+1)/len(v),where='post',color=colors[method],ls=ls,label=LABEL[method]+' / '+LABEL[baseline])
  ax.axvline(1,color='.5',ls=':');ax.set(xscale='log',title=control,xlabel='Episode speedup',ylabel='Fraction of common completed cases');ax.legend(fontsize=7)
 figure(fig,'profile',figs)
 fig,axes=plt.subplots(1,2,figsize=(11,4))
 for ax,baseline in zip(axes,['best_control','mesh_mpgaa']):
  d=maps[maps.cohort.eq('replay')&maps.control.eq('car16')&maps.baseline.eq(baseline)];names=sorted(d['map'].unique());x=np.arange(len(names))
  for i,method in enumerate(NEW):ax.barh(x+(i-.5)*.35,[d[d['map'].eq(n)&d.method.eq(method)].iloc[0].full_speedup for n in names],.35,label=LABEL[method],color=colors[method])
  ax.set_yticks(x,names);ax.axvline(1,color='.5',ls=':');ax.set(xscale='log',title=LABEL[baseline],xlabel='Episode speedup');ax.legend(fontsize=8)
 figure(fig,'maps',figs)
 fig,axes=plt.subplots(1,3,figsize=(12,4))
 car=work[work.control.eq('car16')&work.cohort.eq('replay')&work.family.ne('history')]
 for ax,column,title in zip(axes,['notify_probes','mv_heap_pushes','mv_repair_heap_pushes'],['Opening notification candidates','Search heap insertions','Repair heap insertions']):
  methods=['mesh_mpgaa','trigger_mesh','contour_only','cascade_mesh'];v=[car.loc[car.method.eq(m),column].sum() for m in methods];ax.bar(range(4),np.asarray(v)+1,color=[colors.get(m,'#999999') for m in methods]);ax.set_xticks(range(4),[LABEL[m] for m in methods],rotation=35,ha='right');ax.set(yscale='log',title=title,ylabel='Total logical events + 1')
 figure(fig,'mechanism',figs)
 fig,axes=plt.subplots(2,3,figsize=(12,7),sharex=True)
 for ax,(name,d) in zip(axes.flat,metrics[metrics.cohort.eq('navigation_unknown')].groupby('map')):
  for method in ['cascade_mesh','mesh_mpgaa','lba_reuse','batch_mpgaa','conditional_dstar']:
   v=d[d.method.eq(method)];g=v[v.complete].groupby('radius').full_s.apply(common.gm);ax.plot(g.index,1000*g,'o-',label=LABEL[method],color=colors[method]);f=v[~v.complete];ax.scatter(f.radius,1000*f.full_s,marker='x',color=colors[method])
  ax.set(yscale='log',title=name,xlabel='Discovery radius, cells',ylabel='Planner time, ms');ax.set_xticks([8,16,32,64])
 axes[0,0].legend(fontsize=7);figure(fig,'radius',figs)
 fig,axes=plt.subplots(1,2,figsize=(11,4))
 for ax,control in zip(axes,['car16','grid8']):
  for method in ['mesh_mpgaa','trigger_mesh','cascade_mesh','lba_reuse','batch_mpgaa']:
   d=edit[edit.control.eq(control)&edit.cohort.eq('replay')&edit.method.eq(method)];ax.plot(d.edit_bin,d.median_ms,'o-',label=LABEL[method],color=colors[method])
  ax.set(yscale='log',title=control,xlabel='Observed edits per repair query',ylabel='Median time, ms');ax.legend(fontsize=7)
 figure(fig,'edits',figs)
 fig,axes=plt.subplots(1,2,figsize=(11,4))
 for ax,control in zip(axes,['car16','grid8']):
  methods=['mesh_mpgaa','trigger_mesh','cascade_mesh','batch_mpgaa','conditional_dstar','cmesh_dstar'];d=metrics[metrics.control.eq(control)];ax.boxplot([d[d.method.eq(m)].peak_heap_bytes/2**20 for m in methods],tick_labels=[LABEL[m] for m in methods],showfliers=False);ax.tick_params(axis='x',rotation=35,labelsize=8);ax.set(yscale='log',title=control,ylabel='Requested peak heap, MiB')
 figure(fig,'memory',figs)
 fig,axes=plt.subplots(1,2,figsize=(11,4))
 for ax,control in zip(axes,['car16','grid8']):
  for method in NEW:
   rows=[]
   for n,d in amort[amort.control.eq(control)&amort.family.ne('history')].groupby('repairs'):
    a=d[d.method.eq(method)].set_index('case');b=d[d.method.eq('mesh_mpgaa')].set_index('case');good=a.complete&b.complete;rows.append((n,common.gm(b.loc[good,'seconds']/a.loc[good,'seconds'])))
   ax.plot([p[0] for p in rows],[p[1] for p in rows],'o-',label=LABEL[method],color=colors[method])
  ax.axhline(1,color='.5',ls=':');ax.set(title=control,xlabel='Number of repairs after initial search',ylabel='Cumulative speedup vs native Mesh-MPGAA*');ax.legend(fontsize=8)
 figure(fig,'amortization',figs)
 assert len(r)==manifest['timed_runs'] and len(metrics)==manifest['memory_runs']
 result=dict(status='passed',scenarios=manifest['scenarios'],timed_runs=len(r),memory_runs=len(metrics),timed_calls=len(calls),allocation_matched_rows=matched,exact_cost_disagreements=bad,capped_calls=int(calls.status.eq('capped').sum()),contour_equivalence_queries=len(aa),count_only_runs=sum(j['runs'] for j in ps['jobs']),count_only_matched_rows=probe_matches,relative_mad_median=float(dispersion.relative_mad.median()),relative_mad_p95=float(dispersion.relative_mad.quantile(.95)),analysis_versions=dict(numpy=np.__version__,pandas=pd.__version__,matplotlib=plt.matplotlib.__version__),manifest_sha256=common.sha(HERE/'frozen/manifest.json'),source_sha256=common.sha(Path(__file__)),probe_experiment_sha256=common.sha(HERE/'results/probes/experiment.json'),tables_sha256={p.name:common.sha(p) for p in sorted(out.glob('*.csv'))},figures_sha256=figs)
 (out/'analysis.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if not k.endswith('sha256')}))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,default=HERE/'results/full');main(p.parse_args().directory)
