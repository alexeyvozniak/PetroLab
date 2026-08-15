# PetroLab 0.15.4 — grain-profile release audit

Release branch is built on top of the merged v0.15.3 publication-composer main.

Integrity rules included in this release:

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
- grouped and single profiles export exact ordered rows plus versioned JSON recipes;
- publication-composer routes/wrappers and the v0.15.3 runtime stack are preserved.

Release condition: grain-profile scientific/hardening regression, exact-selection regression, full Windows verification, guided workflow, thermodynamics, amphibole diagnostics, input/search/workflow and desktop UI checks must be green before merge.
