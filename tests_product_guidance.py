from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

import pandas as pd


class Workspace:
    def __init__(self, root: Path):
        self.root = root
        self.previous = os.environ.get("PETROLAB_DATA_DIR")

    def __enter__(self):
        os.environ["PETROLAB_DATA_DIR"] = str(self.root / "data")
        from petrolab.storage import ensure_storage
        from petrolab.db import create_project

        ensure_storage()
        self.project_id = create_project("Product guidance", "CI-only")
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.previous is None:
            os.environ.pop("PETROLAB_DATA_DIR", None)
        else:
            os.environ["PETROLAB_DATA_DIR"] = self.previous


class ProductGuidanceTests(unittest.TestCase):
    def test_smart_start_prefers_actionable_dataset(self):
        from petrolab import db
        from petrolab.smart_start import choose_start_action

        with tempfile.TemporaryDirectory() as temp_dir, Workspace(Path(temp_dir)) as workspace:
            mixed_id = db.add_dataset(
                workspace.project_id, "Mixed", "generic", "mixed.xlsx", "Sheet1", "sha",
                str(Path(temp_dir) / "mixed.csv"), 2, source_kind="managed_copy",
            )
            mica_id = db.add_dataset(
                workspace.project_id, "Mica", "mica", "mica.xlsx", "Sheet1", "sha2",
                str(Path(temp_dir) / "mica.csv"), 1, source_kind="managed_copy",
            )
            db.replace_dataset_rows(mixed_id, pd.DataFrame([
                {"Sample": "S1", "SiO2": 40.0},
                {"Sample": "S2", "SiO2": 50.0},
            ]), source_rows=[2, 3])
            db.replace_dataset_rows(mica_id, pd.DataFrame([
                {"Sample": "M1", "SiO2": 38.0, "Al2O3": 15.0, "MgO": 20.0, "FeOt": 8.0},
            ]), source_rows=[2])
            action = choose_start_action(workspace.project_id)
            self.assertIn(action.route, {"mixed_minerals", "workflow", "formulae"})
            self.assertIsInstance(action.dataset_id, int)

    def test_batch_phase_move_is_logged_and_undoable(self):
        from petrolab import db
        from petrolab.operation_journal import list_operations, undo_operation
        from petrolab.phase_reassignment import move_points_to_mineral

        with tempfile.TemporaryDirectory() as temp_dir, Workspace(Path(temp_dir)) as workspace:
            mixed_id = db.add_dataset(
                workspace.project_id, "Mixed", "generic", "mixed.xlsx", "Sheet1", "sha",
                str(Path(temp_dir) / "mixed.csv"), 1, source_kind="managed_copy",
            )
            db.replace_dataset_rows(
                mixed_id,
                pd.DataFrame([{"Sample": "S1", "Point": "P1", "SiO2": 40.0, "MgO": 20.0}]),
                source_rows=[2],
            )
            source = db.load_dataset_dataframe(mixed_id, include_meta=True)
            analysis_id = str(source.loc[0, "_analysis_id"])
            mica_id = move_points_to_mineral(
                workspace.project_id,
                mixed_id,
                [analysis_id],
                "mica",
                confirmed_phase="trioctahedral mica",
            )
            operations = list_operations(workspace.project_id)
            self.assertTrue(operations)
            with db.connect() as con:
                moved = con.execute("SELECT dataset_id FROM analysis_rows WHERE analysis_id=?", (analysis_id,)).fetchone()
            self.assertEqual(int(moved["dataset_id"]), mica_id)
            undo_operation(workspace.project_id, int(operations[0]["id"]))
            with db.connect() as con:
                restored = con.execute("SELECT dataset_id FROM analysis_rows WHERE analysis_id=?", (analysis_id,)).fetchone()
            self.assertEqual(int(restored["dataset_id"]), mixed_id)

    def test_project_health_surfaces_mixed_without_calling_it_invalid(self):
        from petrolab.project_health import project_health

        with tempfile.TemporaryDirectory() as temp_dir, Workspace(Path(temp_dir)) as workspace:
            health = project_health(workspace.project_id)
            kinds = {issue.kind for issue in health["issues"]}
            self.assertIn("mixed", kinds)
            self.assertNotIn("no_session", kinds)
            mixed = next(issue for issue in health["issues"] if issue.kind == "mixed")
            self.assertEqual(mixed.route, "mixed_minerals")
            self.assertGreaterEqual(mixed.count, 2)

    def test_primary_navigation_is_user_task_oriented(self):
        navigation = Path("petrolab/ui/navigation.py").read_text(encoding="utf-8")
        add_data = Path("petrolab/ui/pages/add_data.py").read_text(encoding="utf-8")
        for marker in [
            "Основное",
            "Рабочий стол",
            "Добавить данные",
            "Требует внимания",
            "Глобальный поиск",
            "Массовые действия",
            "Все инструменты",
        ]:
            self.assertIn(marker, navigation)
        for marker in ["Мои анализы", "Статья / коллега", "Полевые Sample", "pending_study_id"]:
            self.assertIn(marker, add_data)


if __name__ == "__main__":
    unittest.main()
