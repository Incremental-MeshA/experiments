"""Grid-aligned car-like control set.

Eight headings. Each heading owns short ±45° steps plus longer straights and
arcs that share a collision-trace prefix, which is the case MeshA* bundles.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

N_THETA = 8
# (row offset, column offset), theta 0 = east, then counterclockwise.
DIRS: tuple[tuple[int, int], ...] = (
    (0, 1),
    (-1, 1),
    (-1, 0),
    (-1, -1),
    (0, -1),
    (1, -1),
    (1, 0),
    (1, 1),
)


@dataclass(frozen=True)
class Primitive:
    id: int
    start_theta: int
    end_theta: int
    di: int
    dj: int
    cost: float
    cells: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class ControlSet:
    primitives: tuple[Primitive, ...]
    by_theta: tuple[tuple[int, ...], ...]
    between: dict[tuple[int, int, int, int], int]

    def __len__(self) -> int:
        return len(self.primitives)

    def get(self, prim_id: int) -> Primitive:
        return self.primitives[prim_id]


def _rot90(i: int, j: int) -> tuple[int, int]:
    """90° counterclockwise in grid coordinates (row, column)."""
    return -j, i


def _rotate_cells(
    cells: tuple[tuple[int, int], ...], turns: int
) -> tuple[tuple[int, int], ...]:
    rotated = []
    for i, j in cells:
        for _ in range(turns):
            i, j = _rot90(i, j)
        rotated.append((i, j))
    return tuple(rotated)


def _cost(cells: tuple[tuple[int, int], ...]) -> float:
    total = 0.0
    for (i0, j0), (i1, j1) in zip(cells, cells[1:]):
        total += math.hypot(i1 - i0, j1 - j0)
    return total


def _validate(cells: tuple[tuple[int, int], ...]) -> None:
    if cells[0] != (0, 0):
        raise ValueError(f"primitive must start at origin, got {cells[0]}")
    for (i0, j0), (i1, j1) in zip(cells, cells[1:]):
        if max(abs(i1 - i0), abs(j1 - j0)) != 1:
            raise ValueError(f"non-adjacent sweep {cells}")


def _family(heading: int) -> list[tuple[tuple[tuple[int, int], ...], int]]:
    """Primitives for east (0) or north-east (1), as (cells, end heading)."""
    if heading == 0:
        specs = [
            (((0, 0), (0, 1)), 0),
            (((0, 0), (-1, 1)), 1),
            (((0, 0), (1, 1)), 7),
            (((0, 0), (0, 1), (0, 2), (0, 3), (0, 4), (0, 5)), 0),
            (((0, 0), (0, 1), (0, 2), (-1, 3), (-2, 4)), 1),
            (((0, 0), (0, 1), (0, 2), (1, 3), (2, 4)), 7),
            (((0, 0), (0, 1), (0, 2), (-1, 3), (-2, 3), (-3, 3)), 2),
            (((0, 0), (0, 1), (0, 2), (1, 3), (2, 3), (3, 3)), 6),
        ]
    elif heading == 1:
        specs = [
            (((0, 0), (-1, 1)), 1),
            (((0, 0), (-1, 0)), 2),
            (((0, 0), (0, 1)), 0),
            (((0, 0), (-1, 1), (-2, 2), (-3, 3), (-4, 4), (-5, 5)), 1),
            (((0, 0), (-1, 1), (-2, 2), (-3, 2), (-4, 2)), 2),
            (((0, 0), (-1, 1), (-2, 2), (-2, 3), (-2, 4)), 0),
            (((0, 0), (-1, 1), (-2, 2), (-3, 2), (-4, 1), (-5, 0)), 3),
            (((0, 0), (-1, 1), (-2, 2), (-2, 3), (-1, 4), (0, 5)), 7),
        ]
    else:
        raise ValueError(heading)
    for cells, _end in specs:
        _validate(cells)
    return specs


def build_control_set() -> ControlSet:
    """Build the 8-heading control set by rotating the east and NE families."""
    raw: list[tuple[int, int, tuple[tuple[int, int], ...]]] = []
    for base in (0, 1):
        for turns in range(4):
            start_theta = (base + 2 * turns) % N_THETA
            for cells, end_theta in _family(base):
                turned = _rotate_cells(cells, turns)
                _validate(turned)
                raw.append((start_theta, (end_theta + 2 * turns) % N_THETA, turned))

    best: dict[tuple[int, int, int, int], tuple[float, tuple]] = {}
    for start_theta, end_theta, cells in raw:
        end_i, end_j = cells[-1]
        key = (start_theta, end_i, end_j, end_theta)
        cost = _cost(cells)
        previous = best.get(key)
        if previous is None or cost < previous[0] - 1e-12:
            best[key] = (cost, cells)

    ordered = sorted(best.items(), key=lambda item: (item[0][0], item[0][3], item[0][1], item[0][2]))
    primitives = []
    between: dict[tuple[int, int, int, int], int] = {}
    buckets: list[list[int]] = [[] for _ in range(N_THETA)]
    for prim_id, (key, (cost, cells)) in enumerate(ordered):
        start_theta, end_i, end_j, end_theta = key
        primitives.append(
            Primitive(
                id=prim_id,
                start_theta=start_theta,
                end_theta=end_theta,
                di=end_i,
                dj=end_j,
                cost=cost,
                cells=cells,
            )
        )
        between[key] = prim_id
        buckets[start_theta].append(prim_id)

    return ControlSet(
        primitives=tuple(primitives),
        by_theta=tuple(tuple(bucket) for bucket in buckets),
        between=between,
    )
