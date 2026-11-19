#!/usr/bin/env python3
"""Read-only hash/data/document audit; optional small native smoke in /tmp."""
import argparse
import csv
import json
from pathlib import Path
import subprocess
import tempfile

from analyze import HERE,ROOT,load,digest,METHODS


def validate(smoke=False):
    directory=HERE/'results/full'
    state,manifest,meta,rows,memory,hashes=load(directory)
    analysis=directory/'analysis';a=json.loads((analysis/'analysis.json').read_text())
    assert a['status']=='passed' and a['exact_disagreements']==0 and a['allocation_decision_parity']=='passed'
    assert a['analysis_source_sha256']==digest(HERE/'analyze.py')
    assert a['shared_analysis_sha256']==digest(ROOT/'cpp/experiments/analyze.py')
    assert a['episode_metrics_sha256']==digest(analysis/'episode_metrics.csv')
    assert a['raw_sha256']==hashes
    figures=json.loads((analysis/'figures.json').read_text())
    assert figures['analysis_sha256']==digest(analysis/'analysis.json')
    assert figures['source_sha256']==a['analysis_source_sha256']
    assert len(figures['files'])==16
    for path,sha in figures['files'].items():assert digest(ROOT/path)==sha,path
    for r in json.loads((HERE/'reference/origin.json').read_text())['files']:
        assert digest(ROOT/r['copy'])==r['sha256']
    dest=ROOT/'docs/experiments';supplement=json.loads((analysis/'report_provenance.json').read_text())
    assert supplement['analysis_sha256']==digest(analysis/'analysis.json')
    assert supplement['source_sha256']==digest(HERE/'report.py')
    assert supplement['body_sha256']==digest(dest/'mesh_variants_body.md')
    assert supplement['markdown_sha256']==digest(dest/'mesh_variants.md')
    assert supplement['pdf_sha256']==digest(dest/'mesh_variants.pdf')
    assert supplement['figures_manifest_sha256']==digest(analysis/'figures.json')
    assert supplement['verification_sha256']==digest(HERE/'results/verification.json')
    combined=json.loads((ROOT/'cpp/experiments/results/expanded/analysis/report_provenance.json').read_text())
    assert combined['mesh_variants_supplement']==supplement
    assert combined['source_sha256']==digest(ROOT/'cpp/experiments/report.py')
    assert combined['markdown_sha256']==digest(dest/'report.md')
    assert combined['pdf_sha256']==digest(dest/'report.pdf')
    original=ROOT/'cpp/experiments/results/expanded'
    assert combined['analysis_sha256']==digest(original/'analysis/analysis.json')
    old_analysis=json.loads((original/'analysis/analysis.json').read_text())
    for name,sha in old_analysis['raw_sha256'].items():assert digest(original/name)==sha,name
    old_state=json.loads((original/'experiment.json').read_text());assert old_state['status']=='passed'
    for name,record in old_state['jobs'].items():
        assert digest(original/(name+'.csv'))==record['csv_sha256']
        assert digest(original/(name+'.csv.json'))==record['completion_sha256']
    notebook=json.loads((dest/'analysis.ipynb').read_text())
    code_cells=[c for c in notebook['cells'] if c['cell_type']=='code']
    assert len(code_cells)==13 and [c['execution_count'] for c in code_cells]==list(range(1,14))
    assert not any(o.get('output_type')=='error' for c in code_cells for o in c['outputs'])
    pdf_audits=[]
    import fitz
    for filename in ['report.pdf','mesh_variants.pdf']:
        document=fitz.open(dest/filename);outside=[];replacements=0
        for n,page in enumerate(document):
            text=page.get_text();replacements+=text.count('\ufffd')
            for block in page.get_text('dict',clip=fitz.INFINITE_RECT())['blocks']:
                for line in block.get('lines',[]):
                    for span in line['spans']:
                        if not span['text'].strip():continue
                        x0,y0,x1,y1=span['bbox']
                        if x0<-.5 or y0<-.5 or x1>page.rect.width+.5 or y1>page.rect.height+.5:outside.append([n+1,span['text']])
        assert not outside,(filename,outside)
        assert replacements==0,(filename,replacements)
        pdf_audits.append(dict(file=filename,pages=len(document),outside_text_spans=len(outside),replacement_characters=replacements))
    smoke_checks=[]
    if smoke:
        subprocess.run(['make','-C',str(HERE),'-j2','all'],check=True)
        with tempfile.TemporaryDirectory(prefix='ima_variant_delivery_') as tmp:
            d=Path(tmp)
            for control in ['car16','grid8']:
                model=ROOT/'cpp/experiments/frozen'/f'{control}_model.txt'
                audit=subprocess.run([str(HERE/'build/test_models'),str(model)],capture_output=True,text=True,check=True)
                assert json.loads(audit.stdout)['status']=='passed'
                c=next(c for c in meta.values() if c['control']==control and
                       (c['map']=='arena' and c['family']=='off_path' if control=='car16' else c['family']=='paper_dynamic'))
                results=[]
                for suffix in ['','_memory']:
                    output=d/(control+suffix+'.csv')
                    command=[str(HERE/'build'/('experiment'+suffix)),'--input',str(ROOT/'cpp/experiments/frozen'/f'{control}_replay.txt'),
                             '--output',str(output),'--case',c['id'],'--repeats','1']
                    subprocess.run(command,cwd=ROOT,capture_output=True,text=True,check=True)
                    with output.open() as f:data=list(csv.DictReader(f))
                    assert {r['method'] for r in data}==set(METHODS)
                    ignored={'time_s','setup_s','sensing_s','peak_heap_bytes','retained_heap_bytes'}
                    results.append([{k:v for k,v in r.items() if k not in ignored} for r in data])
                assert results[0]==results[1]
                smoke_checks.append(dict(control=control,case=c['id'],rows_per_binary=len(results[0]),allocation_decision_parity=True,model_audit=json.loads(audit.stdout)))
    result=dict(status='passed',git_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                timing_rows=len(rows),memory_rows=len(memory),source_files=len(manifest['source_sha256']),
                frozen_inputs=len(manifest['records']),figure_files=len(figures['files']),pdf_audits=pdf_audits,smoke=smoke_checks)
    result['executed_notebook_cells']=len(code_cells)
    print(json.dumps(result,indent=2));return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--smoke',action='store_true');p.add_argument('--output',type=Path);args=p.parse_args()
    result=validate(args.smoke)
    if args.output:args.output.write_text(json.dumps(result,indent=2)+'\n')
