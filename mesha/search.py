"""One-shot planners: LBA*, LazyLBA*, MeshA*, Mesh/PruningA* and Mesh/ParallA*.

All of them are (weighted) A* with the Euclidean distance to the goal cell.

* LBA* collision-checks a primitive before the successor enters OPEN.
* LazyLBA* inserts the successor first and checks the trace when it is popped.
* MeshA* searches extended cells. Intermediate steps cost 0; finishing a
  primitive costs its length. For a non-initial cell the heuristic is the
  minimum over the bundle's endpoints of (primitive cost + h(endpoint)), as in
  the paper. A non-initial cell is skipped when every free endpoint of its
  bundle has already been expanded.
* Mesh/PruningA* additionally treats two non-initial cells at the same grid cell
  as duplicates when the cells they can reach within two steps coincide
  ("soft duplicates"). It is fast but incomplete.
* Mesh/ParallA* runs Mesh/PruningA* and does one LBA* expansion after every K
  of its expansions, returning whichever finds the goal first (paper: K = 100).

Counters
--------
``checked_cells`` counts grid-cell reads made to decide whether motion is
collision-free. LBA* skips the check for successors that are closed or would
not improve their g-value (see ``lba_check_all``). The start cell of a primitive is never re-read (it is the cell
the search is already in). MeshA* counts each distinct neighbouring cell once per
expansion, plus the endpoint reads made by its bundle-pruning rule.

Every search is written as a generator that yields after each expansion, so
Mesh/ParallA* can interleave two searches. ``search()`` drains the generator.
"""

from __future__ import annotations

import heapq
import math
import time
from dataclasses import dataclass

from mesha.mesh import Mesh, build_mesh
from mesha.primitives import ControlSet

INF = float("inf")
State = tuple[int, int, int]
ALGORITHMS = ("lba", "lazy_lba", "mesha", "mesh_parall")


@dataclass
class SearchResult:
    success: bool
    cost: float
    expansions: int
    generated: int
    checked_cells: int
    rejected: int
    pruned: int
    elapsed_s: float
    capped: bool
    states: list[State] | None = None
    trace: list[tuple[int, int]] | None = None
    prim_ids: list[int] | None = None
    expanded: list[tuple[int, int]] | None = None
    winner: str | None = None


class _Stats:
    __slots__ = ("expansions", "generated", "checked", "rejected", "pruned")

    def __init__(self) -> None:
        self.expansions = self.generated = self.checked = self.rejected = self.pruned = 0


def _as_bytes(grid) -> tuple[bytes, int, int]:
    if isinstance(grid, (bytes, bytearray)):
        raise TypeError("pass a numpy grid so the shape is known")
    height, width = grid.shape
    return grid.astype("uint8").tobytes(), height, width


def trace_of(start: State, prim_ids: list[int], control: ControlSet):
    """States and swept cells of a primitive sequence."""
    states = [start]
    trace: list[tuple[int, int]] = []
    i, j, theta = start
    for prim_id in prim_ids:
        prim = control.get(prim_id)
        if prim.start_theta != theta:
            raise ValueError("primitive does not start at the current heading")
        for di, dj in prim.cells:
            cell = (i + di, j + dj)
            if not trace or trace[-1] != cell:
                trace.append(cell)
        i += prim.di
        j += prim.dj
        theta = prim.end_theta
        states.append((i, j, theta))
    return states, trace


def _blocked_tail(grid: bytes, width: int, height: int, base_i: int, base_j: int, cells) -> tuple[bool, int]:
    """Check cells[1:] (the start cell is where the agent already is)."""
    checked = 0
    for di, dj in cells[1:]:
        checked += 1
        ni = base_i + di
        nj = base_j + dj
        if ni < 0 or nj < 0 or ni >= height or nj >= width or grid[ni * width + nj]:
            return True, checked
    return False, checked


# ------------------------------------------------------------------ lattice

def _lattice_gen(grid, height, width, control, start, goal, weight, lazy, stats, out, record, check_all=False):
    """Generator form of LBA* / LazyLBA*. Puts (cost, goal_state, parent) into out."""
    gi, gj, _ = goal
    hypot = math.hypot
    primitives = control.primitives
    by_theta = control.by_theta
    best: dict[State, float] = {}
    parent: dict[State, tuple[State, int]] = {}
    closed: set[State] = set()
    heap: list = []
    seq = 0
    if not lazy:
        best[start] = 0.0
    heap.append((weight * hypot(start[0] - gi, start[1] - gj), 0.0, 0, start[0], start[1], start[2], -1, -1, -1, -1))
    stats.generated += 1
    while heap:
        _f, neg_g, _s, i, j, theta, pi, pj, pt, pid = heapq.heappop(heap)
        g = -neg_g
        state = (i, j, theta)
        if state in closed:
            continue
        if not lazy and g > best.get(state, INF) + 1e-9:
            continue
        if lazy and pid >= 0:
            hit, n = _blocked_tail(grid, width, height, pi, pj, primitives[pid].cells)
            stats.checked += n
            if hit:
                stats.rejected += 1
                continue
        if pid >= 0:
            parent[state] = ((pi, pj, pt), pid)
        if state == goal:
            out.append((g, state, parent))
            return
        closed.add(state)
        best[state] = g
        stats.expansions += 1
        if record is not None:
            record.append((i, j))
        for prim_id in by_theta[theta]:
            prim = primitives[prim_id]
            ni = i + prim.di
            nj = j + prim.dj
            nstate = (ni, nj, prim.end_theta)
            if check_all and not lazy:
                # textbook variant: check every primitive before looking at g-values
                hit, n = _blocked_tail(grid, width, height, i, j, prim.cells)
                stats.checked += n
                if hit:
                    continue
            if nstate in closed:
                continue
            ng = g + prim.cost
            if ng >= best.get(nstate, INF) - 1e-9:
                continue
            if not lazy and not check_all:
                hit, n = _blocked_tail(grid, width, height, i, j, prim.cells)
                stats.checked += n
                if hit:
                    continue
            if not lazy:
                best[nstate] = ng
            seq += 1
            stats.generated += 1
            heapq.heappush(heap, (ng + weight * hypot(ni - gi, nj - gj), -ng, seq, ni, nj, prim.end_theta, i, j, theta, prim_id))
        yield


def _lattice_path(start, goal_state, parent):
    prim_ids = []
    cursor = goal_state
    while cursor != start:
        prev, prim_id = parent[cursor]
        prim_ids.append(prim_id)
        cursor = prev
    prim_ids.reverse()
    return prim_ids


# ------------------------------------------------------------------ mesh

def _mesh_gen(grid, height, width, control, mesh, start, goal, weight, soft_prune, stats, out, record):
    """Generator form of MeshA* (and Mesh/PruningA* when soft_prune)."""
    si, sj, stheta = start
    gi, gj, _ = goal
    hypot = math.hypot
    initial_of = mesh.initial_of_theta
    theta_of = mesh.theta_of_config
    succ_table = mesh.successors
    finals_table = mesh.finals
    signature = mesh.signature
    start_cfg = initial_of[stheta]
    goal_key = (initial_of[goal[2]], gi, gj)

    def heuristic(i, j, cfg):
        if theta_of[cfg] >= 0:
            return hypot(i - gi, j - gj)
        best_h = INF
        for di, dj, _t, cost in finals_table[cfg]:
            estimate = cost + hypot(i + di - gi, j + dj - gj)
            if estimate < best_h:
                best_h = estimate
        return best_h

    best = {(start_cfg, si, sj): 0.0}
    came_from: dict = {}
    closed: set = set()
    sig_closed: set = set()
    heap = [(weight * hypot(si - gi, sj - gj), 0.0, 0, start_cfg, si, sj)]
    stats.generated += 1
    seq = 0
    while heap:
        _f, neg_g, _s, cfg, i, j = heapq.heappop(heap)
        g = -neg_g
        key = (cfg, i, j)
        if key in closed or g > best.get(key, INF) + 1e-9:
            continue
        closed.add(key)
        theta = theta_of[cfg]
        if key == goal_key:
            out.append((g, key, came_from))
            return
        if theta < 0:
            done = True
            for di, dj, end_theta, _c in finals_table[cfg]:
                ei = i + di
                ej = j + dj
                stats.checked += 1
                if ei < 0 or ej < 0 or ei >= height or ej >= width or grid[ei * width + ej]:
                    continue
                if (initial_of[end_theta], ei, ej) not in closed:
                    done = False
                    break
            if done:
                stats.pruned += 1
                continue
            if soft_prune:
                skey = (signature[cfg], i, j)
                if skey in sig_closed:
                    stats.pruned += 1
                    continue
                sig_closed.add(skey)
        stats.expansions += 1
        if record is not None:
            record.append((i, j))
        seen: dict[tuple[int, int], bool] = {}
        for di, dj, ncfg, cost, _pid in succ_table[cfg]:
            ni = i + di
            nj = j + dj
            blocked = seen.get((ni, nj))
            if blocked is None:
                stats.checked += 1
                blocked = ni < 0 or nj < 0 or ni >= height or nj >= width or bool(grid[ni * width + nj])
                seen[(ni, nj)] = blocked
            if blocked:
                continue
            ng = g + cost
            nkey = (ncfg, ni, nj)
            if nkey in closed or ng >= best.get(nkey, INF) - 1e-9:
                continue
            h = heuristic(ni, nj, ncfg)
            if h == INF:
                continue
            best[nkey] = ng
            came_from[nkey] = key if theta >= 0 else came_from.get(key, key)
            seq += 1
            stats.generated += 1
            heapq.heappush(heap, (ng + weight * h, -ng, seq, ncfg, ni, nj))
        yield


def _mesh_path(start_key, goal_key, came_from, mesh, control):
    chain = [goal_key]
    cursor = goal_key
    while cursor != start_key:
        cursor = came_from[cursor]
        chain.append(cursor)
    chain.reverse()
    prim_ids = []
    for left, right in zip(chain, chain[1:]):
        th0 = mesh.theta_of_config[left[0]]
        th1 = mesh.theta_of_config[right[0]]
        prim_ids.append(control.between[(th0, right[1] - left[1], right[2] - left[2], th1)])
    return prim_ids


# ------------------------------------------------------------------ driver

def search(
    algorithm: str,
    grid,
    control: ControlSet,
    start: State,
    goal: State,
    mesh: Mesh | None = None,
    weight: float = 1.0,
    max_expansions: int = 2_000_000,
    return_path: bool = False,
    parall_k: int = 100,
    lba_check_all: bool = False,
) -> SearchResult:
    """Run `lba`, `lazy_lba`, `mesha`, `mesh_pruning` or `mesh_parall`.

    By default LBA* checks a primitive only when its successor would improve a
    g-value. ``lba_check_all=True`` checks every primitive of an expanded state
    first (the textbook order); costs and expansions are the same.
    """
    clock = time.perf_counter()
    flat, height, width = _as_bytes(grid)
    start = tuple(int(v) for v in start)
    goal = tuple(int(v) for v in goal)
    name = algorithm.lower()
    stats = _Stats()
    record = [] if return_path else None

    def result(success, cost=INF, capped=False, prim_ids=None, winner=None):
        res = SearchResult(
            success, cost, stats.expansions, stats.generated, stats.checked, stats.rejected,
            stats.pruned, time.perf_counter() - clock, capped, winner=winner,
        )
        if return_path and prim_ids is not None:
            res.prim_ids = prim_ids
            res.states, res.trace = trace_of(start, prim_ids, control)
            res.expanded = record
        return res

    for i, j, _t in (start, goal):
        if not (0 <= i < height and 0 <= j < width) or flat[i * width + j]:
            return result(False)
    if start == goal:
        return result(True, 0.0, prim_ids=[])
    if name in ("mesha", "mesh_pruning", "mesh_parall") and mesh is None:
        mesh = build_mesh(control)

    lat_out: list = []
    mesh_out: list = []
    if name in ("lba", "lazy_lba"):
        gens = [("lattice", _lattice_gen(flat, height, width, control, start, goal, weight, name == "lazy_lba", stats, lat_out, record, lba_check_all))]
    elif name in ("mesha", "mesh_pruning"):
        gens = [("mesh", _mesh_gen(flat, height, width, control, mesh, start, goal, weight, name == "mesh_pruning", stats, mesh_out, record))]
    elif name == "mesh_parall":
        gens = [
            ("mesh", _mesh_gen(flat, height, width, control, mesh, start, goal, weight, True, stats, mesh_out, record)),
            ("lattice", _lattice_gen(flat, height, width, control, start, goal, weight, False, stats, lat_out, record)),
        ]
    else:
        raise ValueError(f"unknown algorithm {algorithm}")

    alive = [True] * len(gens)
    steps = 0
    while any(alive):
        for slot, (_kind, gen) in enumerate(gens):
            if not alive[slot]:
                continue
            burst = parall_k if (len(gens) == 2 and slot == 0) else 1
            for _ in range(burst):
                if stats.expansions >= max_expansions:
                    return result(False, capped=True)
                try:
                    next(gen)
                except StopIteration:
                    alive[slot] = False
                    break
                steps += 1
            if mesh_out:
                g, key, came_from = mesh_out[0]
                start_key = (mesh.initial_of_theta[start[2]], start[0], start[1])
                prim_ids = _mesh_path(start_key, key, came_from, mesh, control) if return_path else None
                return result(True, g, prim_ids=prim_ids, winner="mesh")
            if lat_out:
                g, state, parent = lat_out[0]
                prim_ids = _lattice_path(start, state, parent) if return_path else None
                return result(True, g, prim_ids=prim_ids, winner="lattice")
    return result(False)
