# Field appearance and manual geometry editor

PetroLab keeps scientific field calculation and visual/manual editing separate.

## Appearance

For each plotted group/generation, the Advanced XY workspace allows independent control of:

- fill on/off;
- fill colour;
- fill transparency;
- outline colour;
- outline width;
- outline style.

These controls do not change the scientific envelope method.

## Manual geometry

A calculated convex hull, confidence ellipse or KDE field can be converted to a manual polygon by enabling manual geometry editing in the field editor. The current calculated polygon is used as the starting vertex set. Vertices can then be changed, added or removed in the editor.

Once geometry is edited, the field is stored as `manual_envelope_points` and marked with `envelope_geometry_status = manual`. The original envelope method and level remain in metadata. Interactive hover explicitly identifies the field as manual and reports its original calculated method.

`Вернуть расчётное поле` removes the manual override and immediately restores the current reproducible envelope calculation.

## Scientific safety

- Manual field edits never alter analytical rows or Excel data.
- Manual geometry is never presented as a confidence/KDE boundary.
- Manual vertices are saved in style profiles/plot recipes and are reproduced in interactive plots, PNG and SVG export.
- Appearance changes and geometry changes are stored separately.
