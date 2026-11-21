# MPGAA* on the full configuration mesh

Branch `research/mesh-vertex-mpgaa`, based on `de6c4e9`.

**These planners search actual mesh vertices**, including internal primitive
configurations. OPEN, g, learned h, parents and policy arrows all use `(i,j,c)`.
The car model has the original 412 configurations, including 16 boundary roots.
There is no lattice search hidden inside the new methods. Primitive IDs are
reconstructed only after finding the mesh path. The existing dyadic potential
preserves physical costs while making search arcs positive.

* `mesh_mpgaa`: ordinary MPGAA* on this graph, with an opening-shape scan.
  This shared-core baseline is essential; porting MPGAA* is not a novelty claim.
* `trigger_mesh`: subscribe only to blocked mesh arcs that violate a learned-h
  consistency inequality; an opening touches its active bucket, not every
  geometric predecessor pattern.
* `cascade_mesh`: Trigger plus backward zero-base repair cascades in
  `h + potential` order and forward continuation at the exact minimum OPEN key.
  All internal labels and expansions remain explicit.

Ablations: `cascade_scan` removes the event index; `cascade_heap` removes the
forward contour; `contour_only` removes the backward cascade; `mesh_astar` removes
learning and cached policies. Random tests assert that `contour_only` preserves
the exact extraction trace and physical path of `trigger_mesh`.

The frozen cohort contains 232 configurations: all 52 previous car replay and
96 grid replay inputs, plus 84 closed-loop car missions on six maps and both
roots. Discovery radii are 8/16/32/64; dynamic anchors `(k,cr)` are `(2,5)`,
`(8,10)`, `(32,20)`, with `n=k`. Balanced exchanges are clamped and actual rates
retained. Three fresh serial randomized repeats produce 8,964 timing episodes;
2,988 independent allocation episodes measure requested heap bytes. Existing
replay/specifications are exploratory public inputs, not a hidden holdout.
Eight strong repository controls are freshly remeasured; grid retains Octile.

```sh
make -C cpp/mesh_vertex all test
make -C cpp/mesh_vertex sanitize
ASAN_OPTIONS=detect_leaks=1 cpp/mesh_vertex/build/test_sanitize cpp/experiments/frozen/grid8_model.txt
ASAN_OPTIONS=detect_leaks=1 cpp/mesh_vertex/build/test_sanitize cpp/experiments/frozen/car16_model.txt
python cpp/mesh_vertex/run_all.py --output cpp/mesh_vertex/results/reproduction
```

After the canonical run, `probe.py` builds generated header copies and counts
all `Grid.free` calls on every replay method, without using instrumented times.
The historical `checked_cells` field has different coverage in old controls;
it must not be called a complete common collision count. Native checks include
all these calls; the count-only pass verifies equality independently.

```sh
python cpp/mesh_vertex/probe.py
python cpp/mesh_vertex/analyze.py
python cpp/mesh_vertex/report.py
/workspace/md_tools_venv/bin/python cpp/mesh_vertex/notebook.py
python cpp/mesh_vertex/validate.py
```

Source/fixture hashes, commands, binaries, logical allocation matching, exact
cost checks, caps, completion failures and per-map metrics are retained.
`mv_records` and `mv_active_watches` are snapshots, not additive work; use their
per-case maxima. `mv_trace_hash` is an audit fingerprint. Fields `mv_*` are
instrumented only in the new native engine; zeros in old controls mean unavailable.
Expansion units differ
between primitive-lattice controls and full-mesh searches; their counts are
shown with that distinction. No earlier timing seconds are pooled.

The proposed contribution is the mesh repair combination. Adaptive A*, MPGAA*,
watched dependencies, potential reweighting and fringe-style search have prior
work; first-in-literature priority is not established. See
[the design](../../docs/mesh_vertex/design.md),
[the measured report](../../docs/mesh_vertex/report.pdf) and
[the manuscript](../../docs/mesh_vertex/paper.pdf).
