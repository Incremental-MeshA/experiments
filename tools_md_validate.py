#!/usr/bin/env python3
"""Check native provenance, raw completeness, notebook, PDF, and optional bundle."""
import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

import fitz
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'results/md_astar'


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main(bundle=None):
    analysis=json.loads((OUT/'analysis.json').read_text());assert analysis['status']=='passed'
    for p,sha in analysis['environment']['sha256'].items():assert digest(ROOT/p)==sha,p
    assert digest(OUT/'raw.jsonl')==analysis['raw_sha256']
    origin=json.loads((ROOT/'docs/md_astar/reference/ORIGIN.json').read_text())
    for p,sha in origin['sha256'].items():assert digest(ROOT/'docs/md_astar/reference'/p)==sha
    report=dict(provenance='passed',raw_runs=analysis['runs'],query_calls=analysis['query_calls'])
    notebook=json.loads((ROOT/'md_astar.ipynb').read_text());codes=[c for c in notebook['cells'] if c['cell_type']=='code']
    assert all(c['execution_count'] is not None for c in codes)
    assert not any(o.get('output_type')=='error' for c in codes for o in c.get('outputs',[]))
    report['notebook']=dict(executed_cells=len(codes),errors=0)
    pdf=ROOT/'docs/md_astar/report.pdf';doc=fitz.open(pdf);outside=[];outside_text=[];vectors=[]
    for i,page in enumerate(doc):
        for block in page.get_text('dict')['blocks']:
            if block['type']==0:
                for line in block['lines']:
                    for span in line['spans']:
                        if not page.rect.contains(fitz.Rect(span['bbox'])):outside_text.append(dict(page=i+1,text=span['text']))
        for info in page.get_image_info():
            if not page.rect.contains(fitz.Rect(info['bbox'])):outside.append(dict(page=i+1,bbox=info['bbox']))
    def transform(p,m):
        a,b,c,d,e,f=map(float,m);x,y=p;return a*x+c*y+e,b*x+d*y+f
    for i,page in enumerate(PdfReader(pdf).pages):
        objects=page['/Resources'].get('/XObject',{})
        def visit(op,args,cm,tm):
            if op!=b'Do' or args[0] not in objects:return
            obj=objects[args[0]].get_object();box=obj.get('/BBox')
            if not box:return
            x0,y0,x1,y1=map(float,box);matrix=obj.get('/Matrix',[1,0,0,1,0,0])
            pts=[transform(transform(p,matrix),cm) for p in [(x0,y0),(x0,y1),(x1,y0),(x1,y1)]]
            bbox=[min(p[0] for p in pts),min(p[1] for p in pts),max(p[0] for p in pts),max(p[1] for p in pts)];record=dict(page=i+1,bbox=bbox);vectors.append(record)
            if bbox[0]<float(page.mediabox.left)-.01 or bbox[1]<float(page.mediabox.bottom)-.01 or bbox[2]>float(page.mediabox.right)+.01 or bbox[3]>float(page.mediabox.top)+.01:outside.append(record)
        page.extract_text(visitor_operand_before=visit)
    assert not outside and not outside_text,(outside,outside_text)
    assert len(vectors)==3,len(vectors)
    text='\n'.join(p.get_text() for p in doc)
    assert str(analysis['query_calls']) in text.replace(' ','')
    report['pdf']=dict(pages=len(doc),vector_figures=vectors,outside_figures=outside,outside_text=outside_text)
    if bundle:
        bundle=Path(bundle).resolve()
        subprocess.run(['git','bundle','verify',str(bundle)],cwd=ROOT,check=True,capture_output=True)
        with tempfile.TemporaryDirectory(prefix='md_astar_bundle_') as directory:
            project=Path(directory)/'introduction'
            subprocess.run(['git','clone','-q','-b','research/md-astar',str(bundle),str(project)],check=True,capture_output=True)
            for p,sha in analysis['environment']['sha256'].items():assert digest(project/p)==sha,p
            run=subprocess.run(['python','-m','mesha.selfcheck_deferred'],cwd=project,check=True,capture_output=True,text=True,timeout=300)
            result=json.loads((project/'results/md_astar/verification.json').read_text());assert result['status']=='passed'
            report['portable_bundle']=dict(status='passed',sha256=digest(bundle),comparisons=result['comparisons'],oracle_snapshots=result['oracle_snapshots'])
    report['status']='passed'
    (OUT/'artifact_validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--bundle');args=p.parse_args();main(args.bundle)
