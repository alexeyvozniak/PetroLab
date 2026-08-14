from __future__ import annotations

import gc
import sqlite3
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import petrolab.db as db
import petrolab.project_archive as archive
from petrolab.analytical_sessions import create_session
from petrolab.sample_registry import create_sample
from petrolab.source_registry import create_study
from petrolab.storage import ensure_storage


class ArchiveScopeTests(unittest.TestCase):
    def test_snapshot_excludes_child_metadata_from_other_projects(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data = root / "data"
            stack = ExitStack()
            stack.enter_context(patch.object(db, "DATA_DIR", data))
            stack.enter_context(patch.object(db, "DB_PATH", data / "petrolab.sqlite3"))
            stack.enter_context(patch.object(db, "ASSETS_DIR", data / "assets"))
            stack.enter_context(patch.object(db, "BACKUPS_DIR", data / "backups"))
            stack.enter_context(patch.object(archive, "DB_PATH", data / "petrolab.sqlite3"))
            try:
                ensure_storage()
                with db.connect() as con:
                    con.execute("INSERT INTO projects(name,description,created_at) VALUES ('A','','2026-08-14')")
                    a = int(con.execute("SELECT id FROM projects WHERE name='A'").fetchone()["id"])
                    con.execute("INSERT INTO projects(name,description,created_at) VALUES ('B','','2026-08-14')")
                    b = int(con.execute("SELECT id FROM projects WHERE name='B'").fetchone()["id"])
                    con.commit()

                sa = create_sample(a, "A-1")
                sb = create_sample(b, "B-1")
                create_session(a, sa, name="A session")
                create_session(b, sb, name="B session")
                study_a = create_study(a, source_type="article", title="A paper")
                study_b = create_study(b, source_type="article", title="B paper")

                with db.connect() as con:
                    con.execute("INSERT INTO sample_aliases(sample_id,alias,normalized_key,source) VALUES (?,?,?,'manual')", (sa, "A alias", "aalias"))
                    con.execute("INSERT INTO sample_aliases(sample_id,alias,normalized_key,source) VALUES (?,?,?,'manual')", (sb, "B alias", "balias"))
                    con.execute("INSERT INTO semantic_mappings(study_id,domain,source_label,normalized_value,status) VALUES (?,'generation','A','A','resolved')", (study_a,))
                    con.execute("INSERT INTO semantic_mappings(study_id,domain,source_label,normalized_value,status) VALUES (?,'generation','B','B','resolved')", (study_b,))
                    now = "2026-08-14"
                    con.execute("INSERT INTO rock_samples(project_id,name,created_at,updated_at) VALUES (?, 'A rock', ?, ?)", (a, now, now))
                    rock_a = int(con.execute("SELECT id FROM rock_samples WHERE project_id=?", (a,)).fetchone()["id"])
                    con.execute("INSERT INTO rock_samples(project_id,name,created_at,updated_at) VALUES (?, 'B rock', ?, ?)", (b, now, now))
                    rock_b = int(con.execute("SELECT id FROM rock_samples WHERE project_id=?", (b,)).fetchone()["id"])
                    con.execute("INSERT INTO rock_compositions(rock_id,analyte,value,unit,updated_at) VALUES (?, 'SiO2', 50, 'wt%', ?)", (rock_a, now))
                    con.execute("INSERT INTO rock_compositions(rock_id,analyte,value,unit,updated_at) VALUES (?, 'SiO2', 60, 'wt%', ?)", (rock_b, now))
                    con.commit()

                snapshot = root / "snapshot.sqlite3"
                archive._project_database_snapshot(a, snapshot)
                con = sqlite3.connect(snapshot)
                try:
                    self.assertEqual(con.execute("SELECT COUNT(*) FROM projects").fetchone()[0], 1)
                    self.assertEqual(con.execute("SELECT name FROM projects").fetchone()[0], "A")
                    self.assertEqual([row[0] for row in con.execute("SELECT alias FROM sample_aliases")], ["A alias"])
                    self.assertEqual([row[0] for row in con.execute("SELECT source_label FROM semantic_mappings")], ["A"])
                    self.assertEqual(con.execute("SELECT COUNT(*) FROM analytical_sessions").fetchone()[0], 1)
                    self.assertEqual([row[0] for row in con.execute("SELECT value FROM rock_compositions")], [50.0])
                finally:
                    con.close()
            finally:
                gc.collect()
                stack.close()


if __name__ == "__main__":
    unittest.main()
