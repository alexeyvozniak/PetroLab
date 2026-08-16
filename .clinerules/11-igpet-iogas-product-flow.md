# PetroLab product flow: IgPet → ioGAS

This rule complements `.clinerules/10-ux-reference-model.md`.

- `10-ux-reference-model.md` defines lower-level Airtable/JMP/Origin interaction semantics.
- This file defines the macro user journey: **IgPet speed at entry → ioGAS depth after the first result**.

## Core promise

> **Fast first plot, deep second step.**

A user should reach a scientifically reasonable first result with the minimum number of deliberate choices, then progressively gain access to linked exploratory tools without changing data identity or losing context.

## 1. Reuse known context

If PetroLab already knows the current project, dataset scope, Sample, exact analysis selection or source scope, never ask the user to select it again unless a genuine ambiguity exists.

Known context must flow through canonical state objects rather than copied temporary datasets or page-specific filter state.

## 2. Show a useful result early

When the current data support a safe deterministic recommendation, render a recommended scientific view immediately.

Use mineral/data-aware Smart Start logic. Do not require the user to configure X, Y, grouping and datasets before the first useful graph when PetroLab can infer a reasonable starting point.

The recommendation is a starting view, never a hidden scientific conclusion.

## 3. Scientific ambiguity must remain explicit

One-click UX must never silently resolve scientifically meaningful ambiguity.

Examples that still require an explicit decision or unresolved state:

- FeO / Fe2O3 / Fe-total interpretation;
- ambiguous phase/mineral assignment below confidence threshold;
- incompatible or unknown units;
- uncertain analytical provenance;
- invalid compositional-data assumptions.

Prefer `unresolved + warning` over guessing.

## 4. Do not split the product into Beginner and Expert modes

Use progressive disclosure.

Normal flow:

1. recommended result;
2. compact X/Y/group/source controls;
3. selection and linked views;
4. optional axes/style/fields;
5. publication/deep editor only when requested.

Advanced editors may exist as implementation routes, but they must accept and return the same canonical state and must not become a separate mental model.

## 5. First plot must naturally become deep exploration

Every normal analytical graph should be able to continue into:

- point / rectangle / lasso selection;
- Replace / Add / Subtract;
- linked table highlighting;
- linked second/third graph;
- PCA / clustering when applicable;
- source/article comparison;
- hide/show series;
- Work Group / Generation actions;
- linked record/image inspection;
- saved research state.

Never force the user to restart the analysis in another module merely to deepen it.

## 6. Preserve canonical state ownership

Do not create parallel sources of truth.

Canonical ownership remains:

- **data scope/context** → WorkContext/DataScope (or a single compatible DataUniverse adapter);
- **transient selected analyses** → SelectionContext;
- **row presentation/calculation states** → RowDisplayStates;
- **graph definition** → PlotSpec;
- **table representation** → TableViewState;
- **scientific persistent grouping** → Work Group / Generation services.

New orchestration code may reference these objects but must not duplicate them.

## 7. Selection, filter, hide and exclude are never interchangeable

- **Selection**: transient analytical attention.
- **Filter**: changes the current visible/search universe.
- **Hide**: presentation only.
- **Exclude**: removed from calculations/statistics according to explicit semantics.
- **Work Group**: reversible scientific hypothesis/group.
- **Generation**: formal scientific interpretation.

UI labels and implementations must preserve these meanings everywhere.

## 8. One normal table, one normal intake path

Do not create another user-facing table workspace or another independent import product.

Existing compatibility/editing routes should converge into the canonical Table Workspace and Add Data workflow while preserving their safe backend capabilities.

## 9. Checkpoints and templates are different

A **WorkspaceSnapshot** restores a concrete research session including its data universe and panel state.

An **AnalysisTemplate** stores a reusable way to analyse compatible data and must not contain concrete analysis IDs.

Never merge these concepts.

## 10. Do not duplicate datasets to represent a view or selection

Views, source comparisons, filters, selections and saved research states reference the canonical records by stable identity.

Creating a new dataset is a scientific/data-management action, not a UI convenience.

## 11. Prefer contextual actions over new modules

Before adding a new top-level route, ask whether the task can be done as:

- an action on current selection;
- a new linked panel;
- a contextual drawer;
- a PlotSpec transformation;
- a saved view/template.

The default answer should be to keep the user in the current research surface.

## 12. Definition of a successful workflow

A workflow is not complete merely because every individual function exists.

It is complete when:

- the user does not reselect known data;
- the first useful result appears early;
- selection survives changes of representation;
- linked views share the same analysis identity;
- deep controls appear only when needed;
- returning/back does not unexpectedly destroy state;
- scientific provenance and ambiguity remain explicit.

## Golden product path

```text
Find / import / continue
        ↓
Known DataUniverse
        ↓
Recommended scientific result
        ↓
Select / brush
        ↓
Linked table + plots + statistics + source/image context
        ↓
Interpret / calculate
        ↓
Save WorkspaceSnapshot
        ↓
Publish or continue later
```

For the detailed audit, implementation phases and acceptance workflows, see:

`docs/IGPET_IOGAS_SYNTHESIS_AUDIT_AND_PLAN.md`
