# CADly QCAD Refinement Skillset

## 0. Pipeline Context

The input DXF given to the Claude-MCP refinement agent may already have been processed by a rule-based CAD style enhancer.

The rule-based enhancer may add:

* wall outlines
* simple door symbols
* simple window symbols
* basic dimensions

Therefore, Claude-MCP is not the primary CAD-style generator at this stage.

Claude-MCP's main role is:

1. inspect the DXF
2. validate geometry
3. detect obvious problems
4. apply small safe cleanup or repair actions if needed
5. avoid duplicate enhancement elements
6. render the final preview

---

## 1. Do Not Duplicate Enhancement Elements

Before adding anything, inspect existing layers and entities.

If these layers already exist, treat them as evidence that the drawing has already been enhanced:

* WALL
* DOOR
* WINDOW
* DIMENSION

If the drawing already contains DOOR entities, do not add more doors.

If the drawing already contains WINDOW entities, do not add more windows.

If the drawing already contains DIMENSION entities, do not add another full set of dimensions.

If the drawing already contains room labels, do not call add_room_labels.

Do not add title blocks.

Do not add room area labels.

Do not add fixtures unless explicitly requested.

---

## 2. Enhancement Action Usage

The action enhance_cad_style is a broad rule-based enhancement action.

Use enhance_cad_style only when:

* the drawing is still a simple HouseDiffusion-style layout, and
* it only contains room polygons and room labels, and
* it does not already contain CAD-style helper layers such as WALL, DOOR, WINDOW, or DIMENSION.

Do not call enhance_cad_style if the input DXF has already been enhanced.

If the input already has CAD-style elements, prefer:

* empty actions list
* remove_tiny_lines
* normalize_text_size
* clean_cad_layers
* remove_duplicate_elements
* align_walls only when off-axis lines are detected

---

## 3. Repair Philosophy

Preserve the original layout.

Do not redesign the plan.

Do not invent new rooms.

Do not move rooms aggressively.

Do not delete existing room polygons.

Do not change room topology.

Do not normalize meaningful room layers such as:

* living_room
* kitchen
* bedroom
* bathroom

These room layers may be used by the renderer for room coloring.

Only normalize layers when:

* entities are on layer 0
* helper layers are inconsistent
* normalization does not destroy room-type information

---

## 4. Geometry Alignment Caution

Room boundary alignment can be dangerous.

Do not aggressively snap room polygon vertices.

Do not use broad coordinate clustering for room boundaries.

If room boundary correction is needed, it should be handled later by an architectural schema and detailed DXF generator.

For now, prefer preserving room polygons over aggressive geometry correction.

---

## 5. Door and Window Caution

Door and window placement is handled by the rule-based enhancer.

Do not add additional doors or windows during Claude-MCP refinement if DOOR or WINDOW layers already exist.

Do not attempt to infer missing doors or windows unless explicitly requested.

Do not place doors randomly in the middle of rooms.

Do not place windows on interior shared walls.

If existing door or window positions are imperfect but not invalid, preserve them.

---

## 6. Title Block, Area Label, and Fixture Policy

Title blocks are disabled in this pipeline.

Do not call:

* add_title_block

Room area labels are disabled in this pipeline.

Do not call:

* add_room_area_labels

Fixtures are disabled by default.

Do not call:

* add_basic_fixtures

unless the user explicitly requests fixture placement.

The final drawing should focus on:

* room polygons
* wall outlines
* doors
* windows
* basic dimensions
* readable room labels

---

## 7. Safe Cleanup Actions

Use remove_tiny_lines when:

* there are zero-length or nearly zero-length helper lines

Use normalize_text_size when:

* text is too large or too small relative to the drawing

Use clean_cad_layers when:

* helper entities are on layer 0 or inconsistent helper layers

Use remove_duplicate_elements when:

* exact duplicate LINE entities exist

Use align_walls when:

* validation reports off-axis walls
* inspect_dxf reports nearly horizontal or vertical lines that are slightly tilted

Use add_room_labels when:

* room_label_json exists
* labels are missing
* the DXF has fewer text labels than rooms

Use empty actions when:

* the DXF is valid
* CAD-style helper layers already exist
* no obvious geometry problem is found
* additional enhancement would likely create clutter

---

## 8. Required Workflow

Always follow this workflow:

1. inspect_dxf on input_dxf
2. validate_geometry on input_dxf
3. decide whether small repair is necessary
4. apply_refinement_plan

   * use empty actions if no repair is needed
   * use small cleanup or repair actions only if needed
   * avoid duplicate enhancement actions
5. validate_geometry on output_dxf
6. render_preview using output_dxf and output_svg
7. final response should be concise

---

## 9. Final Output Criteria

A successful final drawing should:

* preserve all existing rooms
* preserve room labels
* avoid duplicate labels
* avoid duplicate doors
* avoid duplicate windows
* avoid duplicate dimensions
* have valid geometry
* have a readable SVG preview
* not be overly cluttered
* not destroy room color rendering layers

The goal is not to maximize the number of CAD symbols.

The goal is to produce a stable, readable, CAD-like floorplan preview.