#!/usr/bin/env python3
"""Freeze workloads from reference A* trajectories, before candidate timings."""
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mesha.maps import load_map, save_map
from mesha.mesh import build_mesh
from mesha.primitives import _assemble, build_control_set

HERE = Path(__file__).resolve().parent
OUT = HERE/'frozen'
SEEDS = [48101, 48102]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write_suite(path, control, cases):
    mesh = build_mesh(control)
    maps, index = [], {}
    for c in cases:
        g = c['_initial']
        key = (g.shape, g.tobytes())
        if key not in index:
            index[key] = len(maps)
            maps.append(g)
        c['_map_index'] = index[key]
    with path.open('w', newline='\n') as f:
        def row(*xs):
            def token(x):
                if isinstance(x, str):
                    return json.dumps(x)
                return format(x, '.17g') if isinstance(x, float) else str(x)
            f.write(' '.join(map(token, xs))+'\n')
        f.write('IMA_CPP 1\n')
        row(control.name, control.n_theta, len(control), mesh.n_configs)
        row(*mesh.initial_of_theta)
        for p in control.primitives:
            row(p.start_theta, p.end_theta, p.di, p.dj, p.cost, len(p.cells))
            row(*(v for cell in p.cells for v in cell))
        for k in range(mesh.n_configs):
            row(mesh.theta_of_config[k], *mesh.origin[k], mesh.signature[k], len(mesh.successors[k]), len(mesh.finals[k]))
            for e in mesh.successors[k]:
                row(*e)
            for e in mesh.finals[k]:
                row(*e)
        row(len(maps))
        for k, g in enumerate(maps):
            row('map_'+str(k), *g.shape)
            for line in g:
                f.write(''.join('#' if x else '.' for x in line)+'\n')
        row(len(cases))
        for c in cases:
            row(c['id'], c['family'], c['_map_index'], len(c['queries']))
            for q in c['queries']:
                row(*q['start'], *q['goal'], float(q['expected']) if q['expected'] is not None else -1.0,
                    q.get('category', 'event'), q.get('event', 'event'), len(q['blocks']), len(q['opens']))
                if q['blocks']:
                    row(*(v for cell in q['blocks'] for v in cell))
                if q['opens']:
                    row(*(v for cell in q['opens'] for v in cell))
    clean = [{k: v for k, v in c.items() if not k.startswith('_')} for c in cases]
    path.with_suffix('.contexts.json').write_text(json.dumps(dict(control=control.name, cases=clean), indent=1)+'\n')
    return dict(path=str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path), sha256=sha(path), cases=len(cases), snapshots=sum(len(c['queries']) for c in cases))


class Reference:
    def __init__(self, model):
        self.p = subprocess.Popen([str(HERE/'build/experiment'), '--serve', '--input', str(model)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)

    def plan(self, grid, start, goal):
        self.p.stdin.write('plan '+' '.join(map(str, [*grid.shape, *start, *goal]))+'\n')
        for line in grid:
            self.p.stdin.write(''.join('#' if x else '.' for x in line)+'\n')
        self.p.stdin.flush()
        text = self.p.stdout.readline()
        if not text:
            raise RuntimeError('Reference process stopped')
        r = json.loads(text)
        if r['capped']:
            raise RuntimeError('Reference A* exhausted 3M expansions')
        r['states'] = [tuple(x) for x in r['states']]
        return r

    def close(self):
        self.p.stdin.write('quit\n'); self.p.stdin.flush(); self.p.stdin.close()
        if self.p.wait() != 0:
            raise RuntimeError('Reference process failed')


def covered(control, result, at=0):
    return {(result['states'][k][0]+a, result['states'][k][1]+b)
            for k in range(at, len(result['ids'])) for a, b in control.primitives[result['ids'][k]].cells}


def feasible(grid, control, result, at=0):
    return result['cost'] is not None and all(not grid[x] for x in covered(control, result, at))


def heading(control, di, dj):
    return max(range(control.n_theta), key=lambda k: (control.dirs[k][0]*di+control.dirs[k][1]*dj)/math.hypot(*control.dirs[k]))


def make_maps():
    spec = [
        ('Berlin', ROOT/'data/maps/Berlin_2_256.map', None, 'city'),
        ('AR0700', ROOT/'data/maps/AR0700SR.map', None, 'game'),
        ('arena', HERE/'maps/arena.map', None, 'DAO'),
        ('MA_room96', HERE/'maps/16room_000.map', (0, 0, 96), 'room'),
        ('MA_random96', HERE/'maps/random512-10-0.map', (0, 0, 96), 'random'),
        ('MA_maze96', HERE/'maps/maze512-16-0.map', (0, 0, 96), 'maze'),
    ]
    result = {}
    for name, path, crop, family in spec:
        g = load_map(path)
        original_shape = g.shape
        if crop:
            i, j, size = crop
            g = g[i:i+size, j:j+size].copy()
        result[name] = (g, dict(map=name, map_family=family, shape=list(g.shape), truth_density=float(g.mean()),
                               source=str(path.relative_to(ROOT)), source_sha256=sha(path), original_shape=list(original_shape), crop=crop))
    for density in [10, 20, 30, 40]:
        name = f'random50_p{density}'
        g = (np.random.default_rng(7120+density).random((50, 50)) < density/100).astype(np.uint8)
        save_map(HERE/'maps'/f'{name}.map', g)
        result[name] = (g, dict(map=name, map_family='random50', shape=[50, 50], truth_density=float(g.mean()),
                               source='generated Bernoulli', density_parameter=density/100, map_seed=7120+density))
    return result


def choose_root(grid, control, server, seed, label, rejections):
    rng = np.random.default_rng(int(hashlib.sha256(f'{label}:{seed}'.encode()).hexdigest()[:12], 16))
    free = np.argwhere(grid == 0)
    for trial in range(200):
        a, b = free[rng.integers(len(free), size=2)]
        d = float(np.linalg.norm(a-b))
        if not 30 <= d <= 75:
            continue
        t = heading(control, *(b-a)) if control.n_theta > 1 else 0
        s, goal = (*map(int, a), t), (*map(int, b), t)
        r = server.plan(grid, s, goal)
        if r['cost'] is not None and 16 <= len(r['ids']) <= 100 and r['cost'] < 180:
            return s, goal, r
        rejections.append(dict(map=label, seed=seed, trial=trial, start=s, goal=goal, reason='unreachable or outside frozen length stratum', cost=r['cost']))
    raise RuntimeError('Cannot select reference-solvable root: '+label)


def observe(truth, belief, start, radius, seen):
    i, j, _ = start
    sl = np.s_[max(0, i-radius):min(truth.shape[0], i+radius+1), max(0, j-radius):min(truth.shape[1], j+radius+1)]
    old = belief.copy()
    newly = int((seen[sl] == 0).sum()); seen[sl] = 1; belief[sl] = truth[sl]
    blocks = list(map(tuple, np.argwhere((belief == 1) & (old == 0)).tolist()))
    opens = list(map(tuple, np.argwhere((belief == 0) & (old == 1)).tolist()))
    return blocks, opens, newly


def base_case(info, control, seed, start, goal, result, family, **params):
    return dict(**info, control=control.name, seed=seed, start=start, goal=goal, truth_optimum=result['cost'],
                family=family, params=params, panels=[], queries=[])


def replay(grid, info, control, server, root, seed, family, batch=8, interval=2, radius=8, events=8):
    start, goal, initial = root
    c = base_case(info, control, seed, start, goal, initial, family, batch=batch, interval=interval, radius=radius, max_events=events)
    c['id'] = f'{control.name}__{info["map"]}__{family}__s{seed}__b{batch}__k{interval}__r{radius}'
    rng = np.random.default_rng(seed+int(hashlib.sha256(info['map'].encode()).hexdigest()[:6], 16))
    belief = np.zeros_like(grid) if family == 'unknown_replay' else grid.copy()
    c['_initial'] = belief.copy(); seen = np.zeros_like(grid); overlay = set(); current = start; previous = None
    cumulative = travelled = moves = 0
    for qi in range(events+1):
        old = belief.copy(); blocks, opens = [], []; newly = 0; global_changes = 0
        prior = None; path_cells = set()
        if previous is not None:
            at = min(interval, len(previous['ids']))
            if family == 'unknown_replay':
                for k in range(at):
                    u=previous['states'][k]
                    assert all(not grid[u[0]+a,u[1]+b] for a,b in control.primitives[previous['ids'][k]].cells), 'Reference motion crossed unseen obstacle'
            travelled += sum(control.primitives[p].cost for p in previous['ids'][:at]); moves += at
            current = previous['states'][at]
            prior = sum(control.primitives[p].cost for p in previous['ids'][at:])
            path_cells = covered(control, previous, at)
            if current == goal:
                break  # arrival needs no further map event or search
        if family == 'unknown_replay':
            blocks, opens, newly = observe(grid, belief, current, radius, seen)
        elif qi:
            candidates = [tuple(x) for x in np.argwhere(grid == 0).tolist() if tuple(x) not in {current[:2], goal[:2]}]
            if family == 'off_path':
                candidates = [q for q in candidates if q not in path_cells and not belief[q]]
            elif family == 'on_path':
                witnesses = sorted(q for q in path_cells if q not in {current[:2], goal[:2]} and not belief[q])
                if witnesses:
                    anchor = witnesses[int(rng.integers(len(witnesses)))]
                    candidates.sort(key=lambda q: (max(abs(q[0]-anchor[0]), abs(q[1]-anchor[1])), q))
                candidates = [q for q in candidates if not belief[q]]
            elif family == 'churn':
                for q in overlay:
                    belief[q] = 0
                if qi % 4:
                    candidates = [q for q in candidates if q not in path_cells]
            if family != 'on_path':
                rng.shuffle(candidates)
            if family == 'churn' and qi % 4 == 0:
                witnesses=sorted(q for q in path_cells if q not in {current[:2],goal[:2]} and not belief[q])
                if witnesses:
                    anchor=witnesses[int(rng.integers(len(witnesses)))]
                    candidates=[anchor]+[q for q in candidates if q!=anchor]
            selected = set(candidates[:batch])
            for q in selected:
                belief[q] = 1
            if family == 'churn':
                overlay = selected
            blocks = list(map(tuple, np.argwhere((belief == 1) & (old == 0)).tolist()))
            opens = list(map(tuple, np.argwhere((belief == 0) & (old == 1)).tolist()))
            global_changes = len(blocks)+len(opens)
        r = server.plan(belief, current, goal)
        hits = len(set(blocks) & path_cells)
        incumbent_ok = prior is not None and not (set(blocks) & path_cells)
        cumulative += len(blocks)+len(opens)
        c['queries'].append(dict(start=current, goal=goal, blocks=blocks, opens=opens, expected=r['cost'],
            category='initial' if qi == 0 else 'no_path' if r['cost'] is None else 'increase' if prior is not None and r['cost'] > prior+1e-6 else 'improvement' if prior is not None and r['cost'] < prior-1e-6 else 'unchanged',
            event=family, changes=len(blocks)+len(opens), global_changes=global_changes, cumulative_changes=cumulative,
            on_path_blocks=hits, prior_suffix_cost=prior, incumbent_feasible=incumbent_ok, reference_cost=r['cost'],
            revealed=newly, known_fraction=float(seen.mean()) if family == 'unknown_replay' else 1.0,
            travelled=travelled, reference_moves=moves))
        if qi == 0:
            c['example_states'] = r['states']; c['example_ids'] = r['ids']
        if r['cost'] is None or current == goal:
            break
        previous = r
    c['termination'] = 'goal' if current == goal else 'no_path' if r['cost'] is None else 'event_horizon'
    c['reference_final_travelled']=travelled;c['reference_final_moves']=moves
    return c


def partial_dynamic(grid, info, control, server, root, seed, rate, interval):
    s, goal, initial = root
    c = base_case(info, control, seed, s, goal, initial, 'paper_dynamic', change_rate=rate, interval=interval, radius=interval, max_moves=64)
    c['id'] = f'grid8__{info["map"]}__paper_dynamic__s{seed}__cr{rate}__k{interval}'
    c['panels'] = ['literature_dynamic']; c['_initial'] = grid.copy()
    truth, belief = grid.copy(), grid.copy(); seen = np.ones_like(grid); rng = np.random.default_rng(seed)
    current = s; route = initial; at = 0; travelled = cumulative = pending_global = 0
    for step in range(65):
        if step and current == goal:
            break
        if step and step % interval == 0:
            half = max(1, round(grid.size*rate/200))
            pools={value:[tuple(x) for x in np.argwhere(truth==value).tolist() if tuple(x) not in {current[:2],goal[:2]}] for value in [0,1]}
            for value in [0, 1]:
                cells = pools[value]
                rng.shuffle(cells)
                for q in cells[:half]:
                    truth[q] = 1-value; pending_global += 1
        blocks, opens, _ = observe(truth, belief, current, interval, seen)
        if step == 0 or blocks or opens or current == goal:
            prior = sum(control.primitives[p].cost for p in route['ids'][at:]) if route['cost'] is not None else None
            cells = covered(control, route, at) if route['cost'] is not None else set()
            route = server.plan(belief, current, goal); at = 0; cumulative += len(blocks)+len(opens)
            c['queries'].append(dict(start=current, goal=goal, blocks=blocks, opens=opens, expected=route['cost'],
                category='initial' if step == 0 else 'no_path' if route['cost'] is None else 'dynamic', event='paper_dynamic',
                changes=len(blocks)+len(opens), global_changes=pending_global, cumulative_changes=cumulative,
                on_path_blocks=len(set(blocks)&cells), prior_suffix_cost=prior, incumbent_feasible=prior is not None and not (set(blocks)&cells),
                travelled=travelled, reference_moves=step, known_fraction=1.0))
            pending_global = 0
        if route['cost'] is None or current == goal or step == 64:
            break
        pid = route['ids'][at]; p = control.primitives[pid]
        assert all(not truth[current[0]+a, current[1]+b] for a, b in p.cells), 'Reference drove into an unseen obstacle'
        travelled += p.cost; at += 1; current = route['states'][at]
    c['termination'] = 'goal' if current == goal else 'no_path' if route['cost'] is None else 'move_horizon'
    c['reference_final_travelled']=travelled;c['reference_final_moves']=step
    return c


def history(control, server, updates, reverse):
    g = np.zeros((96, 96), dtype=np.uint8); theta = heading(control, 1, 1)
    s, goal = (10, 10, theta), (85, 85, theta); initial = server.plan(g, s, goal)
    info = dict(map='synthetic_open96', map_family='diagnostic', shape=[96,96], truth_density=0.0, source='generated empty grid')
    c = base_case(info, control, 48101, s, goal, initial, 'history', updates=updates, reverse=reverse, batch=8)
    c['id'] = f'car16__history__n{updates}__reverse{int(reverse)}'; c['_initial'] = g.copy(); c['panels'] = ['history']
    rng = np.random.default_rng(48101); old = set(); cumulative=0
    for q in range(updates+1):
        start = initial['states'][1] if reverse and (q//4)%2 else s
        opens = sorted(old)
        for p in old: g[p]=0
        a,b=(20,75) if q%2 else (75,20)
        patch = {(a+int(rng.integers(-6,7)),b+int(rng.integers(-6,7))) for _ in range(8)} if q else set()
        for p in patch: g[p]=1
        blocks=sorted(patch-old); opens=sorted(old-patch); old=patch
        r=server.plan(g,start,goal); cumulative+=len(blocks)+len(opens)
        c['queries'].append(dict(start=start,goal=goal,blocks=blocks,opens=opens,expected=r['cost'],category='initial' if q==0 else 'history',event='history',
                                 changes=len(blocks)+len(opens),global_changes=len(blocks)+len(opens),cumulative_changes=cumulative,
                                 on_path_blocks=0,incumbent_feasible=True,known_fraction=1.0,travelled=0,reference_moves=0))
    return c


def main():
    OUT.mkdir(exist_ok=True)
    if (OUT/'manifest.json').exists():
        raise RuntimeError('Inputs already frozen; use a different directory/version')
    maps=make_maps(); car=build_control_set('car16')
    grid8=_assemble('grid8',1,((0,1),),[(0,0,((0,0),(di,dj)),math.hypot(di,dj)) for di,dj in [(0,1),(1,0),(0,-1),(-1,0),(1,1),(1,-1),(-1,1),(-1,-1)]])
    records=[];rejections=[];roots={}; car_cases=[]; registry={}; missions={}
    for control in [car,grid8]:
        model=OUT/(control.name+'_model.txt');write_suite(model,control,[])
        server=Reference(model)
        selected=[n for n in maps if n.startswith('random50')] if control.name=='grid8' else [n for n in maps if not n.startswith('random50')]
        for name in selected:
            grid,info=maps[name]
            for seed in SEEDS:
                roots[control.name,name,seed]=choose_root(grid,control,server,seed,name,rejections)
        if control.name=='car16':
            def add(name,seed,family,panel,**params):
                key=(name,seed,family,tuple(sorted(params.items())))
                if key not in registry:
                    registry[key]=replay(*maps[name],control,server,roots['car16',name,seed],seed,family,**params)
                    car_cases.append(registry[key])
                    print('prepared',registry[key]['id'],flush=True)
                registry[key]['panels'].append(panel)
            for name in selected:
                for seed in SEEDS:
                    for family in ['on_path','off_path','churn','unknown_replay']:
                        add(name,seed,family,'main',batch=8,interval=1 if family=='unknown_replay' else 2,radius=8)
            for name in ['MA_room96','MA_random96']:
                for b in [1,8,32,128]:
                    for family in ['on_path','off_path','churn']:
                        add(name,SEEDS[0],family,'batch',batch=b,interval=2,radius=8)
                for seed in SEEDS:
                    for radius in [8,16,32]:
                        add(name,seed,'unknown_replay','visibility',batch=8,interval=1,radius=radius)
                    for k in [1,4,8]:
                        add(name,seed,'churn','frequency',batch=8,interval=k,radius=8)
            for n in [16,64]:
                for reverse in [False,True]:
                    car_cases.append(history(control,server,n,reverse))
            records.append(write_suite(OUT/'car16_replay.txt',control,car_cases))
            mission_names=['arena','MA_room96','MA_random96','MA_maze96']
            radii=[8,16]
        else:
            cases=[]
            for name in selected:
                for seed in SEEDS:
                    for rate in [1,5,10,30]:
                        for k in [2,8,32]:
                            cases.append(partial_dynamic(*maps[name],control,server,roots['grid8',name,seed],seed,rate,k))
            records.append(write_suite(OUT/'grid8_replay.txt',control,cases))
            mission_names=selected;radii=[1,4,8]
        for radius in radii:
            cases=[]
            for name in mission_names:
                grid,info=maps[name]
                for seed in SEEDS:
                    s,t,r=roots[control.name,name,seed]
                    c=base_case(info,control,seed,s,t,r,'unknown_mission',radius=radius,max_steps=160 if control.name=='car16' else 256)
                    c['id']=f'{control.name}__{name}__mission__s{seed}__r{radius}'
                    c['_initial']=grid.copy();c['panels']=['closed_loop']
                    c['queries']=[dict(start=s,goal=t,blocks=[],opens=[],expected=r['cost'],category='mission',event='truth_only')]
                    cases.append(c)
            records.append(write_suite(OUT/f'{control.name}_missions_r{radius}.txt',control,cases))
        server.close()
    (OUT/'root_rejections.json').write_text(json.dumps(rejections,indent=2)+'\n')
    sources=[Path(__file__).resolve(),HERE/'bench.cpp',HERE/'memory.hpp',HERE/'Makefile',ROOT/'mesha/primitives.py',ROOT/'mesha/mesh.py',HERE/'maps/SOURCES.json']
    sources += list((ROOT/'cpp/include/ima').glob('*.hpp'))
    manifest=dict(status='frozen',seeds=SEEDS,records=records,root_selection='Reference LBA*, geometric distance30..75, primitive path16..100, cost<180; candidates never timed during selection.',
        experiment_methods=['lba','lazy_lba','mesha','mesh_parall','dstar_lattice','dstar_mesh','mpgaa','md_astar','md64','md_scan','lba_reuse'],
        cap=1000000,repeats=3,memory_repeats=1,source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sources},
        total_replay_cases=sum(x['cases'] for x in records if '_replay' in x['path']),total_missions=sum(x['cases'] for x in records if '_missions' in x['path']))
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('FROZEN',manifest['total_replay_cases'],'replay cases',manifest['total_missions'],'missions',flush=True)


if __name__=='__main__':
    main()
