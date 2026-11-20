# Closed envelopes on the motion-primitive mesh

The new scientific hypothesis is that an incremental planner should preserve
negative answers as well as optimal paths. The proposed mesh contribution is a
compressed outgoing boundary of a closed state set, with blocked endpoints
represented implicitly. Incremental reachability and graph cuts themselves are
established concepts. A literature search does not establish priority.

## Definitions and invariant

Let V consist of all in-grid primitive-boundary states (cell, heading). Let E_t
contain a primitive iff every original collision cell after its origin is free.
This deliberately includes outgoing arcs of a blocked origin; it is a safe
supergraph of the physically executable graph. The planner checks start and goal
occupancy separately. All positive paths use the original exact costs.

A negative certificate is a set R with s in R, goal outside R, and

    (u in R and (u,v) in E_t) implies v in R.

Any executable path starting in R remains in R by induction, so it cannot reach
the goal. R need not remain exactly reachable, connected, minimal, or free of
blocked origin cells. This is the reason deletions require no region repair.

## Construction

When the exact forward A* exhausts OPEN, its closed boundary states are the
reachable component. A capped search supplies no certificate. Store the component
in a bit vector and scan its outgoing prefix mesh. Prune a subtree if all member
primitive endpoints are already in R, outside the finite grid, or blocked. At the
first blocked prefix cell install a single witness for the entire subtree. No
witness is required for an outside-grid blocker: it can never change. Endpoints
that are blocked are implicit witnesses, described below.

The first failed search pays for both A* and construction of the compressed cut.
This overhead is measured; a one-query episode need not benefit.

## Repair of an update batch

Apply the entire batch to the belief grid before inspecting witnesses. For every
opened witness cell remove its subscription, recheck the full origin-to-node
prefix (blocks may have appeared earlier), then traverse its live subtree. New
blocked prefixes become witnesses. Enabled transitions to outside R add their
endpoints to R and seed a reachability flood. Prefix traversal shares collision
reads among member primitives. Membership is monotone between exact rebuilds.

For every opened cell q, inspect original incoming primitives at each heading of
q. Only tails in R and heads outside R matter. If an incoming primitive is valid,
add its head; otherwise install its first blocked prefix witness. This represents
blocked endpoint witnesses implicitly and avoids explicit records for every
incoming primitive to blocked poses.

Continue the unweighted flood until no valid outgoing transition leaves R. If
the goal enters R, discard the certificate and invoke exact weighted A*. The
flood never produces a positive path or a shortest-path cost. If the current
start is outside R, use exact A* and replace R on failure. Blocks can make R an
overestimate, so reaching the goal in the supergraph may cause a conservative
fallback even when the true start component still cannot reach the goal.

## Completeness of event delivery

Take an arc leaving the final R which has become valid since the last certified
state. If its endpoint was blocked, its opening is processed by the implicit
incoming-primitive join. Otherwise the old cut contains a blocked prefix witness
covering that arc. Every such blocker of a newly valid arc is opened in the
batch, so a witness event traverses the branch or relocates to a remaining block.
Every added endpoint is expanded before accepting the certificate. Hence an
accepted certificate is closed. Duplicate notifications and multiple witnesses
are harmless because membership and active guard keys are sets.

New blocks may leave redundant downstream witnesses. They do not invalidate
closure; a future opening rechecks their full prefix. Redundant records are
released on an exact rebuild. This implementation favors a small proof over
complex decremental garbage collection. Memory and rebuild frequency are
reported.

## Variants and controls

* Envelope-Mesh: negative certificates plus a simple exact mesh boundary A*.
* Dual-Certificate Mesh: add the standard optimal-suffix rule for updates with no
  openings. Removing arcs preserves the optimality of any surviving old optimal
  suffix from the current boundary state. Any opening discards that certificate.
* Cut-Mesh ablation: retain the old closed set on blocks, discard on any opening.
* Lattice-Envelope ablation: identical R and implicit endpoint events, but each
  primitive carries an independent blocked witness. This isolates prefix sharing.
* Mesh cold/reuse: the identical exact A* backend, with no negative certificate.

The new variants search the original boundary graph; prefix mesh nodes are used
for the frontier representation and repair rather than placed in global OPEN.

## Bellman-Circuit Mesh D* Lite

For every materialized boundary origin u, compile its prefix mesh into a local
min-plus circuit. Terminal p has value c(p)+g(head(p)). A blocked mesh node is
infinity; a free node is the minimum of its child/terminal values. The root gives
the exact Bellman rhs(u), with the usual goal override. A g change touches
incoming terminals; a map edit touches mesh nodes at translated offsets.
Propagate toward the root and stop when the minimum does not change. Only an
inconsistent boundary root enters D* Lite's queue. Positive primitive costs and
the standard consistent Euclidean heuristic preserve D* Lite's guarantees.

The implementation stores one double per original prefix node at each relevant
origin. It is intentionally straightforward: no unary-chain contraction, no
online threshold and no coefficient tuning. It may use more memory and do more
local work than conditional lattice D* Lite, which is included as a comparator.
The queue stopping boundary drains all first keys within scaled floating-point
tolerance, as in the repository's corrected D* baseline. Internal mesh edges do
not enter the queue and their cost is never rounded or redistributed.

## Complexity boundaries

Let P be the number of template primitives, R the envelope and W its active
witnesses. Membership storage is O(|V|) bits; the stored member list is O(|R|),
explicit witness storage O(|W|). A batch of o opened cells includes an O(o P)
implicit endpoint join, active witness prefix probes, and one mesh traversal per
newly added state. Common prefix probes are shared in traversal, not in the
implicit incoming join. Blocks require only the usual grid normalization/writes.
The region can grow only |V| times between rebuilds, but an adversary may force a
full rebuild after each batch. Therefore no universal amortized improvement over
D* Lite or repeated A* is claimed. The interesting parameter is the number of
newly exposed frontier states and guards, not the number of all old explored
states.
