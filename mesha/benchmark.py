"""Incremental MeshA* instances and the from-scratch baseline runner.

An instance is a base map, a start state, a goal state, and a short sequence of
obstacle insertions. After each insertion the agent replans from the last state
that is still safe. LBA*, LazyLBA*, and MeshA* ignore everything they learned on
the previous query.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from mesha.maps import generate_maze, generate_rooms, is_free, load_map, load_scen, save_map
from mesha.mesh import Mesh, build_mesh
from mesha.primitives import DIRS, ControlSet, build_control_set
from mesha.search import search

ROOT = Path(__file__).resolve().parents[1]
MAP_DIR = ROOT / "data" / "maps"
BENCH_PATH = ROOT / "data" / "benchmarks" / "incremental_mesha.json"
SEED = 241210320
ALGORITHMS = ("lba", "lazy_lba", "mesha")
DISPLAY = {"lba": "LBA*", "lazy_lba": "LazyLBA*", "mesha": "MeshA*"}

MAP_SPECS = (
    {
        "file": "Berlin_2_256.map",
        "topology": "city",
        "kind": "movingai",
        "length": (28.0, 60.0),
        "note": "MovingAI Berlin street map used with MeshA*.",
    },
    {
        "file": "AR0700SR.map",
        "topology": "indoor",
        "kind": "movingai",
        "length": (25.0, 70.0),
        "note": "MovingAI Dragon Age indoor map used with MeshA*.",
    },
    {
        "file": "maze.map",
        "topology": "maze",
        "kind": "maze",
        "length": (22.0, 48.0),
        "note": "Wide-corridor maze. Turns need the open junctions.",
    },
    {
        "file": "rooms.map",
        "topology": "rooms",
        "kind": "rooms",
        "length": (22.0, 52.0),
        "note": "Rooms connected by doors.",
    },
)


def ensure_maps(rng: np.random.Generator | None = None) -> None:
    """Write the generated maps. MovingAI files are already stored under data/maps."""
    MAP_DIR.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED) if rng is None else rng
    maze_path = MAP_DIR / "maze.map"
    rooms_path = MAP_DIR / "rooms.map"
    if not maze_path.exists():
        save_map(maze_path, generate_maze(n_cells=16, corridor=5, rng=rng))
    if not rooms_path.exists():
        save_map(rooms_path, generate_rooms())


def _heading(grid: np.ndarray, i: int, j: int, rng: np.random.Generator) -> int:
    options = []
    height, width = grid.shape
    for theta, (di, dj) in enumerate(DIRS):
        ni, nj = i + di, j + dj
        if 0 <= ni < height and 0 <= nj < width and grid[ni, nj] == 0:
            options.append(theta)
    if not options:
        return int(rng.integers(0, len(DIRS)))
    return int(options[int(rng.integers(0, len(options)))])


def _geometric_pairs(spec: dict, grid: np.ndarray, rng: np.random.Generator) -> list[dict]:
    lo, hi = spec["length"]
    if spec["kind"] == "movingai":
        tasks = load_scen(MAP_DIR / f"{spec['file']}.scen")
        picked = []
        for task in tasks:
            if not (lo <= task["optimal"] <= hi):
                continue
            if not is_free(grid, *task["start"]) or not is_free(grid, *task["goal"]):
                continue
            if task["start"] == task["goal"]:
                continue
            picked.append(task)
        order = np.arange(len(picked))
        rng.shuffle(order)
        return [picked[int(index)] for index in order]

    free = np.argwhere(grid == 0)
    pairs = []
    guard = 0
    seen = set()
    while guard < 4000 and len(pairs) < 80:
        guard += 1
        a, b = free[rng.integers(0, len(free), size=2)]
        start = (int(a[0]), int(a[1]))
        goal = (int(b[0]), int(b[1]))
        if start == goal or (start, goal) in seen:
            continue
        dist = float(np.hypot(start[0] - goal[0], start[1] - goal[1]))
        if not (lo <= dist <= hi):
            continue
        seen.add((start, goal))
        pairs.append({"start": start, "goal": goal, "optimal": dist})
    return pairs


def _candidates(trace: list[tuple[int, int]], banned: set[tuple[int, int]]) -> list[tuple[int, int]]:
    cells = []
    seen = set()
    for cell in trace:
        if cell in banned or cell in seen:
            continue
        seen.add(cell)
        cells.append(cell)
    return cells


def _cell_at(cells: list[tuple[int, int]], fraction: float) -> tuple[int, int] | None:
    if not cells:
        return None
    index = int(round(fraction * (len(cells) - 1)))
    index = min(max(index, 0), len(cells) - 1)
    return cells[index]


def _replan_state(control: ControlSet, states, prim_ids, block: tuple[int, int]):
    for state, prim_id in zip(states, prim_ids):
        prim = control.get(prim_id)
        swept = [(state[0] + di, state[1] + dj) for di, dj in prim.cells[1:]]
        if block in swept:
            return state
    return states[0]


def _solve(grid, control, mesh, start, goal, cap: int):
    return search(
        "lba", grid, control, start, goal, mesh,
        weight=1.0, max_expansions=cap, return_path=True,
    )


def _cut_path(grid, control, mesh, states, prim_ids, goal, banned, cap: int):
    """Insert one obstacle on the trace and move the start to the last safe state."""
    trace_cells = []
    for state, prim_id in zip(states, prim_ids):
        prim = control.get(prim_id)
        for di, dj in prim.cells:
            trace_cells.append((state[0] + di, state[1] + dj))
    options = _candidates(trace_cells, banned)
    if len(options) < 3:
        return None
    for fraction in (0.55, 0.4, 0.72, 0.3, 0.85):
        block = _cell_at(options, fraction)
        if block is None:
            continue
        restart = _replan_state(control, states, prim_ids, block)
        if restart[:2] == block or restart[:2] == goal[:2]:
            continue
        edited = grid.copy()
        edited[block] = 1
        if edited[restart[0], restart[1]] or edited[goal[0], goal[1]]:
            continue
        result = _solve(edited, control, mesh, restart, goal, cap)
        if result.success and not result.capped:
            return block, restart, result
    return None


def prepare_benchmark(n_tasks: int = 8, expansion_cap: int = 40_000) -> dict:
    """Build a deterministic incremental benchmark and write it to disk."""
    rng = np.random.default_rng(SEED)
    ensure_maps(np.random.default_rng(SEED))
    control = build_control_set()
    mesh = build_mesh(control)
    instances = []
    map_rows = []

    for spec in MAP_SPECS:
        grid = load_map(MAP_DIR / spec["file"])
        pairs = _geometric_pairs(spec, grid, rng)
        kept = 0
        map_rows.append(
            {
                "file": spec["file"],
                "topology": spec["topology"],
                "height": int(grid.shape[0]),
                "width": int(grid.shape[1]),
                "free": int((grid == 0).sum()),
                "note": spec["note"],
            }
        )
        print(f"{spec['file']}: {grid.shape[0]}x{grid.shape[1]}, {len(pairs)} candidate pairs")
        for pair in pairs:
            if kept >= n_tasks:
                break
            solved = None
            for _attempt in range(5):
                start = (*pair["start"], _heading(grid, *pair["start"], rng))
                goal = (*pair["goal"], _heading(grid, *pair["goal"], rng))
                first = _solve(grid, control, mesh, start, goal, expansion_cap)
                if first.success and not first.capped and first.prim_ids:
                    solved = (start, goal, first)
                    break
            if solved is None:
                continue
            start, goal, first = solved
            banned = {start[:2], goal[:2]}
            cut = _cut_path(grid, control, mesh, first.states, first.prim_ids, goal, banned, expansion_cap)
            if cut is None:
                continue
            block1, start1, second = cut
            banned.add(block1)
            grid1 = grid.copy()
            grid1[block1] = 1
            cut2 = _cut_path(
                grid1, control, mesh, second.states, second.prim_ids, goal, banned, expansion_cap
            )
            if cut2 is None:
                continue
            block2, start2, _third = cut2
            instances.append(
                {
                    "id": f"{Path(spec['file']).stem}-{kept:02d}",
                    "map": spec["file"],
                    "topology": spec["topology"],
                    "grid_optimal": pair["optimal"],
                    "reference_cost": first.cost,
                    "queries": [
                        {"start": list(start), "goal": list(goal), "blocks": []},
                        {"start": list(start1), "goal": list(goal), "blocks": [list(block1)]},
                        {
                            "start": list(start2),
                            "goal": list(goal),
                            "blocks": [list(block1), list(block2)],
                        },
                    ],
                }
            )
            kept += 1
            print(
                f"  kept {instances[-1]['id']} cost={first.cost:.1f} "
                f"blocks={block1}->{block2}"
            )
        if kept < n_tasks:
            raise RuntimeError(f"{spec['file']} produced {kept} instances, need {n_tasks}")

    payload = {
        "problem": "incremental-mesha",
        "seed": SEED,
        "n_tasks_per_map": n_tasks,
        "control_set": {
            "name": "car-8x8",
            "headings": 8,
            "primitives": len(control),
            "configurations": mesh.n_configs,
            "description": (
                "Eight headings. Each heading has a 1-step motion, ±45 degree "
                "1-step turns, a 5-step straight, and three arcs. Costs are polyline lengths."
            ),
        },
        "maps": map_rows,
        "instances": instances,
    }
    BENCH_PATH.parent.mkdir(parents=True, exist_ok=True)
    BENCH_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {BENCH_PATH} ({len(instances)} instances)")
    return payload


def load_benchmark(path: Path | None = None) -> dict:
    path = BENCH_PATH if path is None else path
    return json.loads(path.read_text(encoding="utf-8"))


def load_named_maps(benchmark: dict) -> dict[str, np.ndarray]:
    return {row["file"]: load_map(MAP_DIR / row["file"]) for row in benchmark["maps"]}


def apply_blocks(grid: np.ndarray, blocks) -> np.ndarray:
    edited = grid.copy()
    for i, j in blocks:
        edited[int(i), int(j)] = 1
    return edited


def run_benchmark(
    benchmark: dict | None = None,
    weights: tuple[float, ...] = (1.0, 2.0, 5.0),
    algorithms: tuple[str, ...] = ALGORITHMS,
    max_expansions: int = 160_000,
    query_weights: dict[int, tuple[float, ...]] | None = None,
) -> list[dict]:
    """Run the base solvers. Weight sweeps default to the first query only."""
    if benchmark is None:
        benchmark = load_benchmark()
    if query_weights is None:
        query_weights = {0: tuple(weights), 1: (1.0,), 2: (1.0,)}
    maps = load_named_maps(benchmark)
    control = build_control_set()
    mesh: Mesh = build_mesh(control)
    records = []
    total = sum(len(query_weights.get(qi, ())) for inst in benchmark["instances"] for qi in range(len(inst["queries"])))
    total *= len(algorithms)
    done = 0
    for instance in benchmark["instances"]:
        base = maps[instance["map"]]
        for qi, query in enumerate(instance["queries"]):
            grid = apply_blocks(base, query["blocks"])
            start = tuple(int(v) for v in query["start"])
            goal = tuple(int(v) for v in query["goal"])
            for weight in query_weights.get(qi, ()):
                for name in algorithms:
                    result = search(
                        name, grid, control, start, goal, mesh,
                        weight=weight, max_expansions=max_expansions, return_path=False,
                    )
                    records.append(
                        {
                            "id": instance["id"],
                            "map": instance["map"],
                            "topology": instance["topology"],
                            "query": qi,
                            "weight": weight,
                            "algorithm": name,
                            "success": result.success,
                            "cost": None if result.cost == float("inf") else result.cost,
                            "expansions": result.expansions,
                            "generated": result.generated,
                            "checked_cells": result.checked_cells,
                            "rejected": result.rejected,
                            "pruned": result.pruned,
                            "elapsed_s": result.elapsed_s,
                            "capped": result.capped,
                            "n_blocks": len(query["blocks"]),
                        }
                    )
                    done += 1
                if qi == 0 and weight == query_weights.get(0, (weight,))[0]:
                    print(
                        f"[{done:4d}/{total}] {instance['id']} "
                        + " ".join(
                            f"{DISPLAY[name]}={'ok' if records[-len(algorithms) + offset]['success'] else 'fail'}"
                            f":{records[-len(algorithms) + offset]['elapsed_s']:.3f}s"
                            for offset, name in enumerate(algorithms)
                        ),
                        flush=True,
                    )
    return records


def save_records(records: list[dict], path: Path | None = None) -> Path:
    path = ROOT / "results" / "baseline_runs.json" if path is None else path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records), encoding="utf-8")
    return path


def median(values) -> float:
    data = [value for value in values if value is not None]
    if not data:
        return float("nan")
    return float(np.median(np.asarray(data, dtype=float)))


if __name__ == "__main__":
    prepare_benchmark()
