# CADly QCAD Refinement Skillset

## 0. Current Pipeline Context

The input DXF given to this Claude-MCP refinement agent may already have been processed by a rule-based CAD style enhancer.

The rule-based enhancer may have already added:
- wall outlines
- simple door symbols
- simple window symbols
- basic exterior dimensions
- optional fixtures

Therefore, the Claude-MCP agent is not the primary CAD-style generator in this stage.

Its main role is:
1. inspect the enhanced DXF
2. validate geometry
3. detect obvious problems
4. apply only small safe repairs if needed
5. avoid duplicate CAD elements
6. render the final preview

---

## 1. Do Not Duplicate Enhancement Elements

Do not add duplicate elements if they already exist.

Before adding anything, inspect the existing layers and entities.

If these layers already exist, treat them as evidence that enhancement has already been applied:

- WALL
- DOOR
- WINDOW
- DIMENSION
- FURNITURE
- SANITARY

If the drawing already contains DOOR entities, do not add more doors unless a clear missing access problem exists.

If the drawing already contains WINDOW entities, do not add more windows unless a clear missing exterior-window issue exists.

If the drawing already contains DIMENSION entities, do not add more basic dimensions.

If the drawing already contains room labels, do not call add_room_labels.

---

## 2. Enhancement Action Usage

The action enhance_cad_style is a broad rule-based enhancement action.

Use enhance_cad_style only when:
- the drawing is still a simple HouseDiffusion-style layout, and
- it only contains room polygons and room labels, and
- it does not already contain CAD-style layers such as DOOR, WINDOW, DIMENSION.

Do not call enhance_cad_style if the input DXF has already been enhanced.

If the input already has CAD-style elements, prefer:
- empty actions list
- align_walls
- normalize_layers only when safe
- add_room_labels only when labels are missing

---

## 3. Repair Philosophy

Preserve the original layout.

Do not redesign the plan.

Do not invent new rooms.

Do not move rooms aggressively.

Do not delete existing room polygons.

Do not change room topology.

Do not normalize meaningful room layers such as:
- living_room
- kitchen
- bedroom
- bathroom

These room layers may be used by the renderer for room coloring.

Only normalize layer names when:
- entities are on layer 0
- helper layers are inconsistent
- normalization does not destroy room-type information

---

## 4. Validation vs Visual Quality

Geometry validation passing means the DXF is technically valid.

It does not always mean the drawing is visually high quality.

However, if a rule-based CAD enhancer has already added CAD-style elements, do not keep adding more elements just for visual richness.

After rule-based enhancement, the Claude-MCP agent should focus on:
- geometry safety
- readable preview
- avoiding duplicate symbols
- avoiding excessive clutter
- ensuring final output exists

---

## 5. Safe Repair Actions

Use align_walls when:
- validation reports off-axis walls
- inspect_dxf reports nearly horizontal/vertical lines that are slightly tilted

Use normalize_layers when:
- entities are on layer 0
- CAD helper entities are on wrong layers
- normalization will not destroy room type layers

Use add_room_labels when:
- room_label_json exists
- the DXF has fewer text labels than rooms
- labels are not already present

Use empty actions when:
- the DXF is valid
- CAD-style layers already exist
- no obvious geometry problem is found
- additional enhancement would likely create clutter

---

## 6. Door and Window Caution

Door and window symbols from the rule-based enhancer may be approximate.

Do not attempt to add many additional doors or windows unless the plan is clearly missing them.

Do not place doors randomly in the middle of rooms.

Do not place windows on interior shared walls.

Do not add duplicate windows to the same exterior wall.

If existing door/window positions are imperfect but not invalid, preserve them.

---

## 7. Dimension Caution

Dimensions are visual drafting aids.

If basic dimensions already exist, do not add another full set.

Avoid expanding the drawing canvas unnecessarily.

Avoid creating huge text labels.

---

## 8. Final Workflow

Always follow this workflow:

1. inspect_dxf on input_dxf
2. validate_geometry on input_dxf
3. decide whether small repair is necessary
4. apply_refinement_plan
   - use empty actions if no repair is needed
   - use small repair actions only if needed
   - avoid duplicate enhancement actions
5. validate_geometry on output_dxf
6. render_preview using output_dxf and output_svg
7. final response should be concise

---

## 9. Final Output Criteria

A successful final drawing should:
- preserve all existing rooms
- preserve room labels
- avoid duplicate labels
- avoid duplicate doors/windows/dimensions
- have valid geometry
- have a readable SVG preview
- not be overly cluttered
- not destroy room color rendering layers

The goal is not to maximize the number of CAD symbols.
The goal is to produce a stable, readable, CAD-like floorplan preview.