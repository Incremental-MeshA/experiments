#!/usr/bin/env python3
"""Losslessly package large raw CSVs and restore their exact measured bytes."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def pack(directory,threshold=48*1024**2):
    state=json.loads((directory/'experiment.json').read_text());assert state['status']=='passed'
    if (directory/'packed_outputs.json').exists():ensure_unpacked(directory)
    manifest_path=directory/'packed_outputs.json'
    manifest=json.loads(manifest_path.read_text()) if manifest_path.exists() else dict(version=1,entries={})
    for job in state['jobs'].values():
        assert job['status']=='passed'
        for relative,expected in job['output_sha256'].items():
            path=directory/Path(relative).name
            if path.suffix!='.csv' or path.stat().st_size<threshold:continue
            target=Path(str(path)+'.gz')
            if target.exists():
                old=manifest['entries'][path.name];assert old['sha256']==expected and digest(target)==old['gzip_sha256'];continue
            temporary=Path(str(target)+'.tmp');h=hashlib.sha256()
            with temporary.open('xb') as dst:
                with gzip.GzipFile(filename='',mode='wb',fileobj=dst,mtime=0,compresslevel=6) as compressed:
                    with path.open('rb') as src:
                        for block in iter(lambda:src.read(1024*1024),b''):h.update(block);compressed.write(block)
            assert h.hexdigest()==expected,path
            temporary.replace(target)
            manifest['entries'][path.name]=dict(gzip=target.name,sha256=expected,gzip_sha256=digest(target),bytes=path.stat().st_size,gzip_bytes=target.stat().st_size)
            print('packed',path.name,path.stat().st_size,'->',target.stat().st_size,flush=True)
    manifest['source_sha256']=digest(Path(__file__));manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
    ignore=directory/'.gitignore';existing=ignore.read_text() if ignore.exists() else ''
    additional=[name for name in sorted(manifest['entries']) if name not in existing.splitlines()]
    if additional:ignore.write_text(existing+'\n# Exact raw CSV caches restored from the committed gzip files.\n'+'\n'.join(additional)+'\n')
    ensure_unpacked(directory)

def ensure_unpacked(directory):
    manifest_path=directory/'packed_outputs.json'
    if not manifest_path.exists():return
    manifest=json.loads(manifest_path.read_text());assert manifest['version']==1 and manifest['source_sha256']==digest(Path(__file__))
    for name,entry in manifest['entries'].items():
        assert Path(name).name==name and Path(entry['gzip']).name==entry['gzip']
        path=directory/name;archive=directory/entry['gzip'];assert digest(archive)==entry['gzip_sha256']
        temporary=Path(str(path)+'.restore.tmp');output=None
        if not path.exists():output=temporary.open('xb')
        h=hashlib.sha256();size=0
        try:
            with gzip.open(archive,'rb') as src:
                for block in iter(lambda:src.read(1024*1024),b''):
                    h.update(block);size+=len(block)
                    if output:output.write(block)
        finally:
            if output:output.close()
        assert h.hexdigest()==entry['sha256'] and size==entry['bytes'],name
        if output:temporary.replace(path);print('restored',name,flush=True)
        else:assert digest(path)==entry['sha256'],name

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,default=HERE/'results/full');p.add_argument('--pack',action='store_true');args=p.parse_args()
    pack(args.directory.resolve()) if args.pack else ensure_unpacked(args.directory.resolve())
