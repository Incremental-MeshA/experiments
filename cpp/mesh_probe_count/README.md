# Independent collision-probe count pass

The legacy `checked_cells` counter omits endpoint eligibility reads in the new
certificate. It is not a total collision-query count. This pass instruments every
`Grid.free` call in a generated complete C++ header overlay and resets the counter
only around `Planner::replan`. It does not change any frozen measured source.
The instrumented binary is **never used for timing**. All original logical
fields are compared exactly with the unchanged normal trajectories; all answers
also undergo the native cost/path checks. Direct `Grid.blocked` calls used in
common input normalization and reference/verification calls are outside this
counter's definition. Outside-grid probes count as calls; logical API invocations
are not hardware memory-load counts.

184 replay inputs, five methods (Envelope, Dual, Lattice-Envelope, Circuit,
Conditional D* Lite), one count-only repeat =920 episodes. All original
trace/node counters are retained, but papers must use this full collision-API
pass when claiming total geometry-probe savings. Source overlay and binary are
rebuildable, ignored build artifacts; original/patched hashes and compiler
command are recorded under results/experiment.json.

```sh
python cpp/mesh_probe_count/run.py --build
python cpp/mesh_probe_count/run.py --output cpp/mesh_probe_count/reproduction
python cpp/mesh_probe_count/analyze.py --directory cpp/mesh_probe_count/reproduction
```
