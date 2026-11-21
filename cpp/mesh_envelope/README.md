# Mesh closure certificates and Bellman circuits

New C++17 algorithms, in the independent branch `research/mesh-envelope`:

* `envelope_mesh`: a monotone, closed superset of failed-search reachable states;
  outgoing invalid transitions are covered by shared mesh prefix witnesses.
* `dual_mesh`: the same negative certificate, plus optimal suffix reuse for
  cost increases only. New openings discard the positive certificate.
* `circuit_mesh`: local min-plus Bellman circuits on the prefix mesh, with only
  primitive-boundary states in D* Lite's priority queue.

Ablations: `mesh_cold`, `mesh_reuse` (identical exact search backend),
`cut_mesh` (discard negative envelope on any opening), `lattice_envelope`
(same envelope, independent primitive witnesses). The latter is the mesh-representation
ablation; its endpoint rechecks and short-circuit order also differ, so small
timing differences cannot be attributed solely to prefix sharing.
All original primitive costs, ordered collision cells and headings are retained.
No method uses truth-map occupancy beyond the observation supplied by the harness.

Build and check:

```sh
make -C cpp/mesh_envelope all test
make -C cpp/mesh_envelope sanitize
ASAN_OPTIONS=detect_leaks=1 cpp/mesh_envelope/build/test_sanitize cpp/experiments/frozen/grid8_model.txt
ASAN_OPTIONS=detect_leaks=1 cpp/mesh_envelope/build/test_sanitize cpp/experiments/frozen/car16_model.txt
python cpp/mesh_envelope/run_all.py --output cpp/mesh_envelope/results/reproduction
```

`frozen/manifest.json` fixes every input, measured source, method, seed and repeat.
The primary cohort has 228 configurations: 52 car replay (48 balanced main and
4 history), 96 grid replay, 24 new separator episodes, 24 car map-discovery
missions and 32 dynamic missions on all sixteen maps. Dynamic visibility is n=k;
requested balanced changes are clamped to the available pre-phase populations,
and the actual rate is retained. Measurements use three randomized serial
repeats and a separate allocation pass. Previous measured sources are unchanged.

The initial `frozen/preflight_manifest.json` is retained as an audit artifact;
its preliminary selector omitted grid navigation (its root seeds differ from
car seeds). The selector was corrected before the canonical measurements.
Preflight runs are isolated under `results/preflight`, never pooled with times.

The report evaluates novelty as a research hypothesis. Incremental reachability,
cut certificates, suffix reuse and D* Lite are established concepts; the proposed
contribution is the mesh-specific compressed negative frontier and its repair.

The separately specified structural complement is under `frozen/frontier` and
`results/frontier`: width 1/3/7 separators shifting one column, fixed size64,
two map seeds and both models. These twelve configurations are not pooled with
the primary228. It checks explicit mesh witnesses and conservative rebuilds
which a thick separator can hide. All widths are retained.

Rebuild the reports and notebook after both cohorts finish:

```sh
python cpp/mesh_envelope/analyze.py
python cpp/mesh_envelope/analyze_frontier.py
python cpp/mesh_envelope/report.py
/workspace/md_tools_venv/bin/python cpp/mesh_envelope/notebook.py
python cpp/mesh_envelope/validate.py
```

The measured kernels are frozen in commit `3fb2ce4`; analysis and prose are
maintained independently. Source hashes and binary hashes are checked before
measurement and on validation. Reports expose caps, completion failures,
construction overhead, standard-map losses and the lattice frontier ablation.

An additional strong-control cohort is [Conditional D* Lite](../mesh_conditional/README.md).
It jointly remeasures all three new candidates on the184 replay inputs (not184
new independent cases), with conditional map-edge updates, fresh randomized
order and independent allocation. Its times are kept separate from the primary
cohort. Build/test it with `make -C cpp/mesh_conditional all test` and run
`python cpp/mesh_conditional/run_all.py --output cpp/mesh_conditional/results/reproduction`.
The supplementary analyzers support `--directory`; report.py also accepts
`--frontier-directory` and `--conditional-directory` for newly collected data.

`checked_cells` is the historical explicit trace/node counter and omits endpoint
eligibility gates. [The independent probe pass](../mesh_probe_count/README.md)
counts every `Grid.free` call around replan on the184 replay inputs, validates
old logical fields against unmodified trajectories, and discards instrumented
binary times. All probe claims in the report use this complete collision-API
counter; direct `Grid.blocked` input normalization is outside its definition.

The [second stage, SMD-A*](../mesh_symmetric/README.md), follows the lack of a
useful standard-map envelope benefit. It tests two-sided cell deferral and an
incumbent-gap certificate on an unchanged Batch backend, with one-sided and
eager-open controls. Across all serial cohorts there are 276 unique configurations,
19,326 timing episodes, 6,442 allocation episodes and 920 count-only episodes.
Repeated inputs are never counted as independent new cases or pooled in timing
ratios. The negative overall result and the limited successful regimes are
documented in both reports.
