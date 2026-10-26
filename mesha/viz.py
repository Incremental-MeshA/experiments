"""Plots for the incremental MeshA* notebook."""

from __future__ import annotations

import math

import matplotlib.pyplot as plt
import numpy as np

from mesha.benchmark import DISPLAY
from mesha.primitives import ControlSet

COLORS = {
    "lba": "#4C78A8",
    "lazy_lba": "#F58518",
    "mesha": "#54A24B",
    "mesh_parall": "#B279A2",
    "mesh_pruning": "#9D755D",
    "dstar_lattice": "#72B7B2",
    "dstar_mesh": "#E45756",
}


def use_style() -> None:
    plt.rcParams.update({
        "figure.dpi": 110,
        "savefig.dpi": 140,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": False,
        "font.size": 10,
    })


def draw_map(ax, grid: np.ndarray, title: str) -> None:
    ax.imshow(grid, cmap="gray_r", vmin=0, vmax=1, interpolation="nearest")
    free = int((grid == 0).sum())
    height, width = grid.shape
    ax.set_title(f"{title}\n{height}×{width}, {free / grid.size:.0%} free")
    ax.set_xticks([])
    ax.set_yticks([])


def draw_control_set(control: ControlSet, headings=(0, 1, 2, 3)) -> plt.Figure:
    """Primitive traces for a few start headings (the rest are rotations)."""
    fig, axes = plt.subplots(1, len(headings), figsize=(3.2 * len(headings), 3.4))
    cmap = plt.colormaps["twilight"]
    for theta, ax in zip(headings, np.atleast_1d(axes)):
        cells = set()
        for prim_id in control.by_theta[theta]:
            prim = control.get(prim_id)
            cells.update(prim.cells)
        for i, j in cells:
            ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1, color="0.92", zorder=0))
        for prim_id in control.by_theta[theta]:
            prim = control.get(prim_id)
            ax.plot([c[1] for c in prim.cells], [c[0] for c in prim.cells],
                    color=cmap(prim.end_theta / control.n_theta), lw=1.3, alpha=0.9)
            ax.plot([prim.dj], [prim.di], "o", ms=2.5, color=cmap(prim.end_theta / control.n_theta))
        di, dj = control.dirs[theta]
        n = math.hypot(di, dj)
        ax.annotate("", xy=(0.9 * dj / n, 0.9 * di / n), xytext=(0, 0),
                    arrowprops={"arrowstyle": "->", "color": "black", "lw": 1.2})
        ax.set_aspect("equal")
        ax.invert_yaxis()
        ax.set_title(f"start heading {theta} ({math.degrees(control.heading_angle(theta)):.1f}°)\n"
                     f"{len(control.by_theta[theta])} primitives")
        ax.set_xticks([])
        ax.set_yticks([])
    fig.suptitle("Cell traces (grey) and primitive centre lines. Colour is the end heading.")
    fig.tight_layout()
    return fig


def draw_solution(ax, base, blocks, start, goal, trace, expanded, title, control: ControlSet, pad: int = 6):
    """Draw one path. Orange cells are obstacle edits; blue dots are expanded cells."""
    image = np.ones((*base.shape, 3))
    image[base == 1] = (0.22, 0.24, 0.28)
    for i, j in blocks:
        image[int(i), int(j)] = (0.93, 0.45, 0.12)
    ax.imshow(image, interpolation="nearest")
    rows = [int(start[0]), int(goal[0])]
    cols = [int(start[1]), int(goal[1])]
    if expanded:
        er = [c[0] for c in expanded]
        ec = [c[1] for c in expanded]
        ax.scatter(ec, er, s=3, c="#9ecae1", marker="s", linewidths=0, alpha=0.45, zorder=2)
    if trace:
        ax.plot([c[1] for c in trace], [c[0] for c in trace], color="#d62728", lw=1.6, zorder=3)
        rows += [c[0] for c in trace]
        cols += [c[1] for c in trace]
    for i, j in blocks:
        rows.append(int(i))
        cols.append(int(j))
    r0, r1 = max(0, min(rows) - pad), min(base.shape[0], max(rows) + pad + 1)
    c0, c1 = max(0, min(cols) - pad), min(base.shape[1], max(cols) + pad + 1)
    ax.set_xlim(c0 - 0.5, c1 - 0.5)
    ax.set_ylim(r1 - 0.5, r0 - 0.5)
    for state, color in ((start, "#2ca02c"), (goal, "#1f77b4")):
        di, dj = control.dirs[int(state[2])]
        n = math.hypot(di, dj)
        ax.annotate("", xy=(state[1] + 2.2 * dj / n, state[0] + 2.2 * di / n), xytext=(state[1], state[0]),
                    arrowprops={"arrowstyle": "->", "color": color, "lw": 1.4}, zorder=5)
        ax.scatter([state[1]], [state[0]], s=16, c=color, zorder=4)
    ax.set_title(title, fontsize=9)
    ax.set_xticks([])
    ax.set_yticks([])


def grouped_bars(ax, groups, series: dict[str, list[tuple[float, float, float]]], ylabel: str, title: str):
    """series[name] = [(median, q25, q75) per group]; whiskers show the IQR."""
    x = np.arange(len(groups))
    width = 0.8 / max(len(series), 1)
    for index, (name, values) in enumerate(series.items()):
        offset = (index - (len(series) - 1) / 2) * width
        med = np.array([v[0] for v in values])
        lo = med - np.array([v[1] for v in values])
        hi = np.array([v[2] for v in values]) - med
        ax.bar(x + offset, med, width=width, color=COLORS[name], label=DISPLAY[name])
        ax.errorbar(x + offset, med, yerr=[lo, hi], fmt="none", ecolor="0.25", lw=0.8, capsize=2)
    ax.set_xticks(x, groups)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.3)
