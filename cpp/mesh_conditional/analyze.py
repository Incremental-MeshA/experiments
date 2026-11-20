#!/usr/bin/env python3
"""Fresh joint replay validation against the optimized non-mesh D* control."""
import sys,json
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'cpp/mesh_envelope'))
import analyze as base
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pandas.testing import assert_frame_equal
NEW=base.NEW;LABEL={**base.LABEL,'conditional_dstar':'Conditional D* Lite'}
def main():
 directory=HERE/'results/full';manifest=json.loads((HERE/'frozen/manifest.json').read_text());state=json.loads((directory/'experiment.json').read_text());assert state['status']=='passed'
 assert state['manifest_sha256']==base.sha(HERE/'frozen/manifest.json')
 for p,h in {**manifest['sources'],**manifest['files']}.items():assert base.sha(ROOT/p)==h,p
 for j in state['jobs'].values():
  assert j['status']=='passed'
  for p,h in j['outputs'].items():assert base.sha(directory/p)==h,p
 ctx=json.loads((ROOT/manifest['contexts_file']).read_text());meta=pd.DataFrame([dict(case=k,map=v['map'],cohort=v['cohort'],control=v['control'],family=v['family']) for k,v in ctx.items()]);frames=[];mem=[];matched=0;runs=[]
 for job in manifest['plan']:
  d=base.read(directory/('timing_'+job['name']+'.csv'));m=base.read(directory/('memory_'+job['name']+'.csv'));first=d[d.repeat.eq(0)].set_index(['case','method','query']).sort_index();profile=m.set_index(['case','method','query']).sort_index()
  fields=[c for c in first if not c.endswith('_s') and c not in ['repeat','peak_heap_bytes','retained_heap_bytes']]
  assert_frame_equal(first[fields],profile[fields],check_exact=True,check_dtype=False);matched+=len(m)
  assert (m.peak_heap_bytes>=m.retained_heap_bytes).all() and (m.peak_heap_bytes<2**48).all();frames.append(d);mem.append(m.groupby(['case','method'],as_index=False).peak_heap_bytes.max())
  for key,g in d.groupby(['case','method','repeat']):
   runs.append(dict(zip(['case','method','repeat'],key))|dict(full_s=g.time_s.sum()+g.setup_s.sum(),repair_s=g.loc[g['query'].gt(0),'time_s'].sum(),complete=not g.status.isin(['capped','skipped_after_cap']).any()))
 d=pd.concat(frames,ignore_index=True);finite=d.cost.notna()&d.expected.notna();bad=int((d.loc[finite,'cost']-d.loc[finite,'expected']).abs().gt(1e-6).sum());assert not bad
 r=pd.DataFrame(runs);metrics=r.groupby(['case','method'],as_index=False)[['full_s','repair_s']].median().merge(r.groupby(['case','method'],as_index=False).complete.all()).merge(pd.concat(mem),on=['case','method']).merge(meta,on='case')
 pairs=[]
 for case,g in metrics.groupby('case'):
  b=g[g.method.eq('conditional_dstar')].iloc[0]
  for _,v in g[g.method.isin(NEW)].iterrows():
   ok=bool(v.complete and b.complete);pairs.append(dict(case=case,method=v.method,baseline='conditional_dstar',control=v.control,cohort=v.cohort,map=v['map'],family=v.family,complete=ok,full_speedup=b.full_s/v.full_s if ok else np.nan,repair_speedup=b.repair_s/v.repair_s if ok else np.nan,memory_multiplier=v.peak_heap_bytes/b.peak_heap_bytes))
 pairs=pd.DataFrame(pairs);summary=[]
 for key,g in pairs.groupby(['control','cohort','method']):summary.append(dict(zip(['control','cohort','method'],key))|dict(configurations=len(g),pairs=int(g.complete.sum()),full_speedup=base.gm(g.full_speedup),repair_speedup=base.gm(g.repair_speedup),memory_multiplier=base.gm(g.memory_multiplier),wins_10pct=int(g.full_speedup.ge(1.1).sum())))
 maprows=[]
 for key,g in pairs.groupby(['control','cohort','map','method']):maprows.append(dict(zip(['control','cohort','map','method'],key))|dict(configurations=len(g),pairs=int(g.complete.sum()),full_speedup=base.gm(g.full_speedup),repair_speedup=base.gm(g.repair_speedup)))
 out=directory/'analysis';out.mkdir(exist_ok=True);base.save(metrics,out/'case_metrics.csv');base.save(pairs,out/'paired_cases.csv');base.save(pd.DataFrame(summary),out/'summary.csv');base.save(pd.DataFrame(maprows),out/'map_pairs.csv');base.save(d[d.status.eq('capped')][['case','method','repeat','query','expansions']],out/'caps.csv')
 fig,axes=plt.subplots(1,2,figsize=(11,4));figures={}
 for ax,control in zip(axes,['car16','grid8']):
  for m in NEW:
   v=np.sort(pairs[pairs.control.eq(control)&pairs.method.eq(m)].full_speedup.dropna());ax.step(v,np.arange(1,len(v)+1)/len(v),where='post',label=LABEL[m],color=base.COLORS[m])
  ax.axvline(1,color='.5',ls=':');ax.set(xscale='log',title=control,xlabel='Episode speedup vs conditional D* Lite',ylabel='Fraction of completed replay cases');ax.legend(fontsize=8)
 base.figure(fig,'conditional_control',figures)
 result=dict(status='passed',scenarios=manifest['scenarios'],timed_runs=len(r),memory_runs=len(metrics),allocation_matched_rows=matched,capped_calls=int(d.status.eq('capped').sum()),exact_cost_disagreements=bad,protocol=manifest['protocol'],manifest_sha256=base.sha(HERE/'frozen/manifest.json'),tables_sha256={p.name:base.sha(p) for p in out.glob('*.csv')},figures_sha256=figures,source_sha256=base.sha(Path(__file__)))
 assert len(r)==manifest['timed_runs'] and len(metrics)==manifest['memory_runs'];(out/'analysis.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if not k.endswith('sha256')}))
if __name__=='__main__':main()
