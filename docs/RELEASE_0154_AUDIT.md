# PetroLab 0.15.4 — grain-profile and project-scope release audit

Release branch is built on top of the merged v0.15.3 publication-composer main.

Integrity rules included in this release:

## Grain profiles

- routed analysis selections preserve exact `analysis_id` order;
- an absent routed analysis ID is an explicit error rather than a silently shortened profile;
- selections above 120 points are never silently truncated;
- routing is scoped to the active project and accessible datasets;
- `P-5` means point 5, not numeric −5;
- order, distance and geometry columns reject NaN/Inf/non-numeric values where a physical coordinate is required;
- geometry is calculated only inside one non-empty coordinate frame per traverse;
- geometry distance inherits the units of X/Y and is not labelled µm unless the source coordinates are calibrated in µm;
- non-finite derived Y values become plot gaps, never real points or zeroes;
- canonical grain identities (`Grain`, `Зерно`, etc.) cannot be silently concatenated into one traverse;
- multiple-grain comparison is explicit, prepares each grain separately, supports overlay/facets and never averages between grains;
- different image coordinate frames may coexist across different grains, but not inside one geometric traverse;
- grouped and single profiles export exact ordered rows plus versioned JSON recipes.

## Project switching and universal intake

- transient universal-intake file identity is namespaced by `project_id`;
- image-batch wizard identity is namespaced by `project_id` as well;
- the same physical Excel/image batch opened in two projects receives independent transient import/provenance state;
- post-import image handoff is project-scoped and ignores stale completion state from another project;
- a real project switch centrally clears exact plot/table/edit selections, grain-profile identities, quick-import state, universal-intake drafts and whole-rock focus;
- project switching deliberately preserves persistent/user-preference state such as navigation, plot styles, appearance and publication-composer settings;
- wrapper monkey-patches used for universal intake are always restored in `finally`.

## Preserved earlier guarantees

- publication-composer routes/wrappers and the v0.15.3 runtime stack are preserved;
- v0.15.1 tokenized global search remains the production search path, including compound queries where mineral/source terms occur in different columns;
- v0.15.1 exact-selection and physical-point safety wrappers remain layered underneath v0.15.4.

Release condition: grain-profile/project-scope regression, publication-composer regression, exact-selection regression, full Windows verification, guided workflow, thermodynamics, amphibole diagnostics, input/search/workflow and desktop UI checks must all be green before merge.
