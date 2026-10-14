# igz_steel grids — layout grids for steel members

**Date:** 2026-10-13
**Status:** Design approved in conversation; spec awaiting review
**Target host:** IngeTrazo 0.5.8 (Extension API version 2), same as igz_steel 1.0.
**Ships as:** igz_steel 1.1.0 (new modules inside the existing package).

## 1. Purpose

A Grid Creator inside igz_steel. The user enters an origin, spacings and names
for the X and Y directions, copies the grid to any number of elevations, and
the viewport draws the grid with drafting-style bubbles and snaps the cursor
to its intersections on every level. Steel members can then be placed and
stretched to grid points at specific elevations. A radial variant covers
curved structures: concentric arcs, radial lines and straight tangent legs.

Primary user: an estimator or detailer laying out columns, beams, pipe racks
and equipment supports from column-line drawings.

Decisions taken in conversation and recorded here:

- Grids are a **reference overlay**, not geometry (like the host's Levels
  example): drawn over every frame, snappable, saved in the document, never
  listed in the Browser or the Bill of Materials.
- Grid lines extend a user-set distance past the outermost grid on each side.
- Spacings are entered as a **list with repeats**: `25', 3@30', 25'`.
- Default names: **letters along X** (lines running in the Y direction),
  **numbers along Y**, following drafting convention; every line can be
  renamed.
- With several levels, only the **active level is drawn in full**; all
  levels are snappable.
- Radial grids: radial lines plus arcs, with **straight tangent legs**.
- A document may hold **several named grids**, each rotatable about its own
  origin **as a unit**, lines and levels together.
- The dialog works in **imperial feet-inches by default with a Metric
  switch**. Storage is metres, like the rest of the extension.
- A drawing-underlay feature (PDF or image aligned to the grid) was
  discussed and **dropped**.

## 2. Scope

### In scope (1.1)

- Rectangular grids: origin, rotation, X and Y spacing lists, names, extend
  distances, bubble placement, levels.
- Radial grids: center, rotation, radii list, angle list, start angle,
  tangent length, extend distances, levels.
- Levels: typed one by one, or "add N levels at spacing S" upward or
  downward; each level has a name and an elevation.
- Live plan preview in the dialog, with dimension strings and bubble
  renaming.
- Viewport overlay, snap provider, selection and delete through the host's
  pickable items, right-click entry, toolbar button and menu entries.
- Undo for every change; persistence in the `.igz` through document data.
- Pure-Python geometry and parsing with pytest coverage; offscreen Qt tests
  for the dialog.

### Out of scope

- Exporting grids to IFC or DXF (an overlay has no geometry to export).
- Snapping to points along grid lines other than intersections and tangent
  ends.
- Grid lines that are not full-length (partial or offset lines). Rename a
  line `A.5` and skip the bay you do not need instead.
- Dimensions or annotations on the drawing; the dimension strings live in
  the dialog preview only.
- Drawing underlays.

## 3. Architecture

### 3.1 New modules

```
igz_steel/
├── _grid.py          # pure Python: parsing, naming, grid geometry, nearest intersection
├── _grid_dialog.py   # Qt: GridDialog, GridPreview widget, RadialDialog, AddLevelsDialog
├── _grid_host.py     # Qt/host: document data IO, overlay painter, snap provider, pickables
└── icons/tb_grid.svg, tb_grid_light.svg
tests/
├── test_grid_parse.py
├── test_grid_names.py
├── test_grid_rect.py
├── test_grid_radial.py
├── test_grid_store.py
└── test_grid_dialog.py
```

`_grid.py` imports nothing from Qt or the host. It works on floats, tuples,
lists and dicts. `_grid_dialog.py` depends on `_grid.py` and PySide6 only.
`_grid_host.py` depends on `_grid.py`, PySide6 and the host's `ExtensionApp`.
`_core.py` gains one toolbar action, one menu entry, one context-menu entry
and the registrations in `setup`; `SteelSession` owns one `GridDialog`
instance like it owns the member dialog.

### 3.2 Units

All lengths in the document block and in `_grid.py` are metres. The dialog
has its own Imperial / Metric switch, independent of the document unit, and
remembers the last choice in `QSettings` under `igz_steel/grid_units`
(default imperial). The switch controls:

- how spacing text, origin fields, extend fields and elevations are parsed;
- how the preview's dimension strings, the level table, the overlay's level
  label and the snap tip format elevations.

Parsing and formatting live in `_grid.py` (`parse_length`, `fmt_length`) so
they are unit tested and do not depend on the host. The member dialog's
existing Imperial / Metric radio is unchanged.

## 4. Data

### 4.1 Document block

Stored with `app.set_document_data(value)` under the extension key; read
with `app.document_data(default)`. One JSON object:

```json
{
  "version": 1,
  "grids": [
    {
      "id": "g1",
      "name": "Main Building",
      "kind": "rect",
      "visible": true,
      "origin": [0.0, 0.0, 30.48],
      "rotation_deg": 0.0,
      "x": {"text": "25', 3@30', 25'",
            "spacings": [7.62, 9.144, 9.144, 9.144, 7.62],
            "names": ["A", "B", "C", "D", "E", "F"], "start": "A"},
      "y": {"text": "4@20'",
            "spacings": [6.096, 6.096, 6.096, 6.096],
            "names": ["1", "2", "3", "4", "5"], "start": "1"},
      "extend": {"x_neg": 1.524, "x_pos": 1.524, "y_neg": 1.524, "y_pos": 1.524},
      "bubbles": "top_left",
      "levels": [{"name": "EL 100'-0\"", "z": 30.48},
                 {"name": "T.O.S. EL 112'-0\"", "z": 34.1376}],
      "active_level": 0
    },
    {
      "id": "g2",
      "name": "Tank Roof",
      "kind": "radial",
      "visible": true,
      "origin": [60.0, 0.0, 30.48],
      "rotation_deg": 0.0,
      "radii": {"text": "10', 2@15'", "spacings": [3.048, 4.572, 4.572],
                "names": ["A", "B", "C"], "start": "A"},
      "angles": {"text": "6@30", "start_deg": 0.0, "steps_deg": [30, 30, 30, 30, 30, 30],
                 "names": ["1", "2", "3", "4", "5", "6", "7"], "start": "1"},
      "tangent": 6.096,
      "extend": {"radial_in": 1.524, "radial_out": 1.524, "arc": 1.524},
      "bubbles": "all",
      "levels": [{"name": "EL 100'-0\"", "z": 30.48}],
      "active_level": 0
    }
  ],
  "active_grid": "g1",
  "units": "imperial"
}
```

Rules:

- `id` is a short unique string assigned on creation (`g` + the lowest
  counter not already used); the user sees `name`.
- `spacings` and `steps_deg` are the parsed numbers; `text` is what the user
  typed, kept verbatim so the dialog reopens with it. When they disagree
  (hand-edited file), the numbers win and the text is regenerated.
- `names` has one entry per line: `len(spacings) + 1` for rectangular
  directions and radii, `len(steps_deg) + 1` for angles. A list of the wrong
  length is regenerated from `start`.
- `origin` is the intersection of the first X line and the first Y line
  (the center, for radial grids) at the first level's elevation.
  `origin[2]` is informational; levels carry the Z used.
- `rotation_deg` turns the whole grid about world Z at the origin,
  counter-clockwise seen from above. Every line, bubble, level and snap
  point of the grid uses the same rotation.
- `levels` is kept sorted by `z`; `active_level` indexes it. Names are free
  text. At least one level always exists.
- `bubbles`: `"top_left"` (bubbles at the +Y end of X-named lines and the
  −X end of Y-named lines, the drafting default) or `"all"` (both ends). For
  radial grids `"top_left"` means bubbles at the outer end of radial lines
  and the start-angle end of arcs.
- The radial `tangent` is the length of the straight leg continuing each arc
  past the first and the last radial line, tangent to the arc. `0` means no
  legs. `extend.arc` lengthens the leg beyond `tangent` when legs exist, or
  extends the arc itself by that arc length when `tangent` is 0.
- `units` is the dialog's last unit choice for this document; the
  `QSettings` value is the default for new documents.

### 4.2 Reading defensively

`_grid_host.load_grids(app) -> list[Grid]` builds `_grid.Grid` objects from
the block. A grid that fails validation (missing keys, non-numeric values,
unknown kind, empty spacings) is skipped and logged once per document
version; the rest load. A block with a `version` above 1 is read as version
1 with unknown keys ignored. The dialog shows what loaded; Apply rewrites
the whole block, so a repaired file is written back on the next change.

## 5. Pure geometry (`_grid.py`)

### 5.1 Parsing

```python
parse_spacing_list(text: str, units: str) -> list[float]       # metres, raises GridError
parse_length(text: str, units: str) -> float                   # metres, raises GridError
fmt_length(metres: float, units: str) -> str                   # 25'-6" or 7.772 m
parse_angle_list(text: str) -> list[float]                     # degrees
```

Accepted item forms, separated by commas or whitespace, with an optional
`N@` repeat prefix:

| units | forms (examples) |
|---|---|
| imperial | `25'`, `25'-6"`, `25' 6"`, `25'6"`, `25'-6 1/2"`, `306"`, `25.5'`, `25` (bare number = feet) |
| metric | `7.62`, `7.62m`, `7620mm`, `762cm`, `7.62 m` (bare number = metres) |
| angles | `30`, `30°`, `6@30`, `22.5` (always degrees) |

Errors: empty list, a zero or negative item, a repeat count below 1, a
total of more than 200 lines or 200 angles, or an unparseable token. The
message names the token: `Cannot read "3@": expected a spacing after @`.

### 5.2 Names

```python
letter_sequence(start: str, count: int) -> list[str]   # A B C … H J K … Z AA BB …
number_sequence(start: str, count: int) -> list[str]   # 1 2 3 … or 5 6 7 …
next_name(name: str) -> str                            # one step in the same scheme
```

- Letters skip `I` and `O`. After `Z` come `AA`, `BB`, `CC` … (doubled
  letters, skipping `II` and `OO`), then `AAA`.
- `start` decides the scheme: a letter string gives letters, a digit string
  gives numbers. `A.1` or `2.5` style names are accepted as a start but the
  sequence continues from their first token (`A.1` → `A`, `B`, `C`…), so
  intermediate names are meant for renaming single lines.
- Renaming: `Grid.rename_line(direction, index, new_name)` replaces one
  entry. When a spacing list changes length, names are regenerated from
  `start` only if the user never renamed a line in that direction (detected
  by comparing the stored names with the generated sequence); otherwise the
  existing names are kept and extended with `next_name` of the last one, or
  truncated.

### 5.3 Grid objects

```python
@dataclass
class Level: name: str; z: float

@dataclass
class RectGrid:
    id, name, visible, origin (x, y, z), rotation_deg
    x_spacings, x_names, y_spacings, y_names, extend (x_neg, x_pos, y_neg, y_pos)
    bubbles, levels, active_level

@dataclass
class RadialGrid:
    id, name, visible, origin, rotation_deg
    radii, radii_names, start_deg, steps_deg, angle_names
    tangent, extend (radial_in, radial_out, arc), bubbles, levels, active_level

Grid = RectGrid | RadialGrid
```

Shared methods, all returning world coordinates in metres:

```python
grid.lines(level_index) -> list[GridLine]
    GridLine: name, points: list[(x, y, z)], bubbles: list[Bubble]
    Bubble: name, at: (x, y, z), toward: (dx, dy)   # unit direction away from the line end
grid.intersections(level_index) -> list[Node]
    Node: names: (str, str), at: (x, y, z)
grid.corner_marks(level_index) -> list[(x, y, z)]   # 4 corners, or arc ends + center
grid.nearest(point, level_index=None) -> (Node, Level, distance) | None
grid.to_dict() / Grid.from_dict(d)
```

Rectangular lines: an X-named line `x_names[i]` runs from
`(xi, −extend.y_neg)` to `(xi, Ytotal + extend.y_pos)` in grid-local
coordinates, where `xi` is the cumulative sum of `x_spacings`; Y-named
lines likewise. Local coordinates are rotated by `rotation_deg` and
translated by `(origin.x, origin.y, level.z)`.

Radial lines: radial line `k` at angle `start_deg + sum(steps_deg[:k])`,
from radius `r0 − extend.radial_in` (not below 0) to
`rN + extend.radial_out`. Arc `j` at radius `rj` from the first to the last
angle, as a polyline with one vertex every 4° (and at every radial line).
When `tangent > 0`, a straight segment of length `tangent + extend.arc`
continues each arc end along the arc's tangent direction; bubbles for arcs
sit at the leg ends. When `tangent == 0`, each arc end is extended along the
arc by arc length `extend.arc`.

Intersections: every X-named line with every Y-named line; every arc with
every radial line; plus, for radial grids with tangent legs, each leg end
is a `Node` named `(arc_name, "T1")` or `(arc_name, "T2")` so the end of a
curved run can be snapped to.

`nearest` is a brute-force search over the given level or all levels; grids
are small (at most 200 × 200 nodes) and the search runs once per hover.

### 5.4 Levels helper

```python
add_levels(levels, count, spacing, direction, pattern, units) -> list[Level]
```

`direction` is `"up"` (from the highest level) or `"down"` (from the
lowest). `pattern` is a format string with `{el}` for the formatted
elevation and `{n}` for the running number, default `"EL {el}"`; the dialog
offers `"EL {el}"`, `"T.O.S. EL {el}"` and `"Level {n}"`. The result is
sorted by `z`; duplicate elevations (within 1 mm) are refused with a
`GridError`.

## 6. Dialog (`_grid_dialog.py`)

### 6.1 GridDialog

Non-modal, one instance parented to `app.window`, opened from the toolbar,
the Steel menu, the right-click menu, or by double-clicking a grid bubble.
Layout as in the approved mockup:

**Top bar.** Grid combo (names of all grids), New rect, New radial…,
Duplicate, Rename, Delete; a Visible checkbox for the current grid; the
Imperial / Metric switch.

**Left column (rect).**

| Control | Behaviour |
|---|---|
| Origin X, Y, Z | `QLineEdit`s parsed with `parse_length`; red border and tooltip on error |
| Pick origin | Activates `PickPointTool` (6.4); the click fills X, Y, Z and the dialog returns to front |
| Rotation | `QDoubleSpinBox` degrees, −360…360, one decimal |
| Pick dir. | Activates `PickDirectionTool` (6.4); two clicks set rotation to the bearing of the second from the first |
| X spacing, start | spacing text; start name (`A`) |
| Y spacing, start | spacing text; start name (`1`) |
| Swap letters and numbers | swaps the two start names and regenerates both name lists (renamed lines are lost after a confirmation) |
| Extend | one length field with "all sides" checked, or four fields X−, X+, Y−, Y+ |
| Bubbles | combo: Top and left / All ends |

**Levels group.** `QTableWidget` with Name and Elevation columns, sorted by
elevation, editable in place; the current row is the active level. Buttons
Add (one level above the top, using the spacing of the last two levels or
12' / 3.6 m), Add levels… (6.3), Remove (refused for the last level).
Editing an elevation re-sorts and keeps the same row active.

**Preview (right).** `GridPreview` (6.2) for the current grid and active
level, with a Fit button and a hint line. A status line beneath counts lines,
intersections and levels.

**Buttons.** Apply (enabled only when every field parses) writes the block
through `set_document_data`, one undo step, and the viewport redraws. Close
hides the dialog; unapplied edits stay in the dialog until Apply or until
the next document change replaces them. When the document changes
underneath (undo, New, Open), the dialog reloads from the document and
discards unapplied edits, after a one-line notice in its status line.

For a radial grid, the left column shows the radial summary (center,
rotation, radii text, angles text, tangent) read-only with an Edit radial…
button, plus the same Levels group and Visible checkbox.

### 6.2 GridPreview

A `QWidget` painting a plan view of one grid at one level with `QPainter`:

- Lines dashed in the extension accent colour; bubbles as circles of 11 px
  radius with the name centered; the origin as a small cross with `x` and
  `y` letters; a faint north arrow in a corner, rotated by the grid
  rotation so the user sees the grid turned against north.
- Dimension strings along the bottom and the right: one tick per line and
  the formatted spacing between ticks (for radial grids: radii along one
  radial line, angle steps along the outer arc).
- Fit on first show and on the Fit button; wheel zooms about the cursor;
  left-drag pans.
- Double-click on a bubble opens an inline `QLineEdit` over it; Enter calls
  `rename_line`, Escape cancels. A name already used in that direction is
  accepted with a warning icon in the status line.
- On a parse error the preview keeps the last good grid and paints a red
  "fix the highlighted field" banner.

The widget is pure Qt over `_grid.py` data and is reused by `RadialDialog`.

### 6.3 Dialogs off the main dialog

**RadialDialog** (modal): center X, Y, Z with Pick; rotation; radii text and
start name; angles text, start angle and start name; tangent length; extend
radial in, radial out, arc; bubbles combo; its own `GridPreview`. OK
validates everything and returns a `RadialGrid`; Cancel discards.

**AddLevelsDialog** (modal): count (1–100), spacing (length field), direction
(Up from the top / Down from the bottom), name pattern combo (editable).
OK appends the levels through `add_levels`.

**Rename / Delete** use `QInputDialog.getText` and `QMessageBox.question`.
Delete confirms always; the message says how many levels the grid has.

### 6.4 Pick tools

Two small `Tool` subclasses in `_grid_dialog.py` (not in `__init__.py`),
activated with `viewport.set_active_tool`, both `uses_snap = True` so grid
points and geometry snap normally:

- `PickPointTool(on_point)`: one click calls `on_point((x, y, z))` and
  restores the previous tool; Escape just restores.
- `PickDirectionTool(on_angle)`: first click fixes the start, the rubber band
  shows the line to the cursor, second click calls `on_angle(bearing_deg)`.
  Bearing is measured in the XY plane from world +X, counter-clockwise.

While a pick tool is active the dialog stays open but lowered; the status
bar says what to click.

## 7. Viewport (`_grid_host.py`)

### 7.1 Overlay

Registered with `app.add_overlay`. Per frame:

1. Return immediately when there are no visible grids or when
   `scene.edit_group` is not `None` (a group is open for editing).
2. For every visible grid: collect the active level's line points, bubble
   centers and corner marks for the other levels into one array; project
   with `app.world_to_pixels` when present, else with
   `viewport._world_to_pixel` per point; drop points behind the camera.
3. Draw lines with `QPen(accent, 1.2, Qt.DashLine)`, clipped with
   `viewport._clip_pixel_line` when present; bubbles as circles of 10 px
   radius with the name in a 9 pt font, filled with the viewport background
   colour so the name stays legible over geometry; the level label
   `"{grid.name} · {level.name}"` beside the origin; other levels' corner
   marks as 6 px crosses in the accent colour at 40 % alpha with the level
   name next to the mark nearest the origin.
4. A selected grid (7.3) draws its lines solid and 2 px wide.

Any exception is caught, logged once per session and the frame continues,
because the host removes an overlay that raises.

### 7.2 Snap provider

Registered with `app.add_snap_provider`. On each call: when there are
visible grids and no group is open, take `snap.point` (the host's current
3D answer), project it, and find the nearest node over all visible grids
and all their levels in pixel distance using the same projection as the
overlay. Accept within `viewport.snap_threshold_px * 1.5` and return
`core.snap.SnapResult(point, "reference", COLOR, label=tip)` where `tip` is
`B-3 · EL 112'-0"` or, with more than one grid in the document,
`Main Building B-3 · EL 112'-0"`. Otherwise return `None` so the host's
own result stands. Tangent ends read `C-T1`. The host already refuses to
let a provider override a named point on real geometry, so member ends
still win when the cursor is on them.

The projection of all nodes is cached per (document version, camera state,
viewport size) and recomputed only when one of them changes, so hovering
does not re-project thousands of points per frame.

### 7.3 Selection and delete

When `app.add_pickable` exists:

- `pick(viewport, px, py)` returns `grid.id` when the pixel is within a
  bubble circle of a visible grid's active level, else `None`.
- `on_select(id)` stores the selected grid id (highlight in 7.1) and flashes
  the grid name in the status bar; `on_select(None)` clears it.
- `delete(id)` removes that grid from the block through
  `set_document_data` after the same confirmation as the dialog's Delete.
- A double-click on a bubble (two picks of the same id within the
  application's double-click interval) opens the dialog on that grid.

Without `add_pickable` the extension loads and works without click
selection; the dialog, toolbar and menus remain the way to reach grids.

### 7.4 Wiring in `_core.py`

- Toolbar: a fifth action "Steel grids…" with `tb_grid` icons.
- Steel menu: "Grids…" after "Bill of Materials…".
- Context menu: "Steel grids…" always; when a grid is selected (7.3), also
  "Edit grid…" and "Delete grid".
- `setup`: `GridStore(app)` created once; overlay, snap provider and
  pickable registered; `on_document_changed` refreshes the dialog and
  invalidates the projection cache.
- Place and Stretch tools are unchanged: they already use the host's snap
  result, so grid points arrive through `ctx.world` with no new code. The
  snap tip names the grid point.

## 8. Undo and document events

Every mutation (Apply, Delete from the dialog or the viewport, level edits
committed by Apply) writes the complete block once with
`set_document_data`, which the host records as one undo step. The dialog
never writes on keystrokes. `on_document_changed` fires after undo, redo,
New and Open; the store reloads, the dialog refreshes its grid list, table
and preview, and the viewport repaints.

## 9. Error handling

- Parse errors: red field border, tooltip and status-line message; Apply
  disabled; preview keeps the last good state.
- Limits: at most 200 lines per direction, 200 angles, 100 levels, 50 grids;
  spacings above 1000 m refused (typo guard, as for member length).
- Duplicate line names within a direction: allowed with a warning icon.
- Duplicate level elevations within 1 mm: refused.
- Malformed document data: bad grids skipped and logged, others load (4.2).
- Host calls that may be absent (`add_pickable`, `world_to_pixels`,
  `_clip_pixel_line`, `snap_threshold_px`, `flash_status`) are wrapped;
  features degrade (no click selection, per-point projection, unclipped
  lines, 12 px default threshold, no flash) and the extension still loads.
- Overlay and snap provider never raise (7.1).
- `QSettings` unavailable or unwritable: the unit switch falls back to
  imperial for the session.

## 10. Testing

Pure Python, pytest, no Qt or host (same stubs as the existing suite):

- `test_grid_parse.py`: every imperial and metric form in 5.1, repeats,
  mixed lists, bare numbers, each error case with its message; `fmt_length`
  round-trips typical values; angle lists.
- `test_grid_names.py`: letters skip I and O, `Z` → `AA`, `HH` → `JJ`,
  `ZZ` → `AAA`; numbers from any start; `next_name`; renamed lines survive a
  spacing change on the same axis and on the other axis; regeneration when
  no line was renamed.
- `test_grid_rect.py`: line endpoints with asymmetric extend values;
  rotation by 90° maps local X to world Y; intersection coordinates and
  names for a 3 × 2 grid; bubble placement for both modes; levels change Z
  only; `nearest` across levels picks the right node and level; `to_dict`
  / `from_dict` round trip.
- `test_grid_radial.py`: radial line endpoints with extend values; arc
  polylines pass through every radial line; tangent legs have the given
  length and are perpendicular to the end radius; intersections and tangent
  nodes; `extend.arc` with and without tangents; round trip.
- `test_grid_store.py`: a block with one bad grid loads the good one and
  logs; version 2 reads as version 1; `add_levels` up and down with each
  pattern; duplicate elevations refused.

Offscreen Qt (`qapp` fixture):

- `test_grid_dialog.py`: the dialog opens with an empty document and shows
  one default level; typing a bad spacing disables Apply and shows the
  error; Apply emits a block equal to the expected dict; the Imperial /
  Metric switch reformats the table; `GridPreview.paintEvent` runs for a
  rect grid and a radial grid without error; `AddLevelsDialog` returns the
  right levels; `RadialDialog` returns a valid `RadialGrid`.

In-app verification with the user: create a rectangular grid from the
mockup values, place a W12X26 column at B-1 by snapping, add three levels
with Add levels…, place a beam at the second level between B-3 and C-3 by
snapping, rotate the grid 30° and confirm lines and snap points turn
together, build a radial grid with tangents and snap to a tangent end, select
a grid by its bubble and delete it, undo through every step back to an empty
document, save and reopen the file and confirm the grids return.

## 11. Packaging

- `__version__` becomes `1.1.0`; `devtools/package.py` and the catalog entry
  follow the release path recorded for 1.0.0 (new GitHub release with
  `igz_steel.zip`, catalog PR changing version, download URL and sha256).
- README gains a "Grids" section with the spacing syntax table and the
  naming rules.
- No new third-party dependencies; `THIRD-PARTY.md` unchanged.

## 12. Open items deferred to the implementation plan

- The exact `QSettings` organisation and application names to use so the
  unit choice persists across IngeTrazo sessions (read what the host uses,
  else `("igz_steel", "igz_steel")`).
- Whether `viewport.camera` exposes a cheap change counter for the
  projection cache; otherwise hash `(yaw, pitch, distance, target,
  perspective, width, height)`.
- The double-click detection for pickables (7.3) depends on how often the
  host calls `pick`; if it only calls on click, use the two-pick timing, else
  fall back to the context-menu entry "Edit grid…".
