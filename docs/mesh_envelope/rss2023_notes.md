# Closest cut-search reference inspected

Sung and Stone (RSS 2023), *Motion Planning (In)feasibility Detection using a
Prior Roadmap via Path and Cut Search*, DOI 10.15607/RSS.2023.XIX.060.
Source: https://www.roboticsproceedings.org/rss19/p060.pdf (accessed 2026-11-20).
Inspected abstract, problem statement, IPC pseudocode/description and related work.

IPC alternates candidate path search and minimum-cut search, evaluates the
candidate edges, and updates path weights / cut capacities using probabilities
from a prior roadmap (uniform 0.5 is supported if no prior exists). IDPC further
decomposes the graph. The stated objective is to determine feasibility with few
expensive edge evaluations; a positive query may then be refined by a shortest
path planner. Thus negative answers, cut certificates and combining path and cut
reasoning were already explicit contributions before this artifact.

The distinction proposed here is the incremental **repair representation** for a
fixed directed primitive template: shared-prefix invalid witnesses around a
monotone closed superset, implicit blocked endpoints, explicit occupancy updates,
and fallback to an exact weighted solver. We do not run a probabilistic min-cut
solver and do not claim to invent dual positive/negative feasibility reasoning.
The paper also discusses earlier experience-based disconnection proofs, so this
artifact's limited literature search cannot establish priority for certificate
reuse itself. IPC/IDPC were not ported or timed; a serious submission should
compare against an appropriately adapted external implementation or justify the
different objective carefully.
