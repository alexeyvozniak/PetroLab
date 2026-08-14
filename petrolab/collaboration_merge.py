from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from petrolab.db import ASSETS_DIR, DB_PATH, _utcnow, connect, ensure_storage
from petrolab.measurement_registry import ensure_measurement_registry_schema
from petrolab.sample_registry import ensure_sample_registry_schema, find_sample_matches, normalize_sample_key
from petrolab.source_registry import ensure_source_registry_schema


@dataclass(frozen=True)
class IncomingSample:
    source_sample_id: int
    name: str
    normalized_key: str
    suggested_target_ids: tuple[int, ...]


@dataclass(frozen=True)
class CollaborationPlan:
    archive_sha256: str
    incoming_project_name: str
    incoming_project_id: int
    sample_count: int
    dataset_count: int
    analysis_count: int
    rock_count: int
    study_count: int
    samples: tuple[IncomingSample, ...]
    entity_count: int = 0
    observation_count: int = 0
    payload_kind: str = "project"


@dataclass(frozen=True)
class CollaborationResult:
    imported_project_name: str
    sample_count: int
    dataset_count: int
    analysis_count: int
    rock_count: int
    study_count: int
    image_count: int
    entity_count: int = 0
    observation_count: int = 0
    payload_kind: str = "project"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
    root = destination.resolve()
    for member in archive.infolist():
        candidate = (destination / member.filename).resolve()
        if root not in candidate.parents and candidate != root:
            raise ValueError("Архив содержит небезопасный путь")
    archive.extractall(destination)


def _validate_manifest(manifest: dict) -> str:
    format_name = str(manifest.get("format") or "")
    version = int(manifest.get("format_version", 0) or 0)
    if format_name == "petrolab-project-archive" and version in {1, 2}:
        return "project"
    if format_name == "petrolab-portable-archive" and version == 3:
        payload_kind = str(manifest.get("payload_kind") or "")
        if payload_kind not in {"project", "fragment"}:
            raise ValueError("Неизвестный тип переносимого пакета PetroLab")
        return payload_kind
    raise ValueError("Это не поддерживаемый переносимый пакет PetroLab")


def _open_archive(path: Path):
    temp = tempfile.TemporaryDirectory(prefix="petrolab_collab_")
    root = Path(temp.name)
    try:
        with zipfile.ZipFile(path, "r") as archive:
            _safe_extract(archive, root)
        manifest_path = root / "manifest.json"
        if not manifest_path.exists():
            raise ValueError("В архиве отсутствует manifest.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload_kind = _validate_manifest(manifest)
        database = root / "database" / DB_PATH.name
        if not database.exists():
            raise ValueError("В архиве отсутствует база PetroLab")
        check_con = sqlite3.connect(database)
        try:
            check = check_con.execute("PRAGMA integrity_check").fetchone()[0]
            if check != "ok":
                raise ValueError(f"Архивная база повреждена: {check}")
        finally:
            check_con.close()
        return temp, root, database, manifest, payload_kind
    except Exception:
        temp.cleanup()
        raise


def _tables(con: sqlite3.Connection) -> set[str]:
    return {str(row[0]) for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}


def _columns(con: sqlite3.Connection, table: str) -> list[str]:
    return [str(row[1]) for row in con.execute(f"PRAGMA table_info({table})").fetchall()]


def _row_get(row: sqlite3.Row, key: str, default=None):
    return row[key] if key in row.keys() else default


def ensure_collaboration_schema() -> None:
    ensure_sample_registry_schema()
    ensure_source_registry_schema()
    ensure_measurement_registry_schema()
    with connect() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS collaboration_imports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                archive_sha256 TEXT NOT NULL UNIQUE,
                incoming_project_name TEXT NOT NULL DEFAULT '',
                target_project_id INTEGER NOT NULL,
                imported_at TEXT NOT NULL,
                FOREIGN KEY(target_project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """
        )
        con.commit()


def plan_collaboration_merge(archive_path: str | Path, target_project_id: int) -> CollaborationPlan:
    ensure_storage()
    ensure_collaboration_schema()
    source = Path(archive_path).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    archive_sha = _sha256(source)
    with connect() as target:
        if target.execute("SELECT 1 FROM collaboration_imports WHERE archive_sha256=?", (archive_sha,)).fetchone():
            raise ValueError("Этот пакет уже импортирован в PetroLab")
        if not target.execute("SELECT 1 FROM projects WHERE id=?", (int(target_project_id),)).fetchone():
            raise ValueError("Целевой проект не найден")

    temp, _root, database, _manifest, payload_kind = _open_archive(source)
    try:
        incoming = sqlite3.connect(database)
        incoming.row_factory = sqlite3.Row
        try:
            tables = _tables(incoming)
            project = incoming.execute("SELECT * FROM projects LIMIT 1").fetchone()
            if not project:
                raise ValueError("В архиве отсутствует проектный контекст")
            samples = incoming.execute("SELECT * FROM samples ORDER BY id").fetchall() if "samples" in tables else []
            sample_items: list[IncomingSample] = []
            for sample in samples:
                matches = find_sample_matches(int(target_project_id), str(sample["name"]))
                sample_items.append(IncomingSample(
                    int(sample["id"]), str(sample["name"]),
                    str(_row_get(sample, "normalized_key", "") or normalize_sample_key(str(sample["name"]))),
                    tuple(match.sample_id for match in matches),
                ))

            def count(table: str) -> int:
                return int(incoming.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) if table in tables else 0

            return CollaborationPlan(
                archive_sha256=archive_sha,
                incoming_project_name=str(project["name"]),
                incoming_project_id=int(project["id"]),
                sample_count=len(samples),
                dataset_count=count("datasets"),
                analysis_count=count("analysis_rows"),
                rock_count=count("rock_samples"),
                study_count=count("studies"),
                samples=tuple(sample_items),
                entity_count=count("physical_entities"),
                observation_count=count("observations"),
                payload_kind=payload_kind,
            )
        finally:
            incoming.close()
    finally:
        temp.cleanup()


def _insert_copy(
    target: sqlite3.Connection,
    table: str,
    row: sqlite3.Row,
    overrides: dict,
    *,
    skip: set[str] | None = None,
) -> int:
    skip = set(skip or ()) | {"id"}
    target_cols = set(_columns(target, table))
    values = {column: row[column] for column in row.keys() if column in target_cols and column not in skip}
    for key, value in overrides.items():
        if key in target_cols:
            values[key] = value
    names = list(values)
    if not names:
        raise ValueError(f"Нет совместимых колонок для таблицы {table}")
    marks = ",".join("?" for _ in names)
    cur = target.execute(
        f"INSERT INTO {table}({','.join(names)}) VALUES ({marks})",
        [values[name] for name in names],
    )
    return int(cur.lastrowid)


def _create_sample_in_transaction(
    target: sqlite3.Connection, target_project_id: int, source_sample: sqlite3.Row
) -> int:
    now = _utcnow()
    name = str(source_sample["name"]).strip()
    cur = target.execute(
        """
        INSERT INTO samples(
            project_id,name,normalized_key,field_lithology,locality,latitude,longitude,
            description,notes,created_at,updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            int(target_project_id), name, normalize_sample_key(name),
            str(_row_get(source_sample, "field_lithology", "") or ""),
            str(_row_get(source_sample, "locality", "") or ""),
            _row_get(source_sample, "latitude"), _row_get(source_sample, "longitude"),
            str(_row_get(source_sample, "description", "") or ""),
            str(_row_get(source_sample, "notes", "") or ""), now, now,
        ),
    )
    return int(cur.lastrowid)


def _unique_entity_name(
    target: sqlite3.Connection,
    project_id: int,
    parent_id: int | None,
    kind: str,
    name: str,
) -> str:
    candidate = str(name).strip() or kind
    base = candidate
    suffix = 2
    while target.execute(
        """SELECT 1 FROM physical_entities
           WHERE project_id=? AND parent_id IS ? AND kind=? AND name=?""",
        (int(project_id), parent_id, str(kind), candidate),
    ).fetchone():
        candidate = f"{base} · import {suffix}"
        suffix += 1
    return candidate


def _copy_physical_registry(
    incoming: sqlite3.Connection,
    target: sqlite3.Connection,
    *,
    target_project_id: int,
    sample_map: dict[int, int],
    session_map: dict[int, int],
    dataset_map: dict[int, int],
    analysis_map: dict[str, str],
) -> tuple[int, int]:
    incoming_tables = _tables(incoming)
    target_tables = _tables(target)
    if "physical_entities" not in incoming_tables or "physical_entities" not in target_tables:
        return 0, 0

    source_entities = incoming.execute("SELECT * FROM physical_entities ORDER BY id").fetchall()
    entity_map: dict[int, int] = {}
    pending = list(source_entities)
    while pending:
        progressed = False
        next_pending: list[sqlite3.Row] = []
        for row in pending:
            source_parent = _row_get(row, "parent_id")
            if source_parent is not None and int(source_parent) not in entity_map:
                next_pending.append(row)
                continue
            source_sample = _row_get(row, "sample_id")
            target_sample = sample_map.get(int(source_sample)) if source_sample is not None else None
            target_parent = entity_map.get(int(source_parent)) if source_parent is not None else None
            kind = str(row["kind"])
            name = _unique_entity_name(
                target, int(target_project_id), target_parent, kind, str(row["name"])
            )
            new_id = _insert_copy(
                target,
                "physical_entities",
                row,
                {
                    "project_id": int(target_project_id),
                    "sample_id": target_sample,
                    "parent_id": target_parent,
                    "name": name,
                },
            )
            entity_map[int(row["id"])] = new_id
            progressed = True
        if not progressed and next_pending:
            raise ValueError("В пакете повреждена иерархия физических объектов")
        pending = next_pending

    observation_count = 0
    if "observations" in incoming_tables and "observations" in target_tables:
        for row in incoming.execute("SELECT * FROM observations ORDER BY id").fetchall():
            old_entity = _row_get(row, "entity_id")
            old_analysis = _row_get(row, "analysis_id")
            old_dataset = _row_get(row, "dataset_id")
            old_session = _row_get(row, "session_id")
            _insert_copy(
                target,
                "observations",
                row,
                {
                    "project_id": int(target_project_id),
                    "entity_id": entity_map.get(int(old_entity)) if old_entity is not None else None,
                    "analysis_id": analysis_map.get(str(old_analysis)) if old_analysis is not None else None,
                    "dataset_id": dataset_map.get(int(old_dataset)) if old_dataset is not None else None,
                    "session_id": session_map.get(int(old_session)) if old_session is not None else None,
                },
            )
            observation_count += 1
    return len(entity_map), observation_count


def _copy_archive_images(
    root: Path,
    target_project_id: int,
    archive_sha: str,
) -> tuple[int, dict[int, Path], dict[str, Path]]:
    image_root = root / "images"
    if not image_root.exists():
        return 0, {}, {}
    target_asset_root = ASSETS_DIR / f"project_{int(target_project_id)}" / "collaboration" / archive_sha[:12]
    copied_by_asset_id: dict[int, Path] = {}
    copied_by_name: dict[str, Path] = {}
    count = 0
    for file in image_root.rglob("*"):
        if not file.is_file():
            continue
        destination = target_asset_root / file.relative_to(image_root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, destination)
        resolved = destination.resolve()
        copied_by_name[file.name] = resolved
        for parent in file.parents:
            if parent == image_root:
                break
            if parent.name.startswith("asset_"):
                try:
                    copied_by_asset_id[int(parent.name.removeprefix("asset_"))] = resolved
                except ValueError:
                    pass
                break
        count += 1
    return count, copied_by_asset_id, copied_by_name


def apply_collaboration_merge(
    archive_path: str | Path,
    target_project_id: int,
    sample_decisions: dict[int, int | None],
) -> CollaborationResult:
    ensure_storage()
    ensure_collaboration_schema()
    source = Path(archive_path).expanduser().resolve()
    plan = plan_collaboration_merge(source, int(target_project_id))
    incoming_ids = {sample.source_sample_id for sample in plan.samples}
    if set(sample_decisions) != incoming_ids:
        raise ValueError("Нужно явно решить судьбу каждого входящего Sample")

    temp, root, database, _manifest, payload_kind = _open_archive(source)
    incoming = sqlite3.connect(database)
    incoming.row_factory = sqlite3.Row
    image_count = 0
    entity_count = 0
    observation_count = 0
    try:
        with connect() as target:
            target.execute("PRAGMA foreign_keys=ON")
            tables = _tables(incoming)
            target_tables = _tables(target)
            sample_map: dict[int, int] = {}
            incoming_samples = (
                {int(row["id"]): row for row in incoming.execute("SELECT * FROM samples").fetchall()}
                if "samples" in tables else {}
            )

            for source_id, decision in sample_decisions.items():
                source_sample = incoming_samples[int(source_id)]
                if decision is None:
                    target_id = _create_sample_in_transaction(target, int(target_project_id), source_sample)
                else:
                    target_id = int(decision)
                    if not target.execute(
                        "SELECT 1 FROM samples WHERE id=? AND project_id=?",
                        (target_id, int(target_project_id)),
                    ).fetchone():
                        raise ValueError("Выбранный целевой Sample не относится к проекту")
                sample_map[int(source_id)] = target_id
                if "sample_aliases" in tables:
                    for alias in incoming.execute(
                        "SELECT * FROM sample_aliases WHERE sample_id=?", (int(source_id),)
                    ).fetchall():
                        target.execute(
                            """INSERT OR IGNORE INTO sample_aliases(
                                   sample_id,alias,normalized_key,source,created_at
                               ) VALUES (?,?,?,?,?)""",
                            (
                                target_id, alias["alias"], alias["normalized_key"],
                                "collaboration_import", alias["created_at"],
                            ),
                        )

            study_map: dict[int, int] = {}
            if "studies" in tables and "studies" in target_tables:
                for row in incoming.execute("SELECT * FROM studies ORDER BY id").fetchall():
                    study_map[int(row["id"])] = _insert_copy(
                        target, "studies", row, {"project_id": int(target_project_id)}
                    )
                if "semantic_mappings" in tables and "semantic_mappings" in target_tables:
                    for row in incoming.execute("SELECT * FROM semantic_mappings ORDER BY id").fetchall():
                        source_study = int(row["study_id"])
                        if source_study in study_map:
                            _insert_copy(target, "semantic_mappings", row, {"study_id": study_map[source_study]})

            session_map: dict[int, int] = {}
            if "analytical_sessions" in tables and "analytical_sessions" in target_tables:
                for row in incoming.execute("SELECT * FROM analytical_sessions ORDER BY id").fetchall():
                    source_sample_id = _row_get(row, "sample_id")
                    if source_sample_id is None or int(source_sample_id) not in sample_map:
                        continue
                    session_map[int(row["id"])] = _insert_copy(
                        target,
                        "analytical_sessions",
                        row,
                        {
                            "project_id": int(target_project_id),
                            "sample_id": sample_map[int(source_sample_id)],
                        },
                    )

            dataset_map: dict[int, int] = {}
            if "datasets" in tables:
                for row in incoming.execute("SELECT * FROM datasets ORDER BY id").fetchall():
                    overrides = {
                        "project_id": int(target_project_id),
                        "source_kind": "collaboration_import",
                        "source_path": "",
                        "sync_enabled": 0,
                    }
                    source_sample_id = _row_get(row, "sample_id")
                    if source_sample_id is not None:
                        overrides["sample_id"] = sample_map.get(int(source_sample_id))
                    source_session_id = _row_get(row, "session_id")
                    if source_session_id is not None:
                        overrides["session_id"] = session_map.get(int(source_session_id))
                    new_dataset = _insert_copy(target, "datasets", row, overrides)
                    dataset_map[int(row["id"])] = new_dataset
                    if "project_dataset_links" in target_tables:
                        target.execute(
                            """INSERT OR IGNORE INTO project_dataset_links(
                                   project_id,dataset_id,note,added_at,purpose
                               ) VALUES (?,?,?,?,?)""",
                            (
                                int(target_project_id), new_dataset,
                                "Импорт переносимого пакета", _utcnow(), "working",
                            ),
                        )

            if "analytical_session_datasets" in tables and "analytical_session_datasets" in target_tables:
                for row in incoming.execute("SELECT * FROM analytical_session_datasets").fetchall():
                    old_session, old_dataset = int(row["session_id"]), int(row["dataset_id"])
                    if old_session in session_map and old_dataset in dataset_map:
                        target.execute(
                            "INSERT OR IGNORE INTO analytical_session_datasets(session_id,dataset_id) VALUES (?,?)",
                            (session_map[old_session], dataset_map[old_dataset]),
                        )

            if "dataset_studies" in tables and "dataset_studies" in target_tables:
                for row in incoming.execute("SELECT * FROM dataset_studies").fetchall():
                    old_dataset, old_study = int(row["dataset_id"]), int(row["study_id"])
                    if old_dataset in dataset_map and old_study in study_map:
                        target.execute(
                            """INSERT OR REPLACE INTO dataset_studies(
                                   dataset_id,study_id,source_table,source_note
                               ) VALUES (?,?,?,?)""",
                            (
                                dataset_map[old_dataset], study_map[old_study],
                                row["source_table"], row["source_note"],
                            ),
                        )

            existing_analysis = {
                str(row[0]) for row in target.execute("SELECT analysis_id FROM analysis_rows").fetchall()
            }
            analysis_map: dict[str, str] = {}
            if "analysis_rows" in tables:
                for row in incoming.execute(
                    "SELECT * FROM analysis_rows ORDER BY dataset_id,row_index"
                ).fetchall():
                    old_id = str(row["analysis_id"])
                    if int(row["dataset_id"]) not in dataset_map:
                        continue
                    new_id = old_id if old_id not in existing_analysis else uuid4().hex
                    existing_analysis.add(new_id)
                    analysis_map[old_id] = new_id
                    target.execute(
                        """INSERT INTO analysis_rows(
                               analysis_id,dataset_id,row_index,source_row,data_json,updated_at
                           ) VALUES (?,?,?,?,?,?)""",
                        (
                            new_id, dataset_map[int(row["dataset_id"])], row["row_index"],
                            row["source_row"], row["data_json"], row["updated_at"],
                        ),
                    )

            for table in (
                "analysis_work_groups", "analysis_annotations", "analysis_generations",
                "analysis_generation_history",
            ):
                if table not in tables or table not in target_tables:
                    continue
                for row in incoming.execute(f"SELECT * FROM {table}").fetchall():
                    old_id = str(row["analysis_id"])
                    if old_id not in analysis_map:
                        continue
                    try:
                        _insert_copy(target, table, row, {"analysis_id": analysis_map[old_id]})
                    except sqlite3.IntegrityError:
                        pass

            entity_count, observation_count = _copy_physical_registry(
                incoming,
                target,
                target_project_id=int(target_project_id),
                sample_map=sample_map,
                session_map=session_map,
                dataset_map=dataset_map,
                analysis_map=analysis_map,
            )

            rock_map: dict[int, int] = {}
            if "rock_samples" in tables and "rock_samples" in target_tables:
                for row in incoming.execute("SELECT * FROM rock_samples ORDER BY id").fetchall():
                    overrides = {"project_id": int(target_project_id)}
                    source_sample_id = _row_get(row, "sample_id")
                    if source_sample_id is not None:
                        overrides["sample_id"] = sample_map.get(int(source_sample_id))
                    try:
                        new_rock = _insert_copy(target, "rock_samples", row, overrides)
                    except sqlite3.IntegrityError:
                        overrides["name"] = f"{row['name']} · {plan.incoming_project_name}"
                        new_rock = _insert_copy(target, "rock_samples", row, overrides)
                    rock_map[int(row["id"])] = new_rock

                for table in ("rock_compositions", "rock_isotopes"):
                    if table in tables and table in target_tables:
                        for row in incoming.execute(f"SELECT * FROM {table} ORDER BY id").fetchall():
                            old_rock = int(row["rock_id"])
                            if old_rock in rock_map:
                                _insert_copy(target, table, row, {"rock_id": rock_map[old_rock]})
                if "rock_mineral_links" in tables and "rock_mineral_links" in target_tables:
                    for row in incoming.execute("SELECT * FROM rock_mineral_links").fetchall():
                        old_rock, old_dataset = int(row["rock_id"]), int(row["dataset_id"])
                        if old_rock in rock_map and old_dataset in dataset_map:
                            target.execute(
                                """INSERT OR IGNORE INTO rock_mineral_links(
                                       rock_id,dataset_id,relationship,notes,created_at
                                   ) VALUES (?,?,?,?,?)""",
                                (
                                    rock_map[old_rock], dataset_map[old_dataset],
                                    row["relationship"], row["notes"], row["created_at"],
                                ),
                            )

            image_count, copied_by_asset_id, copied_by_name = _copy_archive_images(
                root, int(target_project_id), plan.archive_sha256
            )
            if "image_assets" in tables and "image_assets" in target_tables:
                image_map: dict[int, int] = {}
                for row in incoming.execute("SELECT * FROM image_assets ORDER BY id").fetchall():
                    old_asset_id = int(row["id"])
                    old_path = Path(str(row["stored_path"] or ""))
                    stored = copied_by_asset_id.get(old_asset_id) or copied_by_name.get(old_path.name)
                    old_dataset = _row_get(row, "dataset_id")
                    old_analysis = _row_get(row, "analysis_id")
                    overrides = {
                        "project_id": int(target_project_id),
                        "dataset_id": dataset_map.get(int(old_dataset)) if old_dataset is not None else None,
                        "analysis_id": analysis_map.get(str(old_analysis)) if old_analysis is not None else None,
                        "stored_path": str(stored) if stored else "",
                    }
                    image_map[old_asset_id] = _insert_copy(target, "image_assets", row, overrides)

                if "image_analysis_links" in tables and "image_analysis_links" in target_tables:
                    for row in incoming.execute("SELECT * FROM image_analysis_links").fetchall():
                        old_asset = int(row["asset_id"])
                        old_analysis = str(row["analysis_id"])
                        if old_asset in image_map and old_analysis in analysis_map:
                            target.execute(
                                "INSERT OR IGNORE INTO image_analysis_links(asset_id,analysis_id) VALUES (?,?)",
                                (image_map[old_asset], analysis_map[old_analysis]),
                            )

            target.execute(
                """INSERT INTO collaboration_imports(
                       archive_sha256,incoming_project_name,target_project_id,imported_at
                   ) VALUES (?,?,?,?)""",
                (plan.archive_sha256, plan.incoming_project_name, int(target_project_id), _utcnow()),
            )
            target.commit()
    finally:
        incoming.close()
        temp.cleanup()

    return CollaborationResult(
        imported_project_name=plan.incoming_project_name,
        sample_count=plan.sample_count,
        dataset_count=plan.dataset_count,
        analysis_count=plan.analysis_count,
        rock_count=plan.rock_count,
        study_count=plan.study_count,
        image_count=image_count,
        entity_count=entity_count,
        observation_count=observation_count,
        payload_kind=payload_kind,
    )
