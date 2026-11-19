"""The requested full grid protocol plus the prespecified car adaptation slice."""
import copy
import json
from run_all import HERE,ROOT,digest,verify

def read_manifest():
    mp=HERE/'frozen/manifest.json';full=json.loads(mp.read_text());verify(full)
    sp=HERE/'frozen/requested.json';selection=json.loads(sp.read_text())
    assert selection['full_manifest_sha256']==digest(mp)
    assert selection['car_dynamic']=='prespecified_anchors' and selection['grid_dynamic']=='full_36_parameter_grid'
    m=copy.deepcopy(full);m['selection_sha256']=digest(sp)
    count=timed=memory=0
    for record in m['records']:
        cases=json.loads((ROOT/record['contexts']).read_text())['cases']
        anchors=record['control']=='car16' and record['kind']=='dynamic'
        selected=[c for c in cases if not anchors or c['timing_repeats']==3]
        assert not anchors or all((c['params']['k'],c['params']['cr']) in set(map(tuple,m['anchors'])) for c in selected)
        record['selected_cases']=[c['id'] for c in selected];record['anchors_only']=anchors
        record['timed_runs']=sum(c['timing_repeats'] for c in selected)*len(m['methods'])
        count+=len(selected);timed+=record['timed_runs'];memory+=len(record['memory_cases'])*len(m['methods'])
    m['cases']=count;m['timed_runs']=timed;m['memory_runs']=memory;m['static_cases']=48;m['dynamic_cases']=count-48
    assert (count,timed,memory)==(selection['expected_cases'],selection['expected_timed_runs'],selection['expected_memory_runs'])
    return m
