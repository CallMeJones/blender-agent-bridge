# Reference Brief

Create the brief from visible evidence, not from a subject label.

## Fields

- `subject`: Neutral identifier for the depicted object or figure.
- `silhouette`: Primary outline, negative spaces, stance, contact points, and dominant view.
- `primary_masses`: Largest volumes that determine the read.
- `secondary_forms`: Supporting volumes, transitions, cutouts, attachments, and overlaps.
- `landmarks`: High-salience edges, features, joints, controls, seams, or alignment points.
- `proportion_checks`: Measurable ratios, spacing, alignment, depth ordering, and relative scale.
- `surface_cues`: Only visible material, texture, fiber, gloss, roughness, edge, or finish evidence.
- `negative_constraints`: Specific ways the result must not drift from the reference.
- `source_notes`: Ambiguity, occlusion, crop, perspective, and confidence notes.
- `inspection_views`: Supported diagnostic views needed to test the brief.

The planner requires non-empty `silhouette`, `primary_masses`, and `proportion_checks`. Do not substitute a prose description for these fields.

## Observation Rules

- Express ratios relative to image height, image width, or another visible mass.
- Use only values supplied by the user or measured from the visible image.
- Label each value as supplied, measured, derived, or uncertain.
- Distinguish observation from inference.
- Mark uncertain depth or hidden structure instead of inventing it.
- Describe spatial relationships in a named view.
- Prefer testable statements over aesthetic adjectives.
- Preserve asymmetry when visible.
- Include negative space and contact/support relationships.
- Record perspective distortion when it affects apparent ratios.

Do not fabricate tolerance bands, focal lengths, roughness values, anatomical ratios, or hidden dimensions. Do not add decimal precision beyond the source evidence. If a percentage has an ambiguous baseline or direction, preserve both interpretations as an unresolved constraint until visual comparison or the user disambiguates it.

Do not fill fields from category memory. A subject name does not imply anatomy, parts, topology, materials, or construction method.

## View Selection

Use `front` and `side` as stable defaults for object inspection. Add `rear`, `top`, `underside`, or `front_below` only when relevant. Use `capture_viewport` for a reference-matched three-quarter or custom client-framed view.

Keep the same framing and orientation across repair passes so comparisons remain meaningful.
