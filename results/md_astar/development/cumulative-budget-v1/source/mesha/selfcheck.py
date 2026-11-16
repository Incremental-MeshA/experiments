"""Correctness checks. Run with ``python -m mesha.selfcheck``.

1. The car16 control set has no primitive that other primitives reproduce.
2. Every corner crossing in a trace marks both side cells.
3. At w = 1, LBA*, LazyLBA* and MeshA* return the same optimal cost, valid paths
   and path costs that match g; weighted runs stay within w times optimal.
4. D* Lite on the lattice and on the mesh graph match a from-scratch search
   after the agent moves and new obstacles appear.
"""

from __future__ import annotations

import numpy as np

from mesha.incremental import make_planner
from mesha.mesh import build_mesh
from mesha.primitives import build_control_set, dominated_primitives
from mesha.search import search

ONE_SHOT = ("lba", "lazy_lba", "mesha")


def check_control_set(control) -> None:
    raw = [(p.start_theta, p.end_theta, p.cells, p.cost) for p in control.primitives]
    dominated = dominated_primitives(raw)
    if control.name == "car16" and dominated:
        raise AssertionError(f"car16 has {len(dominated)} redundant primitives")
    for p in control.primitives:
        cells = set(p.cells)
        for (i0, j0), (i1, j1) in zip(p.cells, p.cells[1:]):
            if i0 != i1 and j0 != j1 and control.name == "car16":
                if (i0, j1) not in cells or (i1, j0) not in cells:
                    raise AssertionError(f"primitive {p.id} cuts a corner")
        if p.cost + 1e-9 < np.hypot(p.di, p.dj):
            raise AssertionError(f"primitive {p.id} is cheaper than its chord")
    print(f"  {control.name}: {len(control)} primitives, {len(dominated)} redundant")


def check_case(grid, control, mesh, start, goal, label) -> float:
    results = {a: search(a, grid, control, start, goal, mesh, return_path=True) for a in ONE_SHOT}
    if len({r.success for r in results.values()}) != 1:
        raise AssertionError(f"{label}: success differs {[(a, r.success) for a, r in results.items()]}")
    base = results["lba"]
    if not base.success:
        return float("inf")
    for name, r in results.items():
        if abs(r.cost - base.cost) > 1e-6:
            raise AssertionError(f"{label}: {name} cost {r.cost} vs {base.cost}")
        if abs(sum(control.get(p).cost for p in r.prim_ids) - r.cost) > 1e-6:
            raise AssertionError(f"{label}: {name} path cost disagrees with g")
        if r.states[0] != tuple(start) or r.states[-1] != tuple(goal):
            raise AssertionError(f"{label}: {name} wrong endpoints")
        if any(grid[i, j] for i, j in r.trace):
            raise AssertionError(f"{label}: {name} crosses a blocked cell")
    for w in (2.0, 5.0):
        for name in ONE_SHOT + ("mesh_parall",):
            r = search(name, grid, control, start, goal, mesh, weight=w)
            if not r.success or r.cost > w * base.cost + 1e-6:
                raise AssertionError(f"{label}: {name} at w={w} breaks the bound")
    return base.cost


def check_incremental(grid, control, mesh, start, goal, rng, label) -> int:
    first = search("lba", grid, control, start, goal, mesh, return_path=True)
    if not first.success:
        return 0
    planners = {k: make_planner(k, grid, control, mesh, start, goal) for k in ("dstar_lattice", "dstar_mesh")}
    for kind, planner in planners.items():
        r = planner.plan()
        if abs(r.cost - first.cost) > 1e-6:
            raise AssertionError(f"{label}: {kind} initial cost {r.cost} vs {first.cost}")
    current = grid.copy()
    path = first
    checks = 0
    for _ in range(2):
        if len(path.states) < 3:
            break
        here = path.states[len(path.states) // 2]
        ahead = [c for c in path.trace[path.trace.index(here[:2]) + 1:] if c != tuple(goal[:2])]
        if not ahead:
            break
        center = ahead[min(len(ahead) - 1, int(rng.integers(1, 4)))]
        blocks = [(center[0] + a, center[1] + b) for a in (-1, 0, 1) for b in (-1, 0, 1)
                  if 0 <= center[0] + a < grid.shape[0] and 0 <= center[1] + b < grid.shape[1]]
        blocks = [c for c in blocks if c != tuple(goal[:2]) and c != tuple(here[:2])]
        for c in blocks:
            current[c] = 1
        ref = search("lba", current, control, here, goal, mesh, return_path=True)
        for kind, planner in planners.items():
            r = planner.replan(here, blocks)
            if r.success != ref.success or (ref.success and abs(r.cost - ref.cost) > 1e-6):
                raise AssertionError(f"{label}: {kind} replan {r.cost} vs {ref.cost}")
            checks += 1
        if not ref.success:
            break
        path = ref
    return checks


def main(n_random: int = 40) -> None:
    for name in ("car16", "legacy8"):
        control = build_control_set(name)
        mesh = build_mesh(control)
        print(f"{name}: primitives={len(control)} configs={mesh.n_configs}")
        check_control_set(control)
        empty = np.zeros((36, 48), dtype=np.uint8)
        top = control.n_theta // 4
        for start, goal, label in [
            ((18, 4, 0), (18, 40, 0), "straight east"),
            ((30, 6, top), (6, 40, 0), "turn"),
            ((10, 10, 1), (10, 10, 1), "already there"),
        ]:
            cost = check_case(empty, control, mesh, start, goal, label)
            print(f"  {label}: cost={cost:.3f}")
        wall = np.zeros((30, 40), dtype=np.uint8)
        wall[0:16, 18] = 1
        wall[22:30, 18] = 1
        cost = check_case(wall, control, mesh, (10, 3, 0), (10, 34, 0), "gap detour")
        if cost <= 31 + 1e-6:
            raise AssertionError("detour should be longer than the blocked straight line")
        print(f"  gap detour: cost={cost:.3f}")
        rng = np.random.default_rng(0)
        solved = replans = 0
        for k in range(n_random):
            h, w = (int(v) for v in rng.integers(16, 30, 2))
            grid = (rng.random((h, w)) < rng.uniform(0.03, 0.15)).astype(np.uint8)
            free = np.argwhere(grid == 0)
            a, b = free[rng.integers(0, len(free), 2)]
            start = (int(a[0]), int(a[1]), int(rng.integers(control.n_theta)))
            goal = (int(b[0]), int(b[1]), int(rng.integers(control.n_theta)))
            if check_case(grid, control, mesh, start, goal, f"random {k}") < float("inf"):
                solved += 1
                replans += check_incremental(grid, control, mesh, start, goal, rng, f"random {k}")
        print(f"  random: {solved}/{n_random} solvable, {replans} incremental replans checked")
    print("selfcheck ok")


if __name__ == "__main__":
    main()
