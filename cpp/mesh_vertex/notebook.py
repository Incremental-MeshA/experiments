#!/usr/bin/env python3
"""Execute a compact notebook tied to the validated case-level data."""
from pathlib import Path
import os,hashlib,json
import nbformat
from nbclient import NotebookClient
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];DEST=ROOT/'docs/mesh_vertex'
def main():
 for name,path in [('JUPYTER_RUNTIME_DIR','/tmp/mesh-vertex-jupyter'),('IPYTHONDIR','/tmp/mesh-vertex-ipython')]:os.environ.setdefault(name,path);Path(os.environ[name]).mkdir(parents=True,exist_ok=True)
 cells=[nbformat.v4.new_markdown_cell('# Incremental search on actual mesh vertices\n\nAll timings are from one fresh frozen study. Ratios above one favor the candidate; incomplete navigation is never a time win. Intermediate mesh vertices carry g, learned h, OPEN entries and policies.'),
 nbformat.v4.new_code_cell("from pathlib import Path\nimport json, hashlib\nimport pandas as pd\nfrom IPython.display import display, Image\nroot=Path.cwd()\nad=root/'cpp/mesh_vertex/results/full/analysis'\na=json.loads((ad/'analysis.json').read_text())\nassert a['status']=='passed'\nfor name,h in a['tables_sha256'].items():\n    assert hashlib.sha256((ad/name).read_bytes()).hexdigest()==h\n{k:a[k] for k in ['scenarios','timed_runs','memory_runs','allocation_matched_rows','exact_cost_disagreements','capped_calls','contour_equivalence_queries','count_only_runs']}"),
 nbformat.v4.new_code_cell("s=pd.read_csv(ad/'summary.csv')\ndisplay(s[s.baseline.isin(['best_control','mesh_mpgaa','trigger_mesh','contour_only','cascade_heap'])])\ndisplay(Image(filename=str(root/'docs/mesh_vertex/figures/profile.png')))"),
 nbformat.v4.new_code_cell("m=pd.read_csv(ad/'map_pairs.csv')\ndisplay(m[m.baseline.eq('best_control')])\ndisplay(pd.read_csv(ad/'parameter_pairs.csv').query(\"baseline=='mesh_mpgaa' and cohort!='replay'\"))\ndisplay(Image(filename=str(root/'docs/mesh_vertex/figures/radius.png')))"),
 nbformat.v4.new_code_cell("w=pd.read_csv(ad/'work.csv')\ndisplay(w.query(\"cohort=='replay' and control=='car16' and panel=='main'\").groupby('method')[['mv_boundary_expansions','mv_interior_expansions','notify_probes','mv_heap_pushes','mv_repair_heap_pushes','mv_repair_local_steps']].sum())\ndisplay(pd.read_csv(ad/'completion.csv'))\ndisplay(pd.read_csv(ad/'collision_probes.csv').groupby(['control','method'])[['all_free_calls','online_calls']].sum())\ndisplay(Image(filename=str(root/'docs/mesh_vertex/figures/amortization.png')))"),
 nbformat.v4.new_markdown_cell('Snapshot fields are not additive work; old checked_cells has partial coverage, so the independent all-Grid.free pass supplies common API counts. The contribution hypothesis concerns the mesh repair combination; MPGAA*, watched dependencies, potentials and fringe processing have prior work. Per-map losses, caps, clamped rates, trajectories, peak memory and full claim limits are retained in report.pdf and related_work.md.')]
 meta=dict(kernelspec=dict(name='python3',display_name='Python 3',language='python'),mesh_vertex_artifact=dict(source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),analysis_sha256=hashlib.sha256((HERE/'results/full/analysis/analysis.json').read_bytes()).hexdigest()))
 nb=nbformat.v4.new_notebook(cells=cells,metadata=meta);NotebookClient(nb,timeout=180,kernel_name='python3',resources={'metadata':{'path':str(ROOT)}}).execute();p=DEST/'analysis.ipynb';nbformat.write(nb,p);print(p)
if __name__=='__main__':main()
