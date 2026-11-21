#!/usr/bin/env python3
"""Validate and aggregate only this study's fresh joint measurements."""
import argparse,json,sys
from pathlib import Path
import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];DEST=ROOT/'docs/mesh_lift'
sys.path.insert(0,str(ROOT/'cpp/mesh_envelope'))
import analyze as common
import matplotlib.pyplot as plt
NATIVE=['lift_mesh','cascade_lift','lift_cold','lift_noprune','cascade_cold','cascade_mesh']
MESH_CONTROLS=['mesha','mesha_reuse','cmesh_dstar','cascade_mesh','lift_cold','cascade_cold','lift_noprune']
LABEL={**common.LABEL,'lift_mesh':'Lift-Mesh','cascade_lift':'Cascade-Lift','cascade_mesh':'Cascade-Mesh','lift_cold':'Lift, cold','cascade_cold':'Cascade, cold','lift_noprune':'Cascade, no terminal pruning','mesha_reuse':'MeshA* reuse','best_mesh':'Fastest mesh control','conditional_dstar':'Conditional D* Lite'}
NEW=['lift_mesh','cascade_lift'];CORE=['expansions','checked_cells','notify_probes','heuristic_pops','backend_calls','certified']
SNAP=['mv_active_watches','mv_records'];HASH=['path_hash','world_hash','belief_hash','fingerprint','mv_trace_hash']
def read(p):return pd.read_csv(p,dtype={k:str for k in HASH})
def figure(fig,name,manifest):
 old=common.DEST;common.DEST=DEST
 try:common.figure(fig,name,manifest)
 finally:common.DEST=old
def main(directory,probes):
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
 counters=CORE+[c for c in calls if (c.startswith('mv_') or c.startswith('lift_')) and c not in SNAP+['mv_trace_hash']]
 q=calls[calls.repeat.eq(0)].copy();q['observed_edits']=q.blocks+q.opens
 finite=calls.cost.notna()&calls.expected.notna();bad=int((calls.loc[finite,'cost']-calls.loc[finite,'expected']).abs().gt(1e-6).sum());bad+=int(((calls.cost.notna()!=calls.expected.notna())&~calls.status.isin(['capped','skipped_after_cap'])).sum());assert bad==0
 native=q[q.method.isin(NATIVE)];assert native.expansions.eq(native.mv_boundary_expansions+native.mv_interior_expansions).all()
 assert native[native.control.eq('car16')].mv_interior_expansions.sum()>0
 replay=q[q.cohort.eq('replay')]
 mutation=json.loads((HERE/'validation/mutation.json').read_text());assert mutation['status']=='passed'
 opening_fixture=json.loads((HERE/'validation/repair_counterexample.json').read_text());assert opening_fixture['status']=='passed' and opening_fixture['original_source_sha256']==common.sha(HERE/'algorithms.hpp') and opening_fixture['script_sha256']==common.sha(HERE/'repair_counterexample.py')
 assert opening_fixture['result']['oracle_after_openings']==opening_fixture['result']['lift_cost']==opening_fixture['result']['cascade_lift_cost']==4 and opening_fixture['result']['no_closure_cost']==opening_fixture['result']['no_learned_mark_cost']==5
 assert native.lift_terminal_prunes.sum()>0 and native.lift_writes.sum()>0
 work=q.groupby(['case','method'],as_index=False)[['blocks','opens','observed_edits',*counters]].sum().merge(meta,on='case');common.save(work,out/'work.csv')
 snapshots=q.groupby(['case','method'],as_index=False)[SNAP].max();common.save(snapshots.merge(meta,on='case'),out/'max_state.csv')
 metrics=r.groupby(['case','method'],as_index=False)[['full_s','initial_s','repair_s','travel_cost','moves','plans']].median().merge(r.groupby(['case','method'],as_index=False).complete.all()).merge(pd.concat(memory),on=['case','method']).merge(meta,on='case');common.save(metrics,out/'case_metrics.csv')
 common.save(metrics.groupby(['cohort','control','method'],as_index=False).agg(configurations=('case','size'),complete=('complete','sum')),out/'completion.csv')
 common.save(calls[calls.status.eq('capped')][['case','method','repeat','query','expansions']],out/'caps.csv')
 pairs=[]
 for case,g in metrics.groupby('case'):
  old=g[g.method.isin(manifest['controls'])&g.complete];best=old.sort_values('full_s').iloc[0] if len(old) else None
  mesh=g[g.method.isin(MESH_CONTROLS)&g.complete];bestmesh=mesh.sort_values('full_s').iloc[0] if len(mesh) else None
  for method in NEW:
   a=g[g.method.eq(method)].iloc[0]
   for baseline in dict.fromkeys([*manifest['controls'],*manifest['ablations'],*NEW,'best_control','best_mesh']):
    if method==baseline:continue
    b=best if baseline=='best_control' else bestmesh if baseline=='best_mesh' else (g[g.method.eq(baseline)].iloc[0] if g.method.eq(baseline).any() else None)
    if b is None and baseline not in ['best_control','best_mesh']:continue
    ok=bool(a.complete and b is not None and b.complete)
    pairs.append(dict(case=case,method=method,baseline=baseline,selected_control='none' if b is None else b.method,cohort=a.cohort,control=a.control,map=a['map'],family=a.family,panel=a.panel,seed=a.seed,radius=a.radius,k=a.k,cr=a.cr,complete=ok,full_speedup=b.full_s/a.full_s if ok else np.nan,initial_speedup=b.initial_s/a.initial_s if ok and a.initial_s>0 else np.nan,repair_speedup=b.repair_s/a.repair_s if ok and a.repair_s>0 else np.nan,memory_multiplier=a.peak_heap_bytes/b.peak_heap_bytes if ok else np.nan))
 pairs=pd.DataFrame(pairs);common.save(pairs,out/'paired_cases.csv')
 def aggregate(keys,name):
  rows=[]
  for key,d in pairs.groupby(keys):
   if not isinstance(key,tuple):key=(key,)
   rows.append(dict(zip(keys,key))|dict(configurations=len(d),pairs=int(d.complete.sum()),full_speedup=common.gm(d.full_speedup),initial_speedup=common.gm(d.initial_speedup),repair_speedup=common.gm(d.repair_speedup),memory_multiplier=common.gm(d.memory_multiplier),wins10=int(d.full_speedup.ge(1.1).sum())))
  frame=pd.DataFrame(rows);common.save(frame,out/name);return frame
 summary=aggregate(['cohort','control','panel','method','baseline'],'summary.csv');maps=aggregate(['cohort','control','panel','map','method','baseline'],'map_pairs.csv');aggregate(['cohort','control','family','method','baseline'],'family_pairs.csv');aggregate(['cohort','control','map','radius','k','cr','method','baseline'],'parameter_pairs.csv')
 # Initial-search comparisons use initial completion only; a later cap must
 # not silently remove a difficult but solved first search from this panel.
 initial=metrics.merge(q[q['query'].eq(0)][['case','method','status','cost','expected','expansions','lift_terminal_prunes']],on=['case','method']);initial['initial_complete']=~initial.status.isin(['capped','skipped_after_cap']);common.save(initial,out/'initial_cases.csv')
 ip=[]
 for case,g in initial.groupby('case'):
  for method in NEW:
   v=g[g.method.eq(method)].iloc[0]
   for baseline in dict.fromkeys([*manifest['controls'],*manifest['ablations']]):
    b=g[g.method.eq(baseline)]
    if b.empty:continue
    b=b.iloc[0];ok=bool(v.initial_complete and b.initial_complete)
    ip.append(dict(case=case,cohort=v.cohort,control=v.control,panel=v.panel,map=v['map'],method=method,baseline=baseline,complete=ok,speedup=b.initial_s/v.initial_s if ok else np.nan))
 ip=pd.DataFrame(ip);common.save(ip,out/'initial_pairs.csv');rows=[]
 for key,d in ip.groupby(['cohort','control','panel','method','baseline']):rows.append(dict(zip(['cohort','control','panel','method','baseline'],key))|dict(configurations=len(d),pairs=int(d.complete.sum()),initial_speedup=common.gm(d.speedup)))
 common.save(pd.DataFrame(rows),out/'initial_summary.csv')
 capq=q[q.status.eq('capped')].copy();capq['phase']=np.where(capq['query'].eq(0),'initial','repair');common.save(capq.groupby(['cohort','control','method','phase'],as_index=False).agg(configurations=('case','nunique'),calls=('case','size')),out/'cap_summary.csv')
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
   c=ctx[v['case']];n=int(np.prod(c['shape']));changes.append(dict(case=v['case'],method=v.method,map=c['map'],k=c['params']['k'],n=c['params']['n'],requested_cr=c['params']['cr'],phases=v.phases,clamped=v.clamped_phases,actual_cr=100*v.actual_changes/(n*v.phases) if v.phases else np.nan))
 common.save(pd.DataFrame(changes),out/'actual_changes.csv')
 failures=q[q.cohort.ne('replay')&q.status.eq('no_path')].copy();failures['truth_reachable']=failures.truth_cost.notna();assert not failures.loc[failures.cohort.eq('navigation_unknown'),'truth_reachable'].any();common.save(failures[['case','method','cohort','map','step','truth_reachable','truth_cost']],out/'failure_diagnostics.csv')
 # A separate counter binary measures every Grid.free API invocation for all
 # replay methods. Its timing columns are never imported as performance data.
 ps=json.loads((probes/'experiment.json').read_text());assert ps['status']=='passed' and ps['source_sha256']==common.sha(HERE/'probe.py');probe=[];probe_matches=0
 for job in ps['jobs']:
  p=probes/(job['name']+'.csv');assert common.sha(p)==job['csv_sha256'] and common.sha(Path(str(p)+'.json'))==job['metadata_sha256'];actual=read(p).set_index(['case','method','query']).sort_index();reference=read(directory/('timing_'+job['name']+'.csv'));reference=reference[reference.repeat.eq(0)].set_index(['case','method','query']).sort_index();fields=[c for c in reference if not c.endswith('_s') and c not in ['peak_heap_bytes','retained_heap_bytes']];assert_frame_equal(actual[fields],reference[fields],check_exact=True,check_dtype=False);probe_matches+=len(actual)
  assert actual[actual.index.get_level_values('method').isin(NATIVE)].all_free_calls.eq(actual.loc[actual.index.get_level_values('method').isin(NATIVE),'checked_cells']).all()
  probe.append(actual.reset_index())
 probe=pd.concat(probe,ignore_index=True);probe['online_calls']=np.where(probe['query'].gt(0),probe.all_free_calls,0);pw=probe.groupby(['case','method'],as_index=False)[['all_free_calls','online_calls']].sum().merge(meta,on='case');common.save(pw,out/'collision_probes.csv')
 lookup=pw.set_index(['case','method']);probe_pairs=[]
 for _,v in pairs[pairs.cohort.eq('replay')].iterrows():
  aa_probe=lookup.loc[(v['case'],v.method)];bb_probe=lookup.loc[(v['case'],v.selected_control)] if v.selected_control!='none' else None
  probe_pairs.append(dict(case=v['case'],control=v.control,panel=v.panel,method=v.method,baseline=v.baseline,complete=v.complete,full_api_ratio=bb_probe.all_free_calls/aa_probe.all_free_calls if v.complete and bb_probe is not None and aa_probe.all_free_calls>0 else np.nan,repair_api_ratio=bb_probe.online_calls/aa_probe.online_calls if v.complete and bb_probe is not None and aa_probe.online_calls>0 else np.nan))
 common.save(pd.DataFrame(probe_pairs),out/'collision_pairs.csv')
 dispersion=[]
 for key,d in r.groupby(['case','method']):
  v=d.full_s.median();dispersion.append(dict(case=key[0],method=key[1],relative_mad=float((d.full_s-v).abs().median()/v)))
 dispersion=pd.DataFrame(dispersion);common.save(dispersion,out/'dispersion.csv')
 figs={};plt.rcParams.update({'font.size':9,'pdf.fonttype':42,'axes.spines.top':False,'axes.spines.right':False})
 colors={'lift_mesh':'#e69f00','cascade_lift':'#0072b2','mesha_reuse':'#882255','lift_cold':'#999999','cascade_cold':'#56b4e9','lift_noprune':'#cc79a7','mesh_mpgaa':'#777777','trigger_mesh':'#e69f00','cascade_mesh':'#0072b2','lba_reuse':'#444444','batch_mpgaa':'#009e73','conditional_dstar':'#cc79a7','cmesh_dstar':'#d55e00','contour_only':'#56b4e9','cascade_heap':'#882255'}
 fig,axes=plt.subplots(1,2,figsize=(11,4))
 for ax,control in zip(axes,['car16','grid8']):
  for method in NEW:
   for baseline,ls in [('best_control','-'),('cascade_mesh','--')]:
    v=np.sort(pairs[pairs.control.eq(control)&pairs.cohort.eq('replay')&pairs.panel.eq('main')&pairs.method.eq(method)&pairs.baseline.eq(baseline)].full_speedup.dropna());ax.step(v,np.arange(1,len(v)+1)/len(v),where='post',color=colors[method],ls=ls,label=LABEL[method]+' / '+LABEL[baseline])
  ax.axvline(1,color='.5',ls=':');ax.set(xscale='log',title=control,xlabel='Episode speedup',ylabel='Fraction of common completed cases');ax.legend(fontsize=7)
 figure(fig,'profile',figs)
 fig,axes=plt.subplots(1,2,figsize=(11,4))
 for ax,baseline in zip(axes,['best_control','cascade_mesh']):
  d=maps[maps.cohort.eq('replay')&maps.control.eq('car16')&maps.panel.eq('main')&maps.baseline.eq(baseline)];names=sorted(d['map'].unique());x=np.arange(len(names))
  for i,method in enumerate(NEW):ax.barh(x+(i-.5)*.35,[d[d['map'].eq(n)&d.method.eq(method)].iloc[0].full_speedup for n in names],.35,label=LABEL[method],color=colors[method])
  ax.set_yticks(x,names);ax.axvline(1,color='.5',ls=':');ax.set(xscale='log',title=LABEL[baseline],xlabel='Episode speedup');ax.legend(fontsize=8)
 figure(fig,'maps',figs)
 fig,axes=plt.subplots(1,2,figsize=(11,4))
 d=maps[maps.cohort.eq('replay')&maps.control.eq('car16')&maps.panel.eq('main')&maps.baseline.eq('mesha_reuse')];names=sorted(d['map'].unique());x=np.arange(len(names))
 for ax,column,title in zip(axes,['full_speedup','repair_speedup'],['Whole episode vs MeshA* reuse','Repair vs MeshA* reuse']):
  for i,method in enumerate(NEW):ax.barh(x+(i-.5)*.35,[d[d['map'].eq(name)&d.method.eq(method)].iloc[0][column] for name in names],.35,label=LABEL[method],color=colors[method])
  ax.set_yticks(x,names);ax.axvline(1,color='.5',ls=':');ax.set(xscale='log',title=title,xlabel='Speedup on common completed pairs');ax.legend(fontsize=8)
 figure(fig,'mesh_comparisons',figs)
 fig,axes=plt.subplots(1,3,figsize=(12,4))
 car=work[work.control.eq('car16')&work.cohort.eq('replay')&work.family.ne('history')]
 for ax,column,title in zip(axes,['mv_interior_expansions','mv_heap_pushes','lift_writes'],['Internal mesh expansions','Search heap insertions','Local h writes']):
  methods=['cascade_mesh','lift_noprune','lift_mesh','cascade_lift'];v=[car.loc[car.method.eq(m),column].sum() for m in methods];ax.bar(range(4),np.asarray(v)+1,color=[colors.get(m,'#999999') for m in methods]);ax.set_xticks(range(4),[LABEL[m] for m in methods],rotation=35,ha='right');ax.set(yscale='log',title=title,ylabel='Total logical events + 1')
 figure(fig,'mechanism',figs)
 fig,axes=plt.subplots(2,3,figsize=(12,7),sharex=True)
 for ax,(name,d) in zip(axes.flat,metrics[metrics.cohort.eq('navigation_unknown')].groupby('map')):
  for method in ['cascade_lift','lift_mesh','mesha_reuse','batch_mpgaa','conditional_dstar']:
   v=d[d.method.eq(method)];g=v[v.complete].groupby('radius').full_s.apply(common.gm);ax.plot(g.index,1000*g,'o-',label=LABEL[method],color=colors[method]);f=v[~v.complete];ax.scatter(f.radius,1000*f.full_s,marker='x',color=colors[method])
  ax.set(yscale='log',title=name,xlabel='Discovery radius, cells',ylabel='Planner time, ms');ax.set_xticks([8,16,32,64])
 axes[0,0].legend(fontsize=7);figure(fig,'radius',figs)
 fig,axes=plt.subplots(1,2,figsize=(11,4))
 for ax,control in zip(axes,['car16','grid8']):
  for method in ['lift_mesh','cascade_lift','mesha_reuse','lba_reuse','batch_mpgaa']:
   d=edit[edit.control.eq(control)&edit.cohort.eq('replay')&edit.method.eq(method)];ax.plot(d.edit_bin,d.median_ms,'o-',label=LABEL[method],color=colors[method])
  ax.set(yscale='log',title=control,xlabel='Observed edits per repair query',ylabel='Median time, ms');ax.legend(fontsize=7)
 figure(fig,'edits',figs)
 fig,axes=plt.subplots(1,2,figsize=(11,4))
 for ax,control in zip(axes,['car16','grid8']):
  methods=['lift_mesh','cascade_lift','mesha_reuse','batch_mpgaa','conditional_dstar','cmesh_dstar'];d=metrics[metrics.control.eq(control)];ax.boxplot([d[d.method.eq(m)].peak_heap_bytes/2**20 for m in methods],tick_labels=[LABEL[m] for m in methods],showfliers=False);ax.tick_params(axis='x',rotation=35,labelsize=8);ax.set(yscale='log',title=control,ylabel='Requested peak heap, MiB')
 figure(fig,'memory',figs)
 fig,axes=plt.subplots(1,2,figsize=(11,4))
 for ax,control in zip(axes,['car16','grid8']):
  for method in NEW:
   rows=[]
   for n,d in amort[amort.control.eq(control)&amort.family.ne('history')].groupby('repairs'):
    a=d[d.method.eq(method)].set_index('case');b=d[d.method.eq('cascade_mesh')].set_index('case');good=a.complete&b.complete;rows.append((n,common.gm(b.loc[good,'seconds']/a.loc[good,'seconds'])))
   ax.plot([p[0] for p in rows],[p[1] for p in rows],'o-',label=LABEL[method],color=colors[method])
  ax.axhline(1,color='.5',ls=':');ax.set(title=control,xlabel='Number of repairs after initial search',ylabel='Cumulative speedup vs previous Cascade-Mesh');ax.legend(fontsize=8)
 figure(fig,'amortization',figs)
 fig,axes=plt.subplots(1,3,figsize=(12,4))
 for ax,cohort in zip(axes,['replay','navigation_unknown','navigation_dynamic']):
  d=metrics[metrics.control.eq('car16')&metrics.cohort.eq(cohort)];methods=[m for m in ['cascade_mesh','lift_mesh','cascade_lift','lift_cold','cascade_cold','mesha_reuse','batch_mpgaa','conditional_dstar'] if d.method.eq(m).any()];vals=[d[d.method.eq(m)].complete.mean() for m in methods]
  ax.bar(range(len(methods)),vals,color=[colors.get(m,'#999999') for m in methods]);ax.set_xticks(range(len(methods)),[LABEL[m] for m in methods],rotation=40,ha='right',fontsize=7);ax.set(ylim=(0,1.08),title=cohort,ylabel='Completed fraction')
 figure(fig,'completion',figs)
 from matplotlib.patches import FancyArrowPatch
 fig,ax=plt.subplots(figsize=(10,3.3));positions={'s':(0,.7),'u':(1,0),'w':(2,0),'v':(3,.7),'t':(4.4,.7)}
 for u,v,c in [('s','v','2'),('s','u','1'),('u','w','0.5'),('w','v','1.5'),('v','t','10')]:
  x,y=positions[u];xx,yy=positions[v];arrow=FancyArrowPatch((x,y),(xx,yy),arrowstyle='-|>',mutation_scale=14,shrinkA=16,shrinkB=16,lw=1.4,color='#444444');ax.add_patch(arrow);ax.text((x+xx)/2,(y+yy)/2+.10,c,ha='center',fontsize=11)
 labels={'s':'0 to 12','u':'2 to 11','w':'1.5 to 10.5','v':'0 to 10','t':'0 to 0'}
 for name,(x,y) in positions.items():
  ax.scatter([x],[y],s=900,color='#e69f00' if name=='w' else '#56b4e9' if name=='u' else '#dddddd',edgecolor='#444444',zorder=3);ax.text(x,y,name,ha='center',va='center',zorder=4,fontsize=12);ax.text(x,y-.32,'h: '+labels[name],ha='center',fontsize=10)
 ax.text(1,-.65,'u is pruned after v is CLOSED',ha='center',fontsize=10);ax.text(3,-.65,'Lift raises skipped w; v is unchanged',ha='center',fontsize=10);ax.set(xlim=(-.6,4.9),ylim=(-.9,1.2),title='Consistency closure in a skipped mesh prefix');ax.axis('off');figure(fig,'lift_example',figs)
 assert len(r)==manifest['timed_runs'] and len(metrics)==manifest['memory_runs']
 result=dict(status='passed',scenarios=manifest['scenarios'],timed_runs=len(r),memory_runs=len(metrics),timed_calls=len(calls),allocation_matched_rows=matched,exact_cost_disagreements=bad,capped_calls=int(calls.status.eq('capped').sum()),mutation_detected=True,opening_counterexample=opening_fixture['result'],repair_counterexample_sha256=common.sha(HERE/'validation/repair_counterexample.json'),terminal_prunes=int(native.lift_terminal_prunes.sum()),lift_writes=int(native.lift_writes.sum()),count_only_runs=sum(j['runs'] for j in ps['jobs']),count_only_matched_rows=probe_matches,relative_mad_median=float(dispersion.relative_mad.median()),relative_mad_p95=float(dispersion.relative_mad.quantile(.95)),analysis_versions=dict(numpy=np.__version__,pandas=pd.__version__,matplotlib=plt.matplotlib.__version__),manifest_sha256=common.sha(HERE/'frozen/manifest.json'),source_sha256=common.sha(Path(__file__)),probe_experiment_sha256=common.sha(probes/'experiment.json'),tables_sha256={p.name:common.sha(p) for p in sorted(out.glob('*.csv'))},figures_sha256=figs)
 (out/'analysis.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if not k.endswith('sha256')}))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,default=HERE/'results/full');p.add_argument('--probes',type=Path,default=HERE/'results/probes');args=p.parse_args();main(args.directory,args.probes)
