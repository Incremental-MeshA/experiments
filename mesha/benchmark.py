"""Incremental MeshA* benchmark: instance generation and the experiment runner.

An instance is a map, a start state, a goal state and three queries. After the
first query an obstacle (a disc of radius 2-4 cells) appears on the optimal
path. The agent notices it from a few cells away, stops at the last state of its
plan that is still at least ``SENSE`` cells from the obstacle, and replans to
the same goal. A second obstacle then appears on the repaired plan.

Planners
--------
One-shot (each query from scratch): LBA*, LazyLBA*, MeshA*, Mesh/ParallA*.
Incremental (state kept across queries): D* Lite on the lattice and D* Lite on
the mesh graph (incremental MeshA*).

Selection is solver-neutral: a pair is dropped only when the query has no
solution at all (checked with a practically uncapped search), and every drop is
counted in ``selection`` in the benchmark file.
"""

from __future__ import annotations

import json
import math
import os
import platform
import sys
import time
from datetime import datetime, timezone
from multiprocessing import get_context
from pathlib import Path

import numpy as np

from mesha.incremental import make_planner
from mesha.maps import generate_maze, generate_rooms, load_map, load_scen, save_map
from mesha.mesh import build_mesh
from mesha.primitives import build_control_set
from mesha.search import search

ROOT = Path(__file__).resolve().parents[1]
MAP_DIR = ROOT / "data" / "maps"
BENCH_PATH = ROOT / "data" / "benchmarks" / "incremental_mesha.json"
RESULTS_PATH = ROOT / "results" / "runs.json"
SEED = 241210320
CONTROL = "car16"
ONE_SHOT = ("lba", "lazy_lba", "mesha", "mesh_parall")
INCREMENTAL = ("dstar_lattice", "dstar_mesh")
WEIGHTS = (1.0, 1.1, 2.0, 5.0, 10.0)
SENSE = 4  # cells between the agent and the obstacle when it replans
UNCAPPED = 3_000_000
DISPLAY = {
    "lba": "LBA*",
    "lazy_lba": "LazyLBA*",
    "mesha": "MeshA*",
    "mesh_parall": "Mesh/ParallA*",
    "mesh_pruning": "Mesh/PruningA*",
    "dstar_lattice": "D* Lite (lattice)",
    "dstar_mesh": "D* Lite (mesh)",
}

MAP_SPECS = (
    {"file": "Berlin_2_256.map", "topology": "city", "kind": "movingai", "length": (10.0, 120.0),
     "note": "MovingAI street map (Berlin_2_256)."},
    {"file": "AR0700SR.map", "topology": "indoor", "kind": "movingai", "length": (10.0, 120.0),
     "note": "MovingAI Baldur's Gate II indoor map (AR0700SR)."},
    {"file": "maze.map", "topology": "maze", "kind": "maze", "length": (10.0, 90.0),
     "note": "Generated wide-corridor maze."},
    {"file": "rooms.map", "topology": "rooms", "kind": "rooms", "length": (10.0, 90.0),
     "note": "Generated rooms joined by doors."},
)


def ensure_maps(rng: np.random.Generator | None = None) -> None:
    """Write the generated maps. MovingAI files are stored under data/maps."""
    MAP_DIR.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED) if rng is None else rng
    if not (MAP_DIR / "maze.map").exists():
        save_map(MAP_DIR / "maze.map", generate_maze(n_cells=16, corridor=5, rng=rng))
    if not (MAP_DIR / "rooms.map").exists():
        save_map(MAP_DIR / "rooms.map", generate_rooms())


# ------------------------------------------------------------------ pairs

def _pairs(spec: dict, grid: np.ndarray, rng: np.random.Generator, n_pairs: int) -> list[dict]:
    """Start/goal cells spread evenly over path length."""
    lo, hi = spec["length"]
    free = lambda c: 0 <= c[0] < grid.shape[0] and 0 <= c[1] < grid.shape[1] and grid[c] == 0
    if spec["kind"] == "movingai":
        tasks = [
            t for t in load_scen(MAP_DIR / f"{spec['file']}.scen")
            if lo <= t["optimal"] <= hi and t["start"] != t["goal"] and free(t["start"]) and free(t["goal"])
        ]
        for t in tasks:
            t["length"] = t["optimal"]
            t["length_kind"] = "scen_octile"
    else:
        cells = np.argwhere(grid == 0)
        tasks = []
        seen = set()
        for _ in range(20000):
            a, b = cells[rng.integers(0, len(cells), size=2)]
            s, g = (int(a[0]), int(a[1])), (int(b[0]), int(b[1]))
            d = math.hypot(s[0] - g[0], s[1] - g[1])
            if s == g or (s, g) in seen or not lo <= d <= hi:
                continue
            seen.add((s, g))
            tasks.append({"start": s, "goal": g, "length": d, "length_kind": "euclidean"})
    # stratify: equal-width length bins, round-robin
    n_bins = 8
    bins: list[list[dict]] = [[] for _ in range(n_bins)]
    for t in tasks:
        k = min(n_bins - 1, int((t["length"] - lo) / (hi - lo) * n_bins))
        bins[k].append(t)
    for b in bins:
        order = rng.permutation(len(b))
        b[:] = [b[int(i)] for i in order]
    out = []
    while len(out) < 4 * n_pairs and any(bins):
        for b in bins:
            if b:
                out.append(b.pop())
    return out


# ------------------------------------------------------------------ edits

def _disc(grid, center, radius):
    ci, cj = center
    h, w = grid.shape
    cells = []
    for i in range(ci - radius, ci + radius + 1):
        for j in range(cj - radius, cj + radius + 1):
            if 0 <= i < h and 0 <= j < w and grid[i, j] == 0 and (i - ci) ** 2 + (j - cj) ** 2 <= radius * radius:
                cells.append((i, j))
    return cells


def _make_edit(grid, control, mesh, result, goal, rng):
    """Drop a disc on the planned path; return the edit and the replanned result."""
    states, prim_ids, trace = result.states, result.prim_ids, result.trace
    if len(trace) < 8:
        return None
    radii = [int(r) for r in rng.permutation([2, 3, 4])]
    for fraction in (0.55, 0.4, 0.7, 0.3, 0.85):
        for radius in radii:
            center = trace[int(round(fraction * (len(trace) - 1)))]
            cells = _disc(grid, center, radius)
            if not cells or tuple(goal[:2]) in cells:
                continue
            blocked = set(cells)
            # first primitive whose sweep meets the obstacle
            hit_index = None
            i, j = states[0][0], states[0][1]
            for k, pid in enumerate(prim_ids):
                prim = control.get(pid)
                if any((states[k][0] + a, states[k][1] + b) in blocked for a, b in prim.cells):
                    hit_index = k
                    break
            if hit_index is None:
                continue
            restart_index = None
            for k in range(hit_index, -1, -1):
                si, sj = states[k][0], states[k][1]
                if math.hypot(si - center[0], sj - center[1]) >= radius + SENSE:
                    restart_index = k
                    break
            if restart_index is None:
                continue
            restart = states[restart_index]
            edited = grid.copy()
            for c in cells:
                edited[c] = 1
            replanned = search("lba", edited, control, restart, goal, mesh, max_expansions=UNCAPPED, return_path=True)
            if not replanned.success:
                continue
            before = sum(control.get(pid).cost for pid in prim_ids[restart_index:])
            return {
                "center": list(center),
                "radius": radius,
                "cells": [list(c) for c in cells],
                "restart": list(restart),
                "restart_index": restart_index,
                "cost_before": before,
                "cost_after": replanned.cost,
                "increase": replanned.cost - before,
            }, edited, replanned
    return None


def prepare_benchmark(n_pairs: int = 20, headings_per_pair: int = 3, path: Path | None = None) -> dict:
    """Build a deterministic benchmark and write it to disk."""
    rng = np.random.default_rng(SEED)
    ensure_maps(np.random.default_rng(SEED))
    control = build_control_set(CONTROL)
    mesh = build_mesh(control)
    instances, map_rows, selection = [], [], {}
    for spec in MAP_SPECS:
        grid = load_map(MAP_DIR / spec["file"])
        pairs = _pairs(spec, grid, rng, n_pairs)
        log = {"pairs_considered": 0, "heading_draws": 0, "no_solution": 0, "edit_failed": 0, "kept": 0}
        map_rows.append({
            "file": spec["file"], "topology": spec["topology"], "height": int(grid.shape[0]),
            "width": int(grid.shape[1]), "free": int((grid == 0).sum()), "note": spec["note"],
        })
        kept_pairs = 0
        for pair in pairs:
            if kept_pairs >= n_pairs:
                break
            log["pairs_considered"] += 1
            kept_any = False
            for draw in range(headings_per_pair):
                log["heading_draws"] += 1
                start = (*pair["start"], int(rng.integers(control.n_theta)))
                goal = (*pair["goal"], int(rng.integers(control.n_theta)))
                first = search("lba", grid, control, start, goal, mesh, max_expansions=UNCAPPED, return_path=True)
                if not first.success:
                    log["no_solution"] += 1
                    continue
                edit1 = _make_edit(grid, control, mesh, first, goal, rng)
                if edit1 is None:
                    log["edit_failed"] += 1
                    continue
                e1, grid1, second = edit1
                edit2 = _make_edit(grid1, control, mesh, second, goal, rng)
                if edit2 is None:
                    log["edit_failed"] += 1
                    continue
                e2, _grid2, _third = edit2
                ident = f"{Path(spec['file']).stem}-{kept_pairs:02d}{'abc'[draw]}"
                instances.append({
                    "id": ident,
                    "pair": f"{Path(spec['file']).stem}-{kept_pairs:02d}",
                    "map": spec["file"],
                    "topology": spec["topology"],
                    "pair_length": pair["length"],
                    "pair_length_kind": pair["length_kind"],
                    "reference_cost": first.cost,
                    "queries": [
                        {"start": list(start), "goal": list(goal), "blocks": [], "new_blocks": []},
                        {"start": e1["restart"], "goal": list(goal), "blocks": e1["cells"], "new_blocks": e1["cells"],
                         "edit": {k: v for k, v in e1.items() if k != "cells"}},
                        {"start": e2["restart"], "goal": list(goal), "blocks": e1["cells"] + e2["cells"],
                         "new_blocks": e2["cells"], "edit": {k: v for k, v in e2.items() if k != "cells"}},
                    ],
                })
                log["kept"] += 1
                kept_any = True
            if kept_any:
                kept_pairs += 1
        selection[spec["file"]] = log
        print(f"{spec['file']}: {log}", flush=True)
    payload = {
        "problem": "incremental-mesha",
        "version": 2,
        "seed": SEED,
        "n_pairs_per_map": n_pairs,
        "headings_per_pair": headings_per_pair,
        "sense_radius": SENSE,
        "control_set": {
            "name": control.name,
            "headings": control.n_theta,
            "primitives": len(control),
            "removed_dominated": control.removed_dominated,
            "turning_radius": control.turning_radius,
            "configurations": mesh.n_configs,
            "description": (
                "16 headings, point-sized car-like agent with minimum turning radius 2 cells. "
                "Cubic Hermite primitives between lattice states, up to 24 per heading before "
                "removing primitives that other primitives reproduce. Traces are supercovers "
                "(corner crossings mark both side cells). Cost is curve length."
            ),
        },
        "maps": map_rows,
        "selection": selection,
        "instances": instances,
    }
    path = BENCH_PATH if path is None else path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"wrote {path} ({len(instances)} instances)")
    return payload


def load_benchmark(path: Path | None = None) -> dict:
    return json.loads((BENCH_PATH if path is None else path).read_text(encoding="utf-8"))


def load_named_maps(benchmark: dict) -> dict[str, np.ndarray]:
    return {row["file"]: load_map(MAP_DIR / row["file"]) for row in benchmark["maps"]}


def apply_blocks(grid: np.ndarray, blocks) -> np.ndarray:
    edited = grid.copy()
    for i, j in blocks:
        edited[int(i), int(j)] = 1
    return edited


# ------------------------------------------------------------------ runner

def _row(instance, qi, extra):
    base = {"id": instance["id"], "pair": instance["pair"], "map": instance["map"],
            "topology": instance["topology"], "query": qi}
    base.update(extra)
    return base


def run_instance(args) -> list[dict]:
    """All runs for one instance. Counts are checked identical across repeats."""
    instance, repeats, weights, control_name, seed = args
    control = build_control_set(control_name)
    mesh = build_mesh(control)
    base_grid = load_map(MAP_DIR / instance["map"])
    rng = np.random.default_rng(seed)
    rows = []
    optimal = {}
    # one-shot planners
    for qi, query in enumerate(instance["queries"]):
        grid = apply_blocks(base_grid, query["blocks"])
        for weight in weights:
            times: dict[str, list[float]] = {a: [] for a in ONE_SHOT}
            first: dict = {}
            for _rep in range(repeats):
                for a in rng.permutation(ONE_SHOT):
                    a = str(a)
                    r = search(a, grid, control, query["start"], query["goal"], mesh,
                               weight=weight, max_expansions=UNCAPPED)
                    times[a].append(r.elapsed_s)
                    sig = (r.success, r.cost, r.expansions, r.checked_cells, r.generated)
                    if a in first and first[a][0] != sig:
                        raise RuntimeError(f"non-deterministic counts for {a} on {instance['id']}")
                    first.setdefault(a, (sig, r))
            for a in ONE_SHOT:
                r = first[a][1]
                if weight == 1.0 and a == "lba":
                    optimal[qi] = r.cost
                rows.append(_row(instance, qi, {
                    "kind": "oneshot", "algorithm": a, "weight": weight, "success": r.success,
                    "cost": None if not r.success else r.cost, "expansions": r.expansions,
                    "generated": r.generated, "checked_cells": r.checked_cells, "rejected": r.rejected,
                    "pruned": r.pruned, "capped": r.capped, "winner": r.winner,
                    "time_median": float(np.median(times[a])), "time_min": float(np.min(times[a])),
                }))
    # incremental planners: whole episode, repeated
    per: dict[str, list[list]] = {k: [] for k in INCREMENTAL}
    for _rep in range(repeats):
        for kind in rng.permutation(INCREMENTAL):
            kind = str(kind)
            q0 = instance["queries"][0]
            planner = make_planner(kind, base_grid, control, mesh, q0["start"], q0["goal"], max_expansions=UNCAPPED)
            out = [planner.plan()]
            for query in instance["queries"][1:]:
                out.append(planner.replan(tuple(query["start"]), [tuple(c) for c in query["new_blocks"]]))
            per[kind].append(out)
    for kind in INCREMENTAL:
        runs = per[kind]
        for qi in range(len(instance["queries"])):
            r = runs[0][qi]
            for other in runs[1:]:
                o = other[qi]
                if (o.expansions, o.checked_cells, o.cost) != (r.expansions, r.checked_cells, r.cost):
                    raise RuntimeError(f"non-deterministic counts for {kind} on {instance['id']}")
            ts = [run[qi].elapsed_s for run in runs]
            ok = r.success and abs(r.cost - optimal.get(qi, math.inf)) < 1e-6
            if not ok:
                raise RuntimeError(f"{kind} disagrees with LBA* on {instance['id']} q{qi}: {r.cost} vs {optimal.get(qi)}")
            rows.append(_row(instance, qi, {
                "kind": "incremental", "algorithm": kind, "weight": 1.0, "success": r.success,
                "cost": r.cost, "expansions": r.expansions, "checked_cells": r.checked_cells,
                "updated_vertices": r.updated_vertices, "capped": r.capped,
                "time_median": float(np.median(ts)), "time_min": float(np.min(ts)),
            }))
    return rows


def environment() -> dict:
    cpu = platform.processor() or platform.machine()
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    return {
        "python": sys.version.split()[0],
        "numpy": np.__version__,
        "platform": platform.platform(),
        "cpu": cpu,
        "cpu_count": os.cpu_count(),
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def run_benchmark(benchmark: dict | None = None, repeats: int = 3, weights=WEIGHTS, workers: int = 3,
                  control_name: str = CONTROL, limit: int | None = None) -> dict:
    """Run every planner on every instance. Returns {'meta': ..., 'records': [...]}"""
    benchmark = load_benchmark() if benchmark is None else benchmark
    instances = benchmark["instances"][:limit]
    jobs = [(inst, repeats, tuple(weights), control_name, SEED + k) for k, inst in enumerate(instances)]
    records: list[dict] = []
    clock = time.perf_counter()
    if workers <= 1:
        for k, job in enumerate(jobs):
            records += run_instance(job)
            print(f"[{k + 1}/{len(jobs)}] {job[0]['id']}", flush=True)
    else:
        with get_context("fork").Pool(workers) as pool:
            for k, rows in enumerate(pool.imap(run_instance, jobs)):
                records += rows
                if (k + 1) % 10 == 0 or k + 1 == len(jobs):
                    print(f"[{k + 1}/{len(jobs)}] {time.perf_counter() - clock:.0f}s", flush=True)
    meta = environment()
    meta.update({"repeats": repeats, "workers": workers, "weights": list(weights), "control_set": control_name,
                 "wall_s": time.perf_counter() - clock, "instances": len(instances)})
    return {"meta": meta, "records": records}


def run_legacy_ablation(weights=(1.0, 2.0, 5.0, 10.0)) -> dict:
    """Ablation with the 8-heading legacy8 control set on its own 32 instances.

    Checks whether "weighted MeshA* is as good as LBA*" depends on the control set.
    """
    data = json.loads((ROOT / "data" / "benchmarks" / "legacy8_instances.json").read_text(encoding="utf-8"))
    control = build_control_set("legacy8")
    mesh = build_mesh(control)
    maps = {row["file"]: load_map(MAP_DIR / row["file"]) for row in data["maps"]}
    records = []
    for instance in data["instances"]:
        for qi, query in enumerate(instance["queries"]):
            grid = apply_blocks(maps[instance["map"]], query["blocks"])
            for weight in weights:
                for a in ("lba", "lazy_lba", "mesha", "mesh_parall"):
                    r = search(a, grid, control, query["start"], query["goal"], mesh, weight=weight)
                    records.append({
                        "kind": "legacy", "id": instance["id"], "map": instance["map"],
                        "topology": instance["topology"], "query": qi, "weight": weight, "algorithm": a,
                        "success": r.success, "cost": r.cost if r.success else None,
                        "expansions": r.expansions, "checked_cells": r.checked_cells,
                    })
    return {"meta": {"control_set": "legacy8", "instances": len(data["instances"])}, "records": records}


def save_results(results: dict, path: Path | None = None) -> Path:
    path = RESULTS_PATH if path is None else path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results), encoding="utf-8")
    return path


def median(values) -> float:
    data = [v for v in values if v is not None]
    return float(np.median(np.asarray(data, dtype=float))) if data else float("nan")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--pairs", type=int, default=20)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--legacy", action="store_true")
    opts = parser.parse_args()
    if opts.legacy:
        print("saved", save_results(run_legacy_ablation(), ROOT / "results" / "legacy8_ablation.json"))
    if opts.prepare:
        prepare_benchmark(n_pairs=opts.pairs)
    if opts.run:
        out = run_benchmark(repeats=opts.repeats, workers=opts.workers, limit=opts.limit)
        print("saved", save_results(out))
