#!/usr/bin/env python3
"""Build suffix-sharing mesh: reverse primitives, build mesh, reverse its edges.

The resulting graph still represents FORWARD original primitive paths. Its
backward D* Lite traversal shares original suffixes, unlike the prefix mesh.
"""
import json
from pathlib import Path
from prepare import ROOT,compile_model,load_primitives,write_model


def main():
    stats={}
    for control in ['base','add']:
        prims=load_primitives(ROOT/f'data/source/{control}_control_set.txt')
        rev=[]
        for p in prims:
            dr,dc,th=p['goal']
            rev.append(dict(id=p['id'],heading=th,goal=[-dr,-dc,p['heading']],cost=p['cost'],
                            trace=[(r-dr,c-dc) for r,c in reversed(p['trace'])]))
        headings,delta,alpha,graphs=compile_model(rev)
        graph=graphs['mesh']
        edges=[]
        for e in graph['edges']:
            dr,dc=e['dr'],e['dc']
            edges.append(dict(src=e['dst'],dst=e['src'],dr=-dr,dc=-dc,cost=e['cost'],pid=e['pid'],
                              trace=[(r-dr,c-dc) for r,c in reversed(e['trace'])]))
        suffix=dict(configs=graph['configs'],edges=edges)
        write_model(ROOT/f'data/{control}_suffix.model',prims,headings,delta,alpha,suffix)
        stats[control]=dict(configurations=len(graph['configs']),edges=len(edges),
                            dependency_entries=sum(len(set(e['trace'])) for e in edges),delta=delta,alpha=alpha)
    (ROOT/'data/suffix_manifest.json').write_text(json.dumps(stats,indent=2)+'\n')
    print(json.dumps(stats,indent=2))


if __name__=='__main__':main()
