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
(same envelope, independent primitive witnesses). The latter isolates the mesh.
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
