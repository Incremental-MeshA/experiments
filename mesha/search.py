"""LBA*, LazyLBA*, and MeshA*.

All three are weighted A* with the Euclidean distance to the goal cell.
LBA* collision-checks a primitive before the successor enters OPEN.
LazyLBA* inserts the successor first and checks the trace when the successor
is popped, which is the lazy baseline from the MeshA* paper.
MeshA* searches extended cells. Intermediate steps cost 0; finishing a
primitive costs its length. A non-initial cell is pruned when every free
endpoint of its bundle has already been expanded.
"""

from __future__ import annotations

import heapq
import math
import time
from dataclasses import dataclass

from mesha.mesh import Mesh
from mesha.primitives import ControlSet

INF = float("inf")
State = tuple[int, int, int]


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


def _as_bytes(grid) -> tuple[bytes, int, int]:
    if isinstance(grid, (bytes, bytearray)):
        raise TypeError("pass a numpy grid so the shape is known")
    height, width = grid.shape
    return grid.astype("uint8").tobytes(), height, width


def _trace_from(start: State, prim_ids: list[int], control: ControlSet):
    states = [start]
    trace: list[tuple[int, int]] = []
    i, j, theta = start
    for prim_id in prim_ids:
        prim = control.get(prim_id)
        for di, dj in prim.cells:
            cell = (i + di, j + dj)
            if not trace or trace[-1] != cell:
                trace.append(cell)
        i += prim.di
        j += prim.dj
        theta = prim.end_theta
        states.append((i, j, theta))
    return states, trace


def _blocked_prefix(grid: bytes, width: int, height: int, base_i: int, base_j: int, cells) -> tuple[bool, int]:
    checked = 0
    for di, dj in cells:
        checked += 1
        ni = base_i + di
        nj = base_j + dj
        if ni < 0 or nj < 0 or ni >= height or nj >= width or grid[ni * width + nj]:
            return True, checked
    return False, checked


def _fail(clock, expansions=0, generated=0, checked=0, rejected=0, pruned=0, capped=False) -> SearchResult:
    return SearchResult(
        False, INF, expansions, generated, checked, rejected, pruned,
        time.perf_counter() - clock, capped,
    )


def lattice_search(
    grid: bytes,
    height: int,
    width: int,
    control: ControlSet,
    start: State,
    goal: State,
    weight: float = 1.0,
    lazy: bool = False,
    max_expansions: int = 80_000,
    return_path: bool = False,
) -> SearchResult:
    """A* on the state lattice. LazyLBA* defers collision checks until pop."""
    clock = time.perf_counter()
    si, sj, stheta = start
    gi, gj, _gtheta = goal
    if grid[si * width + sj] or grid[gi * width + gj]:
        return _fail(clock)
    if start == goal:
        return SearchResult(
            True, 0.0, 0, 1, 0, 0, 0, time.perf_counter() - clock, False,
            [start] if return_path else None,
            [start[:2]] if return_path else None,
            [] if return_path else None,
        )

    def heuristic(i: int, j: int) -> float:
        return math.hypot(i - gi, j - gj)

    primitives = control.primitives
    by_theta = control.by_theta
    # best g among generated (eager) or expanded (lazy) states
    best: dict[State, float] = {}
    parent: dict[State, tuple[State, int]] = {}
    closed: set[State] = set()
    open_heap: list = []
    seq = 0
    expansions = 0
    generated = 0
    checked = 0
    rejected = 0
    footprint: list[tuple[int, int]] = []

    def push(g: float, i: int, j: int, theta: int, pi: int, pj: int, pt: int, pid: int) -> None:
        nonlocal seq, generated
        seq += 1
        generated += 1
        heapq.heappush(
            open_heap,
            (g + weight * heuristic(i, j), -g, seq, i, j, theta, pi, pj, pt, pid),
        )

    if not lazy:
        best[start] = 0.0
    push(0.0, si, sj, stheta, -1, -1, -1, -1)

    while open_heap:
        if expansions >= max_expansions:
            return _fail(clock, expansions, generated, checked, rejected, capped=True)
        _f, neg_g, _seq, i, j, theta, pi, pj, pt, pid = heapq.heappop(open_heap)
        g = -neg_g
        state = (i, j, theta)
        if state in closed:
            continue
        if not lazy and g > best.get(state, INF) + 1e-9:
            continue
        if lazy and state in best and g >= best[state] - 1e-9:
            continue

        if lazy and pid >= 0:
            hit, ncheck = _blocked_prefix(grid, width, height, pi, pj, primitives[pid].cells)
            checked += ncheck
            if hit:
                rejected += 1
                continue

        if state == goal:
            if return_path:
                footprint.append((i, j))
                if pid >= 0:
                    parent[state] = ((pi, pj, pt), pid)
            found = _finish_lattice(
                g, expansions, generated, checked, rejected, clock,
                start, state, parent, control, return_path,
            )
            if return_path:
                found.expanded = footprint
            return found

        closed.add(state)
        best[state] = g
        if return_path:
            footprint.append((i, j))
            if pid >= 0:
                parent[state] = ((pi, pj, pt), pid)
        expansions += 1

        for prim_id in by_theta[theta]:
            prim = primitives[prim_id]
            ni = i + prim.di
            nj = j + prim.dj
            if not lazy:
                hit, ncheck = _blocked_prefix(grid, width, height, i, j, prim.cells)
                checked += ncheck
                if hit:
                    continue
            ng = g + prim.cost
            nstate = (ni, nj, prim.end_theta)
            limit = best.get(nstate, INF)
            if ng >= limit - 1e-9:
                continue
            if not lazy:
                best[nstate] = ng
            if return_path and not lazy:
                parent[nstate] = (state, prim_id)
            push(ng, ni, nj, prim.end_theta, i, j, theta, prim_id)

    return _fail(clock, expansions, generated, checked, rejected)


def mesh_search(
    grid: bytes,
    height: int,
    width: int,
    control: ControlSet,
    mesh: Mesh,
    start: State,
    goal: State,
    weight: float = 1.0,
    max_expansions: int = 80_000,
    return_path: bool = False,
) -> SearchResult:
    """A* on extended cells."""
    clock = time.perf_counter()
    si, sj, stheta = start
    gi, gj, gtheta = goal
    if grid[si * width + sj] or grid[gi * width + gj]:
        return _fail(clock)
    if start == goal:
        return SearchResult(
            True, 0.0, 0, 1, 0, 0, 0, time.perf_counter() - clock, False,
            [start] if return_path else None,
            [start[:2]] if return_path else None,
            [] if return_path else None,
        )

    def heuristic_xy(i: int, j: int) -> float:
        return math.hypot(i - gi, j - gj)

    initial_of = mesh.initial_of_theta
    theta_of = mesh.theta_of_config
    succ_table = mesh.successors
    finals_table = mesh.finals
    start_cfg = initial_of[stheta]

    def heuristic(i: int, j: int, config_id: int) -> float:
        if theta_of[config_id] >= 0:
            return heuristic_xy(i, j)
        best_h = INF
        stride = width
        for di, dj, _end_theta, cost in finals_table[config_id]:
            ei = i + di
            ej = j + dj
            if ei < 0 or ej < 0 or ei >= height or ej >= width or grid[ei * stride + ej]:
                continue
            estimate = cost + heuristic_xy(ei, ej)
            if estimate < best_h:
                best_h = estimate
        return best_h

    Key = tuple[int, int, int]
    best: dict[Key, float] = {(start_cfg, si, sj): 0.0}
    came_from: dict[Key, Key] = {}
    closed: set[Key] = set()
    open_heap: list = []
    seq = 0
    expansions = 0
    generated = 0
    checked = 0
    pruned = 0
    footprint: list[tuple[int, int]] = []

    def push(g: float, config_id: int, i: int, j: int) -> None:
        nonlocal seq, generated
        seq += 1
        generated += 1
        heapq.heappush(
            open_heap,
            (g + weight * heuristic(i, j, config_id), -g, seq, config_id, i, j),
        )

    push(0.0, start_cfg, si, sj)

    while open_heap:
        if expansions >= max_expansions:
            return _fail(clock, expansions, generated, checked, 0, pruned, capped=True)
        _f, neg_g, _seq, config_id, i, j = heapq.heappop(open_heap)
        g = -neg_g
        key: Key = (config_id, i, j)
        if key in closed or g > best.get(key, INF) + 1e-9:
            continue
        closed.add(key)
        theta = theta_of[config_id]
        if theta >= 0 and (i, j, theta) == goal:
            if return_path:
                footprint.append((i, j))
            found = _finish_mesh(
                g, expansions, generated, checked, pruned, clock,
                (start_cfg, si, sj), key, came_from, mesh, control, return_path,
            )
            if return_path:
                found.expanded = footprint
            return found
        if theta < 0 and _bundle_done(
            i, j, finals_table[config_id], initial_of, grid, width, height, closed
        ):
            pruned += 1
            continue

        expansions += 1
        if return_path:
            footprint.append((i, j))
        for di, dj, ncfg, cost, _pid in succ_table[config_id]:
            ni = i + di
            nj = j + dj
            checked += 1
            if ni < 0 or nj < 0 or ni >= height or nj >= width or grid[ni * width + nj]:
                continue
            ng = g + cost
            nkey = (ncfg, ni, nj)
            if ng >= best.get(nkey, INF) - 1e-9:
                continue
            best[nkey] = ng
            if return_path:
                if theta >= 0:
                    came_from[nkey] = key
                elif key in came_from:
                    came_from[nkey] = came_from[key]
            push(ng, ncfg, ni, nj)

    return _fail(clock, expansions, generated, checked, 0, pruned)


def _bundle_done(i, j, finals, initial_of, grid, width, height, closed) -> bool:
    for di, dj, end_theta, _cost in finals:
        ei = i + di
        ej = j + dj
        if ei < 0 or ej < 0 or ei >= height or ej >= width or grid[ei * width + ej]:
            continue
        if (initial_of[end_theta], ei, ej) not in closed:
            return False
    return True


def search(
    algorithm: str,
    grid,
    control: ControlSet,
    start: State,
    goal: State,
    mesh: Mesh | None = None,
    weight: float = 1.0,
    max_expansions: int = 80_000,
    return_path: bool = False,
) -> SearchResult:
    """Run `lba`, `lazy_lba`, or `mesha`."""
    flat, height, width = _as_bytes(grid)
    si, sj, _ = start
    gi, gj, _ = goal
    if not (0 <= si < height and 0 <= sj < width and 0 <= gi < height and 0 <= gj < width):
        return _fail(time.perf_counter())
    name = algorithm.lower()
    if name == "lba":
        return lattice_search(
            flat, height, width, control, start, goal, weight, False, max_expansions, return_path
        )
    if name == "lazy_lba":
        return lattice_search(
            flat, height, width, control, start, goal, weight, True, max_expansions, return_path
        )
    if name == "mesha":
        if mesh is None:
            raise ValueError("MeshA* needs a mesh graph")
        return mesh_search(
            flat, height, width, control, mesh, start, goal, weight, max_expansions, return_path
        )
    raise ValueError(f"unknown algorithm {algorithm}")


def _finish_lattice(cost, expansions, generated, checked, rejected, clock, start, goal_state, parent, control, return_path):
    states = trace = prim_ids = None
    if return_path:
        prim_ids = []
        cursor = goal_state
        while cursor != start:
            prev, prim_id = parent[cursor]
            prim_ids.append(prim_id)
            cursor = prev
        prim_ids.reverse()
        states, trace = _trace_from(start, prim_ids, control)
    return SearchResult(
        True, cost, expansions, generated, checked, rejected, 0,
        time.perf_counter() - clock, False, states, trace, prim_ids,
    )


def _finish_mesh(cost, expansions, generated, checked, pruned, clock, start_key, goal_key, came_from, mesh, control, return_path):
    states = trace = prim_ids = None
    if return_path:
        chain = [goal_key]
        cursor = goal_key
        seen = {goal_key}
        while cursor in came_from and came_from[cursor] not in seen:
            cursor = came_from[cursor]
            seen.add(cursor)
            chain.append(cursor)
        chain.reverse()
        prim_ids = []
        for left, right in zip(chain, chain[1:]):
            th0 = mesh.theta_of_config[left[0]]
            th1 = mesh.theta_of_config[right[0]]
            prim_ids.append(control.between[(th0, right[1] - left[1], right[2] - left[2], th1)])
        start = (start_key[1], start_key[2], mesh.theta_of_config[start_key[0]])
        states, trace = _trace_from(start, prim_ids, control)
    return SearchResult(
        True, cost, expansions, generated, checked, 0, pruned,
        time.perf_counter() - clock, False, states, trace, prim_ids,
    )
