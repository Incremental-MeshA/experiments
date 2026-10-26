"""Mesh graph: extended-cell configurations and the transition table.

This is the precomputation in Appendix B of Agranovskiy & Yakovlev (MeshA*).
A configuration is the set of (primitive, trace index) pairs that still pass
through the current cell. Initial configurations are exactly the discrete headings.
"""

from __future__ import annotations

from dataclasses import dataclass

from mesha.primitives import N_THETA, ControlSet, Primitive

Config = frozenset[tuple[int, int]]


@dataclass(frozen=True)
class Mesh:
    initial_of_theta: tuple[int, ...]
    theta_of_config: tuple[int, ...]  # -1 when the configuration is not initial
    successors: tuple[tuple[tuple[int, int, int, float, int], ...], ...]
    finals: tuple[tuple[tuple[int, int, int, float], ...], ...]
    n_configs: int

    def is_initial(self, config_id: int) -> bool:
        return self.theta_of_config[config_id] >= 0


def _successors_of(
    config: Config,
    primitives: tuple[Primitive, ...],
    initial_config: dict[int, Config],
) -> list[tuple[Config, int, int, float, int]]:
    """Algorithm 2: regular successors are grouped by the next-cell displacement."""
    grouped: dict[tuple[int, int], set[tuple[int, int]]] = {}
    completing: list[tuple[Config, int, int, float, int]] = []
    for prim_id, index in config:
        prim = primitives[prim_id]
        current = prim.cells[index]
        nxt = prim.cells[index + 1]
        di = nxt[0] - current[0]
        dj = nxt[1] - current[1]
        if index == len(prim.cells) - 2:
            completing.append(
                (initial_config[prim.end_theta], di, dj, prim.cost, prim_id)
            )
        else:
            grouped.setdefault((di, dj), set()).add((prim_id, index + 1))
    regular = [
        (frozenset(members), di, dj, 0.0, -1)
        for (di, dj), members in grouped.items()
    ]
    return completing + regular


def _finals_of(
    config: Config, primitives: tuple[Primitive, ...]
) -> tuple[tuple[int, int, int, float], ...]:
    """Endpoint offsets used by the MeshA* heuristic and terminal pruning."""
    finals = []
    for prim_id, index in config:
        prim = primitives[prim_id]
        current = prim.cells[index]
        end = prim.cells[-1]
        finals.append(
            (end[0] - current[0], end[1] - current[1], prim.end_theta, prim.cost)
        )
    return tuple(finals)


def build_mesh(control: ControlSet) -> Mesh:
    """Number every configuration reachable from an initial heading."""
    initial_config: dict[int, Config] = {}
    for theta in range(N_THETA):
        initial_config[theta] = frozenset((prim_id, 0) for prim_id in control.by_theta[theta])

    config_id: dict[Config, int] = {}
    order: list[Config] = []

    def ensure(config: Config) -> int:
        found = config_id.get(config)
        if found is None:
            found = len(order)
            config_id[config] = found
            order.append(config)
        return found

    for theta in range(N_THETA):
        ensure(initial_config[theta])

    successors: list[list[tuple[int, int, int, float, int]]] = []
    cursor = 0
    while cursor < len(order):
        config = order[cursor]
        generated = _successors_of(config, control.primitives, initial_config)
        edges = []
        for succ_config, di, dj, cost, prim_id in generated:
            edges.append((di, dj, ensure(succ_config), cost, prim_id))
        successors.append(edges)
        cursor += 1

    if len(successors) != len(order):
        raise RuntimeError("transition table does not cover every configuration")

    theta_of = [-1] * len(order)
    initial_of = [0] * N_THETA
    for theta, config in initial_config.items():
        ident = config_id[config]
        theta_of[ident] = theta
        initial_of[theta] = ident

    finals = tuple(_finals_of(config, control.primitives) for config in order)
    realized = {
        prim_id
        for edges in successors
        for _di, _dj, _cfg, _cost, prim_id in edges
        if prim_id >= 0
    }
    missing = set(range(len(control))) - realized
    if missing:
        raise RuntimeError(f"primitives missing from the mesh graph: {sorted(missing)[:8]}")

    return Mesh(
        initial_of_theta=tuple(initial_of),
        theta_of_config=tuple(theta_of),
        successors=tuple(tuple(edges) for edges in successors),
        finals=finals,
        n_configs=len(order),
    )
