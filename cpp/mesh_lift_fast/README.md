# Simplified Lift on the original mesh

Branch: `perf/lift-zero-cost`; unchanged weighted baseline: commit `49b1df9`.

The production implementation is [algorithms.hpp](algorithms.hpp) with the
standalone [index.hpp](index.hpp). It searches all original mesh configurations
using the original costs, including zero-cost prefix arcs. It needs neither
potentials nor contracted or primitive-level search graphs. Include
`algorithms.hpp`, construct `Index(model)`, then `LiftMPGAA(index, grid, goal,
cap, Options::plain())` or `Options::cascading()`. The index must outlive the
planner, and the Model must outlive both. The goal is fixed for the planner's lifetime.

The benchmark adapters retain the old controls and two distinct comparisons:

| Method | Purpose |
| --- | --- |
| `lift_mesh`, `cascade_lift` | Unchanged weighted baseline |
| `zero_lift`, `zero_cascade` | Only remove potential arithmetic in the original search engine |
| `fast_lift`, `fast_cascade` | Direct index, cached base, focused closure, reusable buffers and explicit depth tie |
| `mesha_reuse`, `batch_mpgaa`, `octile_reuse` | Existing controls; octile is grid-only |
| Other `fast_*` modes | One-component ablations of `fast_cascade` |

Zero-only still uses the old shared index as a topology container. Full fast
uses the independent direct index. Removing a potential changes the secondary
search key, so identical node expansion order is not claimed. The explicit
depth tie has its own ablation.

Build and correctness checks, from the repository root:

```bash
make -C cpp/mesh_lift_fast -j2 all
make -C cpp/mesh_lift_fast test
make -C cpp/mesh_lift_fast sanitize
ASAN_OPTIONS=detect_leaks=1 cpp/mesh_lift_fast/build/test_sanitize cpp/experiments/frozen/grid8_model.txt
ASAN_OPTIONS=detect_leaks=1 cpp/mesh_lift_fast/build/test_sanitize cpp/experiments/frozen/car16_model.txt
```

The committed frozen manifest defines the measured source/input hashes and
the selected 132 unique configurations. The 12 repeated ablation cases are a
separate panel. To repeat measurements without changing the frozen inputs:

```bash
python3 cpp/mesh_lift_fast/run_all.py --output /tmp/lift-fast-rerun
python3 cpp/mesh_lift_fast/run_setup.py --output /tmp/lift-fast-setup-rerun
python3 cpp/mesh_lift_fast/analyze.py --directory /tmp/lift-fast-rerun --setup-directory /tmp/lift-fast-setup-rerun
python3 cpp/mesh_lift_fast/report.py --directory /tmp/lift-fast-rerun
```

Postprocessing needs Python 3 with NumPy, pandas and Matplotlib; PDF export needs
Pandoc, XeLaTeX and Noto Serif / Noto Sans Mono fonts.

Use a fresh output directory. The serial runner preserves failed/incomplete
outputs and resumes only jobs whose output hashes still match. The allocation
binary is a separate pass; its times are never used for performance. Allocation
request counts are measured only inside replay `replan` calls. Peak heap is
requested C++ heap, not RSS. Shared graph setup is excluded equally from planner
clocks and measured separately by `run_setup.py`.

See [design](../../docs/mesh_lift_fast/design.md),
[report](../../docs/mesh_lift_fast/report.md) and
[PDF](../../docs/mesh_lift_fast/report.pdf). This is an implementation audit and
simplification, not a claim of a new literature result.
