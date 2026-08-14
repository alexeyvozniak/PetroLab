# PetroLab: portable projects and interactive XY

## Status

This work is implemented in PR #33. The goal is to let one researcher move a PetroLab project between computers without repeating Excel semantic mapping, image linking, working groups or plot cleanup, while keeping graph-only decisions separate from analytical storage.

## Portable `.petrolab` project

Three archive levels are available:

1. `project` — project-scoped database snapshot + manifest;
2. `project_sources` — project + source Excel/CSV files;
3. `full` — project + source Excel/CSV + image assets.

For a full archive, images can be stored as:

- scientific originals;
- optimized derivative JPEG copies for a smaller portable package.

Optimized copies are explicitly derivatives and never replace the original scientific files.

The database snapshot is project-scoped: rows belonging only to other projects are removed before packaging. Global rows with nullable `project_id` are retained where they may be needed by project recipes or shared styles.

## Restore on another computer

The Projects page can open a `.petrolab` archive.

Safety rules:

- validate archive format and manifest before writing;
- reject ZIP path traversal;
- run SQLite `PRAGMA integrity_check` before replacing the active database;
- restore into an empty workspace by default;
- replacing a non-empty workspace requires explicit confirmation;
- make a SQLite safety backup before an explicit replacement;
- reconnect packaged source files and image assets to local restored paths.

The restore operation intentionally does not attempt an implicit two-way merge between unrelated local workspaces. That would risk ID and scientific-provenance conflicts.

## Interactive XY inspection

- compact hover: X, Y, Sample, Point, Generation and work group when available;
- click, box and lasso selection;
- selected points can be hidden only from the current plot;
- graph exclusions do not modify Excel or analytical storage;
- hidden analysis IDs are reversible and saved with the current plotting state/recipe;
- selected analyses can be opened in a detailed property view together with related images.

## Marker styling

Per group:

- marker shape;
- size multiplier;
- alpha / transparency;
- fill flag;
- outline: black / white / group color / none;
- outline width.

## Group fields / envelopes

Several groups can show fields simultaneously on the same XY diagram. Each group independently selects one display mode:

- points;
- field;
- points + field;
- median center only.

Implemented field methods:

1. `convex_hull` — convex hull of the included points;
2. `confidence_ellipse` — bivariate covariance ellipse with an explicit probability level and a stated bivariate-normal assumption;
3. `kde` — Gaussian-kernel density contour with an explicit probability-mass level.

Fields are calculated from the data that remain after current range, automatic-outlier, manual and interactive graph exclusions. Therefore a point hidden from the current plot cannot silently continue to control that plot's field.

The interactive field hover reports method, level and `n`. Field settings are stored in the same per-group style map used by saved profiles and plot recipes. Publication PNG/SVG output uses the same group-field settings as the interactive view.

## Scientific rules

- no plot action deletes an analysis from Excel;
- graph hiding, statistical outlier suggestions and source-data deletion remain distinct operations;
- confidence ellipses are not presented as distribution-free fields;
- KDE and hull geometry are calculated from the actual included sample rather than hand-drawn approximations;
- source-aware literature/classification overlays remain separate from data-derived group fields;
- unsourced geometry must not be presented as a formal scientific classification field.

## Regression coverage

Windows CI includes dedicated checks for:

- project-scoped archive contents;
- optimized-image derivative mode;
- refusal to overwrite a non-empty workspace without explicit confirmation;
- convex-hull geometry;
- confidence-ellipse geometry;
- KDE contour output and metadata;
- normal PetroLab architecture, storage, scientific, browser and Windows-startup regressions.

## Recommended real-data acceptance test

After merge, validate once on a real PetroLab project before relying on the portable workflow for unique data:

1. import heterogeneous Excel sheets and confirm semantic mappings;
2. attach several images to stable analysis IDs;
3. save a plot recipe with transparency, outlines, one hidden point and at least two simultaneous group fields;
4. export a full `.petrolab` archive;
5. restore it in a clean test workspace on another computer;
6. confirm mappings, analysis IDs, image links, plot recipe and field settings survived unchanged;
7. make one source edit and verify the normal source-sync safeguards still behave as expected.
