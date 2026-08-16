# PetroLab product rules — always active

PetroLab is a local scientific workspace for petrology, mineralogy and geochemistry. The user is a geologist, not a database administrator. UI decisions must optimize the real research workflow, not expose internal implementation details.

## Release goal
- v0.15.7 is a UX consolidation release. Do not add new user-facing modules while P0/P1 items in `docs/UX_AUDIT_V0157_30_PROBLEMS.md` remain open.
- Prefer deleting, merging or simplifying screens over adding another route, wrapper or wizard.
- One user concept must have one primary workflow. Do not create competing ways to do the same task.

## Human-first UI
- Never use `analysis_id`, `dataset_id`, UUIDs, database row ids, raw session-state keys or internal enum names as primary user-facing labels.
- Point identity should be `Sample · Grain · Point · Generation` when available. Fall back to a short source-row label, never a long UUID.
- Dataset labels should be human-readable. Technical IDs belong only in an optional "Технические сведения" area.
- Russian is the primary UI language. Labels must be short, concrete and action-oriented.
- Every destructive action must say what will be removed and require explicit confirmation.
- Every error message must tell the user what happened and what they can do next.

## Table-first scientific workflow
- The table is a primary workspace, not a passive preview.
- Any important selection must be inspectable as rows with identity + chemistry.
- Core table actions: select rows, filter, group, sort, inspect chemistry, assign Sample/Grain/Work Group/Generation/QC, open on plots, build profile, calculate formula, export.
- Selection must survive movement between table, XY, multi-panel, PCA/clusters, profile and Generation.

## Progressive disclosure
- Default screens show only the controls needed for the current task.
- Advanced/debug/internal controls go behind "Дополнительно" or "Технические сведения".
- Do not show a dropdown with dozens of arbitrary dataframe columns. Curate scientific choices first; expose "Другой столбец…" only when needed.
- Do not require users to understand Streamlit, Plotly, database schemas or internal file organization.

## Scientific integrity
- Never silently discard an analysis because it is incomplete, outlying or ambiguous. Preserve it and flag it.
- Preserve source provenance, source row, method and original values.
- Work Group is a reversible hypothesis. Generation is an interpretation. Keep them distinct in storage and UI.
- Derived values/APFU must never overwrite raw chemistry.
- Do not merge scientific entities based only on fuzzy string similarity without user confirmation.

## Interaction rule
After any row/point/cluster selection, show one consistent selection summary and one consistent action bar. The user should never have to search another page to discover what can be done with the current selection.

Read `docs/UX_AUDIT_V0157_30_PROBLEMS.md` before making UX changes.