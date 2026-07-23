# Live Preview Loop

## Goal

Changes should appear in Blender as soon as they are safe to apply. The user should be able to watch external agents build or adjust the scene, while still having an obvious way to commit, undo, or revert changes.

## Product Behavior

Live preview should feel like this:

1. User asks for a change.
2. An external agent inspects scene context and chooses safe helper calls where possible.
3. The add-on applies each low-risk helper call immediately.
4. Blender's viewport, timeline, and relevant UI redraw.
5. The sidebar shows a compact pending summary with `Commit` and `Revert`; Blender's normal undo remains available through Blender itself.

This is separate from generated Python. With **Trust Agent Scripts** off, arbitrary scripts are refused without retaining script state. With trust on, they run immediately with Blender **Run Script**-equivalent permissions and use checkpoints/undo for recovery.

## Preview Transactions

A preview transaction groups one or more visible changes:

```text
preview_transaction
  id
  user_request
  started_at
  changed_data_blocks
  before_state
  applied_steps
  status: pending | committed | reverted | failed
```

The transaction manager should capture enough previous state to revert common helper changes. For large or risky changes, it should also save a `.blend` checkpoint.

Commit and revert results include a compact transaction manifest with created datablocks, modified datablocks, rollback scopes, changed datablocks, and applied step count. Revert also returns `rollback_warnings` when a target object, material, collection, socket, or node link could not be restored exactly.

## Immediate Helper Changes

These are good candidates for live preview:

- Object transforms.
- Object visibility, selection, and collection assignment.
- Material creation and assignment.
- Material scalar/color properties.
- Light creation and light settings.
- Camera creation and camera settings.
- Simple modifiers with bounded settings.
- Keyframes on object transforms, light energy/color, camera properties, and material values.

Current implemented helper actions:

- Move selected objects by location delta.
- Set selected object location, rotation, and/or scale.
- Create mesh primitives.
- Create empty helper objects.
- Set object visibility and viewport display settings.
- Assign/create material for selected mesh objects.
- Assign new emission material node setups.
- Create collections and link selected objects to them.
- Add bounded BEVEL, SUBSURF, SOLIDIFY, and ARRAY modifiers.
- Add Track To constraints to selected objects.
- Add light.
- Add camera.
- Set scene timeline range/current frame/FPS.
- Create simple selected-object transform keyframes.
- Create a keyframed camera orbit rig around a target object.
- Apply bounded lighting preset rigs for product, gallery, and dramatic setups.
- Create production material palettes, with optional swatches and assignment to selected mesh objects.
- Create product turntable staging with optional camera orbit and target rotation keys.
- Organize selected or scene objects into production collections without deleting original data-blocks.
- Commit preview.
- Revert preview.

These should not use the live-preview helper path unless a bounded, reversible tool exists:

- Deleting data-blocks.
- Renaming many objects.
- Applying destructive mesh operations.
- Running arbitrary generated Python, which instead requires active binary session trust.
- Importing/exporting files.
- Editing linked library data.
- Adding drivers or modal handlers.
- Broad animation rewrites across many actions.

## Blender Update Loop

All scene mutations should happen on Blender's main thread. After applying a preview step, the add-on should refresh the dependency graph and request UI redraws for relevant areas. The implementation should centralize this in `live_preview.py` so every helper gets consistent behavior.

Expected implementation responsibilities:

- Apply helper changes on the main thread.
- Record rollback state before mutation.
- Push undo/checkpoint state at transaction boundaries.
- Include rollback coverage in tool results so external clients can report what was protected and the sidebar can show a compact summary.
- Update scene/view layer state after mutation.
- Request redraw for 3D View, Timeline, Graph Editor, Dope Sheet, and Properties areas when relevant.
- Report success/failure back through tool results.

## Animation Preview

For animation edits:

- Insert or update keyframes immediately.
- Return changed frame numbers in the tool result for the external client to report.
- Optionally jump to the first changed frame.
- Optionally play a short preview range after commit.
- Keep revert available before the transaction is committed.

## UX Controls

The sidebar exposes only the current preview summary, `Commit`, full `Revert`, and—when the latest isolated asset import supports it—`Last Step`. Execution mode and safety defaults belong in Add-on Preferences; detailed manifests and logs belong in bridge/tool responses.

## Safety Boundary

Live preview does not mean unchecked autonomy. It means safe, typed changes can be applied visibly and reversibly. Generated Python is controlled by the separate binary, runtime-only **Trust Agent Scripts** switch.
