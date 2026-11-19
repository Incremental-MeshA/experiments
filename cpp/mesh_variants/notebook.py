#!/usr/bin/env python3
"""Execute the combined notebook without replacing either cohort's cells."""
import os
from pathlib import Path
import tempfile

import nbformat
from nbclient import NotebookClient

ROOT=Path(__file__).resolve().parents[2]


def main():
    for variable,name in [('IPYTHONDIR','ima_mesh_ipython'),('JUPYTER_RUNTIME_DIR','ima_mesh_jupyter')]:
        directory=Path(tempfile.gettempdir())/name;directory.mkdir(exist_ok=True)
        os.environ.setdefault(variable,str(directory))
    path=ROOT/'docs/experiments/analysis.ipynb'
    notebook=nbformat.read(path,as_version=4)
    assert sum(c.cell_type=='code' for c in notebook.cells)==13
    NotebookClient(notebook,timeout=120,kernel_name='python3',resources={'metadata':{'path':str(ROOT)}}).execute()
    nbformat.write(notebook,path)
    print('Executed 13 code cells:',path)


if __name__=='__main__':main()
