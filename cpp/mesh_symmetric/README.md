# SMD-A*: symmetric mesh deferral

This second-stage idea follows a negative first-stage result: envelope certificates
were fast on synthetic repeated failures but showed no useful extra mesh benefit
on the standard replay. SMD-A* targets ordinary positive replanning instead.
It reuses the existing mesh detour lower bound and Batch-Mesh-MPGAA* backend.

The working graph may contain deferred blocked cells and omit deferred openings,
so it is neither globally optimistic nor pessimistic. Two certificates suffice:
(1) a returned path is feasible in the observed actual map; (2) every omitted
opening has a mesh lower bound exceeding its cost. A known feasible incumbent
can also be returned when the working optimum reaches its cost, without validating
other tied optimistic paths. Only blocking cells on a needed optimistic candidate
are activated. All search expansions across repair rounds share the same cap.

* `smd_batch`: both update types deferred, mesh opening certificate and incumbent gap.
* `smd_plain`: the same method without the incumbent-gap shortcut.
* `md_batch`: one-sided MD-A* control with the identical Batch backend.
* `lazy_blocks_batch`: a strong ablation with openings applied eagerly, no mesh
  lower-bound queue, and only blocks deferred; incumbent gap retained.

Symmetric deferral and gap acceptance are the proposed combination, not a claim
to invent lazy graph search, the mesh lower bound, or adaptive A*. Priority must
be checked against Lifelong-GLS/GD* and broader lazy incremental search literature.

```sh
make -C cpp/mesh_symmetric all test
python cpp/mesh_symmetric/run_all.py --output cpp/mesh_symmetric/results/reproduction
python cpp/mesh_symmetric/analyze.py
python cpp/mesh_symmetric/report.py
```

The new protocol is fixed before SMD timings: all52 car and96 grid replay inputs
(exploratory reused inputs), plus36 alternate-root navigation configurations on
all six car maps (all four discovery radii and both n=k dynamic anchors). The
alternate navigation root was not used in the first stage, though the maps/specs
already existed in the repository; this is not a hidden benchmark. Fresh timings
are never pooled with first-stage seconds. Three serial randomized repeats and a
separate allocation pass compare strong controls and the shared-backend ablations.

Measured result: on the balanced 48-case car replay panel, the geometric-mean
whole-episode speedup is 0.44 against the fastest completed control and 0.99
against eager-open lazy blocking. The shared-backend one-sided control is also
faster overall (SMD ratio 0.80, 47 common completed pairs). Deferred activation
reduces delivered edits, but does not establish a useful general mesh-specific
runtime advantage. Per-map results, exactness, caps, memory, alternate-root
navigation and all losses are retained in [the report](../../docs/mesh_symmetric/report.pdf).
The manuscript is a research draft with explicit limitations, not a submission-ready
claim of priority or superiority.
