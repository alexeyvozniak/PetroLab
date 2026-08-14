# PetroLab storage and portable exchange

PetroLab has one canonical working database and two portable scopes.

## Working storage

The live scientific registry is a SQLite database named `petrolab.sqlite3` in the PetroLab data directory. Projects are logical scientific contexts inside that database; they are not separate SQLite files. Images and other large binary assets are stored beside the database and linked from it.

This lets the same PetroLab installation search across projects while still preserving project-local interpretation and provenance.

## `.petrolab` packages

`.petrolab` is the single portable container used for exchange and backup. Version 3 is a ZIP-compatible container with:

- `manifest.json` — format version, payload scope and counts;
- `database/petrolab.sqlite3` — a scoped SQLite snapshot;
- optional `images/`;
- optional `sources/`.

The manifest distinguishes two payloads:

- `payload_kind: project` — a complete portable project for backup/transfer;
- `payload_kind: fragment` — a deliberately small collaboration subset, for example one thin section with only EDS probe points and LA-ICP-MS craters.

Legacy project packages from format versions 1 and 2 remain readable.

## Safe import rules

A full project package can restore an empty workspace (or explicitly replace one after backup).

A fragment is never allowed to replace the workspace. It must be merged into an existing project. PetroLab asks the recipient to map every incoming Sample explicitly; similar names are suggestions only. Internal dataset, analysis, physical-entity and observation IDs are remapped as required, while method, unit, uncertainty and provenance are preserved.

The fragment exporter follows the physical hierarchy `Sample → thin section → grain → probe point / LA crater → observation`. Unselected analytical modalities and unrelated project data are omitted.
