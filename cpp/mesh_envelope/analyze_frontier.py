#!/usr/bin/env python3
"""Analyze the prespecified structural complement separately from the primary."""
import json,argparse
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pandas.testing import assert_frame_equal
from analyze import HERE,ROOT,DEST,NEW,COUNTERS,LABEL,COLORS,gm,sha,read,save,figure

def main(directory):
 manifest=json.loads((HERE/'frozen/frontier/manifest.json').read_text());state=json.loads((directory/'experiment.json').read_text());assert state['status']=='passed'
 assert state['manifest_sha256']==sha(HERE/'frozen/frontier/manifest.json')
 for p,h in {**manifest['sources'],**manifest['files']}.items():assert sha(ROOT/p)==h,p
 for j in state['jobs'].values():
  for p,h in j['outputs'].items():assert sha(directory/p)==h,p
 ctx=json.loads((ROOT/manifest['contexts_file']).read_text());meta=pd.DataFrame([dict(case=k,width=v['width'],control=v['control'],seed=v['seed']) for k,v in ctx.items()])
 ds=[];mem=[];matched=0;runs=[];curves=[]
 for job in manifest['plan']:
  d=read(directory/('timing_'+job['name']+'.csv'));m=read(directory/('memory_'+job['name']+'.csv'));fields=[c for c in d if not c.endswith('_s') and c not in ['case','method','query','repeat','peak_heap_bytes','retained_heap_bytes']]
  assert_frame_equal(d[d.repeat.eq(0)].set_index(['case','method','query'])[fields].sort_index(),m.set_index(['case','method','query'])[fields].sort_index(),check_exact=True,check_dtype=False)
  assert not d.status.isin(['capped','skipped_after_cap']).any();assert d.cost.isna().all() and d.expected.isna().all();matched+=len(m);ds.append(d)
  mem.append(m.groupby(['case','method'],as_index=False).peak_heap_bytes.max())
 d=pd.concat(ds,ignore_index=True);metrics=[]
 for key,g in d.groupby(['case','method','repeat']):
  row=dict(zip(['case','method','repeat'],key));row.update(full_s=g.time_s.sum()+g.setup_s.sum(),initial_s=g.loc[g['query'].eq(0),'time_s'].sum(),repair_s=g.loc[g['query'].gt(0),'time_s'].sum())
  for c in COUNTERS:row[c]=g[c].sum()
  for c in ['checked_cells','guard_installs','guard_events','envelope_hits','envelope_builds','envelope_added']:row['online_'+c]=g.loc[g['query'].gt(0),c].sum()
  runs.append(row)
  for n in [0,1,2,4,8,16]:curves.append(dict(case=key[0],method=key[1],repeat=key[2],repairs=n,total_s=g.loc[g['query'].le(n),['time_s','setup_s']].sum().sum()))
 runs=pd.DataFrame(runs);cols=[c for c in runs if c not in ['case','method','repeat']];metrics=runs.groupby(['case','method'],as_index=False)[cols].median().merge(pd.concat(mem),on=['case','method']).merge(meta,on='case')
 pairs=[]
 for case,g in metrics.groupby('case'):
  for m in NEW:
   r=g[g.method.eq(m)].iloc[0]
   for b in ['lba_reuse','mesh_reuse','lattice_envelope','dstar_lattice']:
    v=g[g.method.eq(b)].iloc[0];pairs.append(dict(case=case,method=m,baseline=b,control=r.control,width=r.width,full_speedup=v.full_s/r.full_s,repair_speedup=v.repair_s/r.repair_s,checks_ratio=v.online_checked_cells/max(1,r.online_checked_cells),memory_multiplier=r.peak_heap_bytes/v.peak_heap_bytes))
 pairs=pd.DataFrame(pairs);summary=[]
 for key,g in pairs.groupby(['control','width','method','baseline']):summary.append(dict(zip(['control','width','method','baseline'],key))|{c:gm(g[c]) for c in ['full_speedup','repair_speedup','checks_ratio','memory_multiplier']})
 out=directory/'analysis';out.mkdir(exist_ok=True)
 save(metrics,out/'case_metrics.csv');save(pairs,out/'paired_cases.csv');save(pd.DataFrame(summary),out/'summary.csv');save(pd.DataFrame(curves),out/'amortization.csv')
 figures={};fig,axes=plt.subplots(2,2,figsize=(10,7));plt.rcParams.update({'font.size':9,'pdf.fonttype':42})
 for row,control in enumerate(['car16','grid8']):
  for col,metric in enumerate(['full_s','repair_s']):
   ax=axes[row,col]
   for m in ['mesh_reuse','lattice_envelope','dstar_lattice',*NEW]:
    v=metrics[metrics.control.eq(control)&metrics.method.eq(m)].groupby('width')[metric].apply(gm);ax.plot(v.index,1000*v.values,'o-',label=LABEL[m],color=COLORS.get(m))
   ax.set(yscale='log',xlabel='Barrier width, cells',ylabel='Planner time, ms',title=control+(' whole episode' if col==0 else ' repair only'));ax.set_xticks([1,3,7]);ax.grid(alpha=.2)
 axes[0,0].legend(fontsize=7);figure(fig,'barrier_width',figures)
 result=dict(status='passed',scenarios=manifest['scenarios'],timed_runs=len(runs),memory_runs=matched//17,allocation_matched_rows=matched,exact_cost_disagreements=0,capped_calls=0,protocol=manifest['protocol'],manifest_sha256=sha(HERE/'frozen/frontier/manifest.json'),tables_sha256={p.name:sha(p) for p in sorted(out.glob('*.csv'))},figures_sha256=figures,source_sha256=sha(Path(__file__)))
 assert result['timed_runs']==manifest['timed_runs'] and result['memory_runs']==manifest['memory_runs']
 (out/'analysis.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if not k.endswith('sha256')}))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,default=HERE/'results/frontier');main(p.parse_args().directory)
