#!/usr/bin/env python3
"""Stage two: terminal pruning plus consistency-preserving adaptive lifting."""
import hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
NATIVE=['lift_mesh','cascade_lift','lift_cold','lift_noprune','cascade_cold']
OLD=['lba_reuse','mesha','mesha_reuse','mpgaa','batch_mpgaa','md_astar','boundary_mesh','conditional_dstar','cmesh_dstar']
NAV=['lift_mesh','cascade_lift','cascade_mesh','lift_cold','cascade_cold','mesha_reuse','lba_reuse','batch_mpgaa','md_astar','conditional_dstar','cmesh_dstar']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 dest=HERE/'frozen';dest.mkdir(exist_ok=True);assert not (dest/'manifest.json').exists()
 first=ROOT/'cpp/mesh_vertex/frozen/manifest.json';prior=json.loads(first.read_text());plan=[]
 files=dict(prior['files'])
 contexts=json.loads((ROOT/prior['contexts_file']).read_text())
 for v in contexts.values():v['stage']='terminal_lift_validation'
 p=dest/'contexts.json';p.write_text(json.dumps(contexts,ensure_ascii=False,indent=1)+'\n');files[str(p.relative_to(ROOT))]=sha(p)
 for j in prior['plan']:
  methods=NATIVE+OLD+['cascade_mesh']+(['octile_reuse'] if j['name'].endswith('grid8') else []) if j['mode']=='replay' else NAV
  plan.append(dict(j,methods=methods))
 sources=dict(prior['sources'])
 for p in list(HERE.glob('*.hpp'))+[HERE/x for x in ['replay.cpp','navigation.cpp','test.cpp','Makefile','prepare.py','run_all.py','mutation.py']]:sources[str(p.relative_to(ROOT))]=sha(p)
 m=dict(version=1,base_commit='de6c4e93f2ce76500c418fc9fbbdb5026b4c3ff9',parent_study_manifest_sha256=sha(first),repeats=3,cap=1000000,seed=982313,primary_methods=['lift_mesh','cascade_lift'],controls=OLD+['cascade_mesh','lift_cold','cascade_cold','lift_noprune','octile_reuse'],ablations=['lift_cold','cascade_cold','lift_noprune'],plan=plan,files=files,sources=sources,contexts_file='cpp/mesh_lift/frozen/contexts.json',protocol='Second-stage design after observing 270 aggregate capped calls in the first car replay cohort, before inspecting its aggregate timing comparisons. Full original mesh graph retained. Terminal-closed pruning from MeshA* is combined with local forward h lifting so adaptive consistency is preserved; naive pruning without lifting is tested by a generated mutant. Shared-core cold controls, a no-pruning ablation, the previous Cascade mesh planner, and all eight strong repository controls are freshly remeasured. SAME232 public configurations:52 car replay(48balanced+4history),96grid,84car navigation(sixmaps,two roots,four radii and three n=k dynamic anchors). No new independent maps or holdout claim; no seconds pooled with stage one. Three randomized serial repeats and one separate allocation pass. No algorithm tuning after this freeze.')
 m.update(scenarios=sum(j['cases'] for j in plan),timed_runs=sum(j['cases']*len(j['methods'])*3 for j in plan),memory_runs=sum(j['cases']*len(j['methods']) for j in plan))
 m['protocol']+=' Pre-timing control amendment: MeshA* with standard suffix reuse added to avoid a weak cold-only mesh comparator; the preceding draft manifest is retained. Both cold native variants remain in the fastest-control envelope.'
 assert (m['scenarios'],m['timed_runs'],m['memory_runs'])==(232,9720,3240)
 (dest/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n');print(m['scenarios'],m['timed_runs'],m['memory_runs'])
if __name__=='__main__':main()
