# Exact replanning with two-sided map deferral

Let A be the current observed graph and W the backend's working graph. Initial
maps coincide. Keep B: blocked in A but free in W, and O: free in A but blocked
in W. All primitive costs are fixed and positive. Inputs are cell updates.
No global subgraph ordering between A and W is assumed.

For q in O, the existing mesh compiler supplies L(s,q,t), an admissible lower
bound on any primitive path whose swept collision cells contain q. This matters
because q need not be a primitive-boundary vertex. We reuse the existing MD-A*
compiler and its fast octile/projection correction; the bound itself is not new.
The same traveling lower-bound heap from MD-A* handles moving starts.

## Certificate

Suppose P is a known A-feasible path of cost C, every remaining q in O satisfies
L(s,q,t)>C, and the exact optimum in W is at least C. If an A-path P' cheaper
than C exists, it either uses an omitted opening q (contradicting the bound), or
contains no omitted opening. In the latter case all its cells are free in W:
B only adds free cells to W. Thus P' is a W-path cheaper than C, a contradiction.
Therefore P is optimal in A. A W-optimal candidate which is also A-feasible is a
special case. An infeasible W-optimal candidate need not be repaired when its
cost already meets the cost of a known feasible incumbent.

## Replan

1. Apply observed updates to A. Keep newly blocked/free-in-W cells in B. Queue
   newly opened/blocked-in-W cells in O; opposite updates can cancel without a
   backend change. A previously saved optimal working suffix is reused only if
   it survives actual blocks and no competitive opening has to be released.
2. Compute an exact W-optimal path using the unchanged Batch-Mesh-MPGAA* backend.
3. If a valid incumbent C exists and the working optimum meets C, release any
   still-competitive openings and return the incumbent if none remain.
4. Otherwise validate the optimistic candidate against A. Activate all B cells
   on it as one batch and repair W again if it is invalid.
5. A valid candidate supplies an incumbent C. Release O cells with L<=C and
   repeat; when none remain, return the certified exact path.
6. If W has no path, release all remaining openings. With O empty, A is a
   subgraph of W, so a complete W failure proves an A failure. A cap is never
   treated as a failure proof. Saved positive/negative certificates are cleared
   after a capped incomplete attempt.

Every nonterminal round activates at least one previously deferred cell. Between
input batches, activations move W toward A, so termination is finite; worst-case
work may exceed eager repair. The expansion budget is shared across rounds.
A valid incumbent never meets a newly activated blocking cell, so it stays valid
in both maps through repair. Graph decreases always force a new exact backend
answer before reusing the positive certificate. Saved paths are truncated to the
current start after repair, preventing reuse of earlier prefixes after openings.

The gap-off ablation tests whether avoiding tied invalid candidates matters.
The eager-open ablation applies openings directly (without a pointless heap),
testing the contribution of the mesh lower bound relative to plain lazy blocks.
The one-sided control uses exactly the same backend, isolating two-sided repair
from backend engineering. Tests also verify that a saved certified suffix is
optimal in W, not merely feasible in A, including random start changes and cap
recovery with an unflushed opening.

## Claim boundaries

Generic lazy edge checking, primal/dual bounds, suffix reuse, and the existing
mesh detour bound are prior concepts. The research hypothesis is their coupled
certificate for an incomparably modified working mesh graph. The first stage
informed this design; its replay results are exploratory development data. The
alternate-root navigation check is separate. No claim of priority or universal
speedup should precede the strong-control, ablation and completion results.
