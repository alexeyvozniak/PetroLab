# PetroLab: portable project and interactive plot plan

## Goal

Make PetroLab comfortable for one researcher working on several computers without repeating Excel mapping, image linking, grouping or plot cleanup.

## Phase 1 — implemented in this branch

### Portable project archive

Three export levels:

1. `project` — database snapshot + manifest.
2. `project_sources` — project + source Excel/CSV files.
3. `full` — project + source Excel/CSV + original image assets.

The result is one `.petrolab` file (ZIP container with an explicit manifest). The project page exposes the three choices and a download button.

Current safety rule: the archive service creates backups/export packages only. Automatic restore is intentionally not yet enabled until path rewriting and database merge semantics are covered by tests.

### Interactive XY inspection

- Hover is compact and shows X, Y, Sample, Point, Generation and work group when available.
- Clicking / lasso / box selection remains available.
- Selected points can be hidden only from the current plot; Excel and analytical storage are untouched.
- Hidden point IDs remain recipe/session-level exclusions and can be restored.
- Full selected-analysis inspection with related images remains available.

### Marker styling

Per group:

- marker shape;
- size multiplier;
- alpha / transparency;
- fill flag;
- outline: black / white / group color / none;
- outline width.

## Phase 2 — next implementation

### Restore `.petrolab` on another computer

Required before calling portable projects complete:

- validate archive manifest and version;
- make a safety snapshot of the current workspace;
- restore into a new local workspace, never silently overwrite an existing workspace;
- rewrite source paths to extracted `sources/` files;
- rewrite image paths to extracted `images/` files;
- verify source SHA256 values;
- run schema migrations before opening the restored project;
- expose explicit conflict handling when a project with the same identity already exists.

### Compressed image mode

Add a third image option:

- none;
- optimized working copies;
- originals.

Optimized images must be stored as derivatives and must never replace scientific originals or be represented as originals.

## Phase 3 — group envelopes / fields

Add a separate scientific envelope layer, not a renderer hack.

Supported methods should be explicit and saved in plot recipes:

1. convex hull;
2. confidence ellipse (68 / 90 / 95%);
3. KDE density contour with stated probability level;
4. optional alpha shape after a tested implementation is available.

Each group gets display mode:

- points;
- field;
- points + field;
- centroid / median only.

Every exported field must carry metadata: method, parameters, n, group name and exclusions. Manual and automatic outliers must be applied before envelope calculation and listed in the recipe.

## Phase 4 — overlay manager

Allow several literature/classification overlays at once with independent:

- visibility;
- line width / line style;
- fill / alpha;
- label visibility;
- z-order.

Scientific overlays remain source-aware. Unsourced geometry must not be presented as a formal classification field.

## Acceptance workflow

Before merging each phase, verify on real PetroLab-style data:

1. import heterogeneous Excel sheets;
2. confirm semantic mappings;
3. link images to stable analysis IDs;
4. save a plot recipe with transparency, outline and exclusions;
5. export `.petrolab` in all supported modes;
6. verify archive contents and hashes;
7. after restore is implemented, move the archive to a clean test workspace and confirm mappings, analysis IDs, images and plot recipes survive unchanged.
