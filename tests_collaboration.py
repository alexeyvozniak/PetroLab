from __future__ import annotations

import gc
import json
import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import petrolab.collaboration_merge as collab
import petrolab.db as db
from petrolab.sample_registry import create_sample
from petrolab.storage import ensure_storage


class Workspace:
    def __init__(self, root: Path):
        self.root = root
        self.stack = ExitStack()

    def __enter__(self):
        data = self.root / "data"
        self.stack.enter_context(patch.object(db, "DATA_DIR", data))
        self.stack.enter_context(patch.object(db, "DB_PATH", data / "petrolab.sqlite3"))
        self.stack.enter_context(patch.object(db, "ASSETS_DIR", data / "assets"))
        self.stack.enter_context(patch.object(db, "BACKUPS_DIR", data / "backups"))
        self.stack.enter_context(patch.object(collab, "DB_PATH", data / "petrolab.sqlite3"))
        self.stack.enter_context(patch.object(collab, "ASSETS_DIR", data / "assets"))
        ensure_storage()
        with db.connect() as con:
            con.execute("INSERT INTO projects(name, description, created_at) VALUES ('Target', '', '2026-08-14')")
            self.project_id = int(con.execute("SELECT id FROM projects WHERE name='Target'").fetchone()["id"])
            con.execute(
                """INSERT INTO datasets(id,project_id,name,mineral_key,source_filename,source_sheet,source_sha256,csv_path,row_count,imported_at)
                   VALUES (100,?,'existing','mica','mine.xlsx','S','sha','',1,'2026-08-14')""",
                (self.project_id,),
            )
            con.execute("INSERT INTO analysis_rows(analysis_id,dataset_id,row_index,source_row,data_json,updated_at) VALUES ('collision',100,0,2,'{}','2026-08-14')")
            con.commit()
        self.sample_id = create_sample(self.project_id, "PG-15")
        return self

    def __exit__(self, exc_type, exc, tb):
        gc.collect()
        self.stack.close()


def make_incoming_archive(root: Path) -> Path:
    staging = root / "incoming"
    (staging / "database").mkdir(parents=True)
    database = staging / "database" / "petrolab.sqlite3"
    con = sqlite3.connect(database)
    try:
        con.executescript(
            """
            CREATE TABLE projects(id INTEGER PRIMARY KEY,name TEXT,description TEXT,created_at TEXT);
            CREATE TABLE samples(id INTEGER PRIMARY KEY,project_id INTEGER,name TEXT,normalized_key TEXT,field_lithology TEXT,locality TEXT,latitude REAL,longitude REAL,description TEXT,notes TEXT,created_at TEXT,updated_at TEXT);
            CREATE TABLE sample_aliases(id INTEGER PRIMARY KEY,sample_id INTEGER,alias TEXT,normalized_key TEXT,source TEXT,created_at TEXT);
            CREATE TABLE datasets(id INTEGER PRIMARY KEY,project_id INTEGER,name TEXT,mineral_key TEXT,source_filename TEXT,source_sheet TEXT,source_sha256 TEXT,csv_path TEXT,row_count INTEGER,imported_at TEXT,source_path TEXT,source_kind TEXT,header_row INTEGER,column_map_json TEXT,sync_enabled INTEGER,sample_id INTEGER);
            CREATE TABLE analysis_rows(analysis_id TEXT PRIMARY KEY,dataset_id INTEGER,row_index INTEGER,source_row INTEGER,data_json TEXT,updated_at TEXT);
            CREATE TABLE studies(id INTEGER PRIMARY KEY,project_id INTEGER,source_type TEXT,title TEXT,citation TEXT,doi TEXT,authors TEXT,year TEXT,journal TEXT,colleague TEXT,notes TEXT,created_at TEXT,updated_at TEXT);
            CREATE TABLE dataset_studies(dataset_id INTEGER PRIMARY KEY,study_id INTEGER,source_table TEXT,source_note TEXT);
            CREATE TABLE semantic_mappings(id INTEGER PRIMARY KEY,study_id INTEGER,domain TEXT,source_label TEXT,normalized_value TEXT,author_interpretation TEXT,user_interpretation TEXT,status TEXT,created_at TEXT,updated_at TEXT);
            """
        )
        con.execute("INSERT INTO projects VALUES (9,'Colleague project','','2026-08-14')")
        con.execute("INSERT INTO samples VALUES (1,9,'PG_15','pg15','carbonatite','Kovdor',NULL,NULL,'','','2026-08-14','2026-08-14')")
        con.execute("INSERT INTO sample_aliases VALUES (1,1,'PG 15','pg15','manual','2026-08-14')")
        con.execute("INSERT INTO datasets VALUES (5,9,'colleague mica','mica','paper.xlsx','S1','sha2','',1,'2026-08-14','','managed_copy',1,'{}',0,1)")
        con.execute("INSERT INTO analysis_rows VALUES ('collision',5,0,2,'{\"SiO2\":40.0}','2026-08-14')")
        con.execute("INSERT INTO studies VALUES (7,9,'article','Paper','Citation','10.1/demo','A','2024','J','','','2026-08-14','2026-08-14')")
        con.execute("INSERT INTO dataset_studies VALUES (5,7,'Table S1','')")
        con.execute("INSERT INTO semantic_mappings VALUES (8,7,'morphology','core','core','','','resolved','2026-08-14','2026-08-14')")
        con.commit()
    finally:
        con.close()
    (staging / "manifest.json").write_text(json.dumps({
        "format": "petrolab-project-archive", "format_version": 2,
        "project": {"id": 9, "name": "Colleague project"}, "mode": "project",
    }), encoding="utf-8")
    archive = root / "colleague.petrolab"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in staging.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(staging))
    return archive


class CollaborationTests(unittest.TestCase):
    def test_plan_suggests_but_does_not_auto_merge_sample(self):
        with tempfile.TemporaryDirectory() as temp_dir, Workspace(Path(temp_dir)) as ws:
            archive = make_incoming_archive(Path(temp_dir))
            plan = collab.plan_collaboration_merge(archive, ws.project_id)
            self.assertEqual(plan.samples[0].name, "PG_15")
            self.assertEqual(plan.samples[0].suggested_target_ids, (ws.sample_id,))
            with self.assertRaises(ValueError):
                collab.apply_collaboration_merge(archive, ws.project_id, {})

    def test_explicit_merge_remaps_colliding_analysis_id_and_preserves_provenance(self):
        with tempfile.TemporaryDirectory() as temp_dir, Workspace(Path(temp_dir)) as ws:
            archive = make_incoming_archive(Path(temp_dir))
            result = collab.apply_collaboration_merge(archive, ws.project_id, {1: ws.sample_id})
            self.assertEqual(result.analysis_count, 1)
            with db.connect() as con:
                analyses = con.execute("SELECT analysis_id,data_json FROM analysis_rows ORDER BY rowid").fetchall()
                samples = con.execute("SELECT COUNT(*) FROM samples WHERE project_id=?", (ws.project_id,)).fetchone()[0]
                studies = con.execute("SELECT title,doi FROM studies WHERE project_id=?", (ws.project_id,)).fetchall()
                imported = con.execute("SELECT COUNT(*) FROM collaboration_imports").fetchone()[0]
                aliases = con.execute("SELECT alias FROM sample_aliases WHERE sample_id=?", (ws.sample_id,)).fetchall()
            self.assertEqual(len(analyses), 2)
            self.assertEqual(len({row["analysis_id"] for row in analyses}), 2)
            self.assertEqual(samples, 1)
            self.assertEqual([(row["title"], row["doi"]) for row in studies], [("Paper", "10.1/demo")])
            self.assertEqual(imported, 1)
            self.assertIn("PG 15", [row["alias"] for row in aliases])
            with self.assertRaises(ValueError):
                collab.plan_collaboration_merge(archive, ws.project_id)


if __name__ == "__main__":
    unittest.main()
