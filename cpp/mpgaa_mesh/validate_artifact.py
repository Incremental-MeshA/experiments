#!/usr/bin/env python3
"""Check a clean clone/bundle: exact binaries, oracle tests, analysis tables."""
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
    unchanged=['cpp/include/ima','cpp/experiments','cpp/navigation_sweeps','cpp/navigation_controls','cpp/mesh_variants']
    assert not subprocess.check_output(['git','diff','691b8f0','--',*unchanged],cwd=ROOT)
    subprocess.run(['make','-C',str(HERE),'-j2','all'],cwd=ROOT,check=True)
    binaries={name:digest(HERE/'build'/name) for name in state['binaries']};assert binaries==state['binaries']
    actual=[]
    for model in ['grid8','car16']:
        text=subprocess.check_output([str(HERE/'build/test'),str(ROOT/f'cpp/experiments/frozen/{model}_model.txt')],cwd=ROOT,text=True)
        record=json.loads(text);assert record['status']=='passed';actual.append(record)
    expected=[json.loads(l) for l in (HERE/'results/verification/tests.log').read_text().splitlines() if l.startswith('{')]
    assert actual==expected
    ad=HERE/'results/full/analysis';before=json.loads((ad/'analysis.json').read_text())['tables_sha256']
    analysis=json.loads((ad/'analysis.json').read_text());assert analysis['analysis_source_sha256']==digest(HERE/'analyze.py')
    for name,sha in before.items():assert digest(ad/name)==sha,name
    original_analysis_sha=digest(ad/'analysis.json');original_figures_sha=digest(ad/'figures.json')
    report=json.loads((ad/'report_provenance.json').read_text());dest=ROOT/'docs/mpgaa_mesh'
    assert report['analysis_sha256']==digest(ad/'analysis.json')
    assert report['source_sha256']==digest(HERE/'report.py') and report['layout_sha256']==digest(ROOT/'docs/experiments/layout.tex')
    assert report['vector_filter_sha256']==digest(HERE/'vector_images.lua')
    assert report['markdown_sha256']==digest(dest/'report.md') and report['pdf_sha256']==digest(dest/'report.pdf')
    assert report['figures_manifest_sha256']==digest(ad/'figures.json')
    figures=json.loads((ad/'figures.json').read_text());assert len(figures)==18
    for name,sha in figures.items():assert digest(ROOT/name)==sha,name
    notebook=json.loads((dest/'analysis.ipynb').read_text());cells=[c for c in notebook['cells'] if c['cell_type']=='code']
    assert len(cells)==4 and [c['execution_count'] for c in cells]==list(range(1,5))
    assert not any(o.get('output_type')=='error' for c in cells for o in c['outputs'])
    assert notebook['metadata']['mpgaa_mesh_artifact']['analysis_sha256']==digest(ad/'analysis.json')
    assert notebook['metadata']['mpgaa_mesh_artifact']['source_sha256']==digest(HERE/'notebook.py')
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
    assert not outside,outside[:10];assert replacements==0,replacements
    subprocess.run([sys.executable,str(HERE/'analyze.py')],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
    after=json.loads((ad/'analysis.json').read_text())['tables_sha256'];assert before==after
    assert digest(ad/'analysis.json')==original_analysis_sha,'Analysis metadata is not reproducible'
    assert digest(ad/'figures.json')==original_figures_sha,'Figure files are not reproducible'
    result=dict(status='passed',binaries_reproduced=binaries,independent_comparisons=sum(r['comparisons'] for r in actual),
                identical_analysis_tables=before,unchanged_baseline_directories=unchanged,
                manifest_sha256=digest(HERE/'frozen/manifest.json'),pdf_pages=len(document),outside_text_spans=0,replacement_characters=0,executed_notebook_cells=4)
    output.write_text(json.dumps(result,indent=2)+'\n');print(output)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=Path('/tmp/mpgaa-mesh-delivery.json'));main(p.parse_args().output)
