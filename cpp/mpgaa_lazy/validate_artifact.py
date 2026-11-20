#!/usr/bin/env python3
"""Verify a fresh clone: rebuild, independent oracle, raw hashes, tables, PDF."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from run_all import digest
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
def main(output):
    manifest=json.loads((HERE/'frozen/manifest.json').read_text());state=json.loads((HERE/'results/full/experiment.json').read_text())
    assert state['status']=='passed'
    for path,sha in {**manifest['files'],**manifest['sources']}.items():assert digest(ROOT/path)==sha,path
    unchanged=['cpp/include/ima','cpp/experiments','cpp/navigation_sweeps','cpp/navigation_controls','cpp/mesh_variants','cpp/mpgaa_mesh','docs/mpgaa_mesh']
    assert not subprocess.check_output(['git','diff',manifest['base_commit'],'--',*unchanged],cwd=ROOT)
    subprocess.run(['make','-C',str(HERE),'-j2','all'],cwd=ROOT,check=True)
    binaries={name:digest(HERE/'build'/name) for name in state['binaries']};assert binaries==state['binaries']
    actual=[]
    for model in ['grid8','car16']:
        text=subprocess.check_output([str(HERE/'build/test'),str(ROOT/f'cpp/experiments/frozen/{model}_model.txt')],cwd=ROOT,text=True)
        record=json.loads(text);assert record['status']=='passed';actual.append(record)
    expected=[json.loads(l) for l in (HERE/'results/verification/tests.log').read_text().splitlines() if l.startswith('{')]
    assert actual==expected
    ad=HERE/'results/full/analysis';analysis=json.loads((ad/'analysis.json').read_text());before=analysis['tables_sha256']
    assert analysis['analysis_source_sha256']==digest(HERE/'analyze.py')
    assert analysis['reused_analysis_sha256']==digest(ROOT/'cpp/mpgaa_mesh/analyze.py')
    for name,sha in before.items():assert digest(ad/name)==sha,name
    original_analysis=digest(ad/'analysis.json');original_figures=digest(ad/'figures.json')
    provenance=json.loads((ad/'report_provenance.json').read_text());dest=ROOT/'docs/mpgaa_lazy'
    assert provenance['analysis_sha256']==original_analysis and provenance['source_sha256']==digest(HERE/'report.py')
    assert provenance['layout_sha256']==digest(ROOT/'docs/experiments/layout.tex')
    assert provenance['vector_filter_sha256']==digest(ROOT/'cpp/mpgaa_mesh/vector_images.lua')
    assert provenance['markdown_sha256']==digest(dest/'report.md') and provenance['pdf_sha256']==digest(dest/'report.pdf')
    assert provenance['figures_manifest_sha256']==original_figures
    figures=json.loads((ad/'figures.json').read_text());assert len(figures)==16
    for name,sha in figures.items():assert digest(ROOT/name)==sha,name
    notebook=json.loads((dest/'analysis.ipynb').read_text());cells=[c for c in notebook['cells'] if c['cell_type']=='code']
    assert len(cells)==4 and [c['execution_count'] for c in cells]==[1,2,3,4]
    assert not any(o.get('output_type')=='error' for c in cells for o in c['outputs'])
    assert notebook['metadata']['mpgaa_lazy_artifact']['analysis_sha256']==original_analysis
    assert notebook['metadata']['mpgaa_lazy_artifact']['source_sha256']==digest(HERE/'notebook.py')
    import fitz
    document=fitz.open(dest/'report.pdf');outside=[];replacements=0
    for i,page in enumerate(document):
        replacements+=page.get_text().count('\ufffd')
        for block in page.get_text('dict',clip=fitz.INFINITE_RECT())['blocks']:
            for line in block.get('lines',[]):
                for span in line['spans']:
                    if not span['text'].strip():continue
                    x0,y0,x1,y1=span['bbox']
                    if x0<-.5 or y0<-.5 or x1>page.rect.width+.5 or y1>page.rect.height+.5:outside.append([i+1,span['text']])
    assert not outside,outside[:10];assert not replacements,replacements
    subprocess.run([sys.executable,str(HERE/'analyze.py')],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
    assert json.loads((ad/'analysis.json').read_text())['tables_sha256']==before
    assert digest(ad/'analysis.json')==original_analysis,'Analysis metadata changed'
    assert digest(ad/'figures.json')==original_figures,'Figures changed'
    result=dict(status='passed',binaries_reproduced=binaries,independent_comparisons=sum(r['comparisons'] for r in actual),
        identical_analysis_tables=before,unchanged_baseline_directories=unchanged,manifest_sha256=digest(HERE/'frozen/manifest.json'),
        pdf_pages=len(document),outside_text_spans=0,replacement_characters=0,executed_notebook_cells=4)
    output.write_text(json.dumps(result,indent=2)+'\n');print(output)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=Path('/tmp/mpgaa-lazy-validation.json'));main(p.parse_args().output)
