from __future__ import annotations

import gc
import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import petrolab.collaboration_merge as collab
import petrolab.db as db
import petrolab.exchange_package as exchange
import petrolab.project_archive as archive
import petrolab.selective_exchange_merge as selective_merge
from petrolab.exchange_identity import get_exchange_workspace_uuid
from petrolab.measurement_registry import add_observation, create_entity, ensure_measurement_registry_schema
from petrolab.repositories.image_repository import create_image_record
from petrolab.sample_registry import create_sample
from petrolab.storage import ensure_storage


class Workspace:
    def __init__(self, root: Path):
        self.root = root
        self.stack = ExitStack()

    def __enter__(self):
        data = self.root / "data"
        db_path = data / "petrolab.sqlite3"
        assets = data / "assets"
        backups = data / "backups"
        for module, name, value in (
            (db, "DATA_DIR", data), (db, "DB_PATH", db_path), (db, "ASSETS_DIR", assets),
            (db, "BACKUPS_DIR", backups),
            (archive, "DATA_DIR", data), (archive, "DB_PATH", db_path),
            (archive, "ASSETS_DIR", assets), (archive, "BACKUPS_DIR", backups),
            (exchange, "DB_PATH", db_path),
            (collab, "DB_PATH", db_path), (collab, "ASSETS_DIR", assets),
            (selective_merge, "ASSETS_DIR", assets),
        ):
            self.stack.enter_context(patch.object(module, name, value))
        ensure_storage()
        return self

    def __exit__(self, exc_type, exc, tb):
        gc.collect()
        self.stack.close()


def create_project(name: str) -> int:
    with db.connect() as con:
        con.execute(
            "INSERT INTO projects(name,description,created_at) VALUES (?,?,?)",
            (name, "", "2026-08-15"),
        )
        project_id = int(con.execute("SELECT id FROM projects WHERE name=?", (name,)).fetchone()["id"])
        con.commit()
    return project_id


def create_dataset(project_id: int, sample_id: int, name: str, dataset_id: int) -> int:
    ensure_measurement_registry_schema()
    with db.connect() as con:
        columns = {row[1] for row in con.execute("PRAGMA table_info(datasets)").fetchall()}
        values = {
            "id": int(dataset_id), "project_id": int(project_id), "name": name,
            "mineral_key": "mica", "source_filename": f"{name}.xlsx", "source_sheet": "S1",
            "source_sha256": f"sha-{dataset_id}", "csv_path": "", "row_count": 2,
            "imported_at": "2026-08-15", "source_path": "", "source_kind": "upload",
            "header_row": 1, "column_map_json": "{}", "sync_enabled": 0,
            "sample_id": int(sample_id),
        }
        values = {key: value for key, value in values.items() if key in columns}
        names = list(values)
        con.execute(
            f"INSERT INTO datasets({','.join(names)}) VALUES ({','.join('?' for _ in names)})",
            [values[name] for name in names],
        )
        link_columns = {row[1] for row in con.execute("PRAGMA table_info(project_dataset_links)").fetchall()}
        if "purpose" in link_columns:
            con.execute(
                "INSERT OR IGNORE INTO project_dataset_links(project_id,dataset_id,note,added_at,purpose) VALUES (?,?,?,?,?)",
                (project_id, dataset_id, "", "2026-08-15", "working"),
            )
        else:
            con.execute(
                "INSERT OR IGNORE INTO project_dataset_links(project_id,dataset_id,note,added_at) VALUES (?,?,?,?)",
                (project_id, dataset_id, "", "2026-08-15"),
            )
        con.commit()
    return dataset_id


def add_analysis(dataset_id: int, analysis_id: str, row_index: int, sio2: float) -> None:
    with db.connect() as con:
        con.execute(
            """INSERT INTO analysis_rows(analysis_id,dataset_id,row_index,source_row,data_json,updated_at)
               VALUES (?,?,?,?,?,?)""",
            (analysis_id, dataset_id, row_index, row_index + 2, f'{{"SiO2":{sio2}}}', "2026-08-15"),
        )
        con.commit()


class SelectiveExchangeTests(unittest.TestCase):
    def test_entity_selection_keeps_only_required_scientific_context_and_additive_import_reuses_origin(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "source"
            target_root = root / "target"
            package_one = root / "one.petrolab"
            package_two = root / "two.petrolab"

            with Workspace(source_root):
                project_id = create_project("Кандалакша")
                sample_a = create_sample(project_id, "K-01")
                sample_b = create_sample(project_id, "K-OTHER")
                dataset_a = create_dataset(project_id, sample_a, "EDS K-01", 101)
                dataset_b = create_dataset(project_id, sample_b, "EDS other", 102)
                add_analysis(dataset_a, "eds-1", 0, 41.0)
                add_analysis(dataset_a, "la-1", 1, 42.0)
                add_analysis(dataset_b, "other-1", 0, 50.0)

                thin = create_entity(project_id, kind="thin_section", name="K-01 TS", sample_id=sample_a)
                eds_point = create_entity(
                    project_id, kind="probe_point", name="EDS-1", sample_id=sample_a, parent_id=thin
                )
                la_point = create_entity(
                    project_id, kind="la_crater", name="LA-1", sample_id=sample_a, parent_id=thin
                )
                add_observation(
                    project_id, entity_id=eds_point, analysis_id="eds-1", dataset_id=dataset_a,
                    analyte="SiO2", value=41.0, unit="wt%", method="EDS",
                )
                add_observation(
                    project_id, entity_id=la_point, analysis_id="la-1", dataset_id=dataset_a,
                    analyte="Ti", value=120.0, unit="ug/g", method="LA-ICP-MS",
                )

                image_dir = db.ASSETS_DIR / f"project_{project_id}"
                image_dir.mkdir(parents=True, exist_ok=True)
                image_path = image_dir / "eds1.txt"
                image_path.write_text("image-placeholder", encoding="utf-8")
                create_image_record(
                    project_id=project_id, dataset_id=dataset_a, analysis_ids=["eds-1"],
                    scope_type="Точки анализа", scope_column="", scope_value="", kind="BSE",
                    title="EDS-1 image", original_filename="eds1.txt", stored_path=str(image_path),
                )

                source_workspace_uuid = get_exchange_workspace_uuid()
                first = exchange.create_exchange_package(
                    project_id, package_one,
                    exchange.ExchangeSelection(entity_ids=(eds_point,), include_related_images=True),
                )
                second = exchange.create_exchange_package(
                    project_id, package_two,
                    exchange.ExchangeSelection(entity_ids=(la_point,), include_related_images=True),
                )
                self.assertEqual(first.sample_count, 1)
                self.assertEqual(first.entity_count, 2)  # selected point + thin-section parent
                self.assertEqual(first.dataset_count, 1)
                self.assertEqual(first.analysis_count, 1)
                self.assertEqual(first.image_count, 1)

                with zipfile.ZipFile(package_one, "r") as zf:
                    unpacked = root / "inspect"
                    zf.extractall(unpacked)
                packed = sqlite3.connect(unpacked / "database" / "petrolab.sqlite3")
                try:
                    self.assertEqual(packed.execute("SELECT COUNT(*) FROM samples").fetchone()[0], 1)
                    self.assertEqual(packed.execute("SELECT name FROM samples").fetchone()[0], "K-01")
                    self.assertEqual(packed.execute("SELECT COUNT(*) FROM physical_entities").fetchone()[0], 2)
                    self.assertEqual(packed.execute("SELECT COUNT(*) FROM analysis_rows").fetchone()[0], 1)
                    self.assertEqual(packed.execute("SELECT analysis_id FROM analysis_rows").fetchone()[0], "eds-1")
                    self.assertEqual(packed.execute("SELECT COUNT(*) FROM datasets").fetchone()[0], 1)
                    self.assertEqual(packed.execute("SELECT COUNT(*) FROM image_assets").fetchone()[0], 1)
                    self.assertEqual(
                        packed.execute("SELECT workspace_uuid FROM exchange_workspace_identity WHERE singleton=1").fetchone()[0],
                        source_workspace_uuid,
                    )
                finally:
                    packed.close()

            with Workspace(target_root):
                target_project = create_project("Кандалакша")
                existing_sample = create_sample(target_project, "K-99")
                self.assertIsInstance(existing_sample, int)

                first_plan = collab.plan_collaboration_merge(package_one, target_project)
                first_result = selective_merge.apply_selective_exchange_merge(
                    package_one, target_project,
                    {item.source_sample_id: None for item in first_plan.samples},
                )
                self.assertEqual(first_result.analysis_count, 1)
                with db.connect() as con:
                    self.assertEqual(con.execute("SELECT COUNT(*) FROM samples WHERE project_id=?", (target_project,)).fetchone()[0], 2)
                    self.assertEqual(con.execute("SELECT COUNT(*) FROM datasets WHERE project_id=?", (target_project,)).fetchone()[0], 1)
                    self.assertEqual(con.execute("SELECT COUNT(*) FROM analysis_rows").fetchone()[0], 1)
                    self.assertEqual(con.execute("SELECT COUNT(*) FROM physical_entities WHERE project_id=?", (target_project,)).fetchone()[0], 2)
                    self.assertEqual(con.execute("SELECT COUNT(*) FROM observations WHERE project_id=?", (target_project,)).fetchone()[0], 1)
                    self.assertEqual(con.execute("SELECT COUNT(*) FROM image_analysis_links").fetchone()[0], 1)

                second_plan = collab.plan_collaboration_merge(package_two, target_project)
                second_result = selective_merge.apply_selective_exchange_merge(
                    package_two, target_project,
                    {item.source_sample_id: None for item in second_plan.samples},
                )
                self.assertGreaterEqual(second_result.reused_count, 2)  # Sample + dataset/thin-section context
                with db.connect() as con:
                    self.assertEqual(con.execute("SELECT COUNT(*) FROM samples WHERE project_id=?", (target_project,)).fetchone()[0], 2)
                    self.assertEqual(con.execute("SELECT COUNT(*) FROM datasets WHERE project_id=?", (target_project,)).fetchone()[0], 1)
                    self.assertEqual(con.execute("SELECT COUNT(*) FROM analysis_rows").fetchone()[0], 2)
                    self.assertEqual(con.execute("SELECT COUNT(*) FROM physical_entities WHERE project_id=?", (target_project,)).fetchone()[0], 3)
                    self.assertEqual(con.execute("SELECT COUNT(*) FROM observations WHERE project_id=?", (target_project,)).fetchone()[0], 2)
                    imported_workspaces = {
                        row[0] for row in con.execute("SELECT DISTINCT workspace_uuid FROM exchange_import_map").fetchall()
                    }
                    self.assertIn(source_workspace_uuid, imported_workspaces)


if __name__ == "__main__":
    unittest.main(verbosity=2)
