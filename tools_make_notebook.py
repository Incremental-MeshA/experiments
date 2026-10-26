"""Builds incremental_mesha.ipynb from the cell sources below."""

import sys

import nbformat as nbf

CONCLUSIONS = open(sys.argv[1]).read() if len(sys.argv) > 1 else "## Conclusions\n\n_To be written after the run._"

cells = []
md = lambda s: cells.append(nbf.v4.new_markdown_cell(s.strip()))
code = lambda s: cells.append(nbf.v4.new_code_cell(s.strip()))

md(r"""
# Incremental MeshA*

MeshA* (Agranovskiy and Yakovlev, [arXiv:2412.10320](https://arxiv.org/html/2412.10320v2)) plans a minimum-cost
sequence of motion primitives on an occupancy grid. LBA* searches the lattice whose edges are the primitives.
MeshA* searches *extended cells* (a cell plus the bundle of primitives still sweeping through it), so primitives
that share the first cells of their trace are collision-checked once. Intermediate mesh steps cost 0 and the
primitive's length is charged when the bundle reaches its end heading.

This notebook makes the problem **incremental**: after a plan is found an obstacle appears on it, the agent stops
a few cells short, and replans to the same goal; then a second obstacle hits the repaired plan. It compares

* **one-shot planners**, which solve each query from scratch: LBA*, LazyLBA*, MeshA* and Mesh/ParallA*
  (the paper's baselines and variants), and
* **incremental planners**, which keep their search between queries: D* Lite on the lattice and
  D* Lite on the mesh graph (incremental MeshA*).

The maps are **not** the paper's maps (it uses Labyrinth, ht_0_hightown, Moscow_0_512 and one unnamed map;
movingai.com was not reachable from the machine that ran this). The paper does not say what language its planner
is written in.
""")

code(r"""
%matplotlib inline
import json
from collections import defaultdict

import matplotlib.pyplot as plt
import numpy as np

from mesha.benchmark import (BENCH_PATH, DISPLAY, INCREMENTAL, ONE_SHOT, RESULTS_PATH, ROOT, WEIGHTS,
                             apply_blocks, load_benchmark, load_named_maps)
from mesha.mesh import build_mesh
from mesha.primitives import build_control_set
from mesha.search import search
from mesha.viz import COLORS, draw_control_set, draw_map, draw_solution, grouped_bars, use_style

use_style()
benchmark = load_benchmark()
results = json.loads(RESULTS_PATH.read_text())
legacy = json.loads((ROOT / "results" / "legacy8_ablation.json").read_text())
records = results["records"]
maps = load_named_maps(benchmark)
control = build_control_set(benchmark["control_set"]["name"])
mesh = build_mesh(control)
topos = [row["topology"] for row in benchmark["maps"]]
instances = {inst["id"]: inst for inst in benchmark["instances"]}

def q(values, p):
    values = [v for v in values if v is not None and np.isfinite(v)]
    return float(np.percentile(values, p)) if values else float("nan")

def stats(values):
    return (q(values, 50), q(values, 25), q(values, 75))

print(json.dumps(results["meta"], indent=1))
""")

md(r"""
## Maps, control set and instances

Berlin_2_256 and AR0700SR are MovingAI maps with their scenario files; the maze and the rooms are generated.
Pairs are spread evenly over path length, and each pair gets three random start/goal heading draws, as in the paper.
""")

code(r"""
fig, axes = plt.subplots(1, 4, figsize=(12, 3.4))
for ax, row in zip(axes, benchmark["maps"]):
    draw_map(ax, maps[row["file"]], f"{row['topology']}: {row['file']}")
fig.tight_layout(); plt.show()

cs = benchmark["control_set"]
print(f"control set {cs['name']}: {cs['headings']} headings, {cs['primitives']} primitives "
      f"({cs['removed_dominated']} redundant ones removed), turning radius {cs['turning_radius']}, "
      f"{cs['configurations']} mesh configurations")
fig = draw_control_set(control); plt.show()

print(f"\n{'map':<18}{'pairs':>7}{'draws':>7}{'no path':>9}{'edit failed':>13}{'kept':>6}")
for name, log in benchmark["selection"].items():
    print(f"{name:<18}{log['pairs_considered']:>7}{log['heading_draws']:>7}{log['no_solution']:>9}"
          f"{log['edit_failed']:>13}{log['kept']:>6}")
print(f"total instances: {len(benchmark['instances'])}, queries: {3 * len(benchmark['instances'])}")
""")

code(r"""
fig, axes = plt.subplots(1, 2, figsize=(11, 3.3))
lengths = defaultdict(list)
incs = defaultdict(list)
for inst in benchmark["instances"]:
    lengths[inst["topology"]].append(inst["reference_cost"])
    for query in inst["queries"][1:]:
        incs[inst["topology"]].append(query["edit"]["increase"])
axes[0].boxplot([lengths[t] for t in topos], tick_labels=topos)
axes[0].set_title("Optimal cost of the first query")
axes[1].boxplot([incs[t] for t in topos], tick_labels=topos)
axes[1].set_yscale("symlog", linthresh=1)
axes[1].set_title("Cost increase caused by each obstacle")
fig.tight_layout(); plt.show()
allinc = [v for t in topos for v in incs[t]]
print(f"edits: {len(allinc)}, median increase {np.median(allinc):.2f}, "
      f"no change (<0.01): {sum(v < 0.01 for v in allinc)}, >5: {sum(v > 5 for v in allinc)}")
""")

md(r"""
## Correctness

At `w = 1` LBA*, LazyLBA* and MeshA* solve the same optimisation problem and must agree. The runner already
stops if either D* Lite planner disagrees with the from-scratch optimum on any query. Mesh/ParallA* is not
optimal by design (soft-duplicate pruning), so its overhead is reported instead.
""")

code(r"""
by = defaultdict(dict)
for r in records:
    if r["kind"] == "oneshot":
        by[(r["id"], r["query"], r["weight"])][r["algorithm"]] = r
mismatch = 0
for (ident, qi, w), algos in by.items():
    if w != 1.0:
        continue
    costs = [algos[a]["cost"] for a in ("lba", "lazy_lba", "mesha")]
    if None in costs or max(costs) - min(costs) > 1e-6:
        mismatch += 1
print(f"optimal-cost disagreements among LBA*/LazyLBA*/MeshA*: {mismatch}")
assert mismatch == 0
inc_rows = [r for r in records if r["kind"] == "incremental"]
print(f"incremental replans checked against the optimum: {len(inc_rows)} (all matched)")
capped = [r for r in records if r.get("capped")]
print(f"capped runs: {len(capped)}")
over = [by[k]["mesh_parall"]["cost"] / by[k]["lba"]["cost"] for k in by if k[2] == 1.0 and by[k]["lba"]["cost"]]
print(f"Mesh/ParallA* at w=1: median {100*np.median(over):.1f}% of optimal, mean {100*np.mean(over):.1f}%, "
      f"optimal in {sum(o < 1 + 1e-9 for o in over)}/{len(over)} queries")
""")

md(r"""
## One-shot planners on the original query (the paper's setting)

Ratios are per query, against the same query's LBA* (runtime) or LazyLBA* (collision checks, as in the paper's
Fig. 5); bars are medians, whiskers the interquartile range. Times are the median of three runs. The paper reports
MeshA* at 60-80% of LBA* runtime at `w = 1` (C++ or similar compiled code is likely; the paper does not say).
""")

code(r"""
def paired(metric, base, weight=1.0, queries=(0,), algos=ONE_SHOT):
    out = {t: defaultdict(list) for t in topos}
    for (ident, qi, w), a in by.items():
        if w != weight or qi not in queries or a[base]["cost"] is None:
            continue
        b = a[base][metric]
        if not b:
            continue
        for name in algos:
            if a[name]["success"]:
                out[instances[ident]["topology"]][name].append(a[name][metric] / b)
    return out

def bars(ratio, algos, ax, ylabel, title):
    grouped_bars(ax, topos, {n: [tuple(100 * v for v in stats(ratio[t][n])) for t in topos] for n in algos},
                 ylabel, title)
    ax.axhline(100, color="0.5", lw=0.8, zorder=0)

fig, axes = plt.subplots(1, 3, figsize=(15, 3.8))
bars(paired("time_median", "lba"), ["lazy_lba", "mesha", "mesh_parall"], axes[0], "% of LBA* time",
     "Runtime, w = 1, query 0")
bars(paired("checked_cells", "lazy_lba"), ["lba", "mesha", "mesh_parall"], axes[1], "% of LazyLBA* cells",
     "Collision checks, w = 1, query 0")
bars(paired("expansions", "lba"), ["mesha", "mesh_parall"], axes[2], "% of LBA* expansions",
     "Expansions, w = 1, query 0")
axes[1].set_yscale("log")
h, l = axes[0].get_legend_handles_labels()
fig.legend(h, l, loc="upper center", ncol=4, frameon=False, bbox_to_anchor=(0.5, 1.08))
fig.tight_layout(); plt.show()

def overall(ratio, name):
    return 100 * np.median([v for t in topos for v in ratio[t][name]])

tr, cr, er = paired("time_median", "lba"), paired("checked_cells", "lazy_lba"), paired("expansions", "lba")
cl = paired("checked_cells", "lba")
for name in ("lazy_lba", "mesha", "mesh_parall"):
    print(f"{DISPLAY[name]:<15} time {overall(tr, name):6.1f}% of LBA*   cells {overall(cl, name):6.1f}% of LBA*, "
          f"{overall(cr, name):6.1f}% of LazyLBA*")
""")

md(r"""
### How LBA* checks primitives matters

Our LBA* checks a primitive only if its successor is not closed and would improve its g-value. A textbook LBA*
checks every primitive of an expanded state first. Costs and expansions are identical; collision checks are not.
On every fourth instance (query 0, `w = 1`):
""")

code(r"""
sample = benchmark["instances"][::4]
ratio_default, ratio_textbook = [], []
for inst in sample:
    qq = inst["queries"][0]
    g = maps[inst["map"]]
    d = search("lba", g, control, qq["start"], qq["goal"], mesh)
    t = search("lba", g, control, qq["start"], qq["goal"], mesh, lba_check_all=True)
    m = by[(inst["id"], 0, 1.0)]["mesha"]
    ratio_default.append(m["checked_cells"] / d.checked_cells)
    ratio_textbook.append(m["checked_cells"] / t.checked_cells)
print(f"{len(sample)} instances: MeshA* cells = {100*np.median(ratio_default):.0f}% of our LBA*, "
      f"{100*np.median(ratio_textbook):.0f}% of textbook LBA*")
""")

md(r"""
### Runtime against path length

Interpreter overhead per node is larger for MeshA* (one queue node per cell of every primitive). The ratio
below shows whether that changes with problem size.
""")

code(r"""
fig, axes = plt.subplots(1, 2, figsize=(11, 3.6))
for name in ("mesha", "mesh_parall", "lazy_lba"):
    xs, ys = [], []
    for (ident, qi, w), a in by.items():
        if w == 1.0 and qi == 0 and a["lba"]["cost"]:
            xs.append(a["lba"]["cost"]); ys.append(a[name]["time_median"] / a["lba"]["time_median"])
    axes[0].scatter(xs, ys, s=8, alpha=0.6, color=COLORS[name], label=DISPLAY[name])
    xs2 = [a["lba"]["cost"] for (i, qi, w), a in by.items() if w == 1.0 and qi == 0 and a["lba"]["cost"]]
    ys2 = [a[name]["checked_cells"] / max(1, a["lba"]["checked_cells"]) for (i, qi, w), a in by.items()
           if w == 1.0 and qi == 0 and a["lba"]["cost"]]
    axes[1].scatter(xs2, ys2, s=8, alpha=0.6, color=COLORS[name], label=DISPLAY[name])
for ax, t in zip(axes, ("time / LBA* time", "cells / LBA* cells")):
    ax.axhline(1, color="0.5", lw=0.8); ax.set_yscale("log"); ax.set_xlabel("optimal cost"); ax.set_title(t)
axes[0].legend(frameon=False, fontsize=8)
fig.tight_layout(); plt.show()
""")

md(r"""
## Weighted search

Median solution cost as % of optimal (the paper's Table 1) and median runtime as % of LBA* at the same weight
(the paper's Fig. 4), over all three queries.
""")

code(r"""
opt = {(k[0], k[1]): a["lba"]["cost"] for k, a in by.items() if k[2] == 1.0}
print(f"{'cost % of optimal':<18}" + "".join(f"{'w=' + str(w):>9}" for w in WEIGHTS))
for name in ONE_SHOT:
    row = []
    for w in WEIGHTS:
        vals = [a[name]["cost"] / opt[(k[0], k[1])] for k, a in by.items()
                if k[2] == w and a[name]["success"] and opt.get((k[0], k[1]))]
        row.append(100 * np.median(vals))
    print(f"{DISPLAY[name]:<18}" + "".join(f"{v:9.1f}" for v in row))
print()
print(f"{'time % of LBA*':<18}" + "".join(f"{'w=' + str(w):>9}" for w in WEIGHTS))
for name in ONE_SHOT[1:]:
    row = []
    for w in WEIGHTS:
        vals = [a[name]["time_median"] / a["lba"]["time_median"] for k, a in by.items()
                if k[2] == w and a[name]["success"] and a["lba"]["time_median"] > 0]
        row.append(100 * np.median(vals))
    print(f"{DISPLAY[name]:<18}" + "".join(f"{v:9.1f}" for v in row))

fig, axes = plt.subplots(1, 4, figsize=(13, 3.2), sharey=True)
for ax, topo in zip(axes, topos):
    for name in ONE_SHOT:
        ys = []
        for w in WEIGHTS:
            vals = [a[name]["cost"] / opt[(k[0], k[1])] for k, a in by.items()
                    if k[2] == w and a[name]["success"] and instances[k[0]]["topology"] == topo]
            ys.append(100 * np.median(vals))
        ax.plot(WEIGHTS, ys, marker="o", color=COLORS[name], label=DISPLAY[name])
    ax.set_xscale("log"); ax.set_xticks(WEIGHTS, [str(w) for w in WEIGHTS]); ax.set_title(topo)
    ax.grid(axis="y", alpha=0.3); ax.set_xlabel("w")
axes[0].set_ylabel("median cost, % of optimal"); axes[0].legend(frameon=False, fontsize=8)
fig.tight_layout(); plt.show()
""")

md(r"""
### Ablation: the legacy8 control set

Does the gap between weighted MeshA* and LBA* depend on the control set? The same planners with the simplified
8-heading legacy8 set, whose long primitives are all chains of 1-step primitives, on its own 32 instances:
""")

code(r"""
lopt = {(r["id"], r["query"]): r["cost"] for r in legacy["records"] if r["algorithm"] == "lba" and r["weight"] == 1.0}
lw = sorted({r["weight"] for r in legacy["records"]})
print(f"{'legacy8 cost %':<18}" + "".join(f"{'w=' + str(w):>9}" for w in lw))
for name in ONE_SHOT:
    row = []
    for w in lw:
        vals = [r["cost"] / lopt[(r["id"], r["query"])] for r in legacy["records"]
                if r["algorithm"] == name and r["weight"] == w and r["success"]]
        row.append(100 * np.median(vals))
    print(f"{DISPLAY[name]:<18}" + "".join(f"{v:9.1f}" for v in row))
""")

md(r"""
## Incremental replanning

For queries 1 and 2 the one-shot planners start from scratch, while the D* Lite planners repair the search
they already have. Query 0 is a full search for everyone (D* Lite searches backward from the goal, so its first
search is comparable to a backward A*).
""")

code(r"""
rows = defaultdict(dict)
for r in records:
    if r["weight"] == 1.0:
        rows[(r["id"], r["query"])][r["algorithm"]] = r
algos = ["lba", "mesha", "dstar_lattice", "dstar_mesh"]
for metric, label in (("expansions", "expansions"), ("checked_cells", "collision checks"), ("time_median", "time [s]")):
    print(f"median {label}")
    print(f"  {'query':<8}" + "".join(f"{DISPLAY[a]:>20}" for a in algos))
    for qi in (0, 1, 2):
        vals = [np.median([rows[k][a][metric] for k in rows if k[1] == qi]) for a in algos]
        print(f"  {qi:<8}" + "".join(f"{v:20.4g}" for v in vals))
    print()
""")

code(r"""
def ratio_vs(metric, num, den, queries):
    return [rows[k][num][metric] / rows[k][den][metric] for k in rows
            if k[1] in queries and rows[k][den][metric] > 0]

fig, axes = plt.subplots(1, 3, figsize=(15, 3.8))
pairs = [("dstar_lattice", "lba"), ("dstar_mesh", "mesha"), ("dstar_mesh", "lba")]
for ax, metric, title in zip(axes, ("expansions", "checked_cells", "time_median"),
                             ("Expansions", "Collision checks", "Time")):
    data = [ratio_vs(metric, a, b, (1, 2)) for a, b in pairs]
    ax.boxplot(data, tick_labels=[f"{DISPLAY[a]}\n/ {DISPLAY[b]}" for a, b in pairs], showfliers=False)
    ax.axhline(1, color="0.5", lw=0.8); ax.set_yscale("log"); ax.set_title(f"{title}, replans (queries 1-2)")
    ax.tick_params(axis="x", labelsize=8)
fig.tight_layout(); plt.show()
for (a, b) in pairs:
    for metric in ("expansions", "checked_cells", "time_median"):
        v = ratio_vs(metric, a, b, (1, 2))
        print(f"{DISPLAY[a]:>18} / {DISPLAY[b]:<10} {metric:<14} median {np.median(v):7.3f}  "
              f"IQR {np.percentile(v, 25):.3f}-{np.percentile(v, 75):.3f}")
""")

code(r"""
# by edit severity
buckets = [(0, 1, "< 1"), (1, 5, "1-5"), (5, 1e9, "> 5")]
print(f"{'cost increase':<14}{'n':>5}" + "".join(f"{DISPLAY[a] + ' / ' + DISPLAY[b]:>36}" for a, b in pairs[:2]))
for lo, hi, label in buckets:
    keys = [k for k in rows if k[1] > 0 and lo <= instances[k[0]]["queries"][k[1]]["edit"]["increase"] < hi]
    cells = []
    for a, b in pairs[:2]:
        v = [rows[k][a]["time_median"] / rows[k][b]["time_median"] for k in keys]
        cells.append(f"time x{np.median(v):.2f}, exp x{np.median([rows[k][a]['expansions'] / max(1, rows[k][b]['expansions']) for k in keys]):.2f}")
    print(f"{label:<14}{len(keys):>5}" + "".join(f"{c:>36}" for c in cells))

# per-episode totals
print()
tot = defaultdict(lambda: defaultdict(float))
for (ident, qi), a in rows.items():
    for name, r in a.items():
        tot[ident][name] += r["time_median"]
for a, b in (("dstar_lattice", "lba"), ("dstar_mesh", "mesha"), ("dstar_mesh", "lba"), ("mesha", "lba")):
    v = [tot[i][a] / tot[i][b] for i in tot]
    print(f"episode time {DISPLAY[a]:>18} / {DISPLAY[b]:<10} median {np.median(v):.3f}  IQR {np.percentile(v, 25):.3f}-{np.percentile(v, 75):.3f}")
""")

md(r"""
## Example

The median-length city instance: MeshA* on the first query, and the repaired plan after each obstacle.
""")

code(r"""
city = sorted([i for i in benchmark["instances"] if i["topology"] == "city"], key=lambda i: i["reference_cost"])
inst = city[len(city) // 2]
fig, axes = plt.subplots(1, 3, figsize=(14, 4.4))
for ax, (qi, query) in zip(axes, enumerate(inst["queries"])):
    grid = apply_blocks(maps[inst["map"]], query["blocks"])
    res = search("mesha", grid, control, query["start"], query["goal"], mesh, return_path=True)
    draw_solution(ax, grid, query["blocks"], query["start"], query["goal"], res.trace, res.expanded,
                  f"{inst['id']} query {qi}: cost {res.cost:.1f}, {res.expansions} expansions", control)
fig.tight_layout(); plt.show()
""")

md(CONCLUSIONS)

nb = nbf.v4.new_notebook()
nb["cells"] = cells
nb["metadata"]["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
nbf.write(nb, "incremental_mesha.ipynb")
print("written", len(cells), "cells")
