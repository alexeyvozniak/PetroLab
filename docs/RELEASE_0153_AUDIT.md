# PetroLab 0.15.3 — release audit

This release branch is rebuilt on top of the current v0.15.2 main rather than merged from the stale feature base.

Silent-error closure included in the release:

- manual panel title/label/order/position/crop settings survive source additions and removals by stable `source_id`;
- project-image selector state is scoped by `project_id`;
- duplicate panel source identities are de-duplicated visibly;
- panel-label NaN/Inf values fall back to finite defaults;
- broken images keep their own grid cell and can never shift later panel identities;
- publication Recipe JSON is loadable as well as exportable;
- recipe restore is identity-based and reports unavailable `source_id` values rather than substituting another image;
- duplicate `source_id` values in recipes are rejected;
- labels remain embedded in exported figures and scientific multi-panel output;
- v0.15.2 amphibole runtime and all other current-main files are preserved by rebuilding the release tree from the v0.15.2 main tree.

Release condition: feature regression, exact-selection regression, full Windows verification, guided workflow, thermodynamics, amphibole diagnostics, input/search/workflow and desktop UI checks must all be green on this branch before merge.
