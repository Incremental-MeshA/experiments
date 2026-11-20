#!/usr/bin/env python3
"""Validate raw provenance, independent cost checks and rendered deliverables."""
import argparse,hashlib,json,re,subprocess
from pathlib import Path
import fitz
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main(directory,tests):
 manifest=json.loads((HERE/'frozen/manifest.json').read_text());state=json.loads((directory/'experiment.json').read_text());assert state['status']=='passed'
 assert sha(HERE/'frozen/manifest.json')==state['manifest_sha256']
 for p,h in {**manifest['files'],**manifest['sources']}.items():assert sha(ROOT/p)==h,p
 for j in state['jobs'].values():
  assert j['status']=='passed'
  for p,h in j['outputs'].items():assert sha(directory/p)==h,p
 for p,h in state['binaries'].items():assert sha(HERE/'build'/p)==h,p
 ad=directory/'analysis';a=json.loads((ad/'analysis.json').read_text());assert a['status']=='passed' and a['exact_cost_disagreements']==0
 assert a['timed_runs']==manifest['timed_runs'] and a['memory_runs']==manifest['memory_runs']
 assert a['analysis_source_sha256']==sha(HERE/'analyze.py')
 for p,h in a['tables_sha256'].items():assert sha(ad/p)==h,p
 for p,h in json.loads((ad/'figures.json').read_text()).items():assert sha(ROOT/p)==h,p
 prov=json.loads((ad/'report_provenance.json').read_text());assert prov['analysis_sha256']==sha(ad/'analysis.json') and prov['source_sha256']==sha(HERE/'report.py')
 docs=[]
 for name in ['report','paper']:
  p=ROOT/f'docs/mesh_envelope/{name}.pdf';assert sha(p)==prov[name]['pdf_sha256'];assert sha(p.with_suffix('.md'))==prov[name]['markdown_sha256']
  pdf=fitz.open(p);text='\n'.join(page.get_text() for page in pdf);assert len(pdf)>3 and len(text)>10000
  assert '\ufffd' not in text and '11340' in re.sub(r'\D','',text)
  # No text blocks outside paper bounds; wide tables are a material layout bug.
  for page in pdf:
   for b in page.get_text('blocks'):
    assert b[0]>=-1 and b[2]<=page.rect.width+1,(name,page.number,b[:4])
  docs.append(dict(file=str(p.relative_to(ROOT)),pages=len(pdf),text_chars=len(text),sha256=sha(p)))
 notebook=json.loads((ROOT/'docs/mesh_envelope/analysis.ipynb').read_text());assert notebook['metadata']['mesh_envelope_artifact']['source_sha256']==sha(HERE/'notebook.py');assert notebook['metadata']['mesh_envelope_artifact']['analysis_sha256']==sha(ad/'analysis.json');code=[c for c in notebook['cells'] if c['cell_type']=='code'];assert len(code)==4 and all(c.get('execution_count') for c in code)
 assert not any(o.get('output_type')=='error' for c in code for o in c.get('outputs',[]))
 runs=[]
 if tests:
  for model in ['grid8','car16']:
   result=subprocess.run([str(HERE/'build/test'),str(ROOT/f'cpp/experiments/frozen/{model}_model.txt')],cwd=ROOT,text=True,capture_output=True,check=True)
   x=json.loads(result.stdout);assert x['status']=='passed';runs.append(x)
 supplement=HERE/'results/frontier';fm=json.loads((HERE/'frozen/frontier/manifest.json').read_text());fs=json.loads((supplement/'experiment.json').read_text());fa=json.loads((supplement/'analysis/analysis.json').read_text())
 assert fs['status']=='passed' and fa['status']=='passed' and fa['exact_cost_disagreements']==0
 assert fs['manifest_sha256']==sha(HERE/'frozen/frontier/manifest.json') and fa['manifest_sha256']==fs['manifest_sha256']
 for p,h in {**fm['files'],**fm['sources']}.items():assert sha(ROOT/p)==h,p
 for job in fs['jobs'].values():
  assert job['status']=='passed'
  for p,h in job['outputs'].items():assert sha(supplement/p)==h,p
 for p,h in fa['tables_sha256'].items():assert sha(supplement/'analysis'/p)==h,p
 for p,h in fa['figures_sha256'].items():assert sha(ROOT/p)==h,p
 assert fa['source_sha256']==sha(HERE/'analyze_frontier.py') and fa['timed_runs']==fm['timed_runs'] and fa['memory_runs']==fm['memory_runs']
 cp=ROOT/'cpp/mesh_conditional';cm=json.loads((cp/'frozen/manifest.json').read_text());cs=json.loads((cp/'results/full/experiment.json').read_text());ca=json.loads((cp/'results/full/analysis/analysis.json').read_text())
 assert cs['status']=='passed' and ca['status']=='passed' and ca['exact_cost_disagreements']==0
 assert cs['manifest_sha256']==sha(cp/'frozen/manifest.json') and ca['manifest_sha256']==cs['manifest_sha256']
 for p,h in {**cm['files'],**cm['sources']}.items():assert sha(ROOT/p)==h,p
 for job in cs['jobs'].values():
  assert job['status']=='passed'
  for p,h in job['outputs'].items():assert sha(cp/'results/full'/p)==h,p
 for p,h in ca['tables_sha256'].items():assert sha(cp/'results/full/analysis'/p)==h,p
 for p,h in ca['figures_sha256'].items():assert sha(ROOT/p)==h,p
 for p,h in cs['binaries'].items():assert sha(cp/'build'/p)==h,p
 assert ca['source_sha256']==sha(cp/'analyze.py') and ca['timed_runs']==cm['timed_runs'] and ca['memory_runs']==cm['memory_runs']
 assert prov['frontier_analysis_sha256']==sha(supplement/'analysis/analysis.json') and prov['conditional_analysis_sha256']==sha(cp/'results/full/analysis/analysis.json')
 for p,h in prov['narrative_sha256'].items():assert sha(ROOT/'docs/mesh_envelope'/p)==h,p
 if tests:
  for model in ['grid8','car16']:
   result=subprocess.run([str(cp/'build/test'),str(ROOT/f'cpp/experiments/frozen/{model}_model.txt')],cwd=ROOT,text=True,capture_output=True,check=True);x=json.loads(result.stdout);assert x['status']=='passed';runs.append(dict(x,cohort='conditional'))
 untouched=['cpp/include/ima','cpp/experiments','cpp/navigation_sweeps','cpp/navigation_controls','cpp/mesh_variants','cpp/mpgaa_mesh','cpp/mpgaa_lazy','docs/mpgaa_mesh','docs/mpgaa_lazy']
 diff=subprocess.run(['git','diff','--name-only',manifest['base_commit'],'HEAD','--',*untouched],cwd=ROOT,text=True,capture_output=True,check=True);assert not diff.stdout,diff.stdout
 result=dict(status='passed',scenarios=a['scenarios'],timed_runs=a['timed_runs'],memory_runs=a['memory_runs'],cost_disagreements=0,allocation_matched_rows=a['allocation_matched_rows'],tests=runs,documents=docs,executed_notebook_cells=len(code),old_sources_unchanged=True,structural_complement=dict(scenarios=fa['scenarios'],timed_runs=fa['timed_runs'],memory_runs=fa['memory_runs'],allocation_matched_rows=fa['allocation_matched_rows']),conditional_validation=dict(scenarios=ca['scenarios'],timed_runs=ca['timed_runs'],memory_runs=ca['memory_runs'],allocation_matched_rows=ca['allocation_matched_rows']))
 print(json.dumps(result,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,default=HERE/'results/full');p.add_argument('--skip-tests',action='store_true');args=p.parse_args();main(args.directory,not args.skip_tests)
