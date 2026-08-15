from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from petrolab.db import DB_PATH, ensure_storage, list_projects
from petrolab.exchange_identity import get_exchange_workspace_uuid
from petrolab.project_archive import _safe_name


@dataclass(frozen=True)
class ExchangeSelection:
    """Explicit scientific scope for a colleague package.

    ``sample_ids`` means whole Samples. Other selectors are granular and pull only
    the minimum parent context necessary to understand the selected records.
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
    package_kind: str = "project"


def _tables(con: sqlite3.Connection) -> set[str]:
    return {str(row[0]) for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}


def _columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in con.execute(f"PRAGMA table_info({table})").fetchall()}


def _marks(values) -> str:
    return ",".join("?" for _ in values)


def _int_set(con: sqlite3.Connection, query: str, params=()) -> set[int]:
    return {int(row[0]) for row in con.execute(query, params).fetchall() if row[0] is not None}


def _str_set(con: sqlite3.Connection, query: str, params=()) -> set[str]:
    return {str(row[0]) for row in con.execute(query, params).fetchall() if row[0] is not None}


def _project(project_id: int) -> dict:
    for row in list_projects():
        if int(row["id"]) == int(project_id):
            return row
    raise KeyError(f"Проект {project_id} не найден")


def _accessible_dataset_ids(con: sqlite3.Connection, project_id: int) -> set[int]:
    tables = _tables(con)
    result: set[int] = set()
    if "project_dataset_links" in tables:
        result |= _int_set(
            con,
            "SELECT dataset_id FROM project_dataset_links WHERE project_id=?",
            (int(project_id),),
        )
    if "datasets" in tables and "project_id" in _columns(con, "datasets"):
        # Compatibility for workspaces predating the shared-library membership layer.
        result |= _int_set(con, "SELECT id FROM datasets WHERE project_id=?", (int(project_id),))
    return result


def _validate_project_ids(
    con: sqlite3.Connection,
    table: str,
    values,
    project_id: int,
) -> None:
    wanted = tuple(dict.fromkeys(int(value) for value in values))
    if not wanted:
        return
    if table not in _tables(con) or "project_id" not in _columns(con, table):
        raise ValueError(f"В базе нет проектной таблицы {table}")
    found = _int_set(
        con,
        f"SELECT id FROM {table} WHERE project_id=? AND id IN ({_marks(wanted)})",
        (int(project_id), *wanted),
    )
    if found != set(wanted):
        raise ValueError(f"Часть выбранных записей {table} не относится к текущему проекту")


def _validate_selection(
    con: sqlite3.Connection,
    project_id: int,
    selection: ExchangeSelection,
    accessible_datasets: set[int],
) -> None:
    _validate_project_ids(con, "samples", selection.sample_ids, project_id)
    if selection.entity_ids:
        _validate_project_ids(con, "physical_entities", selection.entity_ids, project_id)
    if selection.image_asset_ids:
        _validate_project_ids(con, "image_assets", selection.image_asset_ids, project_id)

    requested_datasets = {int(value) for value in selection.dataset_ids}
    if requested_datasets - accessible_datasets:
        raise ValueError("Выбран dataset, который не входит в рабочий контекст проекта")

    analysis_ids = tuple(dict.fromkeys(str(value) for value in selection.analysis_ids))
    if analysis_ids:
        rows = con.execute(
            f"SELECT analysis_id,dataset_id FROM analysis_rows WHERE analysis_id IN ({_marks(analysis_ids)})",
            analysis_ids,
        ).fetchall()
        found = {str(row[0]) for row in rows if int(row[1]) in accessible_datasets}
        if found != set(analysis_ids):
            raise ValueError("Часть выбранных аналитических точек не входит в рабочий контекст проекта")


def _entity_ancestors(con: sqlite3.Connection, entity_ids: set[int], project_id: int) -> bool:
    changed = False
    pending = list(entity_ids)
    seen = set(entity_ids)
    while pending:
        entity_id = pending.pop()
        row = con.execute(
            "SELECT parent_id,project_id FROM physical_entities WHERE id=?", (int(entity_id),)
        ).fetchone()
        if row and row[0] is not None:
            if int(row[1]) != int(project_id):
                raise ValueError("Иерархия физических объектов пересекает границу проекта")
            parent = int(row[0])
            if parent not in seen:
                seen.add(parent)
                entity_ids.add(parent)
                pending.append(parent)
                changed = True
    return changed


def _resolve_scope(
    con: sqlite3.Connection,
    project_id: int,
    selection: ExchangeSelection,
) -> dict[str, set]:
    tables = _tables(con)
    accessible = _accessible_dataset_ids(con, int(project_id))
    _validate_selection(con, int(project_id), selection, accessible)

    whole_samples = {int(value) for value in selection.sample_ids}
    sample_ids = set(whole_samples)
    entity_ids = {int(value) for value in selection.entity_ids}
    full_dataset_ids = {int(value) for value in selection.dataset_ids}
    dataset_ids = set(full_dataset_ids)
    analysis_ids = {str(value) for value in selection.analysis_ids}
    image_ids = {int(value) for value in selection.image_asset_ids}
    session_ids: set[int] = set()
    rock_ids: set[int] = set()
    observation_ids: set[int] = set()

    if not any((whole_samples, entity_ids, dataset_ids, analysis_ids, image_ids)):
        raise ValueError("Выберите хотя бы один Sample, шлиф/точку, dataset, анализ или изображение")

    if whole_samples:
        values = tuple(sorted(whole_samples))
        if "physical_entities" in tables:
            entity_ids |= _int_set(
                con,
                f"SELECT id FROM physical_entities WHERE project_id=? AND sample_id IN ({_marks(values)})",
                (int(project_id), *values),
            )
        if "analytical_sessions" in tables:
            session_ids |= _int_set(
                con,
                f"SELECT id FROM analytical_sessions WHERE project_id=? AND sample_id IN ({_marks(values)})",
                (int(project_id), *values),
            )
        if "datasets" in tables and "sample_id" in _columns(con, "datasets"):
            linked = _int_set(
                con,
                f"SELECT id FROM datasets WHERE sample_id IN ({_marks(values)})",
                values,
            ) & accessible
            dataset_ids |= linked
            full_dataset_ids |= linked
        if "rock_samples" in tables and "sample_id" in _columns(con, "rock_samples"):
            rock_ids |= _int_set(
                con,
                f"SELECT id FROM rock_samples WHERE project_id=? AND sample_id IN ({_marks(values)})",
                (int(project_id), *values),
            )

    # An explicitly selected image needs its dataset metadata, but never drags all
    # sibling points. Points remain an explicit scientific choice.
    if image_ids and "image_assets" in tables:
        values = tuple(sorted(image_ids))
        for row in con.execute(
            f"SELECT dataset_id FROM image_assets WHERE project_id=? AND id IN ({_marks(values)})",
            (int(project_id), *values),
        ).fetchall():
            if row[0] is not None and int(row[0]) in accessible:
                dataset_ids.add(int(row[0]))

    for _ in range(20):
        before = (
            frozenset(sample_ids), frozenset(entity_ids), frozenset(dataset_ids),
            frozenset(analysis_ids), frozenset(image_ids), frozenset(session_ids),
            frozenset(observation_ids),
        )

        if full_dataset_ids:
            values = tuple(sorted(full_dataset_ids))
            analysis_ids |= _str_set(
                con,
                f"SELECT analysis_id FROM analysis_rows WHERE dataset_id IN ({_marks(values)})",
                values,
            )

        if analysis_ids:
            values = tuple(sorted(analysis_ids))
            for row in con.execute(
                f"SELECT dataset_id FROM analysis_rows WHERE analysis_id IN ({_marks(values)})",
                values,
            ).fetchall():
                dataset_id = int(row[0])
                if dataset_id not in accessible:
                    raise ValueError("Аналитическая точка ссылается на dataset вне проекта")
                dataset_ids.add(dataset_id)

        if entity_ids and "physical_entities" in tables:
            _entity_ancestors(con, entity_ids, int(project_id))
            values = tuple(sorted(entity_ids))
            sample_ids |= _int_set(
                con,
                f"""SELECT sample_id FROM physical_entities
                    WHERE project_id=? AND id IN ({_marks(values)}) AND sample_id IS NOT NULL""",
                (int(project_id), *values),
            )

        if "observations" in tables and (entity_ids or analysis_ids):
            clauses: list[str] = []
            params: list[object] = [int(project_id)]
            if entity_ids:
                values = tuple(sorted(entity_ids))
                clauses.append(f"entity_id IN ({_marks(values)})")
                params.extend(values)
            if analysis_ids:
                values = tuple(sorted(analysis_ids))
                clauses.append(f"analysis_id IN ({_marks(values)})")
                params.extend(values)
            rows = con.execute(
                "SELECT id,entity_id,analysis_id,dataset_id,session_id FROM observations "
                "WHERE project_id=? AND (" + " OR ".join(clauses) + ")",
                params,
            ).fetchall()
            for row in rows:
                observation_ids.add(int(row[0]))
                if row[1] is not None:
                    entity_ids.add(int(row[1]))
                if row[2] is not None:
                    analysis_ids.add(str(row[2]))
                if row[3] is not None:
                    dataset_id = int(row[3])
                    if dataset_id not in accessible:
                        raise ValueError("Измерение ссылается на dataset вне рабочего проекта")
                    dataset_ids.add(dataset_id)
                if row[4] is not None:
                    session_ids.add(int(row[4]))

        if dataset_ids:
            unknown = dataset_ids - accessible
            if unknown:
                raise ValueError("Пакет попытался выйти за рабочий контекст проекта")
            values = tuple(sorted(dataset_ids))
            dataset_columns = _columns(con, "datasets")
            selected_columns = ["id"]
            if "sample_id" in dataset_columns:
                selected_columns.append("sample_id")
            if "session_id" in dataset_columns:
                selected_columns.append("session_id")
            for row in con.execute(
                f"SELECT {','.join(selected_columns)} FROM datasets WHERE id IN ({_marks(values)})",
                values,
            ).fetchall():
                offset = 1
                if "sample_id" in dataset_columns:
                    if row[offset] is not None:
                        sample_ids.add(int(row[offset]))
                    offset += 1
                if "session_id" in dataset_columns and row[offset] is not None:
                    session_ids.add(int(row[offset]))

        if session_ids and "analytical_sessions" in tables:
            values = tuple(sorted(session_ids))
            sample_ids |= _int_set(
                con,
                f"""SELECT sample_id FROM analytical_sessions
                    WHERE project_id=? AND id IN ({_marks(values)}) AND sample_id IS NOT NULL""",
                (int(project_id), *values),
            )

        if selection.include_related_images and analysis_ids and "image_assets" in tables:
            values = tuple(sorted(analysis_ids))
            if "image_analysis_links" in tables:
                image_ids |= _int_set(
                    con,
                    f"""SELECT l.asset_id FROM image_analysis_links l
                        JOIN image_assets i ON i.id=l.asset_id
                        WHERE i.project_id=? AND l.analysis_id IN ({_marks(values)})""",
                    (int(project_id), *values),
                )
            # Legacy one-point image link.
            image_ids |= _int_set(
                con,
                f"""SELECT id FROM image_assets
                    WHERE project_id=? AND analysis_id IN ({_marks(values)})""",
                (int(project_id), *values),
            )

        if selection.include_related_images and full_dataset_ids and "image_assets" in tables:
            values = tuple(sorted(full_dataset_ids))
            image_ids |= _int_set(
                con,
                f"""SELECT id FROM image_assets
                    WHERE project_id=? AND dataset_id IN ({_marks(values)})""",
                (int(project_id), *values),
            )

        after = (
            frozenset(sample_ids), frozenset(entity_ids), frozenset(dataset_ids),
            frozenset(analysis_ids), frozenset(image_ids), frozenset(session_ids),
            frozenset(observation_ids),
        )
        if after == before:
            break
    else:
        raise RuntimeError("Не удалось стабилизировать зависимости выборочного пакета")

    study_ids: set[int] = set()
    if dataset_ids and "dataset_studies" in tables:
        values = tuple(sorted(dataset_ids))
        study_ids |= _int_set(
            con,
            f"SELECT study_id FROM dataset_studies WHERE dataset_id IN ({_marks(values)})",
            values,
        )

    return {
        "samples": sample_ids,
        "entities": entity_ids,
        "sessions": session_ids,
        "datasets": dataset_ids,
        "analyses": analysis_ids,
        "observations": observation_ids,
        "studies": study_ids,
        "rocks": rock_ids,
        "images": image_ids,
        "full_datasets": full_dataset_ids,
    }


def _delete_not_in(con: sqlite3.Connection, table: str, column: str, allowed: set) -> None:
    if table not in _tables(con):
        return
    if not allowed:
        con.execute(f"DELETE FROM {table}")
        return
    values = tuple(sorted(allowed, key=str))
    con.execute(f"DELETE FROM {table} WHERE {column} NOT IN ({_marks(values)})", values)


def _filter_reference(con: sqlite3.Connection, table: str, column: str, allowed: set) -> None:
    if column not in _columns(con, table):
        return
    if allowed:
        values = tuple(sorted(allowed, key=str))
        con.execute(
            f"DELETE FROM {table} WHERE {column} IS NOT NULL AND {column} NOT IN ({_marks(values)})",
            values,
        )
    else:
        con.execute(f"DELETE FROM {table} WHERE {column} IS NOT NULL")


def _prune_snapshot(
    snapshot: Path,
    project_id: int,
    selection: ExchangeSelection,
) -> tuple[dict[str, set], list[Path], list[tuple[int, Path]], str]:
    con = sqlite3.connect(snapshot)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA foreign_keys=OFF")
        scope = _resolve_scope(con, int(project_id), selection)
        tables = _tables(con)

        # Capture external files before paths/rows are normalized for portability.
        source_paths: list[Path] = []
        if selection.include_sources and scope["datasets"]:
            values = tuple(sorted(scope["datasets"]))
            seen: set[Path] = set()
            for row in con.execute(
                f"SELECT source_path FROM datasets WHERE id IN ({_marks(values)})", values
            ).fetchall():
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

        image_paths: list[tuple[int, Path]] = []
        if scope["images"] and "image_assets" in tables:
            values = tuple(sorted(scope["images"]))
            for row in con.execute(
                f"SELECT id,stored_path FROM image_assets WHERE id IN ({_marks(values)})", values
            ).fetchall():
                value = str(row[1] or "").strip()
                if not value:
                    continue
                path = Path(value).expanduser()
                try:
                    path = path.resolve()
                except OSError:
                    continue
                if path.is_file():
                    image_paths.append((int(row[0]), path))

        workspace_uuid = ""
        if "exchange_workspace_identity" in tables:
            row = con.execute(
                "SELECT workspace_uuid FROM exchange_workspace_identity WHERE singleton=1"
            ).fetchone()
            workspace_uuid = str(row[0]) if row else ""

        _delete_not_in(con, "samples", "id", scope["samples"])
        _delete_not_in(con, "physical_entities", "id", scope["entities"])
        _delete_not_in(con, "analytical_sessions", "id", scope["sessions"])
        _delete_not_in(con, "datasets", "id", scope["datasets"])
        _delete_not_in(con, "analysis_rows", "analysis_id", scope["analyses"])
        _delete_not_in(con, "observations", "id", scope["observations"])
        _delete_not_in(con, "studies", "id", scope["studies"])
        _delete_not_in(con, "rock_samples", "id", scope["rocks"])
        _delete_not_in(con, "image_assets", "id", scope["images"])

        # The package represents one working context even if a raw dataset is owned by
        # the hidden shared library in the source workspace.
        for table in ("datasets", "analytical_sessions", "physical_entities", "observations", "studies", "rock_samples", "image_assets"):
            if table in tables and "project_id" in _columns(con, table):
                con.execute(f"UPDATE {table} SET project_id=?", (int(project_id),))
        if "image_assets" in tables:
            if scope["analyses"]:
                values = tuple(sorted(scope["analyses"]))
                con.execute(
                    f"UPDATE image_assets SET analysis_id=NULL WHERE analysis_id IS NOT NULL AND analysis_id NOT IN ({_marks(values)})",
                    values,
                )
            else:
                con.execute("UPDATE image_assets SET analysis_id=NULL WHERE analysis_id IS NOT NULL")

        if "projects" in tables:
            con.execute("DELETE FROM projects WHERE id<>?", (int(project_id),))

        # Rebuild project membership so every retained raw dataset belongs to this package context.
        if "project_dataset_links" in tables:
            con.execute("DELETE FROM project_dataset_links")
            link_columns = _columns(con, "project_dataset_links")
            for dataset_id in sorted(scope["datasets"]):
                names = ["project_id", "dataset_id"]
                values: list[object] = [int(project_id), int(dataset_id)]
                if "note" in link_columns:
                    names.append("note")
                    values.append("Передано выборочным пакетом PetroLab")
                if "added_at" in link_columns:
                    names.append("added_at")
                    values.append("exchange")
                if "purpose" in link_columns:
                    names.append("purpose")
                    values.append("working")
                con.execute(
                    f"INSERT INTO project_dataset_links({','.join(names)}) VALUES ({_marks(names)})",
                    values,
                )

        # Keep only scientific child metadata that can be understood by the receiver.
        references = {
            "analysis_id": scope["analyses"],
            "dataset_id": scope["datasets"],
            "sample_id": scope["samples"],
            "entity_id": scope["entities"],
            "session_id": scope["sessions"],
            "study_id": scope["studies"],
            "rock_id": scope["rocks"],
            "asset_id": scope["images"],
        }
        protected = {
            "projects", "samples", "physical_entities", "analytical_sessions", "datasets",
            "project_dataset_links", "analysis_rows", "observations", "studies", "rock_samples",
            "image_assets", "exchange_workspace_identity",
        }
        explicit_children = {
            "sample_aliases", "dataset_studies", "semantic_mappings", "rock_compositions",
            "rock_isotopes", "rock_mineral_links", "image_analysis_links",
        }
        for table in tables:
            if table.startswith("sqlite_") or table in protected:
                continue
            columns = _columns(con, table)
            keep = table in explicit_children or (table.startswith("analysis_") and "analysis_id" in columns)
            keep = keep or (table.startswith("dataset_") and "dataset_id" in columns)
            keep = keep or (table.startswith("analytical_") and "session_id" in columns)
            if not keep:
                con.execute(f"DELETE FROM {table}")
                continue
            for column, allowed in references.items():
                if column in columns:
                    _filter_reference(con, table, column, allowed)

        if "datasets" in tables:
            dataset_columns = _columns(con, "datasets")
            if "row_count" in dataset_columns:
                con.execute(
                    """UPDATE datasets SET row_count=(
                           SELECT COUNT(*) FROM analysis_rows a WHERE a.dataset_id=datasets.id
                       )"""
                )
            if "source_path" in dataset_columns:
                con.execute("UPDATE datasets SET source_path='' ")
            if "sync_enabled" in dataset_columns:
                con.execute("UPDATE datasets SET sync_enabled=0")

        con.commit()
        check = con.execute("PRAGMA integrity_check").fetchone()[0]
        if check != "ok":
            raise ValueError(f"Не удалось собрать целостный пакет: {check}")
        return scope, source_paths, image_paths, workspace_uuid
    finally:
        con.close()


def create_exchange_package(
    project_id: int,
    destination: str | Path,
    selection: ExchangeSelection,
) -> ExchangePackageResult:
    """Create a minimal single-file .petrolab package for explicit colleague exchange."""
    ensure_storage()
    project = _project(int(project_id))
    # Persist this before the SQLite snapshot; repeated packages from the same workspace
    # then share one origin identity and can be merged additively without duplication.
    workspace_uuid = get_exchange_workspace_uuid()

    target = Path(destination).expanduser()
    if target.suffix.lower() != ".petrolab":
        target = target.with_suffix(".petrolab")
    target.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="petrolab_exchange_") as temp_dir:
        root = Path(temp_dir)
        database_dir = root / "database"
        database_dir.mkdir(parents=True, exist_ok=True)
        snapshot = database_dir / DB_PATH.name
        shutil.copy2(DB_PATH, snapshot)
        scope, source_paths, image_paths, packed_workspace_uuid = _prune_snapshot(
            snapshot, int(project_id), selection
        )
        if packed_workspace_uuid and packed_workspace_uuid != workspace_uuid:
            raise ValueError("Не удалось зафиксировать идентичность исходного PetroLab")

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
                image_map.append({
                    "asset_id": int(asset_id),
                    "archive_name": archive_name,
                    "original_name": path.name,
                })

        manifest = {
            "format": "petrolab-project-archive",
            "format_version": 3,
            "package_kind": "selection",
            "source_workspace_uuid": workspace_uuid,
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
        target.resolve(),
        len(scope["samples"]),
        len(scope["entities"]),
        len(scope["datasets"]),
        len(scope["analyses"]),
        len(image_paths),
        len(source_paths),
    )


def preview_exchange_package(path: str | Path) -> ExchangePreview:
    """Inspect a PetroLab package before a destination project is chosen."""
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    with tempfile.TemporaryDirectory(prefix="petrolab_exchange_preview_") as temp_dir:
        root = Path(temp_dir)
        with zipfile.ZipFile(source, "r") as archive:
            resolved_root = root.resolve()
            for member in archive.infolist():
                candidate = (root / member.filename).resolve()
                if candidate != resolved_root and resolved_root not in candidate.parents:
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
            def count(table: str) -> int:
                return int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) if table in tables else 0
            return ExchangePreview(
                int(project[0]), str(project[1]), count("samples"), count("physical_entities"),
                count("datasets"), count("analysis_rows"), count("image_assets"),
                str(manifest.get("package_kind") or "project"),
            )
        finally:
            con.close()
