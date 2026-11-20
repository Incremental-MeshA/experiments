#!/usr/bin/env python3
"""Rebuild all tables and scientific figures solely from the frozen raw cohort."""
import argparse,hashlib,json,math,statistics,sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pandas.testing import assert_frame_equal
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];DEST=ROOT/'docs/mesh_envelope'
NEW=['envelope_mesh','dual_mesh','circuit_mesh']
ABLATION=['mesh_cold','mesh_reuse','cut_mesh','lattice_envelope']
LABEL={'envelope_mesh':'Envelope-Mesh','dual_mesh':'Dual-Mesh','circuit_mesh':'Circuit-Mesh','lattice_envelope':'Lattice-Envelope',
       'mesh_cold':'Mesh cold','mesh_reuse':'Mesh reuse','cut_mesh':'Cut reset','lba_reuse':'LBA* reuse','mesha':'MeshA*','mpgaa':'MPGAA*',
       'md_astar':'MD-A*','boundary_mesh':'Boundary-Mesh','boundary_mpgaa':'Boundary-MPGAA*','delta_mpgaa':'Delta-MPGAA*',
       'batch_mpgaa':'Batch-MPGAA*','dstar_lattice':'D* Lite lattice','cmesh_dstar':'C-Mesh-D* Lite','octile_reuse':'Octile reuse','best_control':'Fastest control'}
COLORS={'envelope_mesh':'#0072b2','dual_mesh':'#009e73','circuit_mesh':'#d55e00','lattice_envelope':'#cc79a7',
        'mesh_cold':'#999999','mesh_reuse':'#e69f00','cut_mesh':'#56b4e9','lba_reuse':'#444444','dstar_lattice':'#332288'}
COUNTERS=['expansions','checked_cells','notify_probes','heuristic_pops','backend_calls','certified','envelope_hits','envelope_builds','envelope_added','guard_installs','guard_events','frontier_tests','endpoint_tests','envelope_goal','circuit_nodes','circuit_stops','circuit_rows']
INTKEY=['case','method','query']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def gm(xs):
 a=np.asarray(xs,dtype=float);a=a[np.isfinite(a)&(a>0)]
 return float(np.exp(np.mean(np.log(a)))) if len(a) else float('nan')
def read(p):return pd.read_csv(p,dtype={k:str for k in ['path_hash','world_hash','belief_hash','fingerprint']})
def save(df,p):df.to_csv(p,index=False,float_format='%.17g')
def figure(fig,name,manifest):
 fig.tight_layout();folder=DEST/'figures';folder.mkdir(parents=True,exist_ok=True)
 for ext in ['png','pdf']:
  p=folder/(name+'.'+ext);fig.savefig(p,dpi=170,metadata={'CreationDate':None,'ModDate':None} if ext=='pdf' else {'Software':'mesh-envelope-analysis'});manifest[str(p.relative_to(ROOT))]=sha(p)
 plt.close(fig)
def main(directory):
 manifest=json.loads((HERE/'frozen/manifest.json').read_text());state=json.loads((directory/'experiment.json').read_text());assert state['status']=='passed'
 assert state['manifest_sha256']==sha(HERE/'frozen/manifest.json')
 for p,h in {**manifest['files'],**manifest['sources']}.items():assert sha(ROOT/p)==h,p
 for job in state['jobs'].values():
  assert job['status']=='passed'
  for p,h in job['outputs'].items():assert sha(directory/p)==h,p
 contexts=json.loads((HERE/'frozen/contexts.json').read_text());meta=pd.DataFrame([dict(case=k,cohort=v['cohort'],control=v['control'],map=v['map'],family=v['family'],seed=v.get('seed',0),radius=v.get('params',{}).get('radius',v.get('radius',0))) for k,v in contexts.items()])
 out=directory/'analysis';out.mkdir(exist_ok=True);runs=[];calls=[];memory=[];matched=0;alloc=[];normal=[]
 for job in manifest['plan']:
  stem=job['name'];nav=job['mode']=='navigation';tp=directory/('timing_'+stem);mp=directory/('memory_'+stem)
  tc=read(Path(str(tp)+'_calls.csv') if nav else tp.with_suffix('.csv'));mc=read(Path(str(mp)+'_calls.csv') if nav else mp.with_suffix('.csv'))
  first=tc[tc.repeat.eq(0)].set_index(INTKEY).sort_index();profile=mc.set_index(INTKEY).sort_index()
  fields=[c for c in first if c in profile and not c.endswith('_s') and c not in ['repeat','peak_heap_bytes','retained_heap_bytes']]
  assert_frame_equal(first[fields],profile[fields],check_dtype=False,check_exact=True);matched+=len(first)
  assert (mc.peak_heap_bytes>=mc.retained_heap_bytes).all() and (mc.peak_heap_bytes<2**48).all()
  alloc.append(mc.assign(job=stem));normal.append(tc.assign(job=stem))
  group=['case','method','repeat']
  if nav:
   tr=read(Path(str(tp)+'_runs.csv'));mr=read(Path(str(mp)+'_runs.csv'))
   for _,row in tr.iterrows():
    d=row.to_dict();d['full_s']=d['setup_s']+d['planner_s'];d['complete']=d['status']=='goal';d['initial_s']=d['initial_s'];d['repair_s']=d['repair_s'];runs.append(d)
   memory.append(mr[['case','method','peak_heap_bytes','retained_heap_bytes']])
  else:
   for keys,d in tc.groupby(group,sort=False):
    row=dict(zip(group,keys));row.update(full_s=d.time_s.sum()+d.setup_s.sum(),setup_s=d.setup_s.sum(),initial_s=d.loc[d['query'].eq(0),'time_s'].sum(),repair_s=d.loc[d['query'].gt(0),'time_s'].sum(),complete=not d.status.isin(['capped','skipped_after_cap']).any(),status='capped' if d.status.eq('capped').any() else 'complete',plans=int(d.planned.sum()),moves=0,travel_cost=0)
    for c in COUNTERS:row[c]=d[c].sum()
    runs.append(row)
   memory.append(mc.groupby(['case','method'],as_index=False).agg(peak_heap_bytes=('peak_heap_bytes','max'),retained_heap_bytes=('retained_heap_bytes','last')))
  calls.append(tc.assign(job=stem))
 allruns=pd.DataFrame(runs);save(allruns,out/'runs.csv');calls=pd.concat(calls,ignore_index=True).merge(meta,on='case',validate='many_to_one',suffixes=('','_context'));save(calls,out/'calls.csv')
 memories=pd.concat(memory,ignore_index=True);assert not memories.duplicated(['case','method']).any()
 numeric=['full_s','initial_s','repair_s','setup_s','travel_cost','moves','plans',*COUNTERS]
 numeric=[c for c in dict.fromkeys(numeric) if c in allruns]
 metrics=allruns.groupby(['case','method'],as_index=False)[numeric].median();complete=allruns.groupby(['case','method'],as_index=False).complete.all();metrics=metrics.merge(complete).merge(memories,on=['case','method']).merge(meta,on='case',validate='many_to_one');save(metrics,out/'case_metrics.csv')
 status=calls.groupby(['cohort','control','map','method','status'],as_index=False).size();save(status,out/'statuses.csv')
 disagreement=calls[calls.status.isin(['ok','no_path']) & (calls.cost.notna()!=calls.expected.notna())]
 finite=calls.cost.notna()&calls.expected.notna();badcost=(calls.loc[finite,'cost']-calls.loc[finite,'expected']).abs().gt(1e-6).sum();assert len(disagreement)==0 and badcost==0
 controls=manifest['controls'];pairs=[]
 for case,d in metrics.groupby('case',sort=False):
  old=d[d.method.isin(controls)&d.complete];best=old.sort_values('full_s').iloc[0] if len(old) else None
  for _,r in d[d.method.isin(NEW+ABLATION)].iterrows():
   for baseline in [*controls,*ABLATION,'best_control']:
    base=(best if baseline=='best_control' else (d[d.method.eq(baseline)].iloc[0] if d.method.eq(baseline).any() else None))
    if base is None or base['method']==r['method']:continue
    eligible=bool(r.complete and base.complete)
    pairs.append(dict(case=case,method=r.method,baseline=baseline,selected_control=base.method,cohort=r.cohort,control=r.control,map=r['map'],family=r.family,complete=eligible,
       full_speedup=base.full_s/r.full_s if eligible and r.full_s>0 else np.nan,repair_speedup=base.repair_s/r.repair_s if eligible and r.repair_s>0 else np.nan,
       memory_multiplier=r.peak_heap_bytes/base.peak_heap_bytes if eligible and base.peak_heap_bytes>0 else np.nan))
 pairs=pd.DataFrame(pairs);save(pairs,out/'paired_cases.csv')
 def aggregate(keys,name):
  rows=[]
  for key,d in pairs.groupby(keys,sort=False):
   if not isinstance(key,tuple):key=(key,)
   v=dict(zip(keys,key));v.update(configurations=len(d),pairs=int(d.complete.sum()),full_speedup=gm(d.full_speedup),repair_speedup=gm(d.repair_speedup),memory_multiplier=gm(d.memory_multiplier),wins_10pct=int(d.full_speedup.ge(1.1).sum()),losses_10pct=int(d.full_speedup.le(1/1.1).sum()))
   rows.append(v)
  frame=pd.DataFrame(rows);save(frame,out/name);return frame
 summary=aggregate(['cohort','control','method','baseline'],'summary.csv');maps=aggregate(['cohort','control','map','method','baseline'],'map_pairs.csv');families=aggregate(['cohort','control','family','method','baseline'],'family_pairs.csv')
 # Query medians preserve each experiment unit; repetitions do not inflate n.
 qkeys=['case','method','query'];qmedian=calls.groupby(qkeys,as_index=False).agg(time_s=('time_s','median'),cost=('cost','first'),expected=('expected','first'),blocks=('blocks','first'),opens=('opens','first'),status=('status','first'),**{c:(c,'first') for c in COUNTERS})
 qmedian=qmedian.merge(meta,on='case',validate='many_to_one');save(qmedian,out/'queries.csv')
 qp=[]
 for base in ['lba_reuse','mesh_reuse','cut_mesh','lattice_envelope','dstar_lattice','batch_mpgaa']:
  b=qmedian[qmedian.method.eq(base)].set_index(['case','query'])
  for c in NEW:
   a=qmedian[qmedian.method.eq(c)].set_index(['case','query']);ix=a.index.intersection(b.index);aa,bb=a.loc[ix],b.loc[ix]
   good=~aa.status.isin(['capped','skipped_after_cap'])&~bb.status.isin(['capped','skipped_after_cap'])
   for k in ix[good]:
    x,y=aa.loc[k],bb.loc[k];qp.append(dict(case=k[0],query=k[1],method=c,baseline=base,time_s=x.time_s,base_time_s=y.time_s,speedup=y.time_s/x.time_s if x.time_s>0 else np.nan,answer='no_path' if pd.isna(x.cost) else 'path',edits=x.blocks+x.opens,blocks=x.blocks,opens=x.opens,cohort=x.cohort,control=x.control,map=x['map'],family=x.family))
 qp=pd.DataFrame(qp);save(qp,out/'query_pairs.csv')
 latency=[]
 for key,d in qmedian[qmedian['query'].gt(0)&~qmedian.status.isin(['capped','skipped_after_cap'])].groupby(['cohort','control','map','method']):
  latency.append(dict(zip(['cohort','control','map','method'],key))|dict(queries=len(d),p50_ms=1000*d.time_s.quantile(.5),p95_ms=1000*d.time_s.quantile(.95),p99_ms=1000*d.time_s.quantile(.99)))
 save(pd.DataFrame(latency),out/'latency.csv')
 work=calls[calls.repeat.eq(0)].groupby(['cohort','control','map','method'],as_index=False)[COUNTERS].sum();save(work,out/'work.csv')
 # Prefix totals include cold construction and use medians of complete
 # within-repeat prefix totals; prefixes are not independent configurations.
 amort=[]
 for (case,method),d in calls[calls.cohort.eq('separator')].groupby(['case','method']):
  for n in [0,1,2,4,8,16]:
   x=d[d['query'].le(n)].groupby('repeat')[['time_s','setup_s']].sum().sum(axis=1)
   amort.append(dict(case=case,method=method,repairs=n,total_s=x.median()))
 amort=pd.DataFrame(amort).merge(meta,on='case');save(amort,out/'amortization.csv')
 # Dynamic rate denominator is the immutable grid cell population per phase.
 dyn=[]
 for job in manifest['plan']:
  if job['mode']!='navigation' or not job['name'].endswith('dynamic'):continue
  r=read(directory/('timing_'+job['name']+'_runs.csv'));r=r[r.repeat.eq(0)]
  for _,v in r.iterrows():
   c=contexts[v['case']];n=int(np.prod(c['shape']));params=c.get('params',{})
   dyn.append(dict(case=v['case'],method=v['method'],map=c['map'],control=c['control'],phases=v.phases,clamped_phases=v.clamped_phases,requested_changes=v.requested_changes,actual_changes=v.actual_changes,actual_cr_pct=100*v.actual_changes/(n*v.phases) if v.phases else 0,requested_cr_pct=params.get('cr',c.get('cr',np.nan))))
 save(pd.DataFrame(dyn),out/'actual_changes.csv')
 # Repeat dispersion of whole episodes, never of pooled correlated calls.
 dispersion=[]
 for key,d in allruns.groupby(['case','method']):
  med=d.full_s.median();dispersion.append(dict(case=key[0],method=key[1],relative_mad=float((d.full_s-med).abs().median()/med) if med else 0))
 dispersion=pd.DataFrame(dispersion);save(dispersion,out/'repeat_dispersion.csv')
 figmanifest={};plt.rcParams.update({'font.size':9,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42})
 fig,axes=plt.subplots(1,2,figsize=(11,4))
 for ax,control in zip(axes,['car16','grid8']):
  d=pairs[pairs.control.eq(control)&pairs.baseline.eq('best_control')&pairs.method.isin(NEW)]
  for m in NEW:
   x=np.sort(d[d.method.eq(m)].full_speedup.dropna());ax.step(x,np.arange(1,len(x)+1)/len(x),where='post',label=LABEL[m],color=COLORS[m])
  ax.set(xscale='log',xlabel='Episode speedup vs fastest control',ylabel='Fraction of common completed cases',title=control);ax.axvline(1,color='.5',ls=':');ax.legend(fontsize=8)
 figure(fig,'performance_profile',figmanifest)
 fig,axes=plt.subplots(1,2,figsize=(11,4.5))
 for ax,control in zip(axes,['car16','grid8']):
  d=maps[maps.control.eq(control)&maps.cohort.eq('replay')&maps.baseline.eq('best_control')&maps.method.isin(NEW)]
  matrix=d.pivot(index='map',columns='method',values='full_speedup').reindex(columns=NEW);im=ax.imshow(np.log2(matrix),vmin=-3,vmax=3,cmap='RdBu')
  ax.set_xticks(range(3),[LABEL[m] for m in NEW],rotation=20,ha='right');ax.set_yticks(range(len(matrix)),matrix.index);ax.set_title(control+' replay')
  for i in range(len(matrix)):
   for j in range(3):ax.text(j,i,f'{matrix.iloc[i,j]:.2f}',ha='center',va='center',fontsize=8)
 fig.colorbar(im,ax=axes.tolist(),shrink=.7,label='log2 speedup',pad=.025);fig.subplots_adjust(right=.85,wspace=.55)
 # Explicit colorbar axis keeps tight_layout from overlapping map labels.
 fig.delaxes(fig.axes[-1]);cax=fig.add_axes([.9,.22,.018,.6]);fig.colorbar(im,cax=cax,label='log2 speedup')
 for ext in ['png','pdf']:
  p=DEST/'figures'/('map_replay.'+ext);fig.savefig(p,dpi=170,bbox_inches='tight',metadata={'CreationDate':None,'ModDate':None} if ext=='pdf' else {'Software':'mesh-envelope-analysis'});figmanifest[str(p.relative_to(ROOT))]=sha(p)
 plt.close(fig)
 fig,axes=plt.subplots(2,3,figsize=(12,7),sharex=True)
 for row,control in enumerate(['car16','grid8']):
  for col,family in enumerate(['remote','frontier','reconnect']):
   ax=axes[row,col]
   for m in ['mesh_reuse','lba_reuse','dstar_lattice','lattice_envelope',*NEW]:
    d=amort[amort.control.eq(control)&amort.family.eq(family)&amort.method.eq(m)].groupby('repairs').total_s.apply(gm)
    ax.plot(d.index,1000*d.values,'o-',label=LABEL[m],color=COLORS.get(m),ms=3)
   ax.set(yscale='log',title=f'{control}: {family}',ylabel='Total planner time, ms',xlabel='Number of repairs');ax.grid(alpha=.2)
 axes[0,0].legend(fontsize=7);figure(fig,'amortization',figmanifest)
 fig,axes=plt.subplots(1,2,figsize=(11,4))
 for ax,control in zip(axes,['car16','grid8']):
  for m in NEW:
   d=qp[qp.control.eq(control)&qp.cohort.eq('replay')&qp.method.eq(m)&qp.baseline.eq('lba_reuse')&qp['query'].gt(0)].copy();d['bin']=pd.cut(d.edits,[-1,0,2,8,32,128,1e12],labels=['0','1–2','3–8','9–32','33–128','>128']);v=d.groupby('bin',observed=False).speedup.apply(gm)
   ax.plot(np.arange(len(v)),v.values,'o-',label=LABEL[m],color=COLORS[m]);ax.set_xticks(np.arange(len(v)),v.index,rotation=20)
  ax.set(yscale='log',xlabel='Observed edits per repair',ylabel='Query speedup vs LBA* reuse',title=control);ax.axhline(1,color='.5',ls=':');ax.legend(fontsize=8)
 figure(fig,'edit_scaling',figmanifest)
 fig,axes=plt.subplots(1,2,figsize=(12,4))
 for ax,control in zip(axes,['car16','grid8']):
  methods=[*controls,*NEW];d=metrics[metrics.control.eq(control)];x=[];labels=[]
  for m in methods:
   a=d[d.method.eq(m)].peak_heap_bytes
   if len(a):x.append(a.values/2**20);labels.append(LABEL[m])
  ax.boxplot(x,tick_labels=labels,showfliers=False);ax.set(yscale='log',ylabel='Requested peak heap, MiB',title=control);ax.tick_params(axis='x',rotation=80,labelsize=7)
 figure(fig,'memory',figmanifest)
 fig,axes=plt.subplots(2,3,figsize=(12,7),sharex=True)
 nav=metrics[metrics.cohort.eq('navigation_unknown')]
 for ax,(name,d) in zip(axes.flat,nav.groupby('map')):
  for m in ['lba_reuse','batch_mpgaa','dstar_lattice',*NEW]:
   v=d[d.method.eq(m)].sort_values('radius');ax.plot(v.radius,1000*v.full_s,'o-',label=LABEL[m],color=COLORS.get(m))
  ax.set(yscale='log',title=name,xlabel='Discovery radius, cells',ylabel='Total planner time, ms');ax.set_xticks([8,16,32,64])
 axes[0,0].legend(fontsize=7);figure(fig,'discovery_radius',figmanifest)
 # Separate positive / negative evidence: sum time ratios per fixed map.
 ans=[]
 for key,d in qp[qp['query'].gt(0)&qp.cohort.eq('replay')].groupby(['control','map','answer','method','baseline']):
  ans.append(dict(zip(['control','map','answer','method','baseline'],key))|dict(queries=len(d),speedup_gm=gm(d.speedup),pooled_speedup=d.base_time_s.sum()/d.time_s.sum()))
 save(pd.DataFrame(ans),out/'answer_types.csv')
 # A separate mechanism plot uses only online queries on identical replay
 # inputs, so the first cold proof cannot conceal the frontier representation.
 mech=qmedian[qmedian.cohort.eq('separator') & qmedian['query'].gt(0)].groupby(['control','family','method'],as_index=False)[COUNTERS].sum()
 save(mech,out/'separator_work.csv')
 fig,axes=plt.subplots(1,2,figsize=(11,4))
 for ax,control in zip(axes,['car16','grid8']):
  families=['remote','frontier','reconnect'];methods=['lattice_envelope',*NEW]
  x=np.arange(len(families));width=.19
  for j,m in enumerate(methods):
   v=[mech.loc[mech.control.eq(control)&mech.family.eq(f)&mech.method.eq(m),'checked_cells'].sum() for f in families]
   ax.bar(x+(j-1.5)*width,np.asarray(v)+1,width,label=LABEL[m],color=COLORS[m])
  ax.set_xticks(x,families);ax.set(yscale='log',title=control,ylabel='Online occupancy checks + 1');ax.legend(fontsize=8)
 figure(fig,'frontier_work',figmanifest)
 completion=metrics.groupby(['cohort','control','method'],as_index=False).agg(configurations=('complete','size'),complete=('complete','sum'));save(completion,out/'completion.csv')
 tables={p.name:sha(p) for p in out.glob('*.csv')};(out/'figures.json').write_text(json.dumps(figmanifest,indent=2)+'\n')
 result=dict(status='passed',scenarios=manifest['scenarios'],timed_runs=len(allruns),memory_runs=len(memories),timed_calls=len(calls),allocation_matched_rows=matched,exact_cost_disagreements=int(badcost+len(disagreement)),capped_calls=int(calls.status.eq('capped').sum()),repeat_relative_mad_median=dispersion.relative_mad.median(),repeat_relative_mad_p95=dispersion.relative_mad.quantile(.95),analysis_source_sha256=sha(Path(__file__)),tables_sha256=tables,figures=len(figmanifest),manifest_sha256=sha(HERE/'frozen/manifest.json'))
 assert result['timed_runs']==manifest['timed_runs'] and result['memory_runs']==manifest['memory_runs']
 (out/'analysis.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if not k.endswith('sha256')}))
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,default=HERE/'results/full');main(p.parse_args().directory)
