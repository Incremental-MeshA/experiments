# Lift-Mesh-MPGAA*

Exact incremental C++17 search on every vertex of the original configuration
mesh: boundary and internal g, h, OPEN, CLOSED and policies. Lift combines
MeshA terminal-closed pruning with a local forward consistency closure after
MPGAA learning. Cascade-Lift adds the previous cell-triggered repair and
queue cascades. The closure is directed pathmax, not a new generic operator.

- Russian report: [report.pdf](../../docs/mesh_lift/report.pdf).
- English manuscript: [paper.pdf](../../docs/mesh_lift/paper.pdf).
- Proof and scope: [design.md](../../docs/mesh_lift/design.md).
- Frozen sources, protocol and inputs: frozen/manifest.json.
- Original first-stage study: ../mesh_vertex, preserved independently.

## Build and correctness

    make -C cpp/mesh_lift all
    make -C cpp/mesh_lift test
    make -C cpp/mesh_lift sanitize
    ASAN_OPTIONS=detect_leaks=1 cpp/mesh_lift/build/test_sanitize cpp/experiments/frozen/car16_model.txt
    python3 cpp/mesh_lift/mutation.py
    python3 cpp/mesh_lift/repair_counterexample.py

Modes: lift_mesh, cascade_lift, lift_cold, cascade_cold, lift_noprune.
Controls: earlier cascade_mesh, mesha, mesha_reuse, lba_reuse, mpgaa,
batch_mpgaa, md_astar, boundary_mesh, conditional_dstar, cmesh_dstar;
grid also octile_reuse. The strong mesha_reuse control uses a standard
suffix certificate and is not a novelty claim.

## Reproduce

    python3 cpp/mesh_lift/run_all.py --output /tmp/lift-fresh
    python3 cpp/mesh_lift/probe.py --directory /tmp/lift-fresh --output /tmp/lift-counts
    python3 cpp/mesh_lift/analyze.py --directory /tmp/lift-fresh --probes /tmp/lift-counts

To validate an existing canonical checkout after building, first run
python3 cpp/mesh_lift/probe.py --build-only to restore the generated
count-only binary, then python3 cpp/mesh_lift/validate.py.

Canonical data are results/full and results/probes; never overwrite them
with a new timing cohort. Canonical report.py, notebook.py and validate.py
read those locations. The count-only binary is generated from copied
headers; all its logical fields are checked against the normal build and
its time columns are discarded. Instrumented all_free_calls counts API
invocations inside replan, not hardware loads or constructor checks.

The second-stage protocol reuses all 232 public first-stage configurations
with fresh joint measurements; no independent holdout or pooled times.
Dynamic visibility n=k; balanced edits are clamped, actual cr reported.
Incomplete episodes are never counted as timing wins. Three repeats are
not independent maps. Results and the manuscript disclose completion,
initial and repair cost, memory, work, path quality and per-map losses.
