"""Incremental replanning with D* Lite on the state lattice and on the mesh graph.

The agent follows its plan, discovers new obstacles, and replans from where it
stands to the same goal. D* Lite (Koenig & Likhachev 2002) searches backward from
the goal, so the moving start only shifts the heuristic (the ``km`` term), and
after an edit it repairs only the part of the search that the edit invalidated.

Two graphs share one D* Lite implementation:

* ``LatticeGraph``: vertices are lattice states (i, j, theta), edges are
  primitives, an edge is valid when its trace (minus the start cell) is free.
  This is the incremental counterpart of LBA*.
* ``MeshGraph``: vertices are extended cells (config, i, j) of the MeshA* mesh
  graph, an edge is valid when the cell it steps into is free. This is
  incremental MeshA* (Mesh-D* Lite).

The heuristic h(start, v) is the Euclidean distance from the agent's cell to the
cell where v's current primitive started (for a lattice state, v's own cell). It
is a lower bound on the cost from the agent to v and satisfies the triangle
inequality, which is what D* Lite needs.

Collision checks are cached per edge and counted once per edge, until an edit
touches that edge; both graphs are counted the same way (a lattice edge reads its
trace, a mesh edge reads the one cell it steps into).
"""

from __future__ import annotations

import heapq
import math
import time
from dataclasses import dataclass, field

from mesha.mesh import Mesh
from mesha.primitives import ControlSet

INF = float("inf")
EPS = 1e-9


def _key_le(a, b) -> bool:
    """a <= b for D* Lite keys, with a tolerance: sums of the same costs taken in
    different orders differ in the last bits, and a false 'greater' ends the
    search too early."""
    if a[0] < b[0] - EPS:
        return True
    if a[0] > b[0] + EPS:
        return False
    return a[1] <= b[1] + EPS


def _key_lt(a, b) -> bool:
    if a[0] < b[0] - EPS:
        return True
    if a[0] > b[0] + EPS:
        return False
    return a[1] < b[1] - EPS


@dataclass
class ReplanStats:
    success: bool
    cost: float
    expansions: int
    checked_cells: int
    elapsed_s: float
    capped: bool
    updated_vertices: int = 0


class LatticeGraph:
    name = "lattice"

    def __init__(self, grid, control: ControlSet):
        self.grid = grid
        self.height, self.width = grid.shape
        self.control = control
        self.prims = control.primitives
        self.by_start = control.by_theta
        by_end: list[list[int]] = [[] for _ in range(control.n_theta)]
        for p in control.primitives:
            by_end[p.end_theta].append(p.id)
        self.by_end = tuple(tuple(b) for b in by_end)
        self.cache: dict = {}
        self.checked = 0
        # cell offsets (excluding start) at which each primitive can be hit
        self.hit_offsets = [(p.id, p.start_theta, a, b) for p in control.primitives for a, b in p.cells[1:]]

    def vertex(self, state):
        return (int(state[0]), int(state[1]), int(state[2]))

    def cell(self, v):
        return v[0], v[1]

    def origin(self, v):
        return v[0], v[1]

    def _free(self, i, j, prim):
        key = (i, j, prim.id)
        hit = self.cache.get(key)
        if hit is None:
            hit = False
            g = self.grid
            for a, b in prim.cells[1:]:
                self.checked += 1
                ni, nj = i + a, j + b
                if ni < 0 or nj < 0 or ni >= self.height or nj >= self.width or g[ni, nj]:
                    hit = True
                    break
            self.cache[key] = hit
        return not hit

    def succ(self, v):
        i, j, theta = v
        for pid in self.by_start[theta]:
            p = self.prims[pid]
            if self._free(i, j, p):
                yield (i + p.di, j + p.dj, p.end_theta), p.cost

    def pred(self, v):
        i, j, theta = v
        for pid in self.by_end[theta]:
            p = self.prims[pid]
            ui, uj = i - p.di, j - p.dj
            if self._free(ui, uj, p):
                yield (ui, uj, p.start_theta), p.cost

    def edge_cost(self, u, v):
        pid = self.control.between.get((u[2], v[0] - u[0], v[1] - u[1], v[2]))
        if pid is None:
            return INF
        p = self.prims[pid]
        return p.cost if self._free(u[0], u[1], p) else INF

    def block(self, cells) -> set:
        """Mark cells blocked; return the source vertices of edges that changed."""
        sources = set()
        for ci, cj in cells:
            for pid, start_theta, a, b in self.hit_offsets:
                ui, uj = ci - a, cj - b
                key = (ui, uj, pid)
                if self.cache.get(key) is False:
                    self.cache[key] = True
                sources.add((ui, uj, start_theta))
        return sources

    def unblock(self, cells) -> set:
        """Invalidate collision caches on decreases; include unseen sources."""
        sources = set()
        for ci, cj in cells:
            for pid, theta, a, b in self.hit_offsets:
                ui, uj = ci-a, cj-b
                self.cache.pop((ui,uj,pid), None)
                if 0 <= ui < self.height and 0 <= uj < self.width:
                    sources.add((ui,uj,theta))
        return sources


class MeshGraph:
    name = "mesh"

    def __init__(self, grid, control: ControlSet, mesh: Mesh):
        self.grid = grid
        self.height, self.width = grid.shape
        self.control = control
        self.mesh = mesh
        self.succ_table = mesh.successors
        self.pred_table = mesh.predecessors
        self.origin_of = mesh.origin
        self.cache: dict = {}
        self.checked = 0

    def vertex(self, state):
        return (self.mesh.initial_of_theta[int(state[2])], int(state[0]), int(state[1]))

    def cell(self, v):
        return v[1], v[2]

    def origin(self, v):
        oi, oj = self.origin_of[v[0]]
        return v[1] + oi, v[2] + oj

    def _free_edge(self, u, i, j):
        """Edge from u into cell (i, j); cached per edge like the lattice graph."""
        key = (u, i, j)
        hit = self.cache.get(key)
        if hit is None:
            self.checked += 1
            hit = i < 0 or j < 0 or i >= self.height or j >= self.width or bool(self.grid[i, j])
            self.cache[key] = hit
        return not hit

    def succ(self, v):
        cfg, i, j = v
        for di, dj, ncfg, cost, _pid in self.succ_table[cfg]:
            ni, nj = i + di, j + dj
            if self._free_edge(v, ni, nj):
                yield (ncfg, ni, nj), cost

    def pred(self, v):
        cfg, i, j = v
        for pcfg, di, dj, cost in self.pred_table[cfg]:
            u = (pcfg, i - di, j - dj)
            if self._free_edge(u, i, j):
                yield u, cost

    def edge_cost(self, u, v):
        if not self._free_edge(u, v[1], v[2]):
            return INF
        di, dj = v[1] - u[1], v[2] - u[2]
        for ei, ej, ncfg, cost, _pid in self.succ_table[u[0]]:
            if ncfg == v[0] and ei == di and ej == dj:
                return cost
        return INF

    def block(self, cells) -> set:
        sources = set()
        for ci, cj in cells:
            for cfg in range(self.mesh.n_configs):
                for pcfg, di, dj, _cost in self.pred_table[cfg]:
                    u = (pcfg, ci - di, cj - dj)
                    if self.cache.get((u, ci, cj)) is False:
                        self.cache[(u, ci, cj)] = True
                    sources.add(u)
        return sources

    def unblock(self, cells) -> set:
        sources = set()
        for ci, cj in cells:
            for edges in self.pred_table:
                for pcfg, di, dj, _cost in edges:
                    u = (pcfg,ci-di,cj-dj)
                    self.cache.pop((u,ci,cj), None)
                    if 0 <= u[1] < self.height and 0 <= u[2] < self.width:
                        sources.add(u)
        return sources


@dataclass
class DStarLite:
    graph: object
    start: tuple
    goal: tuple
    max_expansions: int = 2_000_000
    g: dict = field(default_factory=dict)
    rhs: dict = field(default_factory=dict)
    queue: list = field(default_factory=list)
    in_queue: dict = field(default_factory=dict)
    km: float = 0.0
    seq: int = 0
    expansions: int = 0

    def __post_init__(self):
        self.s_start = self.graph.vertex(self.start)
        self.s_goal = self.graph.vertex(self.goal)
        self.s_last = self.s_start
        self.rhs[self.s_goal] = 0.0
        self._push(self.s_goal)

    # ------------------------------------------------------------ core
    def _h(self, v) -> float:
        si, sj = self.graph.cell(self.s_start)
        oi, oj = self.graph.origin(v)
        return math.hypot(si - oi, sj - oj)

    def _key(self, v):
        m = min(self.g.get(v, INF), self.rhs.get(v, INF))
        return (m + self._h(v) + self.km, m)

    def _push(self, v):
        key = self._key(v)
        self.seq += 1
        self.in_queue[v] = key
        heapq.heappush(self.queue, (key[0], key[1], self.seq, v))

    def _update(self, v):
        if v != self.s_goal:
            best = INF
            g = self.g
            for s, c in self.graph.succ(v):
                value = c + g.get(s, INF)
                if value < best:
                    best = value
            self.rhs[v] = best
        self.in_queue.pop(v, None)
        if self.g.get(v, INF) != self.rhs.get(v, INF):
            self._push(v)

    def _top(self):
        while self.queue:
            k1, k2, _s, v = self.queue[0]
            if self.in_queue.get(v) == (k1, k2):
                return (k1, k2), v
            heapq.heappop(self.queue)
        return (INF, INF), None

    def compute(self) -> bool:
        g = self.g
        rhs = self.rhs
        while True:
            top_key, u = self._top()
            start_key = self._key(self.s_start)
            # '<=' rather than '<': the mesh graph has zero-cost edges, so a vertex on
            # the start's own path can tie with the start's key and still change it.
            g_s, rhs_s = g.get(self.s_start, INF), rhs.get(self.s_start, INF)
            start_inconsistent = g_s != rhs_s and not abs(g_s - rhs_s) <= EPS
            if not (_key_le(top_key, start_key) or start_inconsistent):
                return True
            if u is None:
                return True
            if self.expansions >= self.max_expansions:
                return False
            new_key = self._key(u)
            if _key_lt(top_key, new_key):
                self._push(u)
                continue
            heapq.heappop(self.queue)
            del self.in_queue[u]
            self.expansions += 1
            g_u = g.get(u, INF)
            rhs_u = rhs.get(u, INF)
            if g_u > rhs_u:
                g[u] = rhs_u
                for s, c in self.graph.pred(u):
                    if s == self.s_goal:
                        continue
                    value = c + rhs_u
                    if value < rhs.get(s, INF):
                        rhs[s] = value
                        self.in_queue.pop(s, None)
                        if g.get(s, INF) != value:
                            self._push(s)
            else:
                g[u] = INF
                self._update(u)
                for s, c in self.graph.pred(u):
                    if abs(rhs.get(s, INF) - (c + g_u)) < 1e-9 or rhs.get(s, INF) == c + g_u:
                        self._update(s)

    # ------------------------------------------------------------ API
    def plan(self) -> ReplanStats:
        clock = time.perf_counter()
        e0, c0 = self.expansions, self.graph.checked
        ok = self.compute()
        cost = self.g.get(self.s_start, INF) if ok else INF
        cost = min(cost, self.rhs.get(self.s_start, INF)) if ok else INF
        return ReplanStats(
            success=ok and cost < INF,
            cost=cost,
            expansions=self.expansions - e0,
            checked_cells=self.graph.checked - c0,
            elapsed_s=time.perf_counter() - clock,
            capped=not ok,
        )

    def replan(self, new_start, new_blocks, new_opens=()) -> ReplanStats:
        """Move and repair increases/decreases; the old two-argument API stays valid.

        Decreases must seed previously unseen sources too: filtering by g/rhs,
        which is safe for insertions, would miss reconnection of components.
        """
        new_blocks, new_opens = tuple(map(tuple,new_blocks)), tuple(map(tuple,new_opens))
        if set(new_blocks) & set(new_opens):
            raise ValueError('contradictory cell changes')
        for i,j in new_blocks+new_opens:
            if not (0 <= i < self.graph.height and 0 <= j < self.graph.width):
                raise ValueError('cell outside grid')
        clock = time.perf_counter()
        e0, c0 = self.expansions, self.graph.checked
        new_s = self.graph.vertex(new_start)
        self.s_start = new_s
        li, lj = self.graph.cell(self.s_last)
        si, sj = self.graph.cell(new_s)
        self.km += math.hypot(li - si, lj - sj)
        self.s_last = new_s
        updated = 0
        if new_blocks:
            for ci, cj in new_blocks:
                self.graph.grid[ci, cj] = 1
            for u in self.graph.block(new_blocks):
                if u in self.g or u in self.rhs:
                    self._update(u)
                    updated += 1
        if new_opens:
            for ci,cj in new_opens:
                self.graph.grid[ci,cj] = 0
            for u in self.graph.unblock(new_opens):
                self._update(u)
                updated += 1
        ok = self.compute()
        cost = min(self.g.get(self.s_start, INF), self.rhs.get(self.s_start, INF)) if ok else INF
        return ReplanStats(
            success=ok and cost < INF,
            cost=cost,
            expansions=self.expansions - e0,
            checked_cells=self.graph.checked - c0,
            elapsed_s=time.perf_counter() - clock,
            capped=not ok,
            updated_vertices=updated,
        )

    def extract_path(self, limit: int = 100_000) -> tuple[float, list]:
        """Greedy walk along g; returns (cost, vertices). Used for validation."""
        v = self.s_start
        path = [v]
        total = 0.0
        for _ in range(limit):
            if v == self.s_goal:
                return total, path
            best = None
            for s, c in self.graph.succ(v):
                value = c + self.g.get(s, INF)
                if best is None or value < best[0] - 1e-12:
                    best = (value, s, c)
            if best is None or best[0] == INF:
                return INF, path
            total += best[2]
            v = best[1]
            path.append(v)
        return INF, path


def make_planner(kind: str, grid, control: ControlSet, mesh: Mesh, start, goal, max_expansions=2_000_000):
    """D* Lite, MPGAA*, or MD-A*; every public planner owns its input grid.

    Supported kinds: dstar_lattice, dstar_mesh, mpgaa, md_astar, md64, md_scan.
    """
    if kind == 'mpgaa':
        from mesha.adaptive import MPGAA
        return MPGAA(grid,control,start,goal,max_expansions)
    if kind in ('md_astar','md64','md_scan'):
        from mesha.deferred import MeshDeferred
        return MeshDeferred(grid,control,start,goal,max_expansions,variant=kind)
    work = grid.copy()
    if kind == "dstar_lattice":
        graph = LatticeGraph(work, control)
    elif kind == "dstar_mesh":
        graph = MeshGraph(work, control, mesh)
    else:
        raise ValueError(kind)
    return DStarLite(graph, tuple(start), tuple(goal), max_expansions=max_expansions)
