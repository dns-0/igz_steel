# igz_steel — AISC structural steel members for IngeTrazo

**Date:** 2026-10-13
**Status:** Design approved in conversation; spec awaiting review
**Target host:** IngeTrazo 0.5.8 (Extension API version 2). The plugin API is
unstable during 0.x, so the package pins the tested version in its README and
guards every host call it does not strictly need.

## 1. Purpose

An IngeTrazo extension that inserts structural steel members with the exact
dimensions of the AISC Shapes Database v16.0. The user picks a shape and an
insertion point on its cross-section, places the profile at a clicked point,
and stretches it along any 3D axis into a member, by dragging to a point or by
typing a length in the measurement box. Members remember what they are, so
they can be stretched again, edited, tagged for BIM, assigned to layers, and
listed in a Bill of Materials.

Primary user: an estimator or detailer modelling steel framing, equipment
supports and rigging layouts, who needs dimensional accuracy and fast
placement.

## 2. Scope

### In scope (version 1.0)

- All 13 AISC families: W, M, S, HP, C, MC, L, WT, MT, ST, 2L, HSS
  (rectangular, square, round) and PIPE. 2,299 shapes.
- Imperial and metric labels and dimensions (both columns of the database).
- Rounded web-to-flange fillets built from the AISC `k` dimension.
- Insertion point chosen on the cross-section: centroid, any outline vertex,
  any outline edge midpoint, plus named points (top of steel, bottom of
  steel, left, right).
- Place tool: profile follows the cursor, first click fixes the start, the
  member is previewed to the hovered point with axis inference, second click
  or typed length commits. Escape after the first click commits a zero-length
  profile object.
- Stretch tool: select a member or profile, click near an end to free it,
  drag along the member's axis or type a length.
- Edit: reopen the dialog on a selected member and rebuild it in place.
- Roll angle about the member axis (0/90/180/270 presets, free value).
- Layer assignment from the dialog, including creating a new layer.
- Automatic IFC tag by orientation: IfcColumn, IfcBeam or IfcMember.
- Bill of Materials window with per-member rows, per-shape summary and CSV
  export, in the document's units.
- Browser (outliner) type and tooltip for steel members.
- Toolbar, Extensions submenu and right-click context entries.
- One undo step per creation, stretch or edit.

### Out of scope (version 1.0)

- Flange slopes on S, C, MC, ST, M and MT shapes (flanges use the tabulated
  average thickness `tf`).
- Copes, end cuts, mitres, holes, connections, plates.
- Stretching arbitrary closed faces (the host's Push/Pull does that).
- Curved or multi-segment members.
- Custom IFC property sets (the host's BIM layer stores only class and name).

## 3. Package layout

```
igz_steel/
├── __init__.py        # exposes setup(app) only; no Tool subclass defined here
├── _core.py           # setup(app): toolbar, menus, context menu, outliner kind, commands
├── _db.py             # loads data/aisc_v16.json, search and lookup
├── _profiles.py       # pure Python: cross-section outlines, fillets, insertion points
├── _geometry.py       # pure Python: extrusion to faces, member frame maths
├── _tools.py          # PlaceMemberTool, StretchMemberTool (Qt + host Tool base)
├── _dialog.py         # MemberDialog, SectionPreview widget, LayerCombo
├── _bom.py            # pure Python: BOM rows and summary; _bom_dialog in _dialog.py
├── _units.py          # thin wrapper over core.units (format, parse, profile)
├── data/
│   └── aisc_v16.json  # generated; never edited by hand
├── icons/             # tb_place.svg, tb_stretch.svg, tb_edit.svg, tb_bom.svg (+ _light variants)
├── README.md
├── LICENSE            # GPL-3.0-or-later
└── THIRD-PARTY.md     # IngeTrazo API notice, AISC data notice
tools/
└── build_db.py        # developer script: xlsx -> data/aisc_v16.json (needs openpyxl)
tests/
├── test_db.py
├── test_profiles.py
├── test_geometry.py
└── test_bom.py
```

`__init__.py` must not define any `Tool` subclass, because IngeTrazo
instantiates every `Tool` subclass defined in the entry module with no
arguments. The tools live in `_tools.py` and are activated with
`viewport.set_active_tool(...)`, as igz_solids does.

`_profiles.py`, `_geometry.py`, `_bom.py` and `_db.py` import nothing from Qt
or from IngeTrazo. They work on tuples and dicts so pytest can run them in any
Python. Conversion to `QVector3D`, `Mesh`, `Group` happens in `_core.py` and
`_tools.py`.

## 4. Data

### 4.1 Source

`aisc-shapes-database-v160-2.xlsx`, sheet "Database v16.0", 2,299 data rows
and 166 columns. Columns 0–83 are imperial (inches, lb/ft, in²), columns
84–165 repeat the same headers in metric (mm, kg/m, mm²). Missing values are
the en-dash string "–". Column headers of interest:

| Column | Meaning | Families |
|---|---|---|
| Type | family code | all |
| AISC_Manual_Label | label as printed in the Manual | all |
| EDI_Std_Nomenclature | EDI label | all |
| W | weight per foot (per metre) | all |
| A | area | all |
| d | depth; shorter leg for L; see 2L note | W M S HP C MC L WT MT ST 2L |
| bf | flange width | W M S HP C MC WT MT ST |
| tw | web thickness | W M S HP C MC WT MT ST |
| tf | flange thickness | W M S HP C MC WT MT ST |
| kdes | fillet-to-flange distance (design) | W M S HP C MC L WT MT ST |
| k1 | web centreline to flange fillet toe | W M HP |
| t | leg thickness | L 2L |
| b | longer leg (L, 2L); flat wall (HSS) | L 2L HSS |
| Ht, B | overall HSS depth and width | HSS |
| OD, ID | pipe/round HSS outside and inside diameter | PIPE, round HSS |
| tnom, tdes | HSS/pipe nominal and design wall | HSS PIPE |
| x, y | centroid offsets from the designated edge | C MC L WT MT ST 2L |
| T_F | special-note flag (sloped flanges for M/MT) | all |

### 4.2 Generated JSON (`data/aisc_v16.json`)

```json
{
  "source": "AISC Shapes Database v16.0 (August 2023)",
  "generated": "2026-10-13",
  "shapes": [
    {
      "family": "W",
      "label": "W12X26",
      "label_metric": "W310X38.7",
      "edi": "W12X26",
      "imperial": {"W": 26, "A": 7.65, "d": 12.2, "bf": 6.49, "tw": 0.23,
                   "tf": 0.38, "kdes": 0.68, "k1": 0.75},
      "metric":   {"W": 38.7, "A": 4940, "d": 310, "bf": 165, "tw": 5.84,
                   "tf": 9.65, "kdes": 17.3, "k1": 19.1},
      "notes": ""
    }
  ]
}
```

Rules for the converter (`tools/build_db.py`):

- Keep only the geometric columns listed in 4.1 plus `W` and `A`; drop
  section-property columns (Ix, Zx, …) to keep the file small (target under
  600 KB).
- Convert "–" to absent keys. Store numbers as numbers.
- For 2L, parse the back-to-back gap from the label suffix: `2L6X4X1/2X3/4`
  means gap 3/4 in; no suffix means gap 0. Record `"gap"` in both unit blocks
  and `"llbb"` (long legs back-to-back) or `"sllb"` from the label's "LLBB"
  / "SLBB" tokens; absent means LLBB for unequal legs, irrelevant for equal.
- For HSS, classify `"round"` when `OD` is present, else `"rect"`.
- Fail loudly on a header mismatch so a future v17 workbook is noticed.
- The script is a developer tool; the shipped package contains only the JSON.

### 4.3 `_db.py` API

```python
load() -> Database                   # cached singleton, reads the JSON once
Database.families() -> list[str]     # in AISC order
Database.shapes(family) -> list[Shape]
Database.find(label) -> Shape | None # case-insensitive, imperial or metric label
Database.search(text, family=None) -> list[Shape]   # substring, label order kept
Shape.dims(unit_system) -> dict      # "imperial" or "metric" block, values in inches or mm
Shape.dims_m() -> dict               # imperial block converted to metres (always the
                                     # geometry source so rounding is consistent)
Shape.weight_per_m() -> float        # kg/m from the metric W column
Shape.weight_per_ft() -> float       # lb/ft from the imperial W column
```

Geometry always comes from the imperial block converted to metres, so a
member built from a metric label is identical to the one built from its
imperial twin.

## 5. Cross-section profiles (`_profiles.py`)

### 5.1 Output contract

```python
build_profile(shape: Shape, fillets: bool, segments: int) -> Profile

Profile:
  outer:   list[(u, v)]            # closed loop, counter-clockwise, metres
  inner:   list[list[(u, v)]]      # holes (HSS, PIPE), each clockwise
  points:  list[InsertionPoint]    # see 5.3
  centroid: (u, v)
  area:    float                   # computed, used in tests against AISC A
  arc_edges: set[int]              # indices of outer/inner edges that belong to arcs
```

Coordinates: `u` is horizontal (across the flange), `v` is vertical (along
the web), origin at the centroid. Local "up" is +v. For a W shape the web is
the vertical line u = 0 and the flanges are horizontal.

### 5.2 Builders per family

| Family | Outline | Fillets (when on) |
|---|---|---|
| W, M, S, HP | I: flanges `bf × tf`, web `tw`, depth `d` | 4 fillets, radius `kdes − tf` |
| C, MC | channel, web at left (u = −x offset) | 2 fillets, radius `kdes − tf` |
| L | angle, longer leg `b` vertical and shorter leg `d` horizontal (long-leg-vertical drafting convention; roll 90° gives long-leg-horizontal), thickness `t`, heel at bottom-left | 1 inside fillet, radius `kdes − t`; toe radii ignored |
| 2L | two L outlines mirrored about a vertical back-to-back plane at u = 0, separated by `gap` along u; the back-to-back legs are the long legs for LLBB and the short legs for SLBB | as L |
| WT, MT, ST | tee: flange on top, stem down, depth `d` | 2 fillets, radius `kdes − tf` |
| HSS rect/square | outer `Ht × B` with corner radius `2·tdes` outside, `tdes` inside (AISC convention), wall `tdes` | corner arcs always (they define the shape) |
| HSS round, PIPE | circles `OD` and `OD − 2·tdes` with `segments` points | n/a |

If `kdes − tf` is not positive or `kdes` is absent, the fillet is skipped
for that shape without error. Every arc is four segments except round
sections, which use the dialog's segment count (default 24, minimum 8).

Outer loops are emitted counter-clockwise, holes clockwise, and a unit test
enforces this with the signed area.

### 5.3 Insertion points

```python
InsertionPoint: id: str, label: str, uv: (u, v)
```

The list, in this order:

1. `centroid` — "Centroid".
2. Named points, when meaningful for the family: `top` (top of steel, u = 0),
   `bottom`, `left`, `right` (extreme u at mid-height), `top_left`,
   `top_right`, `bottom_left`, `bottom_right` (bounding-box corners).
3. `v<i>` — every vertex of the outer outline that is not on an arc.
4. `m<i>` — the midpoint of every outer edge that is not on an arc.

Ids are stable across rebuilds because they depend only on the family's
outline construction order, not on fillet settings: vertex and midpoint ids
are assigned from the sharp outline before fillets are inserted, and the
fillet step keeps the mapping. The default selection is `centroid`.

## 6. Members (`_geometry.py`)

### 6.1 Local frame

The member axis is local +X. The profile lies in the local YZ plane:
profile `u` maps to local +Y and profile `v` maps to local +Z. The insertion
point is at the local origin, so the profile is translated by minus the
chosen insertion point before extrusion. The start cap is at x = 0 and the
end cap at x = length.

### 6.2 Extrusion

```python
extrude(profile: Profile, length: float, insertion_uv: (u, v))
    -> MemberMesh(faces: list[Face], soft_edges: set[(int, int)])
Face: list[(x, y, z)] or (outer_loop, [hole_loops])
```

- Start cap: the outer loop reversed (normal −X) with holes; end cap: outer
  loop (normal +X) with holes.
- One quad per outer edge and per hole edge, wound so the normal points
  outward. `core.orient.orient_outward` runs afterwards as a safety net, as
  igz_solids does.
- Soft edges: the longitudinal edges between quads whose profile edge lies
  on an arc (`arc_edges`), so fillets and round walls shade as one surface.
  Cap rims stay crisp.
- `length == 0` produces a profile object: a single face (the outer loop
  with holes) with normal +X and no side quads.

### 6.3 World transform

```python
member_matrix(start: (x,y,z), direction: (x,y,z), roll_deg: float) -> 4x4 row list
```

- Local X aligns with `direction` (unit vector).
- Local Z (profile up) is the projection of world +Z onto the plane
  perpendicular to `direction`. When `direction` is within 1° of vertical,
  world +Y is used instead, so a column's flanges face a predictable way.
- `roll_deg` rotates the profile about local X after that alignment.
- Translation is `start`.

The matrix is handed to `QMatrix4x4` in `_core.py`; `_geometry.py` only
produces 16 floats.

### 6.4 Validity rules

- Minimum length for a member: 1 mm. Anything smaller is a profile object.
- Maximum length: 1000 m (guards typos in the measurement box).
- A member whose group has been exploded (no `xform`) or edited into a
  different structure is refused by Stretch and Edit with a message, as the
  stair maker does.

## 7. Group representation

Every member or profile is one `Group` with:

- `mesh`: the local-coordinate mesh from 6.2. Because `xform` is set the
  group is a placed instance; `component = False` is set, as the stair maker
  does, so a copy made by the user gets its own mesh instead of sharing a
  prototype, and editing one member never changes another.
- `xform`: the matrix from 6.3.
- `name`: the AISC label, e.g. `W12X26`, or `W12X26 (profile)` when
  length is 0.
- `layer`: the chosen layer name, or `None` for the default layer.
- `ifc`: `{"class": <IfcColumn|IfcBeam|IfcMember>, "name": <label>}`.
- `ext["igz_steel"]`:

```json
{
  "version": 1,
  "label": "W12X26",
  "unit_system": "imperial",
  "insertion": "centroid",
  "start": [x, y, z],
  "direction": [dx, dy, dz],
  "length": 3.6576,
  "roll": 0.0,
  "fillets": true,
  "segments": 24
}
```

All lengths in metres, direction a unit vector. `unit_system` is only the
label preference used when the dialog reopens; geometry is unit-independent.

IFC class rule (recomputed on every build or stretch): angle between
`direction` and world Z under 5° gives IfcColumn; angle to the XY plane under
5° gives IfcBeam; otherwise IfcMember.

## 8. Interaction

### 8.1 Place tool (`PlaceMemberTool`)

Created by the dialog's **Place** button with the chosen shape, insertion
point, roll, fillets, segments and layer. `uses_snap = True`,
`vcb_label = "Length"`, the axis magnet on.

States:

1. **Hovering the profile.** `rubber_band_lines` returns the profile
   outline as segments, translated so the insertion point sits at
   `ctx.world`. The direction is not known yet, so the outline is shown
   standing in the world YZ plane (member axis along world X) purely as a
   preview. Status: "Click to place the profile · Esc exits".
2. **Start fixed.** First click stores `start = ctx.world`. Hover computes
   `direction = (ctx.world − start)` and, when its length exceeds 1 mm,
   previews the full member wireframe (profile at both ends plus the
   longitudinal edges, not every quad, to keep the preview light) using
   `member_matrix`. The host's axis magnet and arrow-key plane locks act on
   `ctx.world` before the tool sees it, so no extra inference code is needed.
   Status: "Click the end point or type a length · Esc places the profile".
3. **Commit.** Second click commits the member of that length and
   direction. `on_value(viewport, value)` with a float commits a member of
   length `value` (metres) along the current hover direction; a negative
   value reverses the direction; a 3-tuple is treated as an offset from the
   start, like the line tool. With no hover direction yet, `on_value` returns
   `False` so the host shows its usual hint.
4. **Escape in state 2** commits a profile object (length 0) at `start`
   with the preview orientation (axis along world X, roll applied).
   **Escape in state 1** leaves the tool without creating anything.

After a commit the tool returns to state 1 so several members can be placed
in a row; the status bar says which shape is active. The dialog stays open.

### 8.2 Stretch tool (`StretchMemberTool`)

Activated from the toolbar, submenu or context menu with exactly one steel
group selected; otherwise a message explains the requirement.

- For a **member**: the two end points in world space are the grips. The
  first click picks the grip nearest the click (within 20 px, using
  `app.world_to_pixels`); the other end becomes the fixed end. Hover
  projects `ctx.world` onto the infinite axis line; the preview shows the
  member from the fixed end to that projection. Click or `on_value` commits.
  A typed value is the new total length measured from the fixed end. A
  projection that falls on the far side of the fixed end flips the direction
  (the member grows the other way).
- For a **profile object** (length 0): the start is the fixed end and the
  direction is free, exactly as Place state 2; click or typed length commits.
- Commit is a rebuild command (8.4) that keeps the group identity, updates
  `start`, `direction`, `length`, mesh, xform, name and ifc.
- Escape leaves the member unchanged.

### 8.3 Dialog (`MemberDialog`)

Non-modal, one instance parented to `app.window`, reused for Place and Edit.

| Control | Behaviour |
|---|---|
| Family combo | 13 families in AISC order |
| Label system | radio: Imperial / Metric; switches the list labels and the dimension read-out units |
| Filter box | substring filter on the label (e.g. `12X26`, `HSS6X6`) |
| Shape list | labels of the family, filtered; selecting one updates the read-out and preview |
| Read-out | d, bf, tw, tf (or b, t / Ht, B, tdes / OD, tdes), A and W in the chosen unit system |
| Section preview | `SectionPreview` widget draws the outline and the insertion points; clicking a point selects it and highlights it; the selected id is shown as text |
| Roll | spin box in degrees, buttons 0 / 90 / 180 / 270 |
| Fillets | checkbox, default on |
| Round segments | spin box 8–96, default 24; enabled for round HSS and PIPE only |
| Layer | editable combo listing `scene.layers` names; typing a new name creates it on commit |
| Length (Edit only) | `LengthSpinBox` from the host (metres inside, document units shown) |
| Buttons | **Place** (activates the Place tool), **Update** (Edit mode, rebuilds), **Close** |

Opening the dialog from **Edit** with one steel member selected loads its
parameters, shows the Length field and the **Update** button. In Edit mode,
Update keeps `start` and `direction` and rebuilds everything else, including
a new length. `start` is where the insertion point sits, so changing the
insertion point in Edit shifts the section about the axis while the axis
line itself stays put; changing the shape keeps the same insertion id when
the new shape has it and falls back to `centroid` otherwise.

### 8.4 Commands and undo

- New member or profile: `core.history.InsertGroupCommand(group)` (handles
  an open container group and selection).
- Rebuild (stretch, edit): `RebuildMemberCommand(group, new_mesh, new_xform,
  new_ext, new_name, new_ifc, new_layer)` storing the previous values in
  `do()` on first run, swapping them, and restoring in `undo()`, bumping
  `scene.version` both ways, as the stair maker's command does.
- Layer creation: when the chosen layer name is not in `scene.layers`, the
  same command appends `core.layers.Layer(name)` in `do()` and removes it in
  `undo()` only if it created it. For `InsertGroupCommand` the plugin wraps
  it in a small `CompoundCommand` that runs the layer step first.
- After every command: check `viewport.history.last_error`, show it in a
  message box if set, then `viewport.notify_scene_changed()` and
  `viewport.update()`.

### 8.5 Menus, toolbar, context, outliner

- Toolbar "Steel" (object name `igz_steel_toolbar`): Place member, Stretch,
  Edit, Bill of Materials. Built with `MainWindow._new_toolbar` when present,
  else a `QToolBar` as the floor generator does. Icons in `icons/` with light
  and dark variants chosen by palette, as igz_solids does.
- Extensions ▸ Steel submenu with the same four entries plus "Show steel
  toolbar".
- Context menu (`app.add_context_menu`): when the selection holds exactly one
  steel group, add "Edit steel member…" and "Stretch steel member"; the
  dialog opens through `QTimer.singleShot(0, …)`.
- Outliner (`app.add_outliner_kind`): type "Steel member" (or "Steel
  profile"), props label, length and weight in document units, layer.

## 9. Bill of Materials

### 9.1 Data (`_bom.py`, pure Python)

```python
collect(groups, unit_profile) -> BOM
BOM.rows: list[Row]      # one per member, in outliner order
Row: mark, label, family, length_m, weight_kg, layer, ifc_class, group_uid
BOM.summary: list[SummaryRow]   # grouped by label, sorted by family then label
SummaryRow: label, family, count, total_length_m, total_weight_kg
BOM.totals: count, total_length_m, total_weight_kg
to_csv(bom, unit_profile) -> str
```

Marks are sequential per label: `W12X26-1`, `W12X26-2`, … in document order.
Profile objects (length 0) appear in the rows with length 0 and weight 0 and
are flagged "profile" so they are not forgotten in the model; they are
excluded from summary totals.

Weight = `weight_per_m × length_m` (kg); the imperial display converts to
lb with 1 kg = 2.20462 lb, and lengths to feet-inches with the host's
`core.units.format_length` using the document's unit code. The unit profile
comes from `core.units.profile_of(scene.units)`: `imperial` shows ft-in and
lb, anything else shows m and kg.

### 9.2 Window

A non-modal `QDialog` with two tables (members, summary), a totals line, a
**Refresh** button, an **Export CSV…** button (file dialog, UTF-8, header
row, same columns as the tables plus the raw metre and kilogram values) and
**Close**. It subscribes to `app.on_document_changed` and refreshes while
open. Double-clicking a member row selects that group in the model.

## 10. Units

- Geometry is metres everywhere inside the plugin.
- Typed lengths in the measurement box arrive from the host already in
  metres through `on_value`; no parsing in the plugin.
- Dialog length fields use the host's `views.length_field.LengthSpinBox`.
- Read-outs and the BOM format through `core.units`; the plugin never
  hard-codes a unit symbol except "lb" and "kg" for weight, which the host
  does not know.

## 11. Error handling

- A missing or malformed JSON database makes `setup` log the error and
  register nothing, so IngeTrazo shows the plugin as a load error and starts
  normally.
- Any host call that does not exist in an older or newer 0.x build
  (`_new_toolbar`, `add_outliner_kind`, `world_to_pixels`, `LengthSpinBox`)
  is wrapped so the feature degrades (plain toolbar, no outliner tooltip,
  grip picking by world distance, plain double spin box in metres) instead of
  failing the load.
- Commands that raise are rolled back by the host's history; the plugin shows
  `history.last_error` in a message box.
- A selected group that is not a steel member, has been exploded, or lives in
  a document other than the dialog's, is refused with a clear message.

## 12. Testing

Pure-Python unit tests (pytest, no Qt, no host):

- `test_db.py`: the JSON loads, has 2,299 shapes, every family present with
  the expected counts (W 289, M 16, S 28, HP 22, C 32, MC 40, L 137, WT 289,
  MT 14, ST 28, 2L 639, HSS 714, PIPE 51); `find("W12X26")` and
  `find("W310X38.7")` return the same shape; 2L gaps parse.
- `test_profiles.py`: for one shape of every family, with and without
  fillets: outer loop closed and counter-clockwise, holes clockwise, computed
  area within 1.5 % of the AISC `A` (looser 3 % where fillets or toe radii
  are ignored, e.g. L and 2L), bounding box equals `d × bf` (or the family's
  equivalents) within 0.1 mm, insertion point ids stable across the fillet
  toggle.
- `test_geometry.py`: every extruded mesh has each edge shared by exactly two
  faces (watertight); volume equals area × length within 0.5 %;
  `member_matrix` maps local (L, 0, 0) to `start + L·direction` and keeps
  profile "up" aligned to world Z for horizontal members and world Y for
  vertical ones; roll of 90° swaps the profile axes.
- `test_bom.py`: marks, grouping, totals and the CSV header are correct for a
  synthetic set of members; profiles are excluded from totals.

In-app verification (manual and via the Python Console or the MCP bridge):
place a W12X26 by click, by typed length `12'`, and by Escape (profile);
stretch each end; edit to an HSS; assign a new layer and confirm it appears
in the layer list and hides with it; verify the IFC class flips between beam
and column; open the BOM, confirm totals, export CSV; undo through every step
and confirm the document returns to empty.

## 13. Licensing and data terms

- The package is GPL-3.0-or-later, like IngeTrazo and the other catalog
  extensions; it imports host modules at runtime and vendors none of them.
- The AISC workbook is not redistributed. The generated JSON contains only
  dimensional data derived from it, with the AISC disclaimer reproduced in
  README and THIRD-PARTY. The README states that the data is informational
  and that design use requires verification by a licensed engineer, matching
  the workbook's own disclaimer.

## 14. Open items deferred to the implementation plan

- Whether to draw the Stretch tool's end grips as an overlay
  (`app.add_overlay`). Default: draw two small squares at the member ends
  while the tool is active. The 20 px pick radius in 8.2 stands.
- Whether `MainWindow._new_toolbar` exists in 0.5.8 (fallback already
  specified).
- The host's handling of `on_value` tuples for the Stretch tool (only floats
  are required; tuples are accepted as offsets if cheap).
