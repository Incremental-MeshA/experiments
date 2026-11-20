#!/usr/bin/env python3
"""Independent count-only pass; never use this binary for timing comparisons.

The legacy checked_cells counter counts explicit trace/node checks and omits
endpoint eligibility reads. Instrument Grid.free in a generated header overlay,
count ONLY around Planner::replan, and verify all old logical fields against the
unmodified timing cohort. No measured source file is changed.
"""
import hashlib,json,shutil,subprocess,sys,os,argparse
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def prepare():
 dest=HERE/'build/overlay';dest.mkdir(parents=True,exist_ok=True)
 manifest=json.loads((ROOT/'cpp/mesh_conditional/frozen/manifest.json').read_text())
 for p,h in manifest['sources'].items():assert sha(ROOT/p)==h,p
 files={}
 for p in (ROOT/'cpp').rglob('*.hpp'):
  if 'build' in p.relative_to(ROOT/'cpp').parts:continue
  q=dest/p.relative_to(ROOT);q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q);files[str(p.relative_to(ROOT))]=sha(p)
 model=dest/'cpp/include/ima/model.hpp';s=model.read_text();s=s.replace('struct Grid {','inline std::uint64_t mesh_study_free_calls=0;\nstruct Grid {');old='bool free(Cell c) const { return inside(c)';new='bool free(Cell c) const { ++mesh_study_free_calls; return inside(c)';assert old in s;s=s.replace(old,new);model.write_text(s)
 source=ROOT/'cpp/mesh_conditional/replay.cpp';s=source.read_text();s=s.replace('Stats st;mesh_conditional::Work mesh;', 'std::uint64_t all_free_calls=0;\n    Stats st;mesh_conditional::Work mesh;')
 old="mesh_conditional::write_work(out,r.mesh);out<<'\\n';";new="mesh_conditional::write_work(out,r.mesh);out<<','<<r.all_free_calls<<'\\n';";assert old in s;s=s.replace(old,new)
 old='<<mesh_conditional::work_columns<<"\\n";';new='<<mesh_conditional::work_columns<<",all_free_calls\\n";';assert old in s;s=s.replace(old,new)
 old='Path answer=p->replan(s,blocks,opens); row.time=seconds(clock);';new='mesh_study_free_calls=0;Path answer=p->replan(s,blocks,opens);row.all_free_calls=mesh_study_free_calls; row.time=seconds(clock);';assert old in s;s=s.replace(old,new)
 target=dest/'cpp/mesh_conditional/replay_count.cpp';target.write_text(s)
 command=['g++','-O3','-DNDEBUG','-std=c++17','-Wall','-Wextra','-Wpedantic','-I'+str(dest/'cpp/include'),'-I'+str(dest/'cpp/experiments'),'-I'+str(dest/'cpp/mesh_variants'),'-I'+str(dest/'cpp/navigation_sweeps'),'-DIMA_EXPERIMENT_FLAGS="count-only -O3 -DNDEBUG -std=c++17"',str(target),'-o',str(HERE/'build/replay_count')]
 subprocess.run(command,cwd=ROOT,check=True)
 state=dict(status='built',original_sources=files,original_replay_sha256=sha(source),patcher_sha256=sha(Path(__file__)),patched_model_sha256=sha(model),patched_replay_sha256=sha(target),binary_sha256=sha(HERE/'build/replay_count'),command=command,methods=['envelope_mesh','dual_mesh','lattice_envelope','circuit_mesh','conditional_dstar'],definition='Number of Grid.free calls during replan, including endpoint gates and outside-grid probes; excludes direct Grid.blocked calls in common input normalization and all verification/reference calls. Count-only binary; timings discarded.')
 (HERE/'build/manifest.json').write_text(json.dumps(state,indent=2)+'\n');print('COUNT_BINARY_BUILT',flush=True)
def run():
 manifest=json.loads((HERE/'build/manifest.json').read_text());assert manifest['binary_sha256']==sha(HERE/'build/replay_count') and manifest['patcher_sha256']==sha(Path(__file__))
 for p,h in manifest['original_sources'].items():assert sha(ROOT/p)==h,p
 m=json.loads((ROOT/'cpp/mesh_conditional/frozen/manifest.json').read_text());out=HERE/'results';out.mkdir(exist_ok=True);jobs={}
 for job in m['plan']:
  target=out/(job['name']+'.csv');assert not target.exists()
  args=[str(HERE/'build/replay_count'),'--input',str(ROOT/job['input']),'--output',str(target),'--methods',','.join(manifest['methods']),'--repeats','1','--seed','831019','--cap',str(m['cap'])]
  print('counting',job['name'],flush=True)
  with target.with_suffix('.log').open('w') as f:subprocess.run(args,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,check=True)
  meta=json.loads(Path(str(target)+'.json').read_text());assert meta['status']=='passed'
  jobs[job['name']]=dict(command=args,runs=meta['runs'],rows=meta['rows'],csv_sha256=sha(target),json_sha256=sha(Path(str(target)+'.json')))
 state=dict(manifest,status='passed',jobs=jobs);(out/'experiment.json').write_text(json.dumps(state,indent=2)+'\n');print('COUNTS_PASSED',flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--build',action='store_true');a=p.parse_args();prepare() if a.build else run()
