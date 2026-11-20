#!/usr/bin/env python3
"""Audit hashes, every native answer, paired subsets, reports and PDF geometry."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import pandas as pd
from analyze import HERE,ROOT,load,digest

def validate(smoke=False,directory=None):
    directory=(directory or HERE/'results/full').resolve();ad=directory/'analysis'
    state,m,meta,runs,calls,memory,hashes=load(directory)
    a=json.loads((ad/'analysis.json').read_text());assert a['status']=='passed' and a['source_sha256']==digest(HERE/'analyze.py')
    assert a['raw_sha256']==hashes and a['timed_runs']==len(runs) and a['memory_runs']==len(memory) and a['planner_calls']==len(calls)
    assert a['allocation_decision_parity']=='passed' and a['exact_cost_disagreements']==0
    if a.get('packed_outputs_sha256'):assert digest(directory/'packed_outputs.json')==a['packed_outputs_sha256']
    for name,sha in a['tables_sha256'].items():assert digest(ad/name)==sha,name
    assert digest(HERE/'results/verification.json')==a['verification_sha256']
    for p,sha in a['prior_metrics_sha256'].items():assert digest(ROOT/p)==sha,p
    figs=json.loads((ad/'figures.json').read_text());assert figs['analysis_sha256']==digest(ad/'analysis.json') and figs['source_sha256']==digest(HERE/'figures.py')
    assert len(figs['files'])==60
    for p,sha in figs['files'].items():assert digest(ROOT/p)==sha,p
    report=json.loads((ad/'report_provenance.json').read_text());dest=ROOT/'docs/experiments'
    assert report['source_sha256']==digest(HERE/'report.py') and report['analysis_sha256']==digest(ad/'analysis.json')
    assert report['figures_manifest_sha256']==digest(ad/'figures.json')
    for key,name in [('body_sha256','navigation_body.md'),('markdown_sha256','navigation.md'),('atlas_markdown_sha256','navigation_by_map.md'),('pdf_sha256','navigation.pdf'),('atlas_pdf_sha256','navigation_by_map.pdf')]:assert digest(dest/name)==report[key],name
    combined=json.loads((ROOT/'cpp/experiments/results/expanded/analysis/report_provenance.json').read_text())
    assert combined['navigation_supplement']==report and combined['source_sha256']==digest(ROOT/'cpp/experiments/report.py')
    assert combined['markdown_sha256']==digest(dest/'report.md') and combined['pdf_sha256']==digest(dest/'report.pdf')
    # Published balanced budgets: both requested/actual values are exposed in metadata and rows.
    episodes=pd.read_csv(ad/'episode_metrics.csv');dynamic=episodes[episodes.kind.eq('dynamic')]
    assert dynamic.n.eq(dynamic.k).all()
    assert ((dynamic.actual_changes<=dynamic.requested_changes)&dynamic.actual_changes.mod(2).eq(0)).all()
    assert episodes[episodes.repeats.eq(1)].peak_heap_bytes.isna().all()
    notebook=json.loads((dest/'navigation_analysis.ipynb').read_text());code=[c for c in notebook['cells'] if c['cell_type']=='code']
    assert notebook['metadata']['navigation_artifact']['analysis_sha256']==digest(ad/'analysis.json')
    assert notebook['metadata']['navigation_artifact']['source_sha256']==digest(HERE/'notebook.py')
    assert len(code)==8 and [c['execution_count'] for c in code]==list(range(1,9))
    assert not any(o.get('output_type')=='error' for c in code for o in c['outputs'])
    import fitz
    pdf_audits=[]
    for name in ['navigation.pdf','navigation_by_map.pdf','report.pdf']:
        document=fitz.open(dest/name);outside=[];replacement=0
        for i,page in enumerate(document):
            replacement+=page.get_text().count('\ufffd')
            for block in page.get_text('dict',clip=fitz.INFINITE_RECT())['blocks']:
                for line in block.get('lines',[]):
                    for span in line['spans']:
                        if not span['text'].strip():continue
                        x0,y0,x1,y1=span['bbox']
                        if x0<-.5 or y0<-.5 or x1>page.rect.width+.5 or y1>page.rect.height+.5:outside.append([i+1,span['text']])
        assert not outside,(name,outside[:10]);assert replacement==0,(name,replacement)
        pdf_audits.append(dict(file=name,pages=len(document),outside_text_spans=0,replacement_characters=0))
    if smoke:
        subprocess.run(['make','-C',str(HERE),'-j2','all','test'],cwd=ROOT,check=True)
        # Keep the recorded sanitizer evidence unchanged on delivery validation.
        with tempfile.TemporaryDirectory(prefix='ima_nav_delivery_') as tmp:
            d=Path(tmp);data=[]
            for suffix in ['','_memory']:
                prefix=d/('grid'+suffix)
                command=[str(HERE/'build'/('experiment'+suffix)),'--input',str(HERE/'frozen/grid8_random50_p20_dynamic.txt'),
                         '--specs',str(HERE/'frozen/grid8_random50_p20_dynamic.specs.txt'),'--visibility',str(HERE/'frozen/grid8_visibility.txt'),
                         '--case','random50_p20__dynamic__s68101__k2__cr5__n2','--output',str(prefix),'--repeats','1']
                subprocess.run(command,cwd=ROOT,capture_output=True,text=True,check=True)
                frame=pd.read_csv(str(prefix)+'_runs.csv');data.append(frame.set_index('method').fingerprint.sort_index())
            pd.testing.assert_series_equal(*data)
    result=dict(status='passed',cases=len(meta),timed_runs=len(runs),memory_runs=len(memory),planner_calls=len(calls),
                figure_files=len(figs['files']),executed_notebook_cells=len(code),frozen_source_files=len(m['source_sha256']),pdf_audits=pdf_audits,smoke=smoke)
    print(json.dumps(result,indent=2));return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--smoke',action='store_true');p.add_argument('--output',type=Path);p.add_argument('--directory',type=Path,default=HERE/'results/full');args=p.parse_args();r=validate(args.smoke,args.directory)
    if args.output:args.output.write_text(json.dumps(r,indent=2)+'\n')
