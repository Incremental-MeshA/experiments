"""Mesh graph: extended-cell configurations and the transition table.

This is the precomputation in Appendix B of Agranovskiy & Yakovlev (MeshA*).
A configuration is the set of (primitive, trace index) pairs that still pass
through the current cell. Initial configurations are exactly the discrete headings.

Besides the forward table, the mesh stores what the other planners need:
``offset`` (where the bundle's primitives started, relative to the current cell)
for the D* Lite heuristic, ``predecessors`` for backward search, and
``signature`` (cells reachable within two steps) for soft-duplicate pruning.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from mesha.primitives import ControlSet, Primitive

Config = frozenset[tuple[int, int]]


@dataclass(frozen=True)
class Mesh:
    initial_of_theta: tuple[int, ...]
    theta_of_config: tuple[int, ...]  # -1 when the configuration is not initial
    # (di, dj, next config, cost, completed primitive id or -1)
    successors: tuple[tuple[tuple[int, int, int, float, int], ...], ...]
    # (pred config, di, dj, cost): pred at (i - di, j - dj) steps into this config at (i, j)
    predecessors: tuple[tuple[tuple[int, int, int, float], ...], ...]
    finals: tuple[tuple[tuple[int, int, int, float], ...], ...]
    # offset of the bundle's start cell from the current cell
    origin: tuple[tuple[int, int], ...]
    signature: tuple[int, ...]
    n_configs: int

    def is_initial(self, config_id: int) -> bool:
        return self.theta_of_config[config_id] >= 0


def _successors_of(config: Config, primitives: tuple[Primitive, ...], initial_config: dict[int, Config]):
    """Algorithm 2: regular successors are grouped by the next-cell displacement."""
    grouped: dict[tuple[int, int], set[tuple[int, int]]] = {}
    completing = []
    for prim_id, index in sorted(config):
        prim = primitives[prim_id]
        current = prim.cells[index]
        nxt = prim.cells[index + 1]
        di = nxt[0] - current[0]
        dj = nxt[1] - current[1]
        if index == len(prim.cells) - 2:
            completing.append((initial_config[prim.end_theta], di, dj, prim.cost, prim_id))
        else:
            grouped.setdefault((di, dj), set()).add((prim_id, index + 1))
    regular = [(frozenset(m), di, dj, 0.0, -1) for (di, dj), m in sorted(grouped.items())]
    return completing + regular


def _finals_of(config: Config, primitives):
    finals = []
    for prim_id, index in sorted(config):
        prim = primitives[prim_id]
        current = prim.cells[index]
        end = prim.cells[-1]
        finals.append((end[0] - current[0], end[1] - current[1], prim.end_theta, prim.cost))
    return tuple(finals)


@lru_cache(maxsize=None)
def build_mesh(control: ControlSet) -> Mesh:
    """Number every configuration reachable from an initial heading."""
    n_theta = control.n_theta
    initial_config = {
        theta: frozenset((prim_id, 0) for prim_id in control.by_theta[theta]) for theta in range(n_theta)
    }
    config_id: dict[Config, int] = {}
    order: list[Config] = []

    def ensure(config: Config) -> int:
        found = config_id.get(config)
        if found is None:
            found = len(order)
            config_id[config] = found
            order.append(config)
        return found

    for theta in range(n_theta):
        ensure(initial_config[theta])

    successors = []
    cursor = 0
    while cursor < len(order):
        generated = _successors_of(order[cursor], control.primitives, initial_config)
        successors.append([(di, dj, ensure(cfg), cost, pid) for cfg, di, dj, cost, pid in generated])
        cursor += 1

    theta_of = [-1] * len(order)
    initial_of = [0] * n_theta
    for theta, config in initial_config.items():
        ident = config_id[config]
        if theta_of[ident] >= 0:
            raise RuntimeError("two headings share an initial configuration")
        theta_of[ident] = theta
        initial_of[theta] = ident

    origin = []
    for config in order:
        offsets = {tuple(-v for v in control.primitives[p].cells[k]) for p, k in config}
        if len(offsets) != 1:
            raise RuntimeError("bundle members do not share a start cell")
        origin.append(offsets.pop())

    preds: list[list[tuple[int, int, int, float]]] = [[] for _ in order]
    for src, edges in enumerate(successors):
        for di, dj, dst, cost, _pid in edges:
            preds[dst].append((src, di, dj, cost))

    # soft-duplicate signature: cells reachable within <= 2 mesh steps
    sig_ids: dict[frozenset, int] = {}
    signature = []
    for src in range(len(order)):
        cells = set()
        for di, dj, nxt, _c, _p in successors[src]:
            cells.add((di, dj))
            for ei, ej, _n2, _c2, _p2 in successors[nxt]:
                cells.add((di + ei, dj + ej))
        key = frozenset(cells)
        signature.append(sig_ids.setdefault(key, len(sig_ids)))

    finals = tuple(_finals_of(config, control.primitives) for config in order)
    realized = {pid for edges in successors for *_x, pid in edges if pid >= 0}
    missing = set(range(len(control))) - realized
    if missing:
        raise RuntimeError(f"primitives missing from the mesh graph: {sorted(missing)[:8]}")

    return Mesh(
        initial_of_theta=tuple(initial_of),
        theta_of_config=tuple(theta_of),
        successors=tuple(tuple(e) for e in successors),
        predecessors=tuple(tuple(p) for p in preds),
        finals=finals,
        origin=tuple(origin),
        signature=tuple(signature),
        n_configs=len(order),
    )
