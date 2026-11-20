# Closed-loop navigation sweeps

All 15 existing C++ search implementations are used unchanged. This directory adds the environment, sensor, controller, frozen roots and measurement harness for the requested experiments. The main report is [navigation.pdf](../../docs/experiments/navigation.pdf); the per-map atlas is [navigation_by_map.pdf](../../docs/experiments/navigation_by_map.pdf). Both new and prior results are separated by map.

An additional [stronger-grid control](../navigation_controls/README.md) reruns LBA* reuse, MPGAA* and MD-A* alongside octile A* and octile A* reuse on the four prespecified dynamic anchors of all ten grid maps. Its 1,200 timing and 400 allocation episodes are a separate matched cohort; the primary counts below remain unchanged. `finish.py` runs and audits this control before building the reports. It supports `--controls-directory` to select its results directory; by default it uses the same final directory name as the primary results under `navigation_controls/results/`.

## Frozen design

- Static unknown car16: all six previous maps, two previous roots, square sensing radii 8, 16, 32, 64; fixed state goal; at most 512 primitive moves. Initially optimistic, sense before every move.
- Dynamic car16 adaptation: the same six maps and roots, at the four prespecified anchor pairs (2,5), (8,10), (32,20), (64,30); full initial knowledge; at most 384 primitive moves. The full 36-pair sweep belongs to the literal grid8 protocol.
- Dynamic grid8: six full published maps (Berlin, AR0700, arena, room512, random512-10, maze512-16), four existing random50 maps at nominal 10/20/30/40% density; two frozen new roots each; at most 512 moves.
- Every k completed moves, globally change the map; k = 2, 4, 8, 16, 32, 64 and **n = k**. Requested cr = 1, 5, 10, 15, 20, 30 percent of all cells. Round each half to nearest integer, then clamp **equally** to both available pre-phase pools. Protect the current and goal cells. Density is preserved; actual cr is reported. Both pools are selected before any write.
- Grid8 visibility is a Chebyshev n-ball, without occlusion. Car16 visibility is the union of collision footprints of arcs with tails reachable in fewer than n primitive moves on an obstacle-free infinite lattice, clipped to the finite map. Its quarter-turn symmetry is checked geometrically, and the optimized compiler is checked against independent direct BFS for depths 1, 2, 4 and every heading. This is an explicit car adaptation of the grid protocol.
- Common per-phase random cell priorities use deterministic SplitMix64 and rejection-based bounded sampling, independently of algorithm and parameters. Protecting the current cell makes the resulting worlds policy-coupled when trajectories differ. This is not a same-query replay experiment.
- All static cases have 3 timing repeats. Dynamic cases have 1 broad timing repeat, with **prespecified** anchors (k, cr) = (2,5), (8,10), (32,20), (64,30) having 3 repeats. One separate allocation repeat covers the three-repeat subset. The executed selection contains 816 configurations, 17,520 timed runs, 2,640 allocation runs, 15 methods. The full prepared manifest contains 1,200 configurations; the 384 non-anchor dynamic car cases are prepared but are not counted as measured. Two roots are not a broad population sample; repeated timing is not an additional independent navigation task.
- Constructor + all planner calls define episode search time. Online excludes the initial plan and constructor. Sensor, world changes, common preparation, independent LBA* reference and path validation are outside planner timers. The reference can warm caches; all algorithms use the same checking policy. Execution is serial, with deterministic randomized method order per repetition.
- Replan initially and when belief costs change. Otherwise follow a certified cached path suffix. Stop at goal, proven belief no-path, expansion cap (1M per query), or move budget. At belief no-path, additionally solve the true map outside the timer to distinguish a stale-belief dead end. No further exogenous phase occurs without motion.

## Reproduction

Use frozen inputs; do not run `prepare.py` for an ordinary reproduction.

Analysis dependencies are in `requirements.txt`; PDF generation also needs Pandoc, XeLaTeX and the DejaVu/Noto fonts. C++ measurements need a C++17 compiler and Make. The optional `finish.py --wait` waits for the serial native cohort, then generates and audits all reports. Set `NAV_NOTEBOOK_PYTHON` when the notebook dependencies are installed in a separate Python environment.

```bash
make -C cpp/navigation_sweeps -j2 all test
make -C cpp/navigation_sweeps sanitize
python cpp/navigation_sweeps/verify.py --sanitize
python cpp/navigation_sweeps/run_requested.py --output cpp/navigation_sweeps/results/reproduction
python cpp/navigation_sweeps/finish.py --directory cpp/navigation_sweeps/results/reproduction
```

`run_requested.py` validates frozen SHA-256 values and runs all normal jobs before all allocation jobs. A complete job can be reused on the same machine, inputs and source hashes; an interrupted job is never silently overwritten. `frozen/requested.json` selects the executed study from the full prepared manifest. Native `--anchors-only` selects the car adaptation timing slice and every allocation pass; the broad grid8 timing pass includes every k/cr pair. The original `run_all.py` remains as provenance of the full prepared scheduler. The current analysis targets the requested selection.

`prepare.py` documents root selection and freezes sources, suites, contexts, scenario specifications and geometric stencils. It refuses to replace an existing manifest. The empty-model files contain no queries and are used only for geometry preparation. Runtime method-specific world/belief/path hashes and deterministic fingerprints permit audits without including clocks in the decisions.

## Raw files and metrics

Each native job writes four artifacts:

- `*_runs.csv`: every attempted method/repeat episode, including failed attempts. `status` = `goal`, `no_path`, `capped`, `step_limit`. Includes constructor/planner/initial/repair/sensor/reference seconds; moves, plans, phases, clamped phases; requested, delivered global and observed cell edits; observations/probes/newly seen/known cells; remaining belief mismatches; traveled primitive cost and initial true optimum; peak/retained requested heap; exact work counters, including online counters; true/belief hashes and deterministic fingerprint.
- `*_calls.csv`: actual planner calls only. No artificial zero-time follow or goal rows. Includes step/query index, answer/reference/truth costs, phase/k/n/radius/cr, global edits since the previous logged call, observed blocks/opens, sensor probes/known/mismatched cells, work counters, heap and path/world/belief hashes. `truth_cost` is populated only at belief no-path; missing means unreachable there or not queried, disambiguated by `status`.
- `*_traces.csv`: executed primitive transitions, for repeat 0 of prespecified illustrative roots only (static radii 8/64 and dynamic anchors (8,10)/(64,30), first root per map). All methods are traced. This is not an independent timing cohort.
- `.json`: native completion with compiler, flags, run/call/cap counts and wall/preparation times. The outer `experiment.json` stores commands, CPU/platform, binary hashes and all output hashes.

`episode_metrics.csv` takes the median of timing repeats at each case/method and uses the separately measured heap only where available. Missing heap is **not zero**. Full goal comparisons require both methods to reach the fixed goal; dynamic online comparisons additionally require at least one actual phase in both episodes. Pair counts and total coverage accompany every speedup. The nominal cr axes are accompanied by actual cr and clamp flags.

`known_fraction` counts cells whose value has been observed at least once; it is always 1 in the initially known dynamic worlds and does not measure current visibility or freshness. `belief_accuracy = 1 - belief_mismatches / cells` is an offline comparison to the true occupancy, also provided in the episode metrics. The planner is not given this true-map diagnostic. The constructor precedes the first sensor observation, so initial static planning includes the first blocking batch; online timings exclude that initialization.

`aligned_query_cases.csv` and `aligned_query_maps.csv` compare the common part of actual inputs to D* lattice, with equal case/step/start, world and pre/post-belief hashes and update cardinalities. `status=ok` path answers and `status=no_path` certified belief-unreachability answers are separated. Caps are excluded. Internal histories can differ, and this subset control does not replace a same-history replay experiment.

The expansion counter counts popped search states, cell reads count collision probes, notification probes measure update work, and heuristic pops measure internal heuristic search. State representations differ, so raw expansion counts are not identical work units. Requested heap excludes shared immutable models and the common environment; it includes the planner and current returned path. It is neither RSS nor whole-process memory. Dynamic travel divided by the initial static optimum may be below 1 due to openings; it is not a competitive ratio.

`work_by_observed_changes.csv` bins received cell edits (not requested cr) and reports query latency/work per map and method. `prior_by_map.csv` keeps the older 11-method and 15-method timing cohorts separate and includes their completion rates. The old car replay main panels are selected before comparing maps; sensitivity panels remain in the original artifacts.

## Checks and limits

Each uncapped call is compared to fresh C++ LBA* on the same belief; returned trajectories are checked cell by cell. All exact methods require cost equality within 1e-6; Mesh/ParallA* is approximate. Every repeat and allocation pass must preserve decisions and work, including 64-bit hashes read as strings. ASan/UBSan smoke tests exercise all 15 methods in static and dynamic car/grid episodes. Primitive search kernels also retain the independent primitive-Dijkstra checks from the preceding artifact.

The interrupted pre-fix preliminary run is retained in `results/pre_endpoint_guard_fix` with its exact sources, inputs and incomplete raw files, and is excluded from every analysis. Its simulator incorrectly required distinct current and goal **cells**, which can coincide at different car headings. The replacement cohort counts coincident protected cells once. No search kernel changed.

Interpretation is limited by two roots per map, one broad timing pass away from anchors, policy-dependent worlds, capped search, differing visibility geometry, and simultaneous changes of k and n. High global cr destroys map structure and is not equivalent to a few local obstacles. There is no claim of universal superiority or exact replication of a published runtime table.

The complete static timing cohort was imported byte-for-byte from `results/pre_car_full_sweep/raw`, with identical binary/input/source hashes, commands, CPU and serial execution. Its provenance is recorded in `experiment.json`. The partial non-anchor car dynamic sweep is retained there and excluded from analysis. This changes the scope of an optional car adaptation, without dropping any combination of the requested literal grid protocol.

For a fast audit of the published results, use `python cpp/navigation_sweeps/validate_artifact.py --smoke`; no long benchmark rerun is needed. `finish.py` consistently regenerates the analysis, figures, chapter, atlas, notebook and combined report, then audits the chosen directory. Regeneration updates files under `docs/experiments`. Large raw CSVs are committed as lossless gzip files, with canonical uncompressed SHA-256 values retained. The analysis/audit restores missing raw caches automatically. Before resuming a cached native run directly after cloning, run `python cpp/navigation_sweeps/storage.py` if its raw caches are absent. Compressed and uncompressed hashes are independently checked.
