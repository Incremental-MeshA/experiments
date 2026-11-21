#!/usr/bin/env python3
"""Check native cost validation, immutable provenance and rendered artifacts."""
import argparse,hashlib,json,subprocess
from pathlib import Path
import fitz
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main(skip_tests):
 m=json.loads((HERE/'frozen/manifest.json').read_text());s=json.loads((HERE/'results/full/experiment.json').read_text());a=json.loads((HERE/'results/full/analysis/analysis.json').read_text());p=json.loads((HERE/'results/full/analysis/report_provenance.json').read_text());ps=json.loads((HERE/'results/probes/experiment.json').read_text());assert s['status']==a['status']==p['status']==ps['status']=='passed'
 assert s['manifest_sha256']==a['manifest_sha256']==ps['manifest_sha256']==sha(HERE/'frozen/manifest.json')
 for name,h in {**m['files'],**m['sources']}.items():assert sha(ROOT/name)==h,name
 for job in s['jobs'].values():
  assert job['status']=='passed'
  for name,h in job['outputs'].items():assert sha(HERE/'results/full'/name)==h,name
 for name,h in s['binaries'].items():assert sha(HERE/'build'/name)==h,name
 for name,h in a['tables_sha256'].items():assert sha(HERE/'results/full/analysis'/name)==h,name
 for name,h in a['figures_sha256'].items():assert sha(ROOT/name)==h,name
 assert a['source_sha256']==sha(HERE/'analyze.py') and a['exact_cost_disagreements']==0 and a['timed_runs']==m['timed_runs'] and a['memory_runs']==m['memory_runs']
 assert p['analysis_sha256']==sha(HERE/'results/full/analysis/analysis.json') and p['source_sha256']==sha(HERE/'report.py') and p['design_sha256']==sha(ROOT/'docs/mesh_lift/design.md') and p['related_work_sha256']==sha(ROOT/'docs/mesh_lift/related_work.md')
 for name,h in p['render_dependencies'].items():assert sha(ROOT/name)==h,name
 assert ps['source_sha256']==sha(HERE/'probe.py') and ps['binary_sha256']==sha(HERE/'build/replay_count') and a['probe_experiment_sha256']==sha(HERE/'results/probes/experiment.json')
 assert ps['patched_source_sha256']==sha(HERE/'build/count_overlay/cpp/mesh_lift/replay_count.cpp') and ps['patched_model_sha256']==sha(HERE/'build/count_overlay/cpp/include/ima/model.hpp')
 for job in ps['jobs']:
  f=HERE/'results/probes'/(job['name']+'.csv');assert sha(f)==job['csv_sha256'] and sha(Path(str(f)+'.json'))==job['metadata_sha256']
 mutation=json.loads((HERE/'validation/mutation.json').read_text());assert mutation['status']=='passed' and mutation['result']['status']=='mutant_detected' and mutation['original_source_sha256']==sha(HERE/'algorithms.hpp') and mutation['script_sha256']==sha(HERE/'mutation.py')
 docs=[]
 for name in ['report','paper']:
  f=ROOT/f'docs/mesh_lift/{name}.pdf';assert sha(f)==p[name]['pdf_sha256'] and sha(f.with_suffix('.md'))==p[name]['markdown_sha256'];pdf=fitz.open(f);text='\n'.join(pg.get_text() for pg in pdf);assert len(pdf)>=4 and len(text)>10000 and '\ufffd' not in text
  for pg in pdf:
   for b in pg.get_text('blocks'):assert b[0]>=-1 and b[1]>=-1 and b[2]<=pg.rect.width+1 and b[3]<=pg.rect.height+1,(name,pg.number,b[:4])
  docs.append(dict(path=str(f.relative_to(ROOT)),pages=len(pdf),sha256=sha(f)))
 nb=json.loads((ROOT/'docs/mesh_lift/analysis.ipynb').read_text());assert nb['metadata']['mesh_lift_artifact']['source_sha256']==sha(HERE/'notebook.py') and nb['metadata']['mesh_lift_artifact']['analysis_sha256']==sha(HERE/'results/full/analysis/analysis.json');code=[c for c in nb['cells'] if c['cell_type']=='code'];assert len(code)==4 and all(c.get('execution_count') for c in code);assert not any(o.get('output_type')=='error' for c in code for o in c.get('outputs',[]))
 runs=[]
 if not skip_tests:
  for model in ['grid8','car16']:
   r=subprocess.run([str(HERE/'build/test'),str(ROOT/f'cpp/experiments/frozen/{model}_model.txt')],cwd=ROOT,text=True,capture_output=True,check=True);x=json.loads(r.stdout);assert x['status']=='passed';runs.append(x)
 for model in ['grid8','car16']:assert json.loads((HERE/f'validation/asan_{model}.log').read_text())['status']=='passed'
 old=['cpp/include/ima','cpp/experiments','cpp/navigation_sweeps','cpp/navigation_controls','cpp/mesh_variants','cpp/mpgaa_mesh','cpp/mpgaa_lazy','cpp/mesh_envelope','cpp/mesh_conditional','cpp/mesh_symmetric','cpp/mesh_probe_count','docs/mesh_envelope','docs/mesh_symmetric']
 diff=subprocess.run(['git','diff','--name-only',m['base_commit'],'--',*old],cwd=ROOT,text=True,capture_output=True,check=True);assert not diff.stdout,diff.stdout
 result=dict(status='passed',scenarios=a['scenarios'],timed_runs=a['timed_runs'],memory_runs=a['memory_runs'],count_only_runs=a['count_only_runs'],allocation_matched_rows=a['allocation_matched_rows'],count_only_matched_rows=a['count_only_matched_rows'],terminal_prunes=a['terminal_prunes'],lift_writes=a['lift_writes'],mutation_detected=a['mutation_detected'],capped_calls=a['capped_calls'],exact_cost_disagreements=0,old_sources_unchanged=True,tests=runs,documents=docs,executed_notebook_cells=len(code))
 (HERE/'validation/full.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--skip-tests',action='store_true');a=p.parse_args();main(a.skip_tests)
