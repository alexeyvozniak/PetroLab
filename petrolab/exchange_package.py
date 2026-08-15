from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from petrolab.db import ASSETS_DIR, DB_PATH, connect, ensure_storage, list_projects
from petrolab.project_archive import _project_database_snapshot, _safe_name


@dataclass(frozen=True)
class ExchangeSelection:
    """Explicit scientific scope for a colleague package.

    Selecting a Sample means "the whole Sample". Selecting individual entities,
    datasets, analyses or images keeps only those objects plus the minimum parent
    context required to make them meaningful after import.
    """

    sample_ids: tuple[int, ...] = ()
    entity_ids: tuple[int, ...] = ()
    dataset_ids: tuple[int, ...] = ()
    analysis_ids: tuple[str, ...] = ()
    image_asset_ids: tuple[int, ...] = ()
    include_sources: bool = False
    include_related_images: bool = True


@dataclass(frozen=True)
class ExchangePackageResult:
    path: Path
    sample_count: int
    entity_count: int
    dataset_count: int
    analysis_count: int
    image_count: int
    source_count: int


@dataclass(frozen=True)
class ExchangePreview:
    project_id: int
    project_name: str
    sample_count: int
    entity_count: int
    dataset_count: int
    analysis_count: int
    image_count: int


def _tables(con: sqlite3.Connection) -> set[str]:
    return {str(row[0]) for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}


def _columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in con.execute(f"PRAGMA table_info({table})").fetchall()}


def _marks(values) -> str:
    return ",".join("?" for _ in values)


def _ids(con: sqlite3.Connection, query: str, params=()) -> set[int]:
    return {int(row[0]) for row in con.execute(query, params).fetchall()}


def _strings(con: sqlite3.Connection, query: str, params=()) -> set[str]:
    return {str(row[0]) for row in con.execute(query, params).fetchall() if row[0] is not None}


def _project(project_id: int) -> dict:
    for row in list_projects():
        if int(row["id"]) == int(project_id):
            return row
    raise KeyError(f"Проект {project_id} не найден")


def _validate_subset(con: sqlite3.Connection, table: str, ids, project_id: int, *, string_ids: bool = False) -> None:
    values = tuple(dict.fromkeys(ids))
    if not values:
        return
    tables = _tables(con)
    if table not in tables:
        raise ValueError(f"В базе нет таблицы {table}, но для пакета выбраны связанные записи")
    columns = _columns(con, table)
    key = "analysis_id" if string_ids else "id"
    if table == "analysis_rows":
        query = f"""SELECT a.analysis_id
                    FROM analysis_rows a
                    JOIN datasets d ON d.id=a.dataset_id
                    WHERE d.project_id=? AND a.analysis_id IN ({_marks(values)})"""
        found = {str(row[0]) for row in con.execute(query, (int(project_id), *values)).fetchall()}
        expected = {str(value) for value in values}
    elif "project_id" in columns:
        query = f"SELECT {key} FROM {table} WHERE project_id=? AND {key} IN ({_marks(values)})"
        found = {row[0] for row in con.execute(query, (int(project_id), *values)).fetchall()}
        expected = set(values)
    else:
        raise ValueError(f"Нельзя безопасно проверить принадлежность записей {table} проекту")
    if found != expected:
        missing = expected - found
        raise ValueError(f"Выбранные записи {table} не относятся к проекту: {sorted(missing, key=str)}")


def _add_entity_ancestors(con: sqlite3.Connection, entity_ids: set[int]) -> None:
    pending = list(entity_ids)
    while pending:
        entity_id = pending.pop()
        row = con.execute("SELECT parent_id FROM physical_entities WHERE id=?", (int(entity_id),)).fetchone()
        if row and row[0] is not None:
            parent = int(row[0])
            if parent not in entity_ids:
                entity_ids.add(parent)
                pending.append(parent)


def _resolve_scope(con: sqlite3.Connection, project_id: int, selection: ExchangeSelection) -> dict[str, set]:
    tables = _tables(con)
    _validate_subset(con, "samples", selection.sample_ids, project_id)
    if selection.entity_ids:
        _validate_subset(con, "physical_entities", selection.entity_ids, project_id)
    _validate_subset(con, "datasets", selection.dataset_ids, project_id)
    _validate_subset(con, "analysis_rows", selection.analysis_ids, project_id, string_ids=True)
    if selection.image_asset_ids:
        _validate_subset(con, "image_assets", selection.image_asset_ids, project_id)

    whole_samples = {int(value) for value in selection.sample_ids}
    sample_ids = set(whole_samples)
    entity_ids = {int(value) for value in selection.entity_ids}
    full_dataset_ids = {int(value) for value in selection.dataset_ids}
    dataset_ids = set(full_dataset_ids)
    analysis_ids = {str(value) for value in selection.analysis_ids}
    image_ids = {int(value) for value in selection.image_asset_ids}
    session_ids: set[int] = set()
    rock_ids: set[int] = set()

    if not any((whole_samples, entity_ids, dataset_ids, analysis_ids, image_ids)):
        raise ValueError("Выберите хотя бы один Sample, шлиф/точку, dataset, анализ или изображение")

    # A Sample selection intentionally means the complete scientific subtree.
    if whole_samples:
        values = tuple(sorted(whole_samples))
        if "physical_entities" in tables:
            entity_ids |= _ids(con, f"SELECT id FROM physical_entities WHERE sample_id IN ({_marks(values)})", values)
        if "analytical_sessions" in tables:
            session_ids |= _ids(con, f"SELECT id FROM analytical_sessions WHERE sample_id IN ({_marks(values)})", values)
        if "datasets" in tables and "sample_id" in _columns(con, "datasets"):
            linked = _ids(con, f"SELECT id FROM datasets WHERE sample_id IN ({_marks(values)})", values)
            dataset_ids |= linked
            full_dataset_ids |= linked
        if "rock_samples" in tables and "sample_id" in _columns(con, "rock_samples"):
            rock_ids |= _ids(con, f"SELECT id FROM rock_samples WHERE sample_id IN ({_marks(values)})", values)

    # Explicit image selection can bring point links and the minimum dataset context.
    if image_ids and "image_assets" in tables:
        values = tuple(sorted(image_ids))
        rows = con.execute(
            f"SELECT id,dataset_id,analysis_id FROM image_assets WHERE id IN ({_marks(values)})", values
        ).fetchall()
        for row in rows:
            if row[1] is not None:
                dataset_ids.add(int(row[1]))
            if row[2]:
                analysis_ids.add(str(row[2]))
        if "image_analysis_links" in tables:
            analysis_ids |= _strings(
                con,
                f"SELECT analysis_id FROM image_analysis_links WHERE asset_id IN ({_marks(values)})",
                values,
            )

    # Full datasets include all rows. Point-selected datasets remain metadata-only except for selected rows.
    if full_dataset_ids:
        values = tuple(sorted(full_dataset_ids))
        analysis_ids |= _strings(
            con,
            f"SELECT analysis_id FROM analysis_rows WHERE dataset_id IN ({_marks(values)})",
            values,
        )

    # Explicit analysis points determine their dataset and any physical target recorded in observations.
    if analysis_ids:
        values = tuple(sorted(analysis_ids))
        dataset_ids |= _ids(
            con,
            f"SELECT DISTINCT dataset_id FROM analysis_rows WHERE analysis_id IN ({_marks(values)})",
            values,
        )
        if "observations" in tables:
            for row in con.execute(
                f"SELECT entity_id,dataset_id,session_id FROM observations WHERE analysis_id IN ({_marks(values)})",
                values,
            ).fetchall():
                if row[0] is not None:
                    entity_ids.add(int(row[0]))
                if row[1] is not None:
                    dataset_ids.add(int(row[1]))
                if row[2] is not None:
                    session_ids.add(int(row[2]))

    # An explicitly selected physical target pulls its own observations, but not sibling points.
    if entity_ids and "physical_entities" in tables:
        _add_entity_ancestors(con, entity_ids)
        values = tuple(sorted(entity_ids))
        sample_ids |= _ids(
            con,
            f"SELECT DISTINCT sample_id FROM physical_entities WHERE id IN ({_marks(values)}) AND sample_id IS NOT NULL",
            values,
        )
        if "observations" in tables:
            for row in con.execute(
                f"SELECT analysis_id,dataset_id,session_id FROM observations WHERE entity_id IN ({_marks(values)})",
                values,
            ).fetchall():
                if row[0]:
                    analysis_ids.add(str(row[0]))
                if row[1] is not None:
                    dataset_ids.add(int(row[1]))
                if row[2] is not None:
                    session_ids.add(int(row[2]))

    # Resolve dataset parents after all point/entity dependencies are known.
    if dataset_ids:
        values = tuple(sorted(dataset_ids))
        dataset_cols = _columns(con, "datasets")
        select = ["id"]
        if "sample_id" in dataset_cols:
            select.append("sample_id")
        if "session_id" in dataset_cols:
            select.append("session_id")
        for row in con.execute(
            f"SELECT {','.join(select)} FROM datasets WHERE id IN ({_marks(values)})", values
        ).fetchall():
            offset = 1
            if "sample_id" in dataset_cols:
                if row[offset] is not None:
                    sample_ids.add(int(row[offset]))
                offset += 1
            if "session_id" in dataset_cols and row[offset] is not None:
                session_ids.add(int(row[offset]))

    if session_ids and "analytical_sessions" in tables:
        values = tuple(sorted(session_ids))
        sample_ids |= _ids(
            con,
            f"SELECT DISTINCT sample_id FROM analytical_sessions WHERE id IN ({_marks(values)}) AND sample_id IS NOT NULL",
            values,
        )

    # Related point-linked images are useful context; dataset-wide images follow only full datasets.
    if selection.include_related_images and "image_assets" in tables:
        if analysis_ids and "image_analysis_links" in tables:
            values = tuple(sorted(analysis_ids))
            image_ids |= _ids(
                con,
                f"SELECT DISTINCT asset_id FROM image_analysis_links WHERE analysis_id IN ({_marks(values)})",
                values,
            )
        if full_dataset_ids:
            values = tuple(sorted(full_dataset_ids))
            image_ids |= _ids(
                con,
                f"SELECT id FROM image_assets WHERE dataset_id IN ({_marks(values)})",
                values,
            )

    study_ids: set[int] = set()
    if dataset_ids and "dataset_studies" in tables:
        values = tuple(sorted(dataset_ids))
        study_ids |= _ids(
            con,
            f"SELECT DISTINCT study_id FROM dataset_studies WHERE dataset_id IN ({_marks(values)})",
            values,
        )

    # If a whole Sample was selected, retain only rocks linked to it; fragment selections do not
    # unexpectedly pull unrelated whole-rock data.
    return {
        "samples": sample_ids,
        "entities": entity_ids,
        "sessions": session_ids,
        "datasets": dataset_ids,
        "analyses": analysis_ids,
        "studies": study_ids,
        "rocks": rock_ids,
        "images": image_ids,
        "full_datasets": full_dataset_ids,
    }


def _delete_not_in(con: sqlite3.Connection, table: str, column: str, allowed: set) -> None:
    if table not in _tables(con):
        return
    if allowed:
        values = tuple(sorted(allowed, key=str))
        con.execute(f"DELETE FROM {table} WHERE {column} NOT IN ({_marks(values)})", values)
    else:
        con.execute(f"DELETE FROM {table}")


def _prune_snapshot(snapshot: Path, project_id: int, selection: ExchangeSelection) -> tuple[dict[str, set], list[Path]]:
    con = sqlite3.connect(snapshot)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA foreign_keys=OFF")
        scope = _resolve_scope(con, int(project_id), selection)
        tables = _tables(con)

        _delete_not_in(con, "samples", "id", scope["samples"])
        _delete_not_in(con, "physical_entities", "id", scope["entities"])
        _delete_not_in(con, "analytical_sessions", "id", scope["sessions"])
        _delete_not_in(con, "datasets", "id", scope["datasets"])
        _delete_not_in(con, "analysis_rows", "analysis_id", scope["analyses"])
        _delete_not_in(con, "studies", "id", scope["studies"])
        _delete_not_in(con, "rock_samples", "id", scope["rocks"])
        _delete_not_in(con, "image_assets", "id", scope["images"])

        # Keep observations only when every non-null reference still has a retained parent.
        if "observations" in tables:
            clauses = []
            params: list[object] = []
            for column, allowed in (
                ("entity_id", scope["entities"]),
                ("analysis_id", scope["analyses"]),
                ("dataset_id", scope["datasets"]),
                ("session_id", scope["sessions"]),
            ):
                if allowed:
                    values = tuple(sorted(allowed, key=str))
                    clauses.append(f"({column} IS NULL OR {column} IN ({_marks(values)}))")
                    params.extend(values)
                else:
                    clauses.append(f"{column} IS NULL")
            con.execute("DELETE FROM observations WHERE NOT (" + " AND ".join(clauses) + ")", params)

        # Generic child tables are trimmed by their nearest retained owner. This covers aliases,
        # generations, annotations, semantic mappings, rock chemistry and image point links.
        references = (
            ("analysis_id", scope["analyses"]),
            ("dataset_id", scope["datasets"]),
            ("sample_id", scope["samples"]),
            ("entity_id", scope["entities"]),
            ("session_id", scope["sessions"]),
            ("study_id", scope["studies"]),
            ("rock_id", scope["rocks"]),
            ("asset_id", scope["images"]),
        )
        protected = {
            "projects", "samples", "physical_entities", "analytical_sessions", "datasets",
            "analysis_rows", "studies", "rock_samples", "image_assets", "observations",
        }
        for table in tables:
            if table.startswith("sqlite_") or table in protected:
                continue
            columns = _columns(con, table)
            matched = False
            for column, allowed in references:
                if column not in columns:
                    continue
                matched = True
                if allowed:
                    values = tuple(sorted(allowed, key=str))
                    con.execute(
                        f"DELETE FROM {table} WHERE {column} IS NOT NULL AND {column} NOT IN ({_marks(values)})",
                        values,
                    )
                else:
                    con.execute(f"DELETE FROM {table} WHERE {column} IS NOT NULL")
                break
            if matched:
                continue
            # Do not leak unrelated project-local UI/history rows into a tiny colleague package.
            if "project_id" in columns and table not in {"projects"}:
                con.execute(f"DELETE FROM {table}")

        # Project row is context, never a second project payload.
        con.execute("DELETE FROM projects WHERE id<>?", (int(project_id),))
        if "datasets" in tables and "row_count" in _columns(con, "datasets"):
            con.execute(
                """UPDATE datasets
                   SET row_count=(SELECT COUNT(*) FROM analysis_rows a WHERE a.dataset_id=datasets.id)"""
            )
        con.commit()

        check = con.execute("PRAGMA integrity_check").fetchone()[0]
        if check != "ok":
            raise ValueError(f"Не удалось собрать целостный пакет: {check}")

        source_paths: list[Path] = []
        if selection.include_sources and scope["datasets"]:
            values = tuple(sorted(scope["datasets"]))
            rows = con.execute(
                f"SELECT source_path FROM datasets WHERE id IN ({_marks(values)})", values
            ).fetchall()
            seen: set[Path] = set()
            for row in rows:
                value = str(row[0] or "").strip()
                if not value:
                    continue
                path = Path(value).expanduser()
                try:
                    path = path.resolve()
                except OSError:
                    continue
                if path.is_file() and path not in seen:
                    seen.add(path)
                    source_paths.append(path)
        return scope, source_paths
    finally:
        con.close()


def _selected_image_paths(snapshot: Path, image_ids: set[int]) -> list[tuple[int, Path]]:
    if not image_ids:
        return []
    con = sqlite3.connect(snapshot)
    try:
        tables = _tables(con)
        if "image_assets" not in tables:
            return []
        values = tuple(sorted(image_ids))
        rows = con.execute(
            f"SELECT id,stored_path FROM image_assets WHERE id IN ({_marks(values)})", values
        ).fetchall()
    finally:
        con.close()
    result: list[tuple[int, Path]] = []
    for asset_id, stored_path in rows:
        value = str(stored_path or "").strip()
        if not value:
            continue
        path = Path(value).expanduser()
        try:
            path = path.resolve()
        except OSError:
            continue
        if path.is_file():
            result.append((int(asset_id), path))
    return result


def create_exchange_package(
    project_id: int,
    destination: str | Path,
    selection: ExchangeSelection,
) -> ExchangePackageResult:
    """Create a minimal .petrolab package for explicit colleague exchange."""
    ensure_storage()
    project = _project(int(project_id))
    target = Path(destination).expanduser()
    if target.suffix.lower() != ".petrolab":
        target = target.with_suffix(".petrolab")
    target.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="petrolab_exchange_") as temp_dir:
        root = Path(temp_dir)
        database_dir = root / "database"
        database_dir.mkdir(parents=True, exist_ok=True)
        snapshot = database_dir / DB_PATH.name
        _project_database_snapshot(int(project_id), snapshot)
        scope, source_paths = _prune_snapshot(snapshot, int(project_id), selection)
        image_paths = _selected_image_paths(snapshot, scope["images"])

        source_map: list[dict] = []
        if source_paths:
            source_dir = root / "sources"
            source_dir.mkdir(parents=True, exist_ok=True)
            for index, path in enumerate(source_paths, start=1):
                archive_name = f"{index:03d}_{_safe_name(path.name)}"
                shutil.copy2(path, source_dir / archive_name)
                source_map.append({"archive_name": archive_name, "original_name": path.name})

        image_map: list[dict] = []
        if image_paths:
            image_dir = root / "images"
            image_dir.mkdir(parents=True, exist_ok=True)
            for asset_id, path in image_paths:
                archive_name = f"asset_{asset_id}_{_safe_name(path.name)}"
                shutil.copy2(path, image_dir / archive_name)
                image_map.append({"asset_id": asset_id, "archive_name": archive_name, "original_name": path.name})

        manifest = {
            "format": "petrolab-project-archive",
            "format_version": 3,
            "package_kind": "selection",
            "project": {
                "id": int(project["id"]),
                "name": str(project["name"]),
                "description": str(project.get("description") or ""),
            },
            "selection": {
                "sample_count": len(scope["samples"]),
                "entity_count": len(scope["entities"]),
                "dataset_count": len(scope["datasets"]),
                "analysis_count": len(scope["analyses"]),
                "image_count": len(scope["images"]),
                "whole_sample_ids": sorted(int(value) for value in selection.sample_ids),
            },
            "source_files": source_map,
            "images": image_map,
        }
        (root / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in root.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(root))

    return ExchangePackageResult(
        target.resolve(), len(scope["samples"]), len(scope["entities"]), len(scope["datasets"]),
        len(scope["analyses"]), len(image_paths), len(source_paths),
    )


def preview_exchange_package(path: str | Path) -> ExchangePreview:
    """Inspect a PetroLab package without choosing a destination project."""
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    with tempfile.TemporaryDirectory(prefix="petrolab_exchange_preview_") as temp_dir:
        root = Path(temp_dir)
        with zipfile.ZipFile(source, "r") as archive:
            destination_root = root.resolve()
            for member in archive.infolist():
                destination = (root / member.filename).resolve()
                if destination != destination_root and destination_root not in destination.parents:
                    raise ValueError("Архив содержит небезопасный путь")
            archive.extractall(root)
        manifest_path = root / "manifest.json"
        database = root / "database" / DB_PATH.name
        if not manifest_path.is_file() or not database.is_file():
            raise ValueError("В пакете отсутствует manifest или база PetroLab")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("format") != "petrolab-project-archive":
            raise ValueError("Это не пакет PetroLab")
        con = sqlite3.connect(database)
        try:
            tables = _tables(con)
            project = con.execute("SELECT id,name FROM projects LIMIT 1").fetchone()
            if not project:
                raise ValueError("В пакете отсутствует проект")
            count = lambda table: int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) if table in tables else 0
            return ExchangePreview(
                int(project[0]), str(project[1]), count("samples"), count("physical_entities"),
                count("datasets"), count("analysis_rows"), count("image_assets"),
            )
        finally:
            con.close()
