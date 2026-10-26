## Conclusions

Measured on 187 instances (561 queries) on four maps. The environment is printed at the top of the notebook. All
numbers are medians of per-query ratios unless stated.

**Correctness.** LBA*, LazyLBA* and MeshA* agree on the optimal cost of every query. All 1,122 incremental
replans (2 planners × 561 queries) match the from-scratch optimum. No run hit the expansion cap.

**One-shot planning (paper setting, `w = 1`, first query).**

* *Collision checks.* MeshA* reads 70% as many cells as our LBA*. The saving is largest on short paths (42% below
  cost 40) and shrinks on long ones (74% above cost 80). Against a textbook LBA* that checks every primitive
  before looking at g-values, MeshA* reads about 28% as many cells, which is closer to the paper's claim. In both
  cases MeshA* reads about 2× more cells than LazyLBA*. That is the opposite of the paper's Fig. 5. LazyLBA*
  checks only the primitives it pops, and in this control set most generated primitives are never popped.
* *Runtime (Python).* MeshA* takes 2.5× the time of LBA* (2.1× on rooms, 2.7× on the maze) and expands about
  5× more nodes, since every cell of a primitive is a queue entry. The paper's 60-80% of LBA* runtime is not
  reproduced here. In Python, per-node interpreter overhead outweighs the cheap grid reads this saves. The
  comparison that carries over to a compiled implementation is the collision-check count.
* *Mesh/ParallA*.* Median cost is 100.6% of optimal on the first query (100.8% over all 561 queries; paper:
  100.3-100.7%), optimal in 168 of 561 queries. It is faster than MeshA* (1.7× LBA* time instead of 2.5×), as in
  the paper.
* *LazyLBA*.* It is slower than LBA* (1.6× at `w = 1`), as the paper also finds. Grid reads are cheap, so
  checking fewer of them doesn't pay for the extra queue traffic.

**Weighted search.** With the car-like control set, weighted MeshA* is *more* suboptimal than LBA* (at w = 2 / 5
/ 10: 106.0 / 110.7 / 114.0% of optimal, against LBA*'s 104.1 / 108.9 / 112.0%). This is the paper's Table 1
trend. With the 8-heading legacy8 control set (on its own 32 instances), MeshA* stays at a median of 100% for
every weight, so that effect comes from the degenerate control set and not from the algorithm.

**Incremental replanning (queries 1-2, `w = 1`).**

* D* Lite on the lattice expands 0.36× as many states as LBA* from scratch and reads 0.82× as many cells, but
  takes 2.6× as long in Python.
* D* Lite on the mesh graph (incremental MeshA*) expands about as many nodes as MeshA* from scratch but reads
  only 13% as many cells. That is 5.5% of the cells LBA* reads. Its wall time is 3.9× MeshA*'s.
* The advantage fades as obstacles get more disruptive. Where an obstacle raises the optimal cost by more than 5,
  D* Lite on the mesh expands 3.8× more than MeshA* from scratch. Each replan here starts several primitives
  further along the path, and D* Lite has to repair a large part of its backward search tree.
* Summed over a whole episode, every incremental planner is slower in wall time than its from-scratch
  counterpart in this implementation.

**What this means.** Mesh-graph D* Lite cuts collision checking by more than an order of magnitude on replans.
That is the cost MeshA* is designed to save, and it is the expensive part when checks involve a real robot
footprint or a costly map query. With cheap grid reads in Python, bookkeeping dominates and both A* and D* Lite
lose in wall time. Two next steps would settle the runtime question: a compiled implementation, and the
paper's maps (not reachable from the machine that ran this; see the README).

**Limits.** The 561 queries fall well short of the paper's >25,000, and the maps are substitutes. The primitives
are Hermite curves, not the paper's optimised car primitives. Times are Python, measured with 3 workers on
4 cores.
