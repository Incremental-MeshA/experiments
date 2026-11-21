#!/usr/bin/env python3
"""Full Grid.free counts in generated header copies; discard its wall times."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main(directory,output,build_only=False):
 m=json.loads((HERE/'frozen/manifest.json').read_text());state=json.loads((directory/'experiment.json').read_text());assert state['status']=='passed'
 for p,h in m['sources'].items():assert sha(ROOT/p)==h,p
 if (output/'experiment.json').exists() and not build_only:
  old=json.loads((output/'experiment.json').read_text());assert old['status']=='passed' and old['source_sha256']==sha(Path(__file__)) and old['manifest_sha256']==sha(HERE/'frozen/manifest.json')
  for j in old['jobs']:
   p=output/(j['name']+'.csv');assert sha(p)==j['csv_sha256'] and sha(Path(str(p)+'.json'))==j['metadata_sha256']
  print('COUNTS_CACHED');return
 overlay=HERE/'build/count_overlay';overlay.mkdir(parents=True,exist_ok=True)
 for name in m['sources']:
  if not name.endswith('.hpp'):continue
  p=overlay/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,p)
 p=overlay/'cpp/include/ima/model.hpp';s=p.read_text();old='bool free(Cell c) const { return inside(c)';assert old in s;s=s.replace('struct Grid {','inline std::uint64_t lift_probe_free_calls=0;\nstruct Grid {').replace(old,'bool free(Cell c) const { ++lift_probe_free_calls; return inside(c)');p.write_text(s)
 source=HERE/'replay.cpp';s=source.read_text();s=s.replace('Stats st;mesh_lift::Work mesh;','std::uint64_t all_free_calls=0;Stats st;mesh_lift::Work mesh;')
 old="mesh_lift::write_work(out,r.mesh);out<<'\\n';";assert old in s;s=s.replace(old,"mesh_lift::write_work(out,r.mesh);out<<','<<r.all_free_calls<<'\\n';")
 old='<<mesh_lift::work_columns<<"\\n";';assert old in s;s=s.replace(old,'<<mesh_lift::work_columns<<",all_free_calls\\n";')
 old='Path answer=p->replan(s,blocks,opens); row.time=seconds(clock);';assert old in s;s=s.replace(old,'lift_probe_free_calls=0;Path answer=p->replan(s,blocks,opens);row.all_free_calls=lift_probe_free_calls; row.time=seconds(clock);')
 target=overlay/'cpp/mesh_lift/replay_count.cpp';target.write_text(s);binary=HERE/'build/replay_count'
 command=['g++','-O3','-DNDEBUG','-std=c++17','-Wall','-Wextra','-Wpedantic']+['-I'+str(overlay/'cpp'/x) for x in ['include','experiments','mesh_variants','navigation_sweeps']]+['-DIMA_EXPERIMENT_FLAGS="count-only -O3 -std=c++17"',str(target),'-o',str(binary)]
 subprocess.run(command,cwd=ROOT,check=True)
 if build_only:print('COUNT_BINARY_BUILT',sha(binary));return
 d=output;d.mkdir(parents=True,exist_ok=True);jobs=[]
 for job in m['plan']:
  if job['mode']!='replay':continue
  p=d/(job['name']+'.csv');args=[str(binary),'--input',str(ROOT/job['input']),'--output',str(p),'--methods',','.join(job['methods']),'--repeats','1','--seed',str(m['seed']),'--cap',str(m['cap'])]
  print('counting',job['name'],flush=True)
  if not p.exists():
   with p.with_suffix('.log').open('w') as log:subprocess.run(args,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
  meta=json.loads(Path(str(p)+'.json').read_text());assert meta['status']=='passed'
  jobs.append(dict(name=job['name'],command=args,runs=meta['runs'],csv_sha256=sha(p),metadata_sha256=sha(Path(str(p)+'.json'))))
 result=dict(status='passed',source_sha256=sha(Path(__file__)),manifest_sha256=sha(HERE/'frozen/manifest.json'),binary_sha256=sha(binary),patched_source_sha256=sha(target),patched_model_sha256=sha(overlay/'cpp/include/ima/model.hpp'),command=command,jobs=jobs,definition='All Grid.free invocations strictly inside replan, including eligibility gates and outside-map probes; excludes direct Grid.blocked normalization, constructor, and reference/path verification. Logical API calls, not hardware loads. Times discarded.')
 (d/'experiment.json').write_text(json.dumps(result,indent=2)+'\n');print('PROBES_PASSED',sum(j['runs'] for j in jobs))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,default=HERE/'results/full');p.add_argument('--output',type=Path,default=HERE/'results/probes');p.add_argument('--build-only',action='store_true');a=p.parse_args();main(a.directory,a.output,a.build_only)
