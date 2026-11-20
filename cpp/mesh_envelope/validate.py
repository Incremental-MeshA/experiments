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
 notebook=json.loads((ROOT/'docs/mesh_envelope/analysis.ipynb').read_text());code=[c for c in notebook['cells'] if c['cell_type']=='code'];assert len(code)==4 and all(c.get('execution_count') for c in code)
 assert not any(o.get('output_type')=='error' for c in code for o in c.get('outputs',[]))
 runs=[]
 if tests:
  for model in ['grid8','car16']:
   result=subprocess.run([str(HERE/'build/test'),str(ROOT/f'cpp/experiments/frozen/{model}_model.txt')],cwd=ROOT,text=True,capture_output=True,check=True)
   x=json.loads(result.stdout);assert x['status']=='passed';runs.append(x)
 untouched=['cpp/include/ima','cpp/experiments','cpp/navigation_sweeps','cpp/navigation_controls','cpp/mesh_variants','cpp/mpgaa_mesh','cpp/mpgaa_lazy','docs/mpgaa_mesh','docs/mpgaa_lazy']
 diff=subprocess.run(['git','diff','--name-only',manifest['base_commit'],'HEAD','--',*untouched],cwd=ROOT,text=True,capture_output=True,check=True);assert not diff.stdout,diff.stdout
 result=dict(status='passed',scenarios=a['scenarios'],timed_runs=a['timed_runs'],memory_runs=a['memory_runs'],cost_disagreements=0,allocation_matched_rows=a['allocation_matched_rows'],tests=runs,documents=docs,executed_notebook_cells=len(code),old_sources_unchanged=True)
 print(json.dumps(result,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,default=HERE/'results/full');p.add_argument('--skip-tests',action='store_true');args=p.parse_args();main(args.directory,not args.skip_tests)
