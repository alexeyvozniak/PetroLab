from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from petrolab.db import ASSETS_DIR, DB_PATH, ensure_storage, list_accessible_datasets, list_projects
from petrolab.measurement_registry import ensure_measurement_registry_schema
from petrolab.project_archive import _safe_name
from petrolab.sample_registry import list_samples


@dataclass(frozen=True)
class FragmentArchiveResult:
    path: Path
    sample_count: int
    thin_section_count: int
    entity_count: int
    observation_count: int
    dataset_count: int
    analysis_count: int
    source_count: int
    image_count: int


def _tables(con: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }


def _columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in con.execute(f"PRAGMA table_info({table})").fetchall()}


def _delete_not_in(con: sqlite3.Connection, table: str, column: str, allowed: set[object]) -> None:
    """Strict fragment pruning: rows without the retained parent are not portable context."""
    if allowed:
        marks = ",".join("?" for _ in allowed)
        con.execute(
            f"DELETE FROM {table} WHERE {column} IS NULL OR {column} NOT IN ({marks})",
            tuple(allowed),
        )
    else:
        con.execute(f"DELETE FROM {table}")


def _project(project_id: int) -> dict:
    for project in list_projects():
        if int(project["id"]) == int(project_id):
            return project
    raise KeyError(f"Проект {project_id} не найден")


def _sample(project_id: int, sample_id: int) -> dict:
    for sample in list_samples(int(project_id)):
        if int(sample["id"]) == int(sample_id):
            return sample
    raise KeyError(f"Sample {sample_id} не найден в проекте")


def _selected_entity_ids(
    con: sqlite3.Connection,
    *,
    project_id: int,
    sample_id: int,
    thin_section_ids: Iterable[int] | None,
    include_eds: bool,
    include_la: bool,
    include_other: bool,
) -> tuple[set[int], set[int]]:
    tables = _tables(con)
    if "physical_entities" not in tables:
        return set(), set()

    rows = con.execute(
        "SELECT id,parent_id,kind FROM physical_entities WHERE project_id=? AND sample_id=? ORDER BY id",
        (int(project_id), int(sample_id)),
    ).fetchall()
    if not rows:
        return set(), set()

    by_id = {int(row[0]): row for row in rows}
    children: dict[int, list[int]] = {}
    for row in rows:
        if row[1] is not None:
            children.setdefault(int(row[1]), []).append(int(row[0]))

    available_sections = {int(row[0]) for row in rows if str(row[2]) == "thin_section"}
    requested_sections = (
        {int(value) for value in thin_section_ids}
        if thin_section_ids is not None
        else set(available_sections)
    )
    if not requested_sections.issubset(available_sections):
        raise ValueError("Выбранный шлиф не относится к Sample или проекту")

    selected: set[int] = set()

    def include_node(entity_id: int) -> None:
        row = by_id[entity_id]
        kind = str(row[2])
        allowed = (
            kind in {"thin_section", "grain"}
            or (kind == "probe_point" and include_eds)
            or (kind == "la_crater" and include_la)
            or (kind == "aliquot" and include_other)
        )
        if allowed:
            selected.add(entity_id)
        if kind in {"thin_section", "grain"}:
            for child_id in children.get(entity_id, []):
                include_node(child_id)

    for section_id in sorted(requested_sections):
        include_node(section_id)

    return selected, requested_sections


def _method_bucket(method: str) -> str:
    token = str(method or "").strip().upper().replace("–", "-")
    if any(key in token for key in ("LA-ICP", "LA ICP", "LASER", "ABLATION")):
        return "la"
    if any(key in token for key in ("EDS", "EDX", "EPMA", "WDS", "MICROPROBE", "SEM")):
        return "eds"
    return "other"


def _selected_observation_ids(
    con: sqlite3.Connection,
    *,
    project_id: int,
    entity_ids: set[int],
    include_eds: bool,
    include_la: bool,
    include_other: bool,
) -> set[int]:
    if "observations" not in _tables(con):
        return set()
    if not entity_ids:
        return set()
    marks = ",".join("?" for _ in entity_ids)
    rows = con.execute(
        f"""SELECT o.id,o.entity_id,o.method,e.kind
            FROM observations o
            LEFT JOIN physical_entities e ON e.id=o.entity_id
            WHERE o.project_id=? AND o.entity_id IN ({marks})""",
        (int(project_id), *sorted(entity_ids)),
    ).fetchall()
    selected: set[int] = set()
    for row in rows:
        kind = str(row[3] or "")
        bucket = "la" if kind == "la_crater" else "eds" if kind == "probe_point" else _method_bucket(str(row[2] or ""))
        if (bucket == "eds" and include_eds) or (bucket == "la" and include_la) or (bucket == "other" and include_other):
            selected.add(int(row[0]))
    return selected


def _ids_from_rows(
    con: sqlite3.Connection,
    table: str,
    id_column: str,
    where_column: str,
    where_ids: set[object],
) -> set[object]:
    if table not in _tables(con) or not where_ids:
        return set()
    marks = ",".join("?" for _ in where_ids)
    return {
        row[0]
        for row in con.execute(
            f"SELECT DISTINCT {id_column} FROM {table} WHERE {where_column} IN ({marks}) AND {id_column} IS NOT NULL",
            tuple(where_ids),
        ).fetchall()
    }


def _scope_snapshot(
    source_db: Path,
    target_db: Path,
    *,
    project_id: int,
    sample_id: int,
    thin_section_ids: Iterable[int] | None,
    include_eds: bool,
    include_la: bool,
    include_other: bool,
    extra_dataset_ids: Iterable[int] | None,
) -> dict:
    shutil.copy2(source_db, target_db)
    con = sqlite3.connect(target_db)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA foreign_keys=OFF")
        tables = _tables(con)
        entity_ids, selected_sections = _selected_entity_ids(
            con,
            project_id=project_id,
            sample_id=sample_id,
            thin_section_ids=thin_section_ids,
            include_eds=include_eds,
            include_la=include_la,
            include_other=include_other,
        )
        observation_ids = _selected_observation_ids(
            con,
            project_id=project_id,
            entity_ids=entity_ids,
            include_eds=include_eds,
            include_la=include_la,
            include_other=include_other,
        )

        analysis_ids: set[str] = set()
        dataset_ids: set[int] = {int(value) for value in (extra_dataset_ids or [])}
        session_ids: set[int] = set()
        if "observations" in tables and observation_ids:
            marks = ",".join("?" for _ in observation_ids)
            for row in con.execute(
                f"SELECT analysis_id,dataset_id,session_id FROM observations WHERE id IN ({marks})",
                tuple(sorted(observation_ids)),
            ).fetchall():
                if row[0] is not None:
                    analysis_ids.add(str(row[0]))
                if row[1] is not None:
                    dataset_ids.add(int(row[1]))
                if row[2] is not None:
                    session_ids.add(int(row[2]))

        if "analysis_rows" in tables and analysis_ids:
            marks = ",".join("?" for _ in analysis_ids)
            for row in con.execute(
                f"SELECT DISTINCT dataset_id FROM analysis_rows WHERE analysis_id IN ({marks})",
                tuple(sorted(analysis_ids)),
            ).fetchall():
                dataset_ids.add(int(row[0]))

        explicit_dataset_ids = {int(value) for value in (extra_dataset_ids or [])}
        if "analysis_rows" in tables and explicit_dataset_ids:
            marks = ",".join("?" for _ in explicit_dataset_ids)
            for row in con.execute(
                f"SELECT analysis_id FROM analysis_rows WHERE dataset_id IN ({marks})",
                tuple(sorted(explicit_dataset_ids)),
            ).fetchall():
                analysis_ids.add(str(row[0]))

        if "datasets" in tables and dataset_ids and "session_id" in _columns(con, "datasets"):
            marks = ",".join("?" for _ in dataset_ids)
            for row in con.execute(
                f"SELECT DISTINCT session_id FROM datasets WHERE id IN ({marks}) AND session_id IS NOT NULL",
                tuple(sorted(dataset_ids)),
            ).fetchall():
                session_ids.add(int(row[0]))

        study_ids = {
            int(value)
            for value in _ids_from_rows(con, "dataset_studies", "study_id", "dataset_id", dataset_ids)
        }

        asset_ids: set[int] = set()
        if "image_assets" in tables:
            image_cols = _columns(con, "image_assets")
            clauses: list[str] = []
            params: list[object] = []
            if explicit_dataset_ids and "dataset_id" in image_cols:
                marks = ",".join("?" for _ in explicit_dataset_ids)
                clauses.append(f"dataset_id IN ({marks})")
                params.extend(sorted(explicit_dataset_ids))
            if analysis_ids and "analysis_id" in image_cols:
                marks = ",".join("?" for _ in analysis_ids)
                clauses.append(f"analysis_id IN ({marks})")
                params.extend(sorted(analysis_ids))
            if clauses:
                asset_ids.update(
                    int(row[0])
                    for row in con.execute(
                        "SELECT id FROM image_assets WHERE project_id=? AND (" + " OR ".join(clauses) + ")",
                        (int(project_id), *params),
                    ).fetchall()
                )
        if "image_analysis_links" in tables and analysis_ids:
            marks = ",".join("?" for _ in analysis_ids)
            asset_ids.update(
                int(row[0])
                for row in con.execute(
                    f"SELECT DISTINCT asset_id FROM image_analysis_links WHERE analysis_id IN ({marks})",
                    tuple(sorted(analysis_ids)),
                ).fetchall()
            )

        scopes: dict[str, set[object]] = {
            "sample_id": {int(sample_id)},
            "entity_id": set(entity_ids),
            "observation_id": set(observation_ids),
            "dataset_id": set(dataset_ids),
            "analysis_id": set(analysis_ids),
            "session_id": set(session_ids),
            "study_id": set(study_ids),
            "asset_id": set(asset_ids),
        }

        special_tables = {
            "projects", "samples", "sample_aliases", "physical_entities", "observations",
            "datasets", "analysis_rows", "analytical_sessions", "studies", "image_assets",
        }
        portable_dependents = {
            "project_dataset_links",
            "analytical_session_datasets",
            "dataset_studies",
            "semantic_mappings",
            "image_analysis_links",
            "analysis_work_groups",
            "analysis_annotations",
            "analysis_generations",
            "analysis_generation_history",
        }

        if "projects" in tables:
            con.execute("DELETE FROM projects WHERE id<>?", (int(project_id),))
        if "samples" in tables:
            con.execute("DELETE FROM samples WHERE id<>?", (int(sample_id),))
        if "sample_aliases" in tables:
            _delete_not_in(con, "sample_aliases", "sample_id", {int(sample_id)})
        if "physical_entities" in tables:
            _delete_not_in(con, "physical_entities", "id", set(entity_ids))
        if "observations" in tables:
            _delete_not_in(con, "observations", "id", set(observation_ids))
        if "datasets" in tables:
            _delete_not_in(con, "datasets", "id", set(dataset_ids))
            if dataset_ids and "project_id" in _columns(con, "datasets"):
                con.execute("UPDATE datasets SET project_id=?", (int(project_id),))
        if "analysis_rows" in tables:
            _delete_not_in(con, "analysis_rows", "analysis_id", set(analysis_ids))
        if "analytical_sessions" in tables:
            _delete_not_in(con, "analytical_sessions", "id", set(session_ids))
        if "studies" in tables:
            _delete_not_in(con, "studies", "id", set(study_ids))
        if "image_assets" in tables:
            _delete_not_in(con, "image_assets", "id", set(asset_ids))

        for table in sorted(tables):
            if table.startswith("sqlite_") or table in special_tables:
                continue
            if table not in portable_dependents:
                con.execute(f"DELETE FROM {table}")
                continue
            cols = _columns(con, table)
            if "project_id" in cols:
                con.execute(
                    f"DELETE FROM {table} WHERE project_id IS NOT NULL AND project_id<>?",
                    (int(project_id),),
                )
            matched_scope = False
            for column in (
                "observation_id", "entity_id", "analysis_id", "dataset_id", "sample_id",
                "session_id", "study_id", "asset_id",
            ):
                if column in cols:
                    _delete_not_in(con, table, column, scopes[column])
                    matched_scope = True
                    break
            if not matched_scope:
                con.execute(f"DELETE FROM {table}")

        if "project_dataset_links" in tables and dataset_ids:
            link_cols = _columns(con, "project_dataset_links")
            for dataset_id in sorted(dataset_ids):
                existing = con.execute(
                    "SELECT 1 FROM project_dataset_links WHERE project_id=? AND dataset_id=?",
                    (int(project_id), int(dataset_id)),
                ).fetchone()
                if existing:
                    continue
                values = [int(project_id), int(dataset_id)]
                names = ["project_id", "dataset_id"]
                if "note" in link_cols:
                    names.append("note")
                    values.append("Portable fragment")
                if "added_at" in link_cols:
                    names.append("added_at")
                    values.append("portable-fragment")
                if "purpose" in link_cols:
                    names.append("purpose")
                    values.append("exchange")
                con.execute(
                    f"INSERT INTO project_dataset_links({','.join(names)}) VALUES ({','.join('?' for _ in names)})",
                    values,
                )

        con.commit()
        return {
            "entity_ids": entity_ids,
            "section_ids": selected_sections,
            "observation_ids": observation_ids,
            "dataset_ids": dataset_ids,
            "analysis_ids": analysis_ids,
            "session_ids": session_ids,
            "study_ids": study_ids,
            "asset_ids": asset_ids,
        }
    finally:
        con.close()


def _existing_paths(values: Iterable[str]) -> list[Path]:
    result: list[Path] = []
    seen: set[Path] = set()
    for value in values:
        if not value:
            continue
        try:
            path = Path(value).expanduser().resolve()
        except OSError:
            continue
        if path.exists() and path.is_file() and path not in seen:
            seen.add(path)
            result.append(path)
    return result


def create_fragment_archive(
    project_id: int,
    sample_id: int,
    destination: str | Path,
    *,
    thin_section_ids: Iterable[int] | None = None,
    include_eds: bool = True,
    include_la: bool = True,
    include_other: bool = False,
    extra_dataset_ids: Iterable[int] | None = None,
    include_images: bool = True,
    include_sources: bool = False,
) -> FragmentArchiveResult:
    """Create a small mergeable .petrolab package for one Sample or selected thin sections."""
    if not any((include_eds, include_la, include_other, extra_dataset_ids)):
        raise ValueError("Выберите хотя бы один тип данных или dataset")
    ensure_storage()
    ensure_measurement_registry_schema()
    project = _project(int(project_id))
    sample = _sample(int(project_id), int(sample_id))

    accessible = {int(row["id"]): row for row in list_accessible_datasets(int(project_id))}
    explicit_datasets = {int(value) for value in (extra_dataset_ids or [])}
    invalid = explicit_datasets.difference(accessible)
    if invalid:
        raise ValueError("Выбран dataset вне рабочего контекста проекта")

    target = Path(destination).expanduser()
    if target.suffix.lower() != ".petrolab":
        target = target.with_suffix(".petrolab")
    target.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="petrolab_fragment_") as temp_dir:
        root = Path(temp_dir)
        database_dir = root / "database"
        database_dir.mkdir(parents=True, exist_ok=True)
        archived_db = database_dir / DB_PATH.name
        scope = _scope_snapshot(
            DB_PATH,
            archived_db,
            project_id=int(project_id),
            sample_id=int(sample_id),
            thin_section_ids=thin_section_ids,
            include_eds=include_eds,
            include_la=include_la,
            include_other=include_other,
            extra_dataset_ids=explicit_datasets,
        )

        con = sqlite3.connect(archived_db)
        con.row_factory = sqlite3.Row
        try:
            tables = _tables(con)
            datasets = (
                [dict(row) for row in con.execute("SELECT * FROM datasets ORDER BY id").fetchall()]
                if "datasets" in tables else []
            )
            assets = (
                [dict(row) for row in con.execute("SELECT * FROM image_assets ORDER BY id").fetchall()]
                if include_images and "image_assets" in tables else []
            )
            sections = (
                [dict(row) for row in con.execute(
                    "SELECT id,name FROM physical_entities WHERE kind='thin_section' ORDER BY id"
                ).fetchall()]
                if "physical_entities" in tables else []
            )
        finally:
            con.close()

        source_paths = _existing_paths(str(row.get("source_path") or "") for row in datasets) if include_sources else []
        source_map: list[dict] = []
        if source_paths:
            source_root = root / "sources"
            source_root.mkdir(parents=True, exist_ok=True)
            for index, path in enumerate(source_paths, start=1):
                archive_name = f"{index:03d}_{_safe_name(path.name)}"
                shutil.copy2(path, source_root / archive_name)
                source_map.append({"archive_name": archive_name, "original_name": path.name})

        image_count = 0
        if include_images and assets:
            image_root = root / "images"
            for asset in assets:
                value = str(asset.get("stored_path") or "")
                if not value:
                    continue
                path = Path(value).expanduser()
                try:
                    path = path.resolve()
                except OSError:
                    continue
                if not path.exists() or not path.is_file():
                    continue
                asset_id = int(asset["id"])
                destination_path = image_root / f"asset_{asset_id}" / _safe_name(path.name)
                destination_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination_path)
                image_count += 1

        manifest = {
            "format": "petrolab-portable-archive",
            "format_version": 3,
            "payload_kind": "fragment",
            "project": {
                "id": int(project["id"]),
                "name": str(project["name"]),
                "description": str(project.get("description") or ""),
            },
            "selection": {
                "sample": {"id": int(sample["id"]), "name": str(sample["name"])},
                "thin_sections": sections,
                "include_eds": bool(include_eds),
                "include_la": bool(include_la),
                "include_other": bool(include_other),
                "explicit_dataset_ids": sorted(explicit_datasets),
            },
            "counts": {
                "samples": 1,
                "thin_sections": len(sections),
                "entities": len(scope["entity_ids"]),
                "observations": len(scope["observation_ids"]),
                "datasets": len(scope["dataset_ids"]),
                "analyses": len(scope["analysis_ids"]),
                "sources": len(source_paths),
                "images": image_count,
            },
            "source_files": source_map,
            "merge_policy": "explicit-sample-mapping",
        }
        (root / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in root.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(root))

    return FragmentArchiveResult(
        path=target.resolve(),
        sample_count=1,
        thin_section_count=len(scope["section_ids"]),
        entity_count=len(scope["entity_ids"]),
        observation_count=len(scope["observation_ids"]),
        dataset_count=len(scope["dataset_ids"]),
        analysis_count=len(scope["analysis_ids"]),
        source_count=len(source_paths),
        image_count=image_count,
    )
