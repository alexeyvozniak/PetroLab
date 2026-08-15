from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from petrolab.analytical_sessions import ensure_session_schema
from petrolab.collaboration_merge import (
    _columns,
    _create_sample_in_transaction,
    _insert_copy,
    _open_archive,
    _row_get,
    _tables,
    ensure_collaboration_schema,
    plan_collaboration_merge,
)
from petrolab.db import ASSETS_DIR, _utcnow, connect, ensure_storage
from petrolab.exchange_identity import ensure_exchange_identity_schema, record_import_mapping
from petrolab.generations import ensure_generation_storage
from petrolab.measurement_registry import ensure_measurement_registry_schema
from petrolab.repositories.image_repository import ensure_image_link_schema


@dataclass(frozen=True)
class SelectiveExchangeResult:
    imported_project_name: str
    sample_count: int
    dataset_count: int
    analysis_count: int
    entity_count: int
    observation_count: int
    image_count: int
    reused_count: int


def _origin_workspace(incoming: sqlite3.Connection, archive_sha: str) -> str:
    tables = _tables(incoming)
    if "exchange_workspace_identity" in tables:
        row = incoming.execute(
            "SELECT workspace_uuid FROM exchange_workspace_identity WHERE singleton=1"
        ).fetchone()
        if row and row[0]:
            return str(row[0])
    # Legacy/hand-built selective packages are still importable, but only exact-package
    # duplicate protection is possible because there is no stable source workspace ID.
    return f"archive:{archive_sha}"


def _lookup_mapping(
    target: sqlite3.Connection,
    workspace_uuid: str,
    entity_kind: str,
    source_key: str | int,
) -> str | None:
    row = target.execute(
        """SELECT local_key FROM exchange_import_map
           WHERE workspace_uuid=? AND entity_kind=? AND source_key=?""",
        (str(workspace_uuid), str(entity_kind), str(source_key)),
    ).fetchone()
    return str(row[0]) if row else None


def _local_exists(target: sqlite3.Connection, table: str, column: str, value: str | int) -> bool:
    if table not in _tables(target):
        return False
    return bool(target.execute(f"SELECT 1 FROM {table} WHERE {column}=?", (value,)).fetchone())


def _remember(
    target: sqlite3.Connection,
    workspace_uuid: str,
    entity_kind: str,
    source_key: str | int,
    local_key: str | int,
) -> None:
    record_import_mapping(
        target,
        workspace_uuid=workspace_uuid,
        entity_kind=entity_kind,
        source_key=str(source_key),
        local_key=str(local_key),
    )


def _mapped_int(
    target: sqlite3.Connection,
    workspace_uuid: str,
    kind: str,
    source_key: int,
    table: str,
) -> int | None:
    value = _lookup_mapping(target, workspace_uuid, kind, source_key)
    if value is None:
        return None
    try:
        local = int(value)
    except ValueError:
        return None
    return local if _local_exists(target, table, "id", local) else None


def _mapped_text(
    target: sqlite3.Connection,
    workspace_uuid: str,
    kind: str,
    source_key: str,
    table: str,
    column: str,
) -> str | None:
    value = _lookup_mapping(target, workspace_uuid, kind, source_key)
    return value if value and _local_exists(target, table, column, value) else None


def _copy_aliases(
    incoming: sqlite3.Connection,
    target: sqlite3.Connection,
    source_sample_id: int,
    target_sample_id: int,
) -> None:
    if "sample_aliases" not in _tables(incoming) or "sample_aliases" not in _tables(target):
        return
    for alias in incoming.execute(
        "SELECT * FROM sample_aliases WHERE sample_id=?", (int(source_sample_id),)
    ).fetchall():
        target.execute(
            """INSERT OR IGNORE INTO sample_aliases(
                   sample_id,alias,normalized_key,source,created_at
               ) VALUES (?,?,?,?,?)""",
            (
                int(target_sample_id), alias["alias"], alias["normalized_key"],
                "exchange_import", alias["created_at"],
            ),
        )


def apply_selective_exchange_merge(
    archive_path: str | Path,
    target_project_id: int,
    sample_decisions: dict[int, int | None],
) -> SelectiveExchangeResult:
    """Incrementally merge a selection package into an existing project.

    Stable source workspace identity makes repeated packages additive: a dataset,
    physical target or analytical point already received from that workspace is
    reused instead of duplicated. Existing scientific rows are never overwritten.
    """
    ensure_storage()
    ensure_collaboration_schema()
    ensure_exchange_identity_schema()
    ensure_session_schema()
    ensure_generation_storage()
    ensure_measurement_registry_schema()
    ensure_image_link_schema()

    source = Path(archive_path).expanduser().resolve()
    plan = plan_collaboration_merge(source, int(target_project_id))
    incoming_sample_ids = {item.source_sample_id for item in plan.samples}
    if set(sample_decisions) != incoming_sample_ids:
        raise ValueError("Нужно явно решить судьбу каждого входящего Sample")

    temp, root, database, manifest = _open_archive(source)
    if manifest.get("package_kind") != "selection":
        temp.cleanup()
        raise ValueError("Для этого импорта нужен выборочный пакет PetroLab")

    incoming = sqlite3.connect(database)
    incoming.row_factory = sqlite3.Row
    image_count = 0
    reused_count = 0
    try:
        workspace_uuid = _origin_workspace(incoming, plan.archive_sha256)
        with connect() as target:
            target.execute("PRAGMA foreign_keys=ON")
            tables = _tables(incoming)
            target_tables = _tables(target)

            sample_map: dict[int, int] = {}
            incoming_samples = {
                int(row["id"]): row
                for row in incoming.execute("SELECT * FROM samples ORDER BY id").fetchall()
            } if "samples" in tables else {}
            for source_id, decision in sample_decisions.items():
                source_id = int(source_id)
                if decision is None:
                    previous = _mapped_int(target, workspace_uuid, "sample", source_id, "samples")
                    if previous is not None:
                        target_id = previous
                        reused_count += 1
                    else:
                        target_id = _create_sample_in_transaction(
                            target, int(target_project_id), incoming_samples[source_id]
                        )
                else:
                    target_id = int(decision)
                    if not target.execute(
                        "SELECT 1 FROM samples WHERE id=? AND project_id=?",
                        (target_id, int(target_project_id)),
                    ).fetchone():
                        raise ValueError("Выбранный целевой Sample не относится к проекту")
                sample_map[source_id] = target_id
                _remember(target, workspace_uuid, "sample", source_id, target_id)
                _copy_aliases(incoming, target, source_id, target_id)

            study_map: dict[int, int] = {}
            if "studies" in tables and "studies" in target_tables:
                for row in incoming.execute("SELECT * FROM studies ORDER BY id").fetchall():
                    old = int(row["id"])
                    existing = _mapped_int(target, workspace_uuid, "study", old, "studies")
                    if existing is not None:
                        study_map[old] = existing
                        reused_count += 1
                        continue
                    new = _insert_copy(target, "studies", row, {"project_id": int(target_project_id)})
                    study_map[old] = new
                    _remember(target, workspace_uuid, "study", old, new)
                if "semantic_mappings" in tables and "semantic_mappings" in target_tables:
                    for row in incoming.execute("SELECT * FROM semantic_mappings ORDER BY id").fetchall():
                        old_study = int(row["study_id"])
                        if old_study in study_map:
                            try:
                                _insert_copy(target, "semantic_mappings", row, {"study_id": study_map[old_study]})
                            except sqlite3.IntegrityError:
                                pass

            session_map: dict[int, int] = {}
            if "analytical_sessions" in tables and "analytical_sessions" in target_tables:
                for row in incoming.execute("SELECT * FROM analytical_sessions ORDER BY id").fetchall():
                    old = int(row["id"])
                    existing = _mapped_int(target, workspace_uuid, "session", old, "analytical_sessions")
                    if existing is not None:
                        session_map[old] = existing
                        reused_count += 1
                        continue
                    source_sample = _row_get(row, "sample_id")
                    overrides = {"project_id": int(target_project_id)}
                    if source_sample is not None:
                        overrides["sample_id"] = sample_map[int(source_sample)]
                    new = _insert_copy(target, "analytical_sessions", row, overrides)
                    session_map[old] = new
                    _remember(target, workspace_uuid, "session", old, new)

            dataset_map: dict[int, int] = {}
            if "datasets" in tables:
                for row in incoming.execute("SELECT * FROM datasets ORDER BY id").fetchall():
                    old = int(row["id"])
                    existing = _mapped_int(target, workspace_uuid, "dataset", old, "datasets")
                    if existing is not None:
                        dataset_map[old] = existing
                        reused_count += 1
                        continue
                    overrides = {
                        "project_id": int(target_project_id),
                        "source_kind": "exchange_import",
                        "source_path": "",
                        "sync_enabled": 0,
                    }
                    source_sample = _row_get(row, "sample_id")
                    if source_sample is not None:
                        overrides["sample_id"] = sample_map.get(int(source_sample))
                    source_session = _row_get(row, "session_id")
                    if source_session is not None:
                        overrides["session_id"] = session_map.get(int(source_session))
                    new = _insert_copy(target, "datasets", row, overrides)
                    dataset_map[old] = new
                    _remember(target, workspace_uuid, "dataset", old, new)

            if "project_dataset_links" in tables and "project_dataset_links" in target_tables:
                for row in incoming.execute("SELECT * FROM project_dataset_links").fetchall():
                    old_dataset = int(row["dataset_id"])
                    if old_dataset not in dataset_map:
                        continue
                    try:
                        _insert_copy(
                            target, "project_dataset_links", row,
                            {"project_id": int(target_project_id), "dataset_id": dataset_map[old_dataset]},
                        )
                    except sqlite3.IntegrityError:
                        pass

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

            analysis_map: dict[str, str] = {}
            existing_analysis = {
                str(row[0]) for row in target.execute("SELECT analysis_id FROM analysis_rows").fetchall()
            }
            if "analysis_rows" in tables:
                for row in incoming.execute("SELECT * FROM analysis_rows ORDER BY dataset_id,row_index").fetchall():
                    old = str(row["analysis_id"])
                    mapped = _mapped_text(
                        target, workspace_uuid, "analysis", old, "analysis_rows", "analysis_id"
                    )
                    if mapped is not None:
                        analysis_map[old] = mapped
                        reused_count += 1
                        continue
                    new = old if old not in existing_analysis else uuid4().hex
                    existing_analysis.add(new)
                    analysis_map[old] = new
                    target.execute(
                        """INSERT INTO analysis_rows(
                               analysis_id,dataset_id,row_index,source_row,data_json,updated_at
                           ) VALUES (?,?,?,?,?,?)""",
                        (
                            new, dataset_map[int(row["dataset_id"])], row["row_index"],
                            row["source_row"], row["data_json"], row["updated_at"],
                        ),
                    )
                    _remember(target, workspace_uuid, "analysis", old, new)

            for table in (
                "analysis_work_groups", "analysis_annotations", "analysis_generations",
                "analysis_generation_history",
            ):
                if table not in tables or table not in target_tables:
                    continue
                for row in incoming.execute(f"SELECT * FROM {table}").fetchall():
                    old = str(row["analysis_id"])
                    if old not in analysis_map:
                        continue
                    try:
                        _insert_copy(target, table, row, {"analysis_id": analysis_map[old]})
                    except sqlite3.IntegrityError:
                        pass

            entity_map: dict[int, int] = {}
            if "physical_entities" in tables and "physical_entities" in target_tables:
                pending = {
                    int(row["id"]): row
                    for row in incoming.execute("SELECT * FROM physical_entities ORDER BY id").fetchall()
                }
                while pending:
                    progressed = False
                    for old, row in list(pending.items()):
                        parent = _row_get(row, "parent_id")
                        if parent is not None and int(parent) not in entity_map:
                            continue
                        existing = _mapped_int(
                            target, workspace_uuid, "physical_entity", old, "physical_entities"
                        )
                        if existing is not None:
                            entity_map[old] = existing
                            reused_count += 1
                        else:
                            source_sample = _row_get(row, "sample_id")
                            overrides = {
                                "project_id": int(target_project_id),
                                "sample_id": sample_map.get(int(source_sample)) if source_sample is not None else None,
                                "parent_id": entity_map.get(int(parent)) if parent is not None else None,
                            }
                            new = _insert_copy(target, "physical_entities", row, overrides)
                            entity_map[old] = new
                            _remember(target, workspace_uuid, "physical_entity", old, new)
                        del pending[old]
                        progressed = True
                    if not progressed:
                        raise ValueError("В пакете повреждена иерархия шлифов/зёрен/аналитических точек")

            observation_count = 0
            if "observations" in tables and "observations" in target_tables:
                for row in incoming.execute("SELECT * FROM observations ORDER BY id").fetchall():
                    old = int(row["id"])
                    existing = _mapped_int(target, workspace_uuid, "observation", old, "observations")
                    if existing is not None:
                        reused_count += 1
                        continue
                    source_entity = _row_get(row, "entity_id")
                    source_analysis = _row_get(row, "analysis_id")
                    source_dataset = _row_get(row, "dataset_id")
                    source_session = _row_get(row, "session_id")
                    overrides = {
                        "project_id": int(target_project_id),
                        "entity_id": entity_map.get(int(source_entity)) if source_entity is not None else None,
                        "analysis_id": analysis_map.get(str(source_analysis)) if source_analysis is not None else None,
                        "dataset_id": dataset_map.get(int(source_dataset)) if source_dataset is not None else None,
                        "session_id": session_map.get(int(source_session)) if source_session is not None else None,
                    }
                    new = _insert_copy(target, "observations", row, overrides)
                    _remember(target, workspace_uuid, "observation", old, new)
                    observation_count += 1

            rock_map: dict[int, int] = {}
            if "rock_samples" in tables and "rock_samples" in target_tables:
                for row in incoming.execute("SELECT * FROM rock_samples ORDER BY id").fetchall():
                    old = int(row["id"])
                    existing = _mapped_int(target, workspace_uuid, "rock", old, "rock_samples")
                    if existing is not None:
                        rock_map[old] = existing
                        reused_count += 1
                        continue
                    source_sample = _row_get(row, "sample_id")
                    overrides = {"project_id": int(target_project_id)}
                    if source_sample is not None:
                        overrides["sample_id"] = sample_map.get(int(source_sample))
                    try:
                        new = _insert_copy(target, "rock_samples", row, overrides)
                    except sqlite3.IntegrityError:
                        overrides["name"] = f"{row['name']} · {plan.incoming_project_name}"
                        new = _insert_copy(target, "rock_samples", row, overrides)
                    rock_map[old] = new
                    _remember(target, workspace_uuid, "rock", old, new)
                for table in ("rock_compositions", "rock_isotopes"):
                    if table in tables and table in target_tables:
                        for row in incoming.execute(f"SELECT * FROM {table} ORDER BY id").fetchall():
                            old_rock = int(row["rock_id"])
                            if old_rock in rock_map:
                                try:
                                    _insert_copy(target, table, row, {"rock_id": rock_map[old_rock]})
                                except sqlite3.IntegrityError:
                                    pass

            image_map: dict[int, int] = {}
            manifest_images = {
                int(item["asset_id"]): str(item["archive_name"])
                for item in manifest.get("images", [])
                if isinstance(item, dict) and item.get("asset_id") is not None and item.get("archive_name")
            }
            image_root = root / "images"
            target_asset_root = (
                ASSETS_DIR / f"project_{int(target_project_id)}" / "exchange" / plan.archive_sha256[:12]
            )
            if "image_assets" in tables and "image_assets" in target_tables:
                for row in incoming.execute("SELECT * FROM image_assets ORDER BY id").fetchall():
                    old = int(row["id"])
                    existing = _mapped_int(target, workspace_uuid, "image", old, "image_assets")
                    if existing is not None:
                        image_map[old] = existing
                        reused_count += 1
                        continue
                    archive_name = manifest_images.get(old)
                    source_file = image_root / archive_name if archive_name else None
                    if source_file is None or not source_file.is_file():
                        old_name = Path(str(row["stored_path"] or "")).name
                        matches = list(image_root.rglob(old_name)) if image_root.exists() and old_name else []
                        source_file = matches[0] if len(matches) == 1 else None
                    stored = ""
                    if source_file is not None and source_file.is_file():
                        target_asset_root.mkdir(parents=True, exist_ok=True)
                        destination = target_asset_root / source_file.name
                        shutil.copy2(source_file, destination)
                        stored = str(destination.resolve())
                        image_count += 1
                    source_dataset = _row_get(row, "dataset_id")
                    source_analysis = _row_get(row, "analysis_id")
                    overrides = {
                        "project_id": int(target_project_id),
                        "dataset_id": dataset_map.get(int(source_dataset)) if source_dataset is not None else None,
                        "analysis_id": analysis_map.get(str(source_analysis)) if source_analysis is not None else None,
                        "stored_path": stored,
                    }
                    new = _insert_copy(target, "image_assets", row, overrides)
                    image_map[old] = new
                    _remember(target, workspace_uuid, "image", old, new)

            if "image_analysis_links" in tables and "image_analysis_links" in target_tables:
                for row in incoming.execute("SELECT * FROM image_analysis_links").fetchall():
                    old_asset, old_analysis = int(row["asset_id"]), str(row["analysis_id"])
                    if old_asset in image_map and old_analysis in analysis_map:
                        target.execute(
                            "INSERT OR IGNORE INTO image_analysis_links(asset_id,analysis_id) VALUES (?,?)",
                            (image_map[old_asset], analysis_map[old_analysis]),
                        )

            # A reused dataset may receive more point rows in a later package.
            for new_dataset in set(dataset_map.values()):
                if "row_count" in _columns(target, "datasets"):
                    target.execute(
                        """UPDATE datasets SET row_count=(
                               SELECT COUNT(*) FROM analysis_rows WHERE dataset_id=?
                           ) WHERE id=?""",
                        (new_dataset, new_dataset),
                    )

            target.execute(
                """INSERT INTO collaboration_imports(
                       archive_sha256,incoming_project_name,target_project_id,imported_at
                   ) VALUES (?,?,?,?)""",
                (plan.archive_sha256, plan.incoming_project_name, int(target_project_id), _utcnow()),
            )
            target.commit()

        return SelectiveExchangeResult(
            plan.incoming_project_name,
            plan.sample_count,
            plan.dataset_count,
            plan.analysis_count,
            len(entity_map),
            observation_count,
            image_count,
            reused_count,
        )
    finally:
        incoming.close()
        temp.cleanup()
