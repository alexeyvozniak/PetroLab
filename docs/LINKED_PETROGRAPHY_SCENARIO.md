# PetroLab: linked petrography workflow

## Product goal

PetroLab must treat chemistry, analytical points, images, grains and thin sections as different representations of one scientific object rather than separate pages.

The core loop is:

**Excel/CSV + images → exact image-to-analysis links → observed Textural zone → Smart Start plot → linked Selection → Work Group → confirmed Generation → save → return to the same physical points on the thin section.**

A second core loop is:

**Thin section + PPL/XPL/BSE → physical point / grain / region → EPMA + LA-ICP-MS + other measurements → plots → click a chemical point → highlight its physical position → click a physical point → highlight it in every linked plot/table.**

This scenario extends the existing WorkContext, SelectionContext, PlotSpec, image links, physical-point model, thin-section workspace, Textural zone, Work Group and Generation. It must not create parallel copies of those concepts.

## Scientific semantics

The following concepts remain distinct:

- **Physical point**: one place on a grain/thin section. Several analytical observations may belong to it.
- **Analysis / observation**: EPMA, LA-ICP-MS, EDS or another measurement with immutable `analysis_id`.
- **Image / thin-section image**: visual representation of a sample, grain or field.
- **Textural zone**: observed petrographic position (core, rim, reaction zone, inclusion, etc.). It is observational evidence, not an interpretation of chemical generation.
- **Selection**: transient current analytical selection shared between views.
- **Work Group**: exploratory scientific grouping created during investigation.
- **Generation**: confirmed interpretation; never created silently from clustering or morphology.
- **Hide / Exclude**: presentation/statistical state, not classification.

## P0 — true graph ↔ thin-section round trip

Create one adapter/service over the existing models; do not add a second SelectionContext.

Required operations:
- `analysis_ids -> related physical points`
- `physical point/marker -> linked analysis_ids`
- deterministic behavior when several analyses or several physical points are linked
- preserve analytical method provenance
- never infer physical identity from similar labels alone

For current Selection:
- show `Open on thin section` when a physical link exists;
- if there is one physical point, open it directly;
- if there are several, show a compact chooser;
- open the exact thin section/image and visually highlight the coordinate/region;
- preserve current Selection during navigation.

From a point, grain or selected region:
- `Show linked analyses` sets canonical Selection;
- `Open in plots` reuses current DataUniverse when compatible or creates an exact analysis scope when necessary;
- Smart Start may provide the first plot, but must not broaden exact analysis scope.

When Selection changes:
- linked table/plots update;
- thin-section view shows all physical points corresponding to current Selection when they belong to the open thin section;
- hidden/excluded state does not change physical linkage;
- Generation/Work Group styling may be used to color point overlays, but physical links remain independent of style.

## Scientific invariants

`Textural zone`, `Work Group`, `Generation`, Selection, Hide and Exclude remain distinct. Image or spatial morphology never becomes Generation without an explicit scientific interpretation step.

PPL/XPL/BSE of the same thin section remain separate images until the user explicitly confirms registration. PetroLab must never silently assume equal pixel coordinates across those images.

## Golden acceptance scenarios

### Gate 1 — Excel + images → generations

- import analytical table + images;
- link images to exact analytical points;
- assign observed Textural zones;
- open Smart Start without re-selecting the dataset;
- create graphical selections and Work Groups;
- explicitly confirm Generations with rationale;
- close/reopen and verify interpretation/image links persist.

### Gate 2 — BSE → EPMA/LA → graph ↔ location

- open/create a thin section;
- add BSE image;
- create at least three physical markers/points;
- link one point to EPMA + LA-ICP-MS and others to analytical observations;
- open linked chemistry in plots;
- select a graph point and open the exact BSE location;
- select a physical point on BSE and return to plots;
- verify the same canonical Selection remains highlighted and exact scope is not broadened.

### Gate 3 — morphology is not Generation

- assign core/rim as Textural zone from image;
- create a chemical Work Group crossing the morphology boundary;
- verify neither concept overwrites the other;
- confirm Generation only by explicit user action.

## Definition of done

The scenario is complete only when both round trips work without context loss:

**plot → exact analysis → physical point → thin section/image → plot**

and

**thin section/image → physical point → linked analyses → plot/table/statistics → same physical point.**

No navigation step may broaden an exact selection, silently convert morphology into Generation, or duplicate scientific data just to preserve a view.
