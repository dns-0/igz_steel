# igz_steel — AISC steel members for IngeTrazo

`igz_steel` places structural steel members with the dimensions of the
**AISC Shapes Database v16.0** (all 13 families: W, M, S, HP, C, MC, L, WT,
MT, ST, 2L, HSS and PIPE — 2,299 shapes), stretches them along any axis, edits
them in place, tags them for BIM, assigns layers and produces a Bill of
Materials.

- **Version:** 1.0.0 — **License:** GPL-3.0-or-later (see LICENSE, THIRD-PARTY.md)
- **Tested with:** IngeTrazo 0.5.8 (Extension API 2). The API is still 0.x; a
  newer IngeTrazo may need an update of this extension.
- **Dependencies:** none beyond IngeTrazo itself.

## Installation

In IngeTrazo open **Extensions ▸ Open plugins folder**, drop the `igz_steel`
folder there (or unzip `igz_steel.zip` so that the folder is
`plugins/igz_steel/`) and restart IngeTrazo. A **Steel** toolbar and an
**Extensions ▸ Steel** submenu appear.

## Using it

1. **Place member…** — pick a family and a shape (type part of the label to
   filter, e.g. `12X26`; switch to metric labels if you prefer `W310X38.7`).
   Click an insertion point on the section preview (centroid, top of steel,
   any corner or edge midpoint). Set roll, fillets, round segments and the
   layer (type a new name to create one). Press **Place**.
2. In the model the profile follows the cursor. **Click** the start point.
   Move along any axis (IngeTrazo's axis inference and arrow-key locks work as
   for the Line tool). **Click** the end point, or **type a length** in the
   Measurements box (`12'`, `3.5m`, `3660mm`…). **Esc** after the first click
   leaves a flat profile you can stretch later.
3. **Stretch member** — select a member, click the end you want to move, then
   click the new end or type the new total length. A click past the fixed end
   grows the member the other way.
4. **Edit member…** — select a member and change its shape, insertion point,
   roll, fillets, layer or length. The start point and axis stay put.
5. **Bill of Materials…** — every member with mark, shape, length, weight,
   layer and IFC class, a summary by shape and totals; **Export CSV…** writes
   the table. Double-click a row to select that member. Lengths and weights
   follow the document's units (feet-inches and pounds, or metres and
   kilograms).

Members are tagged **IfcColumn** (vertical), **IfcBeam** (horizontal) or
**IfcMember** (sloped). The Browser shows them as "Steel member" with shape,
length and weight.

## Notes and limits

- Geometry: parallel flanges at the tabulated average thickness (flange slopes
  on S, C, MC, M and MT are ignored, though the fillet radius on S, C, MC and
  ST is reduced to match the sloped section's area); fillets from `kdes`; HSS
  corners at 2t outside and t inside; round sections as polygons (8–96
  segments).
- Members placed while a group is open for editing are refused; close the
  group first. A member that was exploded or made unique can no longer be
  stretched or edited by this extension.
- The AISC data is reproduced for modelling only. Verify anything structural
  with a licensed engineer (see THIRD-PARTY.md for AISC's disclaimer).

## Development

```
python -m venv .venv && .venv/Scripts/python -m pip install pytest openpyxl PySide6
.venv/Scripts/python -m pytest -q
.venv/Scripts/python devtools/build_db.py <aisc workbook .xlsx> igz_steel/data/aisc_v16.json
.venv/Scripts/python devtools/package.py        # dist/igz_steel.zip
bash devtools/install.sh                        # copy into %APPDATA%\ingetrazo\plugins
```
