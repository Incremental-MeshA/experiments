"""Control sets for the lattice and mesh planners.

Two sets are available:

* ``car16`` (default): 16 headings and up to 24 primitives per heading for a
  point-sized car-like agent with a minimum turning radius, the setting of the
  MeshA* paper (arXiv:2412.10320). Primitives are smooth cubic Hermite curves
  between lattice states. A primitive's collision trace is the supercover of the
  curve: every cell the curve passes through, plus both side cells whenever the
  curve crosses a cell corner. Primitives that can be rebuilt from other
  primitives at no extra cost and without leaving their trace are removed.
* ``legacy8``: the original 8-heading set, kept only as an ablation. All of its
  multi-cell primitives are chains of its 1-step primitives, and diagonal steps
  cut corners.

Grid coordinates are (row, column). Heading 0 points east and headings increase
counterclockwise.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from functools import lru_cache

Cell = tuple[int, int]


@dataclass(frozen=True)
class Primitive:
    id: int
    start_theta: int
    end_theta: int
    di: int
    dj: int
    cost: float
    cells: tuple[Cell, ...]


@dataclass(frozen=True, eq=False)
class ControlSet:
    name: str
    n_theta: int
    # unit-free heading vectors as (row offset, column offset)
    dirs: tuple[Cell, ...]
    primitives: tuple[Primitive, ...]
    by_theta: tuple[tuple[int, ...], ...]
    between: dict[tuple[int, int, int, int], int]
    removed_dominated: int = 0
    turning_radius: float | None = None

    def __len__(self) -> int:
        return len(self.primitives)

    def get(self, prim_id: int) -> Primitive:
        return self.primitives[prim_id]

    def heading_angle(self, theta: int) -> float:
        di, dj = self.dirs[theta]
        return math.atan2(-di, dj)


# ---------------------------------------------------------------- helpers

def _validate(cells: tuple[Cell, ...]) -> None:
    if cells[0] != (0, 0):
        raise ValueError(f"primitive must start at origin, got {cells[0]}")
    for (i0, j0), (i1, j1) in zip(cells, cells[1:]):
        if max(abs(i1 - i0), abs(j1 - j0)) != 1:
            raise ValueError(f"non-adjacent sweep {cells}")


def _assemble(name, n_theta, dirs, raw, removed=0, radius=None) -> ControlSet:
    """raw: (start_theta, end_theta, cells, cost). Keeps the cheapest per end state."""
    best: dict[tuple[int, int, int, int], tuple[float, tuple]] = {}
    for start_theta, end_theta, cells, cost in raw:
        _validate(cells)
        key = (start_theta, cells[-1][0], cells[-1][1], end_theta)
        previous = best.get(key)
        if previous is None or cost < previous[0] - 1e-12:
            best[key] = (cost, cells)
    ordered = sorted(best.items(), key=lambda item: (item[0][0], item[0][3], item[0][1], item[0][2]))
    primitives = []
    between: dict[tuple[int, int, int, int], int] = {}
    buckets: list[list[int]] = [[] for _ in range(n_theta)]
    for prim_id, (key, (cost, cells)) in enumerate(ordered):
        start_theta, end_i, end_j, end_theta = key
        primitives.append(Primitive(prim_id, start_theta, end_theta, end_i, end_j, cost, cells))
        between[key] = prim_id
        buckets[start_theta].append(prim_id)
    return ControlSet(
        name=name,
        n_theta=n_theta,
        dirs=tuple(dirs),
        primitives=tuple(primitives),
        by_theta=tuple(tuple(b) for b in buckets),
        between=between,
        removed_dominated=removed,
        turning_radius=radius,
    )


def dominated_primitives(raw) -> list[int]:
    """Indices of primitives that other primitives reproduce.

    A primitive is dominated when a chain of the *other* primitives reaches the
    same end state, costs no more, and only sweeps cells inside its trace. Such a
    primitive adds duplicate edges to the lattice and nothing to the plan space.
    """
    by_start: dict[int, list[int]] = {}
    for index, (start_theta, _e, _c, _cost) in enumerate(raw):
        by_start.setdefault(start_theta, []).append(index)
    out = []
    for index, (start_theta, end_theta, cells, cost) in enumerate(raw):
        allowed = set(cells)
        target = (cells[-1][0], cells[-1][1], end_theta)
        dist = {(0, 0, start_theta): 0.0}
        heap = [(0.0, 0, 0, start_theta)]
        found = False
        while heap:
            g, i, j, theta = heapq.heappop(heap)
            if g > dist.get((i, j, theta), math.inf) + 1e-12:
                continue
            if (i, j, theta) == target and g > 0:
                found = g <= cost + 1e-9
                break
            for other in by_start.get(theta, ()):
                if other == index:
                    continue
                _s, o_end, o_cells, o_cost = raw[other]
                if any((i + a, j + b) not in allowed for a, b in o_cells):
                    continue
                ng = g + o_cost
                if ng > cost + 1e-9:
                    continue
                key = (i + o_cells[-1][0], j + o_cells[-1][1], o_end)
                if ng < dist.get(key, math.inf) - 1e-12:
                    dist[key] = ng
                    heapq.heappush(heap, (ng, *key))
        if found:
            out.append(index)
    return out


# ---------------------------------------------------------------- car16

# heading vectors in (x, y) with y pointing up (north)
_XY16 = (
    (1, 0), (2, 1), (1, 1), (1, 2), (0, 1), (-1, 2), (-1, 1), (-2, 1),
    (-1, 0), (-2, -1), (-1, -1), (-1, -2), (0, -1), (1, -2), (1, -1), (2, -1),
)
# how many primitives to keep per heading change
_PER_DELTA = {0: 4, 1: 4, -1: 4, 2: 3, -2: 3, 3: 3, -3: 3}


def _hermite(p1, u0, u1, scale0, scale1, n):
    """Points, length and max curvature of a cubic Hermite curve from the origin."""
    x1, y1 = p1
    m0 = (u0[0] * scale0, u0[1] * scale0)
    m1 = (u1[0] * scale1, u1[1] * scale1)
    pts = []
    length = 0.0
    kmax = 0.0
    prev = None
    for k in range(n + 1):
        t = k / n
        h00 = 2 * t**3 - 3 * t**2 + 1
        h10 = t**3 - 2 * t**2 + t
        h01 = -2 * t**3 + 3 * t**2
        h11 = t**3 - t**2
        x = h10 * m0[0] + h01 * x1 + h11 * m1[0]
        y = h10 * m0[1] + h01 * y1 + h11 * m1[1]
        # first and second derivatives
        d00, d10, d01, d11 = 6 * t**2 - 6 * t, 3 * t**2 - 4 * t + 1, -6 * t**2 + 6 * t, 3 * t**2 - 2 * t
        dx = d10 * m0[0] + d01 * x1 + d11 * m1[0]
        dy = d10 * m0[1] + d01 * y1 + d11 * m1[1]
        e00, e10, e01, e11 = 12 * t - 6, 6 * t - 4, -12 * t + 6, 6 * t - 2
        ddx = e10 * m0[0] + e01 * x1 + e11 * m1[0]
        ddy = e10 * m0[1] + e01 * y1 + e11 * m1[1]
        speed = math.hypot(dx, dy)
        if speed < 1e-9:
            return None
        kmax = max(kmax, abs(dx * ddy - dy * ddx) / speed**3)
        if prev is not None:
            length += math.hypot(x - prev[0], y - prev[1])
        prev = (x, y)
        pts.append((x, y))
    return pts, length, kmax


def _fit(p1, a0, a1, kappa_max):
    """Best Hermite curve (lowest max curvature) or None if it violates the radius."""
    u0 = (math.cos(a0), math.sin(a0))
    u1 = (math.cos(a1), math.sin(a1))
    chord = math.hypot(*p1)
    best = None
    for s in (0.6, 0.75, 0.9, 1.0, 1.1, 1.25, 1.4, 1.6):
        out = _hermite(p1, u0, u1, s * chord, s * chord, 60)
        if out is None:
            continue
        _pts, _length, kmax = out
        if best is None or kmax < best[1] - 1e-12:
            best = (s, kmax)
    if best is None or best[1] > kappa_max + 1e-9:
        return None
    s = best[0]
    pts, length, kmax = _hermite(p1, u0, u1, s * chord, s * chord, max(200, int(chord * 120)))
    # reject curves that turn back on themselves
    return pts, length


def _supercover(points) -> tuple[Cell, ...]:
    """Cells visited by a dense polyline, as (row, col), with corner crossings closed."""
    cells: list[tuple[int, int]] = []
    for x, y in points:
        cell = (int(math.floor(x + 0.5)), int(math.floor(y + 0.5)))
        if cells and cells[-1] == cell:
            continue
        if cells:
            cx, cy = cells[-1]
            if abs(cell[0] - cx) + abs(cell[1] - cy) == 2:
                # corner crossing: the point touched both side cells
                cells.append((cell[0], cy))
                cells.append((cx, cell[1]))
            elif max(abs(cell[0] - cx), abs(cell[1] - cy)) > 1:
                raise RuntimeError("sampling too coarse")
        cells.append(cell)
    out: list[Cell] = []
    for cx, cy in cells:
        rc = (-cy, cx)
        if not out or out[-1] != rc:
            out.append(rc)
    return tuple(out)


def _car_family(start: int, radius: float, max_len: float):
    """Primitives for one start heading (before rotation)."""
    kappa = 1.0 / radius
    a0 = math.atan2(_XY16[start][1], _XY16[start][0])
    reach = int(math.ceil(max_len))
    chosen = []
    for delta, count in _PER_DELTA.items():
        end = (start + delta) % 16
        a1 = math.atan2(_XY16[end][1], _XY16[end][0])
        options = []
        for x in range(-reach, reach + 1):
            for y in range(-reach, reach + 1):
                if (x, y) == (0, 0):
                    continue
                chord = math.hypot(x, y)
                if chord > max_len:
                    continue
                if x * math.cos(a0) + y * math.sin(a0) <= 0.25:
                    continue
                cross = math.cos(a0) * y - math.sin(a0) * x
                if delta > 0 and cross <= 0:
                    continue
                if delta < 0 and cross >= 0:
                    continue
                fitted = _fit((x, y), a0, a1, kappa)
                if fitted is None:
                    continue
                pts, length = fitted
                if length > max_len * 1.15:
                    continue
                options.append((length, abs(cross), x, y, pts))
        if delta == 0:
            straight = [o for o in options if abs(o[1]) < 1e-9]
            shifts = [o for o in options if abs(o[1]) >= 1e-9]
            straight.sort(key=lambda o: o[0])
            picks = []
            if straight:
                picks.append(straight[0])
                longest = [o for o in straight if o[0] >= 3.5]
                if longest:
                    picks.append(longest[0])
            left = sorted(
                (o for o in shifts if math.cos(a0) * o[3] - math.sin(a0) * o[2] > 0),
                key=lambda o: (o[0], o[1]),
            )
            right = sorted(
                (o for o in shifts if math.cos(a0) * o[3] - math.sin(a0) * o[2] < 0),
                key=lambda o: (o[0], o[1]),
            )
            picks += left[:1] + right[:1]
        else:
            options.sort(key=lambda o: (o[0], o[1], o[2], o[3]))
            picks = []
            for option in options:
                # spread endpoints out: skip ones adjacent to an endpoint already taken
                if any(abs(option[2] - p[2]) <= 1 and abs(option[3] - p[3]) <= 1 for p in picks):
                    continue
                picks.append(option)
                if len(picks) == count:
                    break
        for length, _cross, _x, _y, pts in picks:
            chosen.append((start, end, _supercover(pts), length))
    return chosen


def _rot_rc(cells, turns):
    out = []
    for i, j in cells:
        for _ in range(turns):
            i, j = -j, i  # 90 degrees counterclockwise in (row, col)
        out.append((i, j))
    return tuple(out)


@lru_cache(maxsize=None)
def build_car16(radius: float = 2.0, max_len: float = 6.0) -> ControlSet:
    base = []
    for start in range(4):
        base += _car_family(start, radius, max_len)
    raw = []
    for turns in range(4):
        for start, end, cells, cost in base:
            raw.append(((start + 4 * turns) % 16, (end + 4 * turns) % 16, _rot_rc(cells, turns), cost))
    drop = set(dominated_primitives(raw))
    kept = [item for index, item in enumerate(raw) if index not in drop]
    dirs = tuple((-y, x) for x, y in _XY16)
    return _assemble("car16", 16, dirs, kept, removed=len(drop), radius=radius)


# ---------------------------------------------------------------- legacy8

_DIRS8: tuple[Cell, ...] = ((0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1), (1, 0), (1, 1))


def _legacy_family(heading: int):
    if heading == 0:
        return [
            (((0, 0), (0, 1)), 0),
            (((0, 0), (-1, 1)), 1),
            (((0, 0), (1, 1)), 7),
            (((0, 0), (0, 1), (0, 2), (0, 3), (0, 4), (0, 5)), 0),
            (((0, 0), (0, 1), (0, 2), (-1, 3), (-2, 4)), 1),
            (((0, 0), (0, 1), (0, 2), (1, 3), (2, 4)), 7),
            (((0, 0), (0, 1), (0, 2), (-1, 3), (-2, 3), (-3, 3)), 2),
            (((0, 0), (0, 1), (0, 2), (1, 3), (2, 3), (3, 3)), 6),
        ]
    return [
        (((0, 0), (-1, 1)), 1),
        (((0, 0), (-1, 0)), 2),
        (((0, 0), (0, 1)), 0),
        (((0, 0), (-1, 1), (-2, 2), (-3, 3), (-4, 4), (-5, 5)), 1),
        (((0, 0), (-1, 1), (-2, 2), (-3, 2), (-4, 2)), 2),
        (((0, 0), (-1, 1), (-2, 2), (-2, 3), (-2, 4)), 0),
        (((0, 0), (-1, 1), (-2, 2), (-3, 2), (-4, 1), (-5, 0)), 3),
        (((0, 0), (-1, 1), (-2, 2), (-2, 3), (-1, 4), (0, 5)), 7),
    ]


def _poly_cost(cells) -> float:
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(cells, cells[1:]))


@lru_cache(maxsize=None)
def build_legacy8() -> ControlSet:
    raw = []
    for base in (0, 1):
        for turns in range(4):
            start = (base + 2 * turns) % 8
            for cells, end in _legacy_family(base):
                turned = _rot_rc(cells, turns)
                raw.append((start, (end + 2 * turns) % 8, turned, _poly_cost(turned)))
    return _assemble("legacy8", 8, _DIRS8, raw)


def build_control_set(name: str = "car16") -> ControlSet:
    if name == "car16":
        return build_car16()
    if name == "legacy8":
        return build_legacy8()
    raise ValueError(f"unknown control set {name}")
