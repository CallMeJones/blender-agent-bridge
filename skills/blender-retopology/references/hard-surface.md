# Hard-surface decisions

The goal is a small, intelligible mesh whose geometry follows the object's construction. Keep flat regions sparse and spend loops on curvature, bevels, openings and silhouette features.

## Make a measured part plan

Identify parts from the actual source and multiple views, not from disconnected-island counts alone: UV seams can split a single semantic surface. Record each proposed part's source region, axes, extents, attachment points, important features, topology choice and appearance strategy. Maintain uncertainty when hidden surfaces cannot be determined.

Useful choices include:

- Flat housings and base rails: broad faces with loops at deliberate bevels or openings. Planar ngons can be suitable for static caps; inspect exported triangulation.
- Rotational casings, flanges and wheels: profile rings at changes in radius, with radial segments selected by silhouette error and viewing distance.
- Tubes and handles: longitudinal strips along bends, enough cross-section segments to represent the profile, deliberate endpoints and connections.
- Grilles, sockets and cutouts: preserve negative space as geometry. A normal map cannot recreate a hole or detached silhouette.
- Small surface grooves and wear: consider baked shading once larger forms and projection correspondence are established.

Do not assume every hard-surface part needs all quads. Prefer readable loops and controlled shading over a numeric quad target. Treat smooth shading, sharp edges and bevels deliberately; a mesh can have excellent counts and poor highlights.

## Choose reconstruction selectively

First establish primary masses and fit them against the measured source, then openings and attachments, then bevels and detail. Keep separate parts when the real object has separate components. If exact fidelity is required, retain difficult source regions or fit the new surface locally; do not silently replace them with ideal primitives.

Any projection must be restricted to the corresponding source region. Global nearest-surface fitting can pull a thin tube onto an adjacent housing or bridge the two sides of a flange. Inspect contacts and both sides of thin shells after fitting. Discover an appropriate current helper or use a source-scoped trusted script; this skill does not imply that a dedicated semantic fitting helper exists.

Closed parts may overlap at an assembly. That can be acceptable for an editable/render prop, but is not a fused watertight fabrication solid. Do not fill an open cage merely to make a manifold statistic pass.

## Appearance strategy

Decimated geometry close to the original is usually easier to rebake than an idealized reconstruction. New caps, rearranged parts and altered openings can produce missed rays or cross-part projection even with larger cages. Review exterior and visible interior areas separately; label any diagnostic masks, and do not silently exclude visible misses from reported coverage.

Bake from the untouched textured source. When correspondence is inadequate, repair the affected region or explicitly choose authored materials/textures. Avoid repeated global cage increases that contaminate close components.

## Example requests to exercise

- "Make this dense electrical enclosure editable, keeping its mounting holes and silhouette." Expect sparse panels, intentional hole loops and matching highlights.
- "Simplify this flanged pipe without closing its bore." Expect axial/radial loops, open negative space and a bore check after export.
- "Rebuild this curved handle with regular quads." Expect strips along the bend, preserved cross-section and intentional endpoints.

These are distinct trial forms. Do not use the pump dimensions or its triangle budget as defaults for them.
