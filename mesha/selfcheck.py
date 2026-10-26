"""Optimality checks: LBA*, LazyLBA*, and MeshA* must agree at w = 1."""

from __future__ import annotations

import numpy as np

from mesha.mesh import build_mesh
from mesha.primitives import build_control_set
from mesha.search import search


def _check(grid, control, mesh, start, goal, label):
    results = {
        name: search(name, grid, control, start, goal, mesh, return_path=True, max_expansions=200_000)
        for name in ("lba", "lazy_lba", "mesha")
    }
    costs = {name: result.cost for name, result in results.items()}
    if not all(result.success for result in results.values()):
        raise AssertionError(f"{label}: not all solvers succeeded { {n: r.success for n, r in results.items()} }")
    anchor = costs["lba"]
    for name, cost in costs.items():
        if abs(cost - anchor) > 1e-6:
            raise AssertionError(f"{label}: cost mismatch {costs}")
        result = results[name]
        if abs(sum(control.get(pid).cost for pid in result.prim_ids) - cost) > 1e-6:
            raise AssertionError(f"{label}: {name} path cost disagrees with g")
        if result.states[0] != start or result.states[-1] != goal:
            raise AssertionError(f"{label}: {name} endpoints {result.states[0]} -> {result.states[-1]}")
        for i, j in result.trace:
            if grid[i, j]:
                raise AssertionError(f"{label}: {name} crosses a blocked cell {(i, j)}")
    return costs["lba"], {name: result.expansions for name, result in results.items()}


def main() -> None:
    control = build_control_set()
    mesh = build_mesh(control)
    print(f"primitives={len(control)} configs={mesh.n_configs}")

    empty = np.zeros((36, 48), dtype=np.uint8)
    cases = [
        ((8, 4, 0), (8, 28, 0), "straight east"),
        ((20, 4, 2), (4, 30, 0), "diagonal-ish"),
        ((4, 4, 4), (20, 36, 6), "west start"),
        ((10, 10, 1), (10, 10, 1), "already there"),
    ]
    for start, goal, label in cases:
        cost, expansions = _check(empty, control, mesh, start, goal, label)
        print(f"  {label}: cost={cost:.3f} expansions={expansions}")

    wall = np.zeros((30, 30), dtype=np.uint8)
    wall[0:18, 14] = 1
    wall[22:30, 14] = 1
    cost, expansions = _check(wall, control, mesh, (10, 2, 0), (10, 24, 0), "gap detour")
    straight = 22.0
    if cost <= straight + 1e-6:
        raise AssertionError(f"detour should be longer than the blocked straight line, got {cost}")
    print(f"  gap detour: cost={cost:.3f} expansions={expansions}")

    rng = np.random.default_rng(0)
    scattered = np.zeros((40, 40), dtype=np.uint8)
    for _ in range(180):
        scattered[int(rng.integers(0, 40)), int(rng.integers(0, 40))] = 1
    scattered[5, 5] = 0
    scattered[30, 32] = 0
    cost, expansions = _check(scattered, control, mesh, (5, 5, 0), (30, 32, 2), "scattered")
    print(f"  scattered: cost={cost:.3f} expansions={expansions}")
    print("selfcheck ok")


if __name__ == "__main__":
    main()
