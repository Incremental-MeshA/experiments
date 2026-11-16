"""MPGAA* reference backend on the repository's native directed primitive graph.

Independent port of Hernandez, Asin & Baier (AAAI 2015), Algorithms 1--2.
Reverse heuristic repair uses explicit predecessors. A conservative spatial
filter and grouped swept-cell notifications strengthen this control and MD-A*
identically. No C++ timings or quantized costs are used here.
"""
from __future__ import annotations

import heapq
import math
import time
from dataclasses import dataclass
from functools import lru_cache

from mesha.incremental import EPS, ReplanStats

INF = math.inf


@dataclass
class AdaptiveStats(ReplanStats):
    states: tuple = ()
    prim_ids: tuple = ()
    certified: bool = False
    backend_calls: int = 1
    activated_cells: int = 0
    deferred_cells: int = 0
    refined_cells: int = 0
    notify_probes: int = 0


@lru_cache(maxsize=None)
def dependency_groups(control):
    groups = {}
    by_end = [[] for _ in range(control.n_theta)]
    reach_i = reach_j = 0
    for p in control.primitives:
        by_end[p.end_theta].append(p.id)
        for a, b in set(p.cells[1:]):
            groups.setdefault((p.start_theta, a, b), []).append(p.id)
            reach_i = max(reach_i, abs(a))
            reach_j = max(reach_j, abs(b))
    return tuple((t, a, b, tuple(ids)) for (t, a, b), ids in sorted(groups.items())), tuple(map(tuple, by_end)), reach_i, reach_j


class MPGAA:
    """Exact adaptive A* for fixed goal; accepts blocks AND openings.

    Floating comparisons use the repository's EPS, and reported path costs are
    computed from the actual primitive sequence, rather than a cached h value.
    """
    def __init__(self, grid, control, start, goal, max_expansions=2_000_000, *, copy_grid=True):
        self.grid = grid.copy() if copy_grid else grid
        self.height, self.width = grid.shape
        self.flat = bytearray(self.grid.astype('uint8').tobytes())
        self.control = control
        self.start, self.goal = tuple(start), tuple(goal)
        self.max_expansions = max_expansions
        self.groups, self.by_end, self.reach_i, self.reach_j = dependency_groups(control)
        self.h, self.next, self.support, self.cache = {}, {}, {}, {}
        self.box = None
        self.no_path_start = None
        self.checked = self.expanded = self.notified = 0

    def base(self, u):
        return math.hypot(u[0] - self.goal[0], u[1] - self.goal[1])

    def lower(self, u):
        value = self.h.get(u)
        return self.base(u) if value is None else value

    def inside(self, u):
        return 0 <= u[0] < self.height and 0 <= u[1] < self.width

    def free(self, u):
        return self.inside(u) and not self.flat[u[0] * self.width + u[1]]

    def head(self, u, pid):
        p = self.control.primitives[pid]
        return u[0] + p.di, u[1] + p.dj, p.end_theta

    def valid(self, u, pid):
        key = (u, pid)
        hit = self.cache.get(key)
        if hit is None:
            p = self.control.primitives[pid]
            hit = True
            for a, b in p.cells[1:]:
                self.checked += 1
                i, j = u[0] + a, u[1] + b
                if not (0 <= i < self.height and 0 <= j < self.width) or self.flat[i * self.width + j]:
                    hit = False
                    break
            self.cache[key] = hit
        return hit

    def _relevant(self, q):
        if self.box is None:
            return False
        a, b, c, d = self.box
        return a-self.reach_i <= q[0] <= c+self.reach_i and b-self.reach_j <= q[1] <= d+self.reach_j

    def _observe(self, blocks, opens):
        affected = {}
        for q in tuple(blocks) + tuple(opens):
            if not self._relevant(q):
                continue
            for theta, a, b, ids in self.groups:
                self.notified += 1
                u = (q[0]-a, q[1]-b, theta)
                if not self.inside(u):
                    continue
                for pid in ids:
                    self.cache.pop((u, pid), None)
                selected = self.next.get(u)
                if selected is not None and selected[1] in ids and q not in self._opened_set:
                    self.next.pop(u, None)
                if q in self._opened_set and u in self.h:
                    affected.setdefault(u, set()).update(ids)
        queue = []

        def lower(u, value, parent, pid):
            old = self.h.get(u)
            if old is None or value >= old-EPS:
                return
            value = max(self.base(u), value)
            self.h[u] = value
            self.next.pop(u, None)
            self.support[u] = (parent, pid)
            heapq.heappush(queue, (value, u))

        for u, ids in sorted(affected.items()):
            for pid in sorted(ids):
                v = self.head(u, pid)
                value = self.control.primitives[pid].cost + self.lower(v)
                if value < self.h[u]-EPS and self.valid(u, pid):
                    lower(u, value, v, pid)
        while queue:
            value, u = heapq.heappop(queue)
            if value != self.lower(u):
                continue
            arrow = self.support.get(u)
            if arrow is not None and (arrow[0] == self.goal or arrow[0] in self.next):
                self.next[u] = arrow
            for pid in self.by_end[u[2]]:
                p = self.control.primitives[pid]
                v = (u[0]-p.di, u[1]-p.dj, p.start_theta)
                if v in self.h and p.cost+value < self.h[v]-EPS and self.valid(v, pid):
                    lower(v, p.cost+value, u, pid)

    def _goal_condition(self, u, memo):
        chain = []
        seen = set()
        while u != self.goal and u not in memo:
            if u in seen:
                raise AssertionError('positive-cost next pointers contain a cycle')
            seen.add(u)
            chain.append(u)
            arrow = self.next.get(u)
            if arrow is None or abs(self.lower(u)-self.control.primitives[arrow[1]].cost-self.lower(arrow[0])) > 8*EPS:
                good = False
                break
            u = arrow[0]
        else:
            good = u == self.goal or memo[u]
        for x in chain:
            memo[x] = good
        return good

    def _solve(self, start):
        self.start = tuple(start)
        if not self.free(self.start) or not self.free(self.goal):
            return INF, (), (), False
        best, parent, closed, memo = {self.start: 0.0}, {}, {}, {}
        heap = [(self.lower(self.start), 0.0, 0, self.start)]
        seq = 0
        join = None
        while heap:
            _f, neg, _seq, u = heapq.heappop(heap)
            gu = -neg
            if gu != best.get(u, INF):
                continue
            if self._goal_condition(u, memo):
                join = u
                break
            if self.expanded >= self.max_expansions:
                return INF, (), (), True
            self.expanded += 1
            closed[u] = gu
            i, j, _ = u
            if self.box is None:
                self.box = (i, j, i, j)
            else:
                a, b, c, d = self.box
                self.box = (min(a,i), min(b,j), max(c,i), max(d,j))
            for pid in self.control.by_theta[u[2]]:
                p = self.control.primitives[pid]
                v = self.head(u, pid)
                value = gu+p.cost
                if value < best.get(v, INF)-EPS and self.valid(u, pid):
                    best[v] = value
                    parent[v] = (u, pid)
                    seq += 1
                    heapq.heappush(heap, (value+self.lower(v), -value, seq, v))
        if join is None:
            return INF, (), (), False
        ids, vertices = [], [join]
        u = join
        while u != self.start:
            u, pid = parent[u]
            ids.append(pid)
            vertices.append(u)
        ids.reverse()
        vertices.reverse()
        u = join
        while u != self.goal:
            u, pid = self.next[u]
            ids.append(pid)
            vertices.append(u)
        cost = math.fsum(self.control.primitives[p].cost for p in ids)
        for u, gu in closed.items():
            old = self.lower(u)
            if cost-gu < old-1e-7:
                raise AssertionError('adaptive heuristic lost consistency')
            self.h[u] = max(old, cost-gu)
        for u, v, pid in zip(vertices, vertices[1:], ids):
            self.next[u] = (v, pid)
        return cost, tuple(vertices), tuple(ids), False

    def plan(self):
        return self.replan(self.start, (), ())

    def replan(self, new_start, new_blocks=(), new_opens=()):
        clock = time.perf_counter()
        blocks, opens = tuple(map(tuple, new_blocks)), tuple(map(tuple, new_opens))
        if set(blocks) & set(opens):
            raise ValueError('contradictory cell changes')
        for i,j in blocks+opens:
            if not (0 <= i < self.height and 0 <= j < self.width):
                raise ValueError('cell outside grid')
        blocks = tuple(q for q in blocks if not self.flat[q[0]*self.width+q[1]])
        opens = tuple(q for q in opens if self.flat[q[0]*self.width+q[1]])
        self.checked = self.expanded = self.notified = 0
        for value, cells in [(1, blocks), (0, opens)]:
            for i, j in cells:
                if not (0 <= i < self.height and 0 <= j < self.width):
                    raise ValueError('cell outside grid')
                self.grid[i,j] = value
                self.flat[i*self.width+j] = value
        self._opened_set = set(opens)
        self._observe(blocks, opens)
        if tuple(new_start) == self.no_path_start and not opens:
            cost, states, ids, capped = INF, (), (), False
        else:
            cost, states, ids, capped = self._solve(tuple(new_start))
        self.no_path_start = tuple(new_start) if cost == INF and not capped else None
        return AdaptiveStats(cost < INF, cost, self.expanded, self.checked,
                             time.perf_counter()-clock, capped, states=states, prim_ids=ids,
                             notify_probes=self.notified)

    def audit(self):
        if abs(self.lower(self.goal)) > EPS:
            raise AssertionError('h(goal) != 0')
        for u, hu in self.h.items():
            if hu < self.base(u)-EPS:
                raise AssertionError('h below base')
            for pid in self.control.by_theta[u[2]]:
                if self.valid(u,pid) and hu > self.control.primitives[pid].cost+self.lower(self.head(u,pid))+1e-7:
                    raise AssertionError('inconsistent h')
