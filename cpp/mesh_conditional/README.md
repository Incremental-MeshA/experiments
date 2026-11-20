# Conditional D* Lite control

This is a standard optimized lattice D* Lite control, not a proposed new algorithm.
The original repository baseline conditionally propagates g changes, but maps
occupancy notifications to full backups. This control also gates map-edge events:
newly enabled arcs can only decrease rhs via c+g(head); disabled arcs trigger a
backup only if their value can support rhs. Whole batches invalidate the edge
cache before backups. Identical active queue keys are not pushed again. Primitive
costs, collision traces, Euclidean heuristic, tolerance and expansion budget match
the new boundary algorithms. A blocked source's outgoing arcs may remain in the
auxiliary graph; free-source paths cannot enter a blocked endpoint, preserving
the original physical planning problem.

Fresh joint validation uses all184 replay configurations from the primary study
and structural complement. All three unchanged new algorithms are remeasured in
the same binary alongside the control, three randomized serial repeats plus an
allocation pass. No times are pooled with the earlier seventeen-control binary;
these are repeated input instances, not184 extra independent maps. Navigation is
not rerun in this additional control cohort.

```sh
make -C cpp/mesh_conditional all test
python cpp/mesh_conditional/run_all.py --output cpp/mesh_conditional/results/reproduction
python cpp/mesh_conditional/analyze.py
```

The protocol and all source/input hashes are frozen before these measurements.
The build/tests are queued during the first cohort's un-timed allocation phase;
timing starts only after both preceding cohorts finish.
