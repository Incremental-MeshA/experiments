# Related work and scope of the novelty claim

Metadata and available abstracts were retrieved from OpenAlex on 2026-11-20;
exact reference titles and authors were checked with Crossref (see
`references_verified.json`).
raw query results are preserved in `literature_search.json`. This is a scoped
search, not a systematic literature review. We inspected the indexed abstracts;
we do not claim to have audited every full text or established priority.

* **MeshA*: Efficient Path Planning with Motion Primitives**, AAAI 2026,
  [DOI 10.1609/aaai.v40i43.41004](https://doi.org/10.1609/aaai.v40i43.41004).
  Shares collision-cell structure among primitives and establishes the mesh
  representation. Our new frontier uses an unmerged prefix forest over exactly
  the same ordered primitive traces. It does not reproduce every quotient/merge
  in the paper's full configuration mesh. Original MeshA* and contracted
  C-Mesh-D* Lite are freshly timed controls.
* **Koenig and Likhachev, D* Lite**, AAAI 2002,
  [AAAI proceedings](https://cdn.aaai.org/AAAI/2002/AAAI02-072.pdf).
  Repairs g/rhs with moving starts. Conditional Bellman updates, reuse of labels,
  and D* Lite's queue are established; Circuit-Mesh is a local compilation and
  event-sharing variant, not a new proof of D* Lite.
* **Koenig, Likhachev and Furcy, Lifelong Planning A***, Artificial Intelligence
  155, 2004, [DOI 10.1016/j.artint.2003.12.001](https://doi.org/10.1016/j.artint.2003.12.001).
  Incremental graph search under edge changes is the established problem setting.
* **Hernández, Asín and Baier, MPGAA*** is represented here by the
  repository's existing directed MPGAA* implementation and its original
  benchmark protocol reference,
  [AAAI 2015 DOI 10.1609/aaai.v29i1.9355](https://doi.org/10.1609/aaai.v29i1.9355).
  Crossref title: *Reusing Previously Found A* Paths for Fast Goal-Directed
  Navigation in Dynamic Terrain*. The new separator experiment is distinct from
  that published benchmark.
* **Mandalika et al., Generalized Lazy Search for Robot Motion Planning:
  Interleaving Search and Edge Evaluation via Event-Based Toggles**, ICAPS 2019,
  [DOI 10.1609/icaps.v29i1.3543](https://doi.org/10.1609/icaps.v29i1.3543).
  Lazy evaluation, event-based search/evaluation choices and reusing invalid-edge
  information are prior work.
* **Lazy Lifelong Planning for Efficient Replanning in Graphs with Expensive Edge
  Evaluation**, IROS 2022,
  [DOI 10.1109/IROS47612.2022.9981389](https://doi.org/10.1109/IROS47612.2022.9981389).
  Lifelong-GLS combines LPA* and GLS. The indexed abstract promises exact optimal
  solutions in dynamic graphs; generic incremental lazy search cannot be claimed
  as the new contribution here.
* **Lazy incremental search for efficient replanning with bounded suboptimality
  guarantees**, IJRR 2024,
  [DOI 10.1177/02783649241227869](https://doi.org/10.1177/02783649241227869).
  Introduces exact L-GLS and Generalized D* for nonstationary queries alongside
  bounded variants. Their published implementations were not integrated into
  this measured cohort. Consequently our results establish no superiority over
  those external implementations, especially for costly high-dimensional
  collision evaluation.
* **Sung and Stone, Motion Planning (In)feasibility Detection using a Prior
  Roadmap via Path and Cut Search**, RSS 2023,
  [DOI 10.15607/RSS.2023.XIX.060](https://doi.org/10.15607/RSS.2023.XIX.060).
  IPC alternates candidate path and cut search; IDPC also decomposes the roadmap.
  Both target inexpensive feasibility detection with few expensive edge checks.
  We inspected the paper's abstract, problem, IPC algorithm and related work
  (`rss2023_notes.md`). Positive/negative certificates and cut reasoning are
  established; our proposed distinction is mesh-specific incremental frontier
  repair under explicit map updates. IPC/IDPC were not ported or timed here.
* **Sturtevant, Benchmarks for Grid-Based Pathfinding**, IEEE TCIAIG 2012,
  [DOI 10.1109/TCIAIG.2012.2197681](https://doi.org/10.1109/TCIAIG.2012.2197681).
  Standard map sources are recorded in the immutable map registry. The new
  separator maps are mechanism experiments, not published benchmark maps.

The defensible proposed contribution is a **mesh-compressed negative frontier**:
a closed superset survives arbitrary edge deletions; prefix witnesses and
implicit blocked endpoints deliver only insertion events capable of exposing
outgoing transitions; a weighted solver is invoked only after the certificate
ceases to prove failure. A closed-set non-reachability proof and incremental
reachability flood are elementary and are not claimed as new. Dual-Mesh adds a
standard positive suffix certificate, so its positive reuse is also not a novelty
claim. The empirical question is whether the compressed frontier is worth its
construction and repair costs relative to a lattice frontier and strong exact
planners on the frozen workloads.
