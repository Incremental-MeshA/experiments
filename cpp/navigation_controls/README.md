# Stronger grid baselines: separate matched control

This additional cohort measures the standard octile A* baseline with dense stamped arrays and larger-g tie breaking, and its optimal-suffix reuse variant. These are known baseline techniques, not proposed novel algorithms. The original LBA* reuse, MPGAA* and MD-A* are rerun alongside them in the same binary and serial measurement pass.

The native harness is an exact copy of `navigation_sweeps/bench.cpp` except its factory namespace. It uses the same frozen grid8 inputs, environment, sensor, controller, reference, timing boundaries and cap. All ten grid maps are measured at the four already prespecified anchors `(k,cr)=(2,5),(8,10),(32,20),(64,30)`, with `n=k`, two roots and three timing repeats. There are 80 configurations, 1,200 timed episodes and 400 separate allocation episodes. This is additional to the primary 15-method study. Compare clocks only within this cohort.

The octile baseline is grid8-specific: one heading, eight unit displacements, costs 1 and sqrt(2), destination-cell diagonal collision validity. The constructor validates these assumptions; dense arrays are included in constructor time and requested heap. The heuristic uses the actual primitive costs and a downward rounding factor. Positive-cost A* reconstructs the original primitive path, uses the shared collision counters and retains the same per-query expansion cap. The reuse option invalidates its cached suffix on intersecting blocks and requires no openings before certifying it, matching the original LBA* reuse semantics. It does not retain a shortest-path search tree.

The deterministic test compares 1,152 answers of both new baselines with the original lattice A*, on 48 random maps with moving starts, mixed increases/decreases and unreachable cases. A separate test checks the expansion cap. The same suite runs with ASan/UBSan and allocation tracking. Every benchmark call also receives the original independent fresh LBA* reference outside its timer.

```bash
make -C cpp/navigation_controls -j2 all test
make -C cpp/navigation_controls sanitize
python cpp/navigation_controls/run_all.py
python cpp/navigation_controls/analyze.py
python cpp/navigation_controls/validate_artifact.py --smoke
```

`run_all.py` freezes its sources, checks the primary frozen manifest, records binary/compiler/output hashes and resumes only complete verified jobs. Do not edit measured sources and reuse the same output directory. `analyze.py` checks all exact costs, repeated decisions, allocation parity and exact fingerprints of the three old methods against the primary cohort. Analysis retains failed episodes, phase-free successes and missing comparisons. Online ratios require both goals, actual phases and nonzero repair times. The report chapter and map atlas incorporate the resulting section and figure with explicit provenance. `navigation_sweeps/finish.py` runs this cohort after the primary native jobs, then generates and audits both.

The additional control does not remove the study's limitations: two roots, policy-dependent worlds due to current-cell protection, `n=k`, and implementation-specific runtime. Strong grid results cannot be extrapolated to car16. No universal novelty or state-of-the-art claim follows from this experiment.
