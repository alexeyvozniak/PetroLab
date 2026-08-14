from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import petrolab.db as db
from petrolab.analytical_sessions import annotation_table
from petrolab.generations import generation_map
from petrolab.operation_journal import (
    assign_generation_with_journal,
    list_operations,
    reassign_phase_with_journal,
    set_annotation_with_journal,
    undo_operation,
)
from petrolab.phase_suggestions import materialize_confirmed_phases
from petrolab.project_health import project_health
from petrolab.smart_start import recommendations
from tests_guided_workflow import Workspace


class ProductGuidanceTests(unittest.TestCase):
    def test_smart_plot_recommendations_use_only_existing_columns(self):
        mica = recommendations("mica", ["Al2O3", "TiO2", "K2O"])
        self.assertTrue(mica)
        self.assertEqual((mica[0].x, mica[0].y), ("Al2O3", "TiO2"))
        self.assertNotIn("Mg#_formula", {mica[0].x, mica[0].y})

        cpx = recommendations("clinopyroxene", ["Na2O", "Cr2O3", "SiO2"])
        self.assertEqual((cpx[0].x, cpx[0].y), ("Na2O", "Cr2O3"))

        empty = recommendations("mica", ["Sample", "Point"])
        self.assertEqual(empty, [])

    def test_generation_annotation_and_phase_operations_are_reversible(self):
        with tempfile.TemporaryDirectory() as temp_dir, Workspace(Path(temp_dir)) as workspace:
            count = assign_generation_with_journal(workspace.project_id, ["a1", "a2"], "G1")
            self.assertEqual(count, 2)
            self.assertEqual(generation_map()["a1"], "G1")
            op = list_operations(workspace.project_id)[0]
            undo_operation(workspace.project_id, int(op["id"]))
            self.assertNotIn("a1", generation_map())
            self.assertNotIn("a2", generation_map())

            count = set_annotation_with_journal(
                workspace.project_id, ["a1", "a2"],
                namespace="morphology", key="zone", value="core", label="Zone → core",
            )
            self.assertEqual(count, 2)
            self.assertEqual(annotation_table(["a1"], namespace="morphology")["a1"]["zone"], "core")
            op = list_operations(workspace.project_id)[0]
            undo_operation(workspace.project_id, int(op["id"]))
            self.assertNotIn("zone", annotation_table(["a1"], namespace="morphology").get("a1", {}))

            children = materialize_confirmed_phases(10, {"a1": "trioctahedral mica"})
            mica_id = int(children["trioctahedral mica"])
            count = reassign_phase_with_journal(workspace.project_id, ["a1"], "calcic amphibole")
            self.assertEqual(count, 1)
            with db.connect() as con:
                moved = con.execute(
                    "SELECT a.dataset_id, d.mineral_key FROM analysis_rows a JOIN datasets d ON d.id=a.dataset_id WHERE a.analysis_id='a1'"
                ).fetchone()
                phase = con.execute(
                    "SELECT value FROM analysis_annotations WHERE analysis_id='a1' AND namespace='phase' AND key='confirmed_phase'"
                ).fetchone()
            self.assertNotEqual(int(moved["dataset_id"]), mica_id)
            self.assertEqual(str(moved["mineral_key"]), "amphibole")
            self.assertEqual(str(phase["value"]), "calcic amphibole")

            op = list_operations(workspace.project_id)[0]
            undo_operation(workspace.project_id, int(op["id"]))
            with db.connect() as con:
                restored = con.execute("SELECT dataset_id FROM analysis_rows WHERE analysis_id='a1'").fetchone()
                phase = con.execute(
                    "SELECT value FROM analysis_annotations WHERE analysis_id='a1' AND namespace='phase' AND key='confirmed_phase'"
                ).fetchone()
            self.assertEqual(int(restored["dataset_id"]), mica_id)
            self.assertEqual(str(phase["value"]), "trioctahedral mica")

    def test_project_health_surfaces_mixed_without_calling_it_invalid(self):
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
        for marker in ["Основное", "Добавить данные", "Требует внимания", "Массовые действия", "Расширенные инструменты"]:
            self.assertIn(marker, navigation)
        for marker in ["Мои анализы", "Статья / коллега", "Полевые Sample", "pending_study_id"]:
            self.assertIn(marker, add_data)


if __name__ == "__main__":
    unittest.main()
