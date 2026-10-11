# Character topology

Inspect intended motion, existing rig, shape keys, pose and expression needs before selecting an approach. Cleanup and a regular quad remesh can produce a useful static reference or starting cage; they do not establish deformation quality.

Keep the original rigged mesh and morphs. Working-copy cleanup captures the evaluated current pose without transferring the rig or shape keys. Never report a static remesh as preserving animation data. Transfer/rebind work must be explicitly part of the user's scope.

## Shape and loop planning

Use the observed anatomy and intended movement. Record critical silhouette regions, articulations, facial openings, contacts and asymmetry. Preserve intentional eyes, teeth, mouth interiors, clothing and accessories; do not discard small islands just because they have few faces.

Plan continuous loops and enough supporting rows at joints that bend. Review poles and abrupt density transitions outside high-strain areas. For facial work, treat lips, eyelids and expression paths as separate requirements rather than accepting a high overall quad percentage. Do not weld fingers, lips, eyelids or nearby garment layers indiscriminately.

Use localized surface fitting with masks or corresponding source parts. Blind nearest-surface projection can jump between fingers or close a mouth. If automatic output cannot meet the needed flow, use deliberate loop construction or preserve that source region and report the remaining work.

Mechanical accessories can follow the hard-surface workflow; their quad count says nothing about the body's deformation readiness.

## Deformation evidence

Before calling a character ready for the requested animation, verify actual rig/weight binding and any required expression shapes. Compare against the original or agreed silhouette in neutral pose and relevant bends/twists, including joints at their intended extremes. Check pinching, volume collapse, self-intersection, sliding attachments and facial closure. Capture front/side and close views where failure would be visible.

The bridge's retopology evaluation always reports `animation_ready=false`. A distance pass, regular wireframe or successfully exported GLB must not override that limit. If rigging or deformation work is outside scope, deliver a static topology candidate and state what remains unvalidated.

Rebake only after important shape and loop changes are settled. Inspect close layers for cross-projection and preserve visible texture seams. Do not claim a repaired texture map proves correct deformation.
