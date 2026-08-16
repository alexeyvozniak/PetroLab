# PetroLab: linked petrography workflow

## Product goal

PetroLab must treat chemistry, analytical points, images, grains and thin sections as different representations of one scientific object rather than separate pages.

The core loop is:

**Excel/CSV + images → exact image-to-analysis links → observed Textural zone → Smart Start plot → linked Selection → Work Group → confirmed Generation → save → return to the same physical points on the thin section.**

A second core loop is:

**Thin section + PPL/XPL/BSE → physical point / grain / region → EPMA + LA-ICP-MS + other measurements → plots → click a chemical point → highlight its physical position → click a physical point → highlight it in every linked plot/table.**

This scenario starts from the current `main` after PR #89. It extends the existing WorkContext, SelectionContext, PlotSpec, image links, physical-point model, thin-section workspace, Textural zone, Work Group and Generation. It must not create parallel copies of those concepts.

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

## Scenario A — table and images to generations

1. User drops one analytical table and many images in Add Data.
2. PetroLab safely imports the table and resolves scientific ambiguities without silent assumptions.
3. Images are reviewed one by one. For every image the user can link the image to one or more exact analyses, a dataset, sample/grain/field, or skip it.
4. While reviewing an image, the user may assign observed Textural zone to any subset of the linked analyses.
5. After import, `Open first plot` reuses the same DataUniverse and immediately shows a safe Smart Start plot when possible.
6. User selects a chemical population on the plot. The same analyses are selected in all linked plots and the table.
7. User may temporarily style, hide, exclude, or create a Work Group from that Selection.
8. User repeats this for other populations and compares them across several linked diagrams.
9. Only after interpretation does the user explicitly confirm a Work Group/Selection as PetroLab Generation, optionally with rationale.
10. Generation, Textural zone, image links and physical context persist after reopening the project.

## Scenario B — thin section to chemistry and back

1. User creates/opens a Thin Section linked to Sample.
2. PPL, XPL, BSE and other images can belong to the same physical thin section without assuming automatic geometric registration.
3. User can define Grain/Region and create a Physical Point on a thin-section image.
4. The Physical Point can be linked to one or several analyses from different analytical methods (e.g. EPMA + LA-ICP-MS).
5. Selecting a physical point creates/updates canonical Selection using all analyses linked to that point, or lets the user choose a specific observation when needed.
6. The same Selection highlights in the canonical table, XY plots, multi-panel plots and statistics.
7. Selecting a chemical point in any linked plot exposes its related physical point, grain, thin section and images.
8. If the physical point has image coordinates, PetroLab opens the appropriate thin-section image and highlights that exact location.
9. Returning from the thin section to plots preserves DataUniverse, PlotSpec and Selection.

## P0 — true graph ↔ thin-section round trip

### P0.1 Canonical bridge: Selection ↔ Physical Point

Create one adapter/service over the existing models; do not add a second SelectionContext.

Required operations:
- `analysis_ids -> related physical points`
- `physical_point_id -> linked analysis_ids`
- deterministic behavior when several analyses or several physical points are linked
- preserve analytical method provenance
- never infer physical identity from similar labels alone

### P0.2 Plot → image/thin-section

For current Selection:
- show `Open on thin section` when a physical link exists;
- if there is one physical point, open it directly;
- if there are several, show a compact chooser;
- open the exact thin section/image and visually highlight the coordinate/region;
- preserve current Selection during navigation.

### P0.3 Thin-section → plot

From a point, grain or selected region:
- `Show linked analyses` sets canonical Selection;
- `Open in plots` reuses current DataUniverse when compatible or creates an exact analysis scope when necessary;
- Smart Start may provide the first plot, but must not broaden exact analysis scope.

### P0.4 Linked visual state

When Selection changes:
- linked table/plots update;
- thin-section view shows all physical points corresponding to current Selection when they belong to the open thin section;
- hidden/excluded state does not change physical linkage;
- Generation/Work Group styling may be used to color point overlays, but physical links remain independent of style.

## P1 — image registration and shared coordinates

PPL/XPL/BSE of the same thin section remain separate images until the user explicitly confirms registration.

Add a registration model that stores transforms between images. Registration must be reversible and provenance-aware.

Minimum useful workflow:
1. choose reference image;
2. choose moving image;
3. mark 2–4 corresponding control points or use a safe assisted method;
4. preview alignment;
5. confirm transform;
6. project physical points/regions between registered images.

Never silently assume equal pixel coordinates across PPL/XPL/BSE.

## P1 — WorkspaceSnapshot

Save the research state independently from scientific classification.

Snapshot should reference, not duplicate:
- project/work context;
- exact DataUniverse / dataset ids / analysis ids when appropriate;
- open plot panels and layout;
- PlotSpec for each panel;
- source/series visibility;
- axis ranges;
- active thin section/image and overlay state;
- optional transient Selection clearly marked as transient.

Generation, Textural zone and Work Group remain persisted scientific/working data and are not replaced by snapshot state.

## UX contract

There must not be separate mental models called “image workflow”, “thin-section workflow” and “plot workflow”. They are views of one investigation.

Contextual actions are preferred:
- on plot Selection: `Images`, `Thin section`, `Work Group`, `Generation`, `Statistics`;
- on thin-section point: `Chemistry`, `Plots`, `Linked measurements`;
- on image: `Linked points`, `Textural zone`, `Open thin section` when applicable.

The user should not have to re-select Sample, dataset or mineral when canonical context already knows them.

## Golden acceptance scenarios

### Gate 1 — Excel + 10 images → generations

- import Excel + 10 images;
- link every image to exact analytical points;
- assign at least two Textural zones from images;
- open first Smart Start plot without re-selecting the dataset;
- make three independent graphical selections;
- save them as three Work Groups;
- confirm them as three Generations with rationale;
- close/reopen project;
- verify Generations, Textural zones, image links and physical identities are unchanged.

### Gate 2 — thin section + BSE → EPMA/LA → graph ↔ location

- open/create a thin section;
- add BSE image;
- create at least three Physical Points;
- link one point to EPMA + LA-ICP-MS and the others to analytical observations;
- open linked chemistry in plots;
- select a graph point and open the exact physical position on BSE;
- click/select a physical point on BSE and return to plots;
- verify the same canonical Selection is highlighted in all linked plots/table;
- verify exact analysis scope was not broadened.

### Gate 3 — morphology is not Generation

- assign core/rim as Textural zone from image;
- create a chemical Work Group that crosses the morphology boundary;
- verify PetroLab does not silently overwrite either concept;
- confirm Generation only by explicit user action.

### Gate 4 — registered PPL/XPL/BSE

- place a physical point on reference BSE;
- register XPL to BSE explicitly;
- verify projected position on XPL;
- remove/disable registration and verify PetroLab stops claiming shared coordinates.

## Definition of done

This scenario is not complete merely because every page works independently.

It is complete when the two round trips work without context loss:

**plot → exact analysis → physical point → thin section/image → plot**

and

**thin section/image → physical point → linked analyses → plot/table/statistics → same physical point.**

No navigation step may broaden an exact selection, silently convert morphology into Generation, or duplicate scientific data just to preserve a view.
