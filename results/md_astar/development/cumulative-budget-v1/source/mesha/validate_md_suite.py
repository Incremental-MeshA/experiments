"""Check MD-A* and its shared MPGAA* backend on every upstream query."""
import hashlib
import json
import math
from pathlib import Path

from mesha.benchmark import load_benchmark,load_named_maps
from mesha.incremental import make_planner
from mesha.mesh import build_mesh
from mesha.primitives import build_control_set
from mesha.selfcheck_deferred import validate_path

ROOT=Path(__file__).resolve().parents[1]


def main():
    benchmark=load_benchmark();maps=load_named_maps(benchmark)
    historical=json.loads((ROOT/'results/runs.json').read_text())
    expected={(r['id'],r['query']):r['cost'] for r in historical['records']
              if r['algorithm']=='lba' and r['weight']==1.0}
    control=build_control_set('car16');mesh=build_mesh(control);checks=0
    for i,case in enumerate(benchmark['instances']):
        first=case['queries'][0];grid=maps[case['map']]
        for kind in ['mpgaa','md_astar']:
            planner=make_planner(kind,grid,control,mesh,first['start'],first['goal'])
            current=grid.copy()
            for qi,q in enumerate(case['queries']):
                blocks=tuple(map(tuple,q['new_blocks']))
                for cell in blocks:current[cell]=1
                r=planner.plan() if qi==0 else planner.replan(q['start'],blocks)
                assert r.success and not r.capped
                assert abs(r.cost-expected[case['id'],qi])<1e-6,(case['id'],qi,kind,r.cost,expected[case['id'],qi])
                validate_path(current,control,tuple(q['start']),tuple(q['goal']),r);checks+=1
        if i%12==0:print(i+1,'/',len(benchmark['instances']),flush=True)
    paths=['mesha/adaptive.py','mesha/deferred.py','mesha/incremental.py','mesha/mesh.py','mesha/primitives.py']
    result=dict(status='passed',instances=len(benchmark['instances']),queries=3*len(benchmark['instances']),
          comparisons=checks,path_validations=checks,cost_tolerance=1e-6,
          oracle='Frozen upstream LBA* costs at weight 1; no historical times reused.',
          sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths})
    out=ROOT/'results/md_astar';out.mkdir(parents=True,exist_ok=True)
    (out/'full_verification.json').write_text(json.dumps(result,indent=2)+'\n');print(result,flush=True)


if __name__=='__main__':main()
