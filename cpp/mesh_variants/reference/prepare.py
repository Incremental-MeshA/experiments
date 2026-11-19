#!/usr/bin/env python3
"""Compile published motion primitives into lattice, mesh and contracted mesh.

No upstream implementation is copied. Costs are quantized once to 1e-6 units.
The compiler checks the origin/depth invariant needed by reverse search.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from collections import defaultdict, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCALE = 1_000_000


def load_primitives(path):
    prims = []
    for block in Path(path).read_text().split('===== prim description: =====')[1:]:
        lines = block.splitlines()
        def value(prefix):
            return next(s[len(prefix):].strip() for s in lines if s.startswith(prefix))
        trace = [tuple(map(int, x.split())) for x in block.split('collision is:\n')[1].split('---')[0].strip().splitlines()]
        goal = list(map(int, value('goal state (i, j, heading num):').split()))
        p = dict(id=int(value('prim ID is:')), heading=int(value('start heading (number):')),
                 goal=goal, cost=math.floor(float(value('length is:')) * SCALE + 0.5), trace=trace)
        assert trace[0] == (0, 0) and trace[-1] == tuple(goal[:2]) and len(trace) > 1
        assert all(a != b for a, b in zip(trace, trace[1:]))
        prims.append(p)
    prims.sort(key=lambda p: p['id'])
    assert len({(p['heading'], *p['goal']) for p in prims}) == len(prims)
    return prims


def d8(r, c):
    a, b = sorted((abs(r), abs(c)))
    return 1000 * b + 414 * a


def compile_model(prims):
    byid = {p['id']: p for p in prims}
    headings = max(p['heading'] for p in prims) + 1
    initial = [tuple((p['id'], 0) for p in prims if p['heading'] == h) for h in range(headings)]
    assert all(initial)
    confs = list(initial)
    lookup = {v: i for i, v in enumerate(confs)}
    edges = []
    delta = min(p['cost'] // (2 * (len(p['trace']) - 1)) for p in prims)
    assert delta > 0
    alpha = min(p['cost'] // d8(*p['goal'][:2]) for p in prims if d8(*p['goal'][:2]))
    q = 0
    while q < len(confs):
        conf = confs[q]
        origins = {(byid[p]['heading'], k, *byid[p]['trace'][k]) for p, k in conf}
        assert len(origins) == 1, ('nonunique origin', conf)
        depth = conf[0][1]
        groups = defaultdict(list)
        for pid, k in conf:
            p = byid[pid]
            dr, dc = (p['trace'][k+1][j] - p['trace'][k][j] for j in (0, 1))
            if k+1 == len(p['trace']) - 1:
                edges.append(dict(src=q, dst=p['goal'][2], dr=dr, dc=dc,
                                  cost=p['cost']-delta*depth, pid=pid, trace=[(0, 0), (dr, dc)]))
            else:
                groups[(dr, dc)].append((pid, k+1))
        for (dr, dc), g in sorted(groups.items()):
            g = tuple(g)
            if g not in lookup:
                lookup[g] = len(confs)
                confs.append(g)
            edges.append(dict(src=q, dst=lookup[g], dr=dr, dc=dc,
                              cost=delta, pid=-1, trace=[(0, 0), (dr, dc)]))
        q += 1
    configs = []
    for i, conf in enumerate(confs):
        pid, depth = conf[0]
        p = byid[pid]
        configs.append(dict(initial=i if i < headings else -1, depth=depth,
                            origin=p['trace'][depth], finals=list(conf)))
    mesh = dict(configs=configs, edges=edges)
    # Keep all branch/join/initial configurations. A removed node has exactly
    # one incoming AND one outgoing template edge, so no path choice is lost.
    outgoing, incoming = defaultdict(list), defaultdict(list)
    for e in edges:
        outgoing[e['src']].append(e)
        incoming[e['dst']].append(e)
    kept = [q for q in range(len(confs)) if q < headings or len(outgoing[q]) != 1 or len(incoming[q]) != 1]
    remap = {q: i for i, q in enumerate(kept)}
    contracted = []
    for q in kept:
        for first in outgoing[q]:
            e = first
            r = c = cost = 0
            trace = [(0, 0)]
            while True:
                trace.extend((r+a, c+b) for a, b in e['trace'][1:])
                r += e['dr']; c += e['dc']; cost += e['cost']
                dst = e['dst']
                if dst in remap:
                    break
                assert e['pid'] < 0
                e = outgoing[dst][0]
            contracted.append(dict(src=remap[q], dst=remap[dst], dr=r, dc=c, cost=cost,
                                   pid=e['pid'], trace=trace))
    cmesh = dict(configs=[configs[q] for q in kept], edges=contracted)
    lattice = dict(configs=[dict(initial=h, depth=0, origin=(0, 0), finals=[]) for h in range(headings)],
                   edges=[dict(src=p['heading'], dst=p['goal'][2], dr=p['goal'][0], dc=p['goal'][1],
                               cost=p['cost'], pid=p['id'], trace=p['trace']) for p in prims])
    return headings, delta, alpha, dict(lattice=lattice, mesh=mesh, cmesh=cmesh)


def write_model(path, prims, headings, delta, alpha, graph):
    with Path(path).open('w') as f:
        f.write(f'{headings} {len(prims)} {len(graph["configs"])} {len(graph["edges"])} {delta} {alpha}\n')
        for p in prims:
            f.write(' '.join(map(str, [p['id'], p['heading'], *p['goal'], p['cost'], len(p['trace']),
                                      *(v for rc in p['trace'] for v in rc)])) + '\n')
        for c in graph['configs']:
            f.write(' '.join(map(str, [c['initial'], c['depth'], *c['origin'], len(c['finals']),
                                      *(v for x in c['finals'] for v in x)])) + '\n')
        for e in graph['edges']:
            f.write(' '.join(map(str, [e['src'], e['dst'], e['dr'], e['dc'], e['cost'], e['pid'],
                                      len(e['trace']), *(v for rc in e['trace'] for v in rc)])) + '\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reference', type=Path, default=None)
    args = ap.parse_args()
    out = ROOT / 'data'; out.mkdir(exist_ok=True)
    manifest = {'cost_scale': SCALE, 'source': 'https://github.com/PathPlanning/MeshAStar', 'control_sets': {}}
    for name in ['base', 'add']:
        src = (args.reference / 'data' if args.reference else ROOT/'data/source') / f'{name}_control_set.txt'
        prims = load_primitives(src)
        h, delta, alpha, graphs = compile_model(prims)
        (out / f'{name}_primitives.json').write_text(json.dumps(prims, indent=2))
        desc = dict(primitives=len(prims), headings=h, delta=delta, alpha=alpha,
                    sha256=hashlib.sha256(src.read_bytes()).hexdigest(), graphs={})
        for kind, graph in graphs.items():
            write_model(out / f'{name}_{kind}.model', prims, h, delta, alpha, graph)
            desc['graphs'][kind] = dict(configurations=len(graph['configs']), edges=len(graph['edges']),
                                       dependency_entries=sum(len(set(e['trace'])) for e in graph['edges']))
        manifest['control_sets'][name] = desc
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
