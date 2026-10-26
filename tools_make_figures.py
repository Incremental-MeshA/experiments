"""Renders the README figures into docs/figures/ from results/runs.json.

Run from the project root: python tools_make_figures.py
"""

import json
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from mesha.benchmark import DISPLAY, ONE_SHOT, RESULTS_PATH, ROOT, WEIGHTS, apply_blocks, load_benchmark, load_named_maps  # noqa: E402
from mesha.mesh import build_mesh  # noqa: E402
from mesha.primitives import build_control_set  # noqa: E402
from mesha.search import search  # noqa: E402
from mesha.viz import COLORS, draw_control_set, draw_map, draw_solution, use_style  # noqa: E402

OUT = ROOT / "docs" / "figures"
OUT.mkdir(parents=True, exist_ok=True)
use_style()
plt.rcParams["savefig.bbox"] = "tight"

bench = load_benchmark()
res = json.loads(RESULTS_PATH.read_text())
legacy = json.loads((ROOT / "results" / "legacy8_ablation.json").read_text())
recs = res["records"]
maps = load_named_maps(bench)
control = build_control_set(bench["control_set"]["name"])
mesh = build_mesh(control)
topos = [m["topology"] for m in bench["maps"]]
inst = {i["id"]: i for i in bench["instances"]}
TOPO_RU = {"city": "город", "indoor": "помещение", "maze": "лабиринт", "rooms": "комнаты"}

by = defaultdict(dict)
rows = defaultdict(dict)
for r in recs:
    if r["kind"] == "oneshot":
        by[(r["id"], r["query"], r["weight"])][r["algorithm"]] = r
    if r["weight"] == 1.0:
        rows[(r["id"], r["query"])][r["algorithm"]] = r


def save(fig, name):
    fig.savefig(OUT / name)
    plt.close(fig)
    print("wrote", OUT / name)


def iqr(v):
    return np.percentile(v, 50), np.percentile(v, 25), np.percentile(v, 75)


# 1. maps
fig, axes = plt.subplots(1, 4, figsize=(13, 3.6))
for ax, row in zip(axes, bench["maps"]):
    draw_map(ax, maps[row["file"]], f"{TOPO_RU[row['topology']]}: {row['file']}")
save(fig, "01_maps.png")

# 2. control set
fig = draw_control_set(control)
fig.suptitle("Набор примитивов car16: трассы клеток (серые) и центральные линии; цвет — конечный курс")
save(fig, "02_control_set.png")

# 3. example episode
city = sorted([i for i in bench["instances"] if i["topology"] == "city"], key=lambda i: i["reference_cost"])
ex = city[len(city) // 2]
fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))
for ax, (qi, q) in zip(axes, enumerate(ex["queries"])):
    grid = apply_blocks(maps[ex["map"]], q["blocks"])
    r = search("mesha", grid, control, q["start"], q["goal"], mesh, return_path=True)
    title = f"запрос {qi}: стоимость {r.cost:.1f}, раскрытий MeshA* {r.expansions}"
    if qi:
        title += f"\nпрепятствие r={q['edit']['radius']}, рост стоимости +{q['edit']['increase']:.1f}"
    draw_solution(ax, grid, q["blocks"], q["start"], q["goal"], r.trace, r.expanded, title, control)
fig.suptitle(f"Эпизод {ex['id']}: зелёный — агент, синий — цель, красный — план, "
             "оранжевый — новые препятствия, голубой — раскрытые клетки", y=1.04)
save(fig, "03_episode.png")

# 4. edit severity
fig, axes = plt.subplots(1, 2, figsize=(11, 3.5))
lengths = [[i["reference_cost"] for i in bench["instances"] if i["topology"] == t] for t in topos]
incs = [[q["edit"]["increase"] for i in bench["instances"] if i["topology"] == t for q in i["queries"][1:]] for t in topos]
axes[0].boxplot(lengths, tick_labels=[TOPO_RU[t] for t in topos])
axes[0].set_title("Оптимальная стоимость первого запроса")
axes[1].boxplot(incs, tick_labels=[TOPO_RU[t] for t in topos])
axes[1].set_yscale("symlog", linthresh=1)
axes[1].set_title("Рост оптимальной стоимости из-за препятствия")
save(fig, "04_instances.png")

# 5. one-shot w=1 query 0
def paired(metric, base, algos):
    out = {t: defaultdict(list) for t in topos}
    for (i, qi, w), a in by.items():
        if w == 1.0 and qi == 0 and a[base][metric]:
            for n in algos:
                out[inst[i]["topology"]][n].append(a[n][metric] / a[base][metric])
    return out


fig, axes = plt.subplots(1, 3, figsize=(16, 4.2))
specs = [
    ("time_median", "lba", ["lazy_lba", "mesha", "mesh_parall"], "% от времени LBA*", "Время (Python)"),
    ("checked_cells", "lba", ["lazy_lba", "mesha", "mesh_parall"], "% от проверок LBA*", "Проверки клеток на коллизии"),
    ("expansions", "lba", ["mesha", "mesh_parall"], "% от раскрытий LBA*", "Раскрытия вершин"),
]
for ax, (metric, base, algos, ylabel, title) in zip(axes, specs):
    data = paired(metric, base, algos)
    x = np.arange(len(topos))
    width = 0.8 / len(algos)
    for k, n in enumerate(algos):
        st = [iqr(data[t][n]) for t in topos]
        med = np.array([100 * s[0] for s in st])
        lo = med - np.array([100 * s[1] for s in st])
        hi = np.array([100 * s[2] for s in st]) - med
        off = (k - (len(algos) - 1) / 2) * width
        ax.bar(x + off, med, width, color=COLORS[n], label=DISPLAY[n])
        ax.errorbar(x + off, med, yerr=[lo, hi], fmt="none", ecolor="0.25", lw=0.8, capsize=2)
    ax.axhline(100, color="0.4", lw=0.8)
    ax.set_xticks(x, [TOPO_RU[t] for t in topos])
    ax.set_ylabel(ylabel)
    ax.set_title(f"{title}, w = 1, исходный запрос")
    if metric == "expansions":
        ax.set_yscale("log")
    ax.grid(axis="y", alpha=0.3)
    ax.legend(frameon=False, fontsize=8)
save(fig, "05_oneshot.png")

# 6. cell ratio vs length
fig, ax = plt.subplots(figsize=(6.5, 4))
xs, ys1, ys2 = [], [], []
for (i, qi, w), a in by.items():
    if w == 1.0 and qi == 0:
        xs.append(a["lba"]["cost"])
        ys1.append(a["mesha"]["checked_cells"] / a["lba"]["checked_cells"])
        ys2.append(a["mesha"]["checked_cells"] / a["lazy_lba"]["checked_cells"])
ax.scatter(xs, ys1, s=10, color=COLORS["lba"], alpha=0.7, label="MeshA* / LBA*")
ax.scatter(xs, ys2, s=10, color=COLORS["lazy_lba"], alpha=0.7, label="MeshA* / LazyLBA*")
ax.axhline(1, color="0.4", lw=0.8)
ax.set_yscale("log")
ax.set_xlabel("оптимальная стоимость пути")
ax.set_ylabel("отношение числа проверок клеток")
ax.set_title("Экономия проверок у MeshA* падает с длиной пути")
ax.legend(frameon=False)
save(fig, "06_cells_vs_length.png")

# 7. weighted cost + ablation
opt = {(k[0], k[1]): a["lba"]["cost"] for k, a in by.items() if k[2] == 1.0}
lopt = {(r["id"], r["query"]): r["cost"] for r in legacy["records"] if r["algorithm"] == "lba" and r["weight"] == 1.0}
lw = sorted({r["weight"] for r in legacy["records"]})
fig, axes = plt.subplots(1, 3, figsize=(16, 4))
for name in ONE_SHOT:
    ys = [100 * np.median([a[name]["cost"] / opt[(k[0], k[1])] for k, a in by.items() if k[2] == w and a[name]["success"]])
          for w in WEIGHTS]
    axes[0].plot(WEIGHTS, ys, marker="o", color=COLORS[name], label=DISPLAY[name])
    ys = [100 * np.median([a[name]["time_median"] / a["lba"]["time_median"] for k, a in by.items() if k[2] == w])
          for w in WEIGHTS]
    axes[1].plot(WEIGHTS, ys, marker="o", color=COLORS[name], label=DISPLAY[name])
    ys = [100 * np.median([r["cost"] / lopt[(r["id"], r["query"])] for r in legacy["records"]
                           if r["algorithm"] == name and r["weight"] == w and r["success"]]) for w in lw]
    axes[2].plot(lw, ys, marker="o", color=COLORS[name], label=DISPLAY[name])
for ax, title, ylabel in zip(
    axes,
    ("Стоимость, car16", "Время, car16", "Стоимость, упрощённый набор legacy8\n(LBA* = LazyLBA*, MeshA* = Mesh/ParallA*)"),
    ("медиана, % от оптимума", "медиана, % от времени LBA*", "медиана, % от оптимума"),
):
    ax.set_xscale("log")
    ax.set_xticks([1, 2, 5, 10], ["1", "2", "5", "10"])
    ax.set_xticks([1.1], ["1.1"], minor=True)
    ax.tick_params(axis="x", which="minor", labelsize=7, pad=12)
    ax.set_xlabel("вес эвристики w")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(alpha=0.3)
axes[0].legend(frameon=False, fontsize=8)
axes[2].set_ylim(axes[0].get_ylim())
save(fig, "07_weighted.png")

# 8. incremental: per query medians
algos = ["lba", "mesha", "dstar_lattice", "dstar_mesh"]
fig, axes = plt.subplots(1, 3, figsize=(16, 4))
for ax, (metric, title) in zip(axes, (("expansions", "Раскрытия"), ("checked_cells", "Проверки клеток"),
                                      ("time_median", "Время, с"))):
    x = np.arange(3)
    width = 0.2
    for k, n in enumerate(algos):
        med = [np.median([rows[key][n][metric] for key in rows if key[1] == qi]) for qi in range(3)]
        ax.bar(x + (k - 1.5) * width, med, width, color=COLORS[n], label=DISPLAY[n])
    ax.set_xticks(x, ["запрос 0\n(с нуля)", "запрос 1\n(перепланирование)", "запрос 2\n(перепланирование)"])
    ax.set_yscale("log")
    ax.set_title(f"{title}: медиана по запросам")
    ax.grid(axis="y", alpha=0.3)
axes[0].legend(frameon=False, fontsize=8)
save(fig, "08_incremental_queries.png")

# 9. incremental ratio boxplots + by severity
pairs = [("dstar_lattice", "lba"), ("dstar_mesh", "mesha"), ("dstar_mesh", "lba")]
fig, axes = plt.subplots(1, 3, figsize=(16, 4.2))
for ax, (metric, title) in zip(axes, (("expansions", "Раскрытия"), ("checked_cells", "Проверки клеток"),
                                      ("time_median", "Время"))):
    data = [[rows[k][a][metric] / rows[k][b][metric] for k in rows if k[1] > 0 and rows[k][b][metric] > 0]
            for a, b in pairs]
    ax.boxplot(data, tick_labels=[f"{DISPLAY[a]}\n/ {DISPLAY[b]}" for a, b in pairs], showfliers=False)
    ax.axhline(1, color="0.4", lw=0.8)
    ax.set_yscale("log")
    ax.set_title(f"{title}\nинкрементальный / с нуля, запросы 1–2")
    ax.tick_params(axis="x", labelsize=8)
save(fig, "09_incremental_ratios.png")

buckets = [(0, 1, "< 1"), (1, 5, "1–5"), (5, 1e9, "> 5")]
fig, axes = plt.subplots(1, 2, figsize=(11, 3.8))
for ax, metric, title in zip(axes, ("expansions", "checked_cells"), ("Раскрытия", "Проверки клеток")):
    x = np.arange(len(buckets))
    for k, (a, b) in enumerate(pairs[:2]):
        med = []
        for lo, hi, _ in buckets:
            keys = [key for key in rows if key[1] > 0 and lo <= inst[key[0]]["queries"][key[1]]["edit"]["increase"] < hi]
            med.append(np.median([rows[key][a][metric] / max(1, rows[key][b][metric]) for key in keys]))
        ax.bar(x + (k - 0.5) * 0.38, med, 0.38, color=COLORS[a], label=f"{DISPLAY[a]} / {DISPLAY[b]}")
    ax.axhline(1, color="0.4", lw=0.8)
    ax.set_xticks(x, [f"рост {lbl}" for _, _, lbl in buckets])
    ax.set_yscale("log")
    ax.set_title(f"{title} при перепланировании\nв зависимости от силы препятствия")
    ax.legend(frameon=False, fontsize=8)
save(fig, "10_incremental_severity.png")
