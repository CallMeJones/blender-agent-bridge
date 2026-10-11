# Pump reconstruction study

The real Tripo pump exposed two different requirements: preserve a detailed generated appearance, and obtain geometry that reads like deliberate human modelling. A larger decimation budget helped the first requirement without solving the second.

| Candidate | Geometry | Observed result |
| --- | --- | --- |
| Original | 92,512 triangles | Dense arbitrary triangulation |
| 10k reduction | About 10,000 triangles | Lost important small features and texture clarity |
| 40k reduction with 2K rebake | 40,000 triangles | Better detail retention; still an automatically reduced surface |
| Authored reconstruction | 8,468 triangle equivalents; 3,634 of 3,880 faces are quads | 110 editable mechanical parts with deliberate strips and sparse panels |

The reconstruction used measured profiles for casings, rings for flanges, strips for handles/hoses and sparse beams for the base. It is an approximation: the shape and surface texture differ from the generated source. Component caps and simplified forms also caused the global sampled surface comparison to fail. Closed overlapping components are not a fused fabrication solid.

Raw-source baking onto the reconstruction completed but achieved only 57.18% projection coverage and showed black gaps. It was rejected. The accepted candidate retained clean procedural PBR material cues, not a successful transfer of the original texture. A higher quad percentage must not hide these limitations.

## Executable example

[../scripts/pump_study.py](../scripts/pump_study.py) packages the authored geometry as a portable example. It creates a new collection and a separate assembled review mesh, preserves existing objects, and refuses a second build with the same collection name before mutation. It has no cloud calls, automatic save or implicit export.

Run in an isolated Blender process from the repository root:

```text
blender --background --factory-startup --python-exit-code 1 --python skills/blender-retopology/scripts/pump_study.py
```

For live use, first inspect the current scene and trust state; execute a reviewed, reference-derived script through the bridge. Do not copy this pump recipe into an unrelated subject or invoke it as a general retopology operation. The fixed dimensions describe this one study. For exports, select either named parts or the assembled mesh, not both.

Headless regression checks cover its sub-10k exported budget, closed component geometry, positive winding, sparse base panels and normalized UVs. Shape likeness, material fidelity and deformation readiness remain separate checks.
