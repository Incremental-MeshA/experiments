#!/usr/bin/env python3
"""Validate total collision-API probes against unchanged logical trajectories."""
import sys,json,time,argparse
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'cpp/mesh_envelope'))
import analyze as base
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pandas.testing import assert_frame_equal

def main(directory):
 path=directory/'experiment.json'
 while not path.exists():time.sleep(15)
 state=json.loads(path.read_text());assert state['status']=='passed'
 assert state['patcher_sha256']==base.sha(HERE/'run.py')
 for p,h in state['original_sources'].items():assert base.sha(ROOT/p)==h,p
 frames=[];matched=0
 for name,job in state['jobs'].items():
  p=directory/(name+'.csv');assert base.sha(p)==job['csv_sha256'] and base.sha(Path(str(p)+'.json'))==job['json_sha256']
  d=base.read(p)
  normal=base.read(ROOT/'cpp/mesh_conditional/results/full'/('timing_'+name+'.csv'));normal=normal[normal.repeat.eq(0)]
  oldroot=ROOT/('cpp/mesh_envelope/results/frontier' if name.startswith('frontier_') else 'cpp/mesh_envelope/results/full')
  lattice=base.read(oldroot/('timing_'+name+'.csv'));lattice=lattice[lattice.repeat.eq(0)&lattice.method.eq('lattice_envelope')]
  reference=pd.concat([normal,lattice],ignore_index=True).set_index(['case','method','query']).sort_index();actual=d.set_index(['case','method','query']).sort_index()
  fields=[c for c in reference if c in actual and not c.endswith('_s') and c not in ['repeat','peak_heap_bytes','retained_heap_bytes']]
  assert_frame_equal(reference[fields],actual[fields],check_dtype=False,check_exact=True);assert d.all_free_calls.ge(d.checked_cells).all();matched+=len(d);frames.append(d)
 allcalls=pd.concat(frames,ignore_index=True);ctx=json.loads((ROOT/'cpp/mesh_conditional/frozen/contexts.json').read_text());meta=pd.DataFrame([dict(case=k,control=v['control'],cohort=v['cohort'],map=v['map'],family=v['family']) for k,v in ctx.items()])
 allcalls=allcalls.drop(columns=['family']).merge(meta,on='case');rows=[]
 for key,g in allcalls.groupby(['control','cohort','map','family','method']):
  online=g[g['query'].gt(0)];rows.append(dict(zip(['control','cohort','map','family','method'],key))|dict(calls=len(g),all_free_calls=int(g.all_free_calls.sum()),legacy_checks=int(g.checked_cells.sum()),online_all_free_calls=int(online.all_free_calls.sum()),online_legacy_checks=int(online.checked_cells.sum()),missing_from_legacy=int((g.all_free_calls-g.checked_cells).sum())))
 out=directory/'analysis';out.mkdir(exist_ok=True);work=pd.DataFrame(rows);base.save(work,out/'probe_work.csv')
 pairs=[]
 for case,g in allcalls.groupby('case'):
  for candidate,baseline in [('envelope_mesh','lattice_envelope'),('circuit_mesh','conditional_dstar')]:
   a=g[g.method.eq(candidate)];b=g[g.method.eq(baseline)]
   for online in [False,True]:
    aa=a[a['query'].gt(0)] if online else a;bb=b[b['query'].gt(0)] if online else b
    pairs.append(dict(case=case,method=candidate,baseline=baseline,online=online,cohort=aa.cohort.iloc[0],control=aa.control.iloc[0],map=aa['map'].iloc[0],family=aa.family.iloc[0],free_calls=int(aa.all_free_calls.sum()),base_free_calls=int(bb.all_free_calls.sum()),complete=not aa.status.isin(['capped','skipped_after_cap']).any() and not bb.status.isin(['capped','skipped_after_cap']).any(),ratio=bb.all_free_calls.sum()/aa.all_free_calls.sum() if aa.all_free_calls.sum()>0 and not aa.status.isin(['capped','skipped_after_cap']).any() and not bb.status.isin(['capped','skipped_after_cap']).any() else np.nan))
 pairs=pd.DataFrame(pairs);base.save(pairs,out/'probe_pairs.csv')
 fig,axes=plt.subplots(1,2,figsize=(11,4));figures={}
 for ax,control in zip(axes,['car16','grid8']):
  methods=['envelope_mesh','lattice_envelope','circuit_mesh','conditional_dstar'];families=['remote','frontier','reconnect'];x=np.arange(3);width=.19
  for j,m in enumerate(methods):
   vals=[work.loc[work.control.eq(control)&work.cohort.eq('separator')&work.family.eq(f)&work.method.eq(m),'online_all_free_calls'].sum() for f in families]
   ax.bar(x+(j-1.5)*width,np.asarray(vals)+1,width,label='Conditional D* Lite' if m=='conditional_dstar' else base.LABEL[m],color='#332288' if m=='conditional_dstar' else base.COLORS[m])
  ax.set_xticks(x,families);ax.set(yscale='log',ylabel='All replanning Grid.free calls + 1',title=control);ax.legend(fontsize=7)
 base.figure(fig,'all_collision_probes',figures)
 result=dict(status='passed',counted_runs=sum(j['runs'] for j in state['jobs'].values()),logical_matched_rows=matched,definition=state['definition'],source_sha256=base.sha(Path(__file__)),experiment_sha256=base.sha(path),tables_sha256={p.name:base.sha(p) for p in out.glob('*.csv')},figures_sha256=figures)
 (out/'analysis.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if not k.endswith('sha256')}))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,default=HERE/'results');main(p.parse_args().directory)
