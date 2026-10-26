"""Plots for the incremental MeshA* notebook."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

from mesha.benchmark import DISPLAY
from mesha.primitives import DIRS, N_THETA, ControlSet

COLORS = {
    "lba": "#4C78A8",
    "lazy_lba": "#F58518",
    "mesha": "#54A24B",
}
HEADING = ("E", "NE", "N", "NW", "W", "SW", "S", "SE")


def use_style() -> None:
    plt.rcParams.update(
        {
            "figure.dpi": 120,
            "savefig.dpi": 140,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": False,
            "font.size": 10,
        }
    )


def draw_map(ax, grid: np.ndarray, title: str) -> None:
    ax.imshow(grid, cmap="gray_r", vmin=0, vmax=1, interpolation="nearest")
    free = int((grid == 0).sum())
    height, width = grid.shape
    ax.set_title(f"{title}\n{height}×{width}, {free / grid.size:.0%} free")
    ax.set_xticks([])
    ax.set_yticks([])


def draw_control_set(control: ControlSet) -> plt.Figure:
    fig, axes = plt.subplots(2, 4, figsize=(10.5, 5.4))
    colors = plt.colormaps["tab10"]
    for theta, ax in enumerate(axes.ravel()):
        for prim_id in control.by_theta[theta]:
            prim = control.get(prim_id)
            rows = [cell[0] for cell in prim.cells]
            cols = [cell[1] for cell in prim.cells]
            ax.plot(cols, rows, color=colors(prim.end_theta), lw=1.6, solid_capstyle="round")
        di, dj = DIRS[theta]
        ax.annotate(
            "",
            xy=(0.9 * dj, 0.9 * di),
            xytext=(0, 0),
            arrowprops={"arrowstyle": "->", "color": "black", "lw": 1.1},
        )
        ax.set_aspect("equal")
        ax.invert_yaxis()
        ax.set_title(f"θ = {HEADING[theta]}")
        ax.set_xticks([])
        ax.set_yticks([])
    fig.suptitle("Control set. Color is the heading at the end of the primitive.")
    fig.tight_layout()
    return fig


def draw_solution(
    ax,
    base: np.ndarray,
    blocks,
    start,
    goal,
    trace,
    expanded,
    title: str,
    pad: int = 6,
) -> None:
    """Draw one repaired path. Orange cells are the obstacle edits."""
    image = np.ones((*base.shape, 3))
    image[base == 1] = (0.22, 0.24, 0.28)
    for i, j in blocks:
        image[int(i), int(j)] = (0.93, 0.45, 0.12)
    ax.imshow(image, interpolation="nearest")
    rows = [int(start[0]), int(goal[0])]
    cols = [int(start[1]), int(goal[1])]
    if expanded:
        er = [cell[0] for cell in expanded]
        ec = [cell[1] for cell in expanded]
        ax.scatter(ec, er, s=3, c="#9ecae1", marker="s", linewidths=0, alpha=0.45, zorder=2)
        rows.extend(er)
        cols.extend(ec)
    if trace:
        ax.plot(
            [cell[1] for cell in trace],
            [cell[0] for cell in trace],
            color="#d62728",
            lw=1.8,
            solid_capstyle="round",
            zorder=3,
        )
        rows.extend(cell[0] for cell in trace)
        cols.extend(cell[1] for cell in trace)
    for i, j in blocks:
        rows.append(int(i))
        cols.append(int(j))
    _zoom(ax, rows, cols, base.shape, pad)
    _arrow(ax, start, "#2ca02c")
    _arrow(ax, goal, "#1f77b4")
    ax.scatter([start[1]], [start[0]], s=18, c="#2ca02c", zorder=4)
    ax.scatter([goal[1]], [goal[0]], s=18, c="#1f77b4", zorder=4)
    ax.set_title(title)
    ax.set_xticks([])
    ax.set_yticks([])


def _arrow(ax, state, color: str) -> None:
    di, dj = DIRS[int(state[2])]
    ax.annotate(
        "",
        xy=(state[1] + 0.85 * dj, state[0] + 0.85 * di),
        xytext=(state[1], state[0]),
        arrowprops={"arrowstyle": "->", "color": color, "lw": 1.3},
        zorder=5,
    )


def _zoom(ax, rows, cols, shape, pad: int) -> None:
    r0 = max(0, min(rows) - pad)
    r1 = min(shape[0], max(rows) + pad + 1)
    c0 = max(0, min(cols) - pad)
    c1 = min(shape[1], max(cols) + pad + 1)
    ax.set_xlim(c0 - 0.5, c1 - 0.5)
    ax.set_ylim(r1 - 0.5, r0 - 0.5)


def grouped_bars(ax, topologies, series: dict[str, list[float]], ylabel: str, title: str):
    x = np.arange(len(topologies))
    width = 0.8 / max(len(series), 1)
    handles = []
    for index, (name, values) in enumerate(series.items()):
        offset = (index - (len(series) - 1) / 2) * width
        bars = ax.bar(x + offset, values, width=width, color=COLORS[name], label=DISPLAY[name])
        handles.append(bars)
    ax.set_xticks(x, topologies)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.3)
    return handles
