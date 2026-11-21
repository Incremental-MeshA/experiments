# Branch and reproducible artifact

The separate branch is research/mesh-vertex-mpgaa. It contains the complete
first-stage full-mesh study under cpp/mesh_vertex and the second-stage Lift
study under cpp/mesh_lift. Earlier repository implementations and results
are preserved. The studies share public configurations but use distinct
fresh timing cohorts; their seconds are not pooled.

The local delivery uses an incremental Git bundle to avoid duplicating the
large immutable base history. It requires commit
**de6c4e93f2ce76500c418fc9fbbdb5026b4c3ff9**. The parent full bundle is
/workspace/introduction-mesh-envelope.bundle; the new bundle is
/workspace/introduction-mesh-vertex-mpgaa.bundle.

To reconstruct from the two bundles:

    git clone --branch research/mesh-envelope /workspace/introduction-mesh-envelope.bundle introduction
    cd introduction
    git fetch /workspace/introduction-mesh-vertex-mpgaa.bundle research/mesh-vertex-mpgaa:research/mesh-vertex-mpgaa
    git switch research/mesh-vertex-mpgaa
    make -C cpp/mesh_lift all
    python3 cpp/mesh_lift/probe.py --build-only
    python3 cpp/mesh_lift/validate.py

The external /workspace/mesh_vertex_delivery_validation.json records the
final commit and bundle SHA256, both study validations, fresh reaggregation
and reproduced measurement-binary hashes. This record is outside the
commit so its final-commit hash does not create a self-reference.
The fresh verification workspace uses its own imported new pack and source
files, shared immutable old Git objects, and raw symlinks individually
checked against committed blob bytes. It does not claim an independent
physical copy of the large base history. A GitHub push or PR is not implied
by this local branch delivery.
