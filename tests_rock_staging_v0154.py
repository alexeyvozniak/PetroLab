from __future__ import annotations

import gc
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import petrolab.db as db
import petrolab.repositories.rock_repository as rock_repository
import petrolab.rock_comparison as rock_comparison
import petrolab.rock_determinations as determinations
import petrolab.rock_staged_service as rock_staging
import petrolab.sample_registry as samples
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
        self.stack.enter_context(patch.object(rock_repository, "DB_PATH", data / "petrolab.sqlite3"))
        ensure_storage()
        with db.connect() as con:
            con.execute("INSERT INTO projects(name, description, created_at) VALUES ('Whole rock', '', '2026-08-15')")
            self.project_id = int(con.execute("SELECT id FROM projects WHERE name='Whole rock'").fetchone()["id"])
            con.commit()
        return self

    def __exit__(self, exc_type, exc, tb):
        gc.collect()
        self.stack.close()
        gc.collect()


class RockStagingTests(unittest.TestCase):
    def test_repeated_sample_creates_two_determinations_without_overwriting_first(self):
        with tempfile.TemporaryDirectory() as temp_dir, Workspace(Path(temp_dir)) as ws:
            frame = pd.DataFrame({
                "Sample": ["19KL23", "19KL23"],
                "Lithology": ["lamprophyre", "lamprophyre"],
                "Source": ["Smith 2014", "Jones 2018"],
                "Method": ["XRF", "XRF"],
                "SiO2": [40.0, 42.0],
                "MgO": [8.0, 9.0],
                "Occurrence": ["Kandalaksha", "Kandalaksha"],
            })
            result = rock_staging.import_staged_rocks(
                frame,
                project_id=ws.project_id,
                source_file="literature.xlsx",
                source_sheet="compilation",
            )
            self.assertEqual(result.created_rocks, 1)
            self.assertEqual(result.reused_rocks, 1)
            self.assertEqual(len(result.rock_ids), 1)
            self.assertEqual(len(result.determination_ids), 2)
            self.assertEqual(result.source_links, 2)
            self.assertEqual(result.custom_attributes, 2)

            rock_id = result.rock_ids[0]
            stored = determinations.list_rock_determinations(rock_id)
            self.assertEqual(len(stored), 2)
            self.assertEqual({item["source_label"] for item in stored}, {"Smith 2014", "Jones 2018"})
            self.assertEqual({item["composition"]["SiO2"] for item in stored}, {40.0, 42.0})

            # Backward-compatible default composition is the first determination only.
            legacy = rock_repository.get_composition(rock_id)
            by_analyte = {str(row["analyte"]): float(row["value"]) for _, row in legacy.iterrows()}
            self.assertEqual(by_analyte["SiO2"], 40.0)
            self.assertEqual(by_analyte["MgO"], 8.0)

            # Comparison workspaces see both analytical determinations, not just the
            # legacy preferred/default composition.
            comparison = rock_comparison.whole_rock_comparison_dataframe(ws.project_id)
            self.assertEqual(len(comparison), 2)
            self.assertEqual(set(comparison[rock_comparison.ROCK_SOURCE_COLUMN]), {"Smith 2014", "Jones 2018"})
            self.assertEqual(set(comparison["SiO2"].astype(float)), {40.0, 42.0})

    def test_confirmed_russian_alias_reuses_canonical_sample(self):
        with tempfile.TemporaryDirectory() as temp_dir, Workspace(Path(temp_dir)) as ws:
            sample_id = samples.create_sample(ws.project_id, "Kandalaksha")
            frame = pd.DataFrame({
                "Sample": ["Кандалакша"],
                "Lithology": ["lamprophyre"],
                "SiO2": [41.0],
                "MgO": [8.5],
            })
            result = rock_staging.import_staged_rocks(
                frame,
                project_id=ws.project_id,
                confirmed_samples={"Кандалакша": sample_id},
            )
            self.assertEqual(result.created_rocks, 1)
            rock = rock_repository.get_rock(result.rock_ids[0])
            self.assertEqual(int(rock["sample_id"]), sample_id)
            self.assertEqual(rock["name"], "Kandalaksha")
            record = next(item for item in samples.list_samples(ws.project_id) if int(item["id"]) == sample_id)
            self.assertIn("Кандалакша", record["aliases"])


if __name__ == "__main__":
    unittest.main()
