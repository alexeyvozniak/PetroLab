# Architecture and safety rules

## No more runtime patch layers
- Do not add new `v015x_*_wrapper`, bridge, monkey-patch or temporary function replacement layers.
- When touching a workflow currently implemented through wrappers, prefer consolidating behavior into one canonical implementation.
- Remove obsolete wrappers after their behavior is absorbed and covered by tests.
- A fix is not complete if it only adds another wrapper around the broken wrapper.

## Explicit shared state models
Create small explicit models/services rather than unrelated session-state keys.

Required concepts:
- `SelectionContext`: selected immutable analysis ids + origin + optional grouping/cluster metadata.
- `PlotSpec`: exact data selection + X/Y + grouping + source visibility + styles + axis settings.
- `NavigationHistory`: previous route + relevant context, bounded history stack.
- `TableViewState`: filters, sorting/grouping, visible column mode and selected rows.

These names may be adjusted if a cleaner existing pattern already exists, but there must be one canonical state mechanism per concept.

## Streamlit state/key policy
- Every widget key must be deterministically scoped by page/component instance and entity/context where necessary.
- Never reuse a fixed key inside a component that may render more than once.
- Central reusable components should accept a `key_prefix`/scope parameter.
- Do not rely on deleting arbitrary unrelated session-state keys to make navigation work.
- Add regression tests for duplicate-key scenarios.

## Navigation
- `navigate()` must remain the single high-level route transition API or be replaced by one equally explicit router.
- User-initiated navigation pushes history; internal rerenders do not.
- Back restores the previous route and relevant work/selection context.
- Automatic post-import routing must not destroy history.

## Data/storage safety
- Existing user SQLite databases and imported datasets must remain readable.
- Prefer additive/migratable schema changes. Never require users to delete their data directory.
- Never mutate source Excel or raw chemistry unless the existing explicit sync operation was requested.
- Preserve provenance and stable analysis ids across UI refactors.
- Database/service writes belong in service/repository functions, not directly inside arbitrary UI callbacks when a service abstraction already exists.

## Scope discipline
- Work Groups shown in a project should be scoped to the current project/data context unless the UI explicitly says they are global.
- Dataset/source selection must not silently broaden to all project data after a rerun.
- Exact selections must remain exact.

## Dependency discipline
- Prefer existing dependencies and Streamlit/Plotly capabilities.
- Do not add a large UI framework merely to solve a small interaction.
- If a new dependency is truly necessary, document why and add a focused test.

## Git discipline
- Work only on the current UX branch.
- Make small logical commits after a coherent block is tested.
- Do not push, merge to `main`, rewrite history or delete user data without explicit user permission.

Before implementation, inspect `ARCHITECTURE.md`, the current route/render chain in `petrolab/ui/pages/__init__.py`, and `docs/UX_AUDIT_V0157_30_PROBLEMS.md`.