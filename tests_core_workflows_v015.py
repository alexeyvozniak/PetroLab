from __future__ import annotations

import gc
import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import matplotlib.pyplot as plt
import pandas as pd

import petrolab.db as db
from petrolab.auto_pipeline import auto_process_dataset
from petrolab.composite_points import composite_points_dataframe, set_physical_point_links
from petrolab.measurement_registry import create_entity
from petrolab.multi_panel_plotting import build_multi_panel_scatter
from petrolab.tectonic_discrimination import TECTONIC_PRESETS, prepare_tectonic_dataframe
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
        ensure_storage()
        with db.connect() as con:
            con.execute("INSERT INTO projects(name, description, created_at) VALUES ('Demo', '', '2026-08-15')")
            self.project_id = int(con.execute("SELECT id FROM projects WHERE name='Demo'").fetchone()["id"])
            con.commit()
        return self

    def add_dataset(self, dataset_id: int, name: str, mineral_key: str, rows: list[tuple[str, dict]], source: str) -> None:
        with db.connect() as con:
            con.execute(
                """INSERT INTO datasets(id,project_id,name,mineral_key,source_filename,source_sheet,source_sha256,csv_path,row_count,imported_at,source_kind)
                   VALUES(?,?,?,?,?,'Sheet1',?,'',?,'2026-08-15','managed_copy')""",
                (int(dataset_id), int(self.project_id), name, mineral_key, source, f"sha-{dataset_id}", len(rows)),
            )
            con.execute(
                """INSERT INTO project_dataset_links(project_id,dataset_id,note,added_at,purpose)
                   VALUES(?,?,?,'2026-08-15','working')""",
                (int(self.project_id), int(dataset_id), "test"),
            )
            for index, (analysis_id, payload) in enumerate(rows):
                con.execute(
                    """INSERT INTO analysis_rows(analysis_id,dataset_id,row_index,source_row,data_json,updated_at)
                       VALUES(?,?,?,?,?,'2026-08-15')""",
                    (analysis_id, int(dataset_id), index, index + 2, json.dumps(payload, ensure_ascii=False)),
                )
            con.commit()

    def __exit__(self, exc_type, exc, tb):
        gc.collect()
        self.stack.close()


class CoreWorkflowV015Tests(unittest.TestCase):
    def test_composite_point_joins_epma_and_la_without_rewriting_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir, Workspace(Path(temp_dir)) as ws:
            ws.add_dataset(
                10, "EPMA", "mica",
                [("epma-13", {"Sample": "K-1", "Point": "13", "MgO": 20.2, "SiO2": 40.1})],
                "probe.xlsx",
            )
            ws.add_dataset(
                11, "LA", "generic",
                [("la-13", {"Sample": "K-1", "Point": "13", "Rb [µg/g]": 825.0, "Sr [µg/g]": 112.0})],
                "laser.xlsx",
            )
            section_id = create_entity(ws.project_id, kind="thin_section", name="K-1 thin section")
            point_id = create_entity(ws.project_id, kind="probe_point", name="P-13", parent_id=section_id)
            set_physical_point_links(ws.project_id, point_id, ["epma-13", "la-13"])

            frame = composite_points_dataframe(ws.project_id, thin_section_id=section_id)
            self.assertEqual(len(frame), 1)
            row = frame.iloc[0]
            self.assertAlmostEqual(float(row["MgO"]), 20.2)
            self.assertAlmostEqual(float(row["Rb [µg/g]"]), 825.0)
            self.assertEqual(int(row["Связанных анализов"]), 2)
            provenance = json.loads(str(row["_provenance_json"]))
            self.assertEqual(provenance["MgO"][0]["analysis_id"], "epma-13")
            self.assertEqual(provenance["Rb [µg/g]"][0]["analysis_id"], "la-13")
            with db.connect() as con:
                stored = con.execute("SELECT analysis_id,data_json FROM analysis_rows ORDER BY analysis_id").fetchall()
            self.assertEqual([str(item["analysis_id"]) for item in stored], ["epma-13", "la-13"])

    def test_composite_conflict_never_silently_picks_one_method(self):
        from petrolab.composite_points import _merge_records

        merged, provenance, conflicts = _merge_records([
            {"analysis_id": "a", "dataset_id": 1, "dataset": "EPMA", "source": "a.xlsx", "values": {"MgO": 20.0}},
            {"analysis_id": "b", "dataset_id": 2, "dataset": "EDS", "source": "b.xlsx", "values": {"MgO": 21.0}},
        ])
        self.assertIn("MgO", conflicts)
        self.assertTrue(pd.isna(merged["MgO"]))
        self.assertEqual(merged["MgO · EPMA"], 20.0)
        self.assertEqual(merged["MgO · EDS"], 21.0)
        self.assertEqual(provenance["MgO · EPMA"][0]["analysis_id"], "a")

    def test_auto_probe_pipeline_materializes_only_high_confidence_rows_and_marks_provenance(self):
        with tempfile.TemporaryDirectory() as temp_dir, Workspace(Path(temp_dir)) as ws:
            ws.add_dataset(
                20,
                "mixed probe",
                "generic",
                [
                    ("mica-1", {"Sample": "S1", "Point": "1", "SiO2": 40.0, "Al2O3": 15.0, "MgO": 20.0, "FeO": 10.0, "K2O": 9.0}),
                    ("apatite-1", {"Sample": "S1", "Point": "2", "P2O5": 42.0, "CaO": 55.0, "F": 3.0}),
                    ("uncertain-1", {"Sample": "S1", "Point": "3", "SiO2": 49.0, "Na2O": 1.0, "MgO": 0.2, "CaO": 0.2}),
                ],
                "probe.xlsx",
            )
            report = auto_process_dataset(ws.project_id, 20)
            self.assertGreaterEqual(report.auto_assigned_rows, 2)
            self.assertGreaterEqual(len(report.phase_dataset_ids), 2)
            with db.connect() as con:
                annotations = con.execute(
                    "SELECT analysis_id,value,source FROM analysis_annotations WHERE namespace='phase' ORDER BY analysis_id"
                ).fetchall()
                all_rows = con.execute("SELECT analysis_id FROM analysis_rows ORDER BY analysis_id").fetchall()
            self.assertEqual(len(all_rows), 3, "auto split must move, never duplicate source rows")
            self.assertTrue(annotations)
            self.assertTrue(all(str(row["source"]).startswith("auto_high_confidence:") for row in annotations))

    def test_multi_panel_uses_one_selection_and_shared_groups(self):
        frame = pd.DataFrame({
            "Al2O3": [12.0, 13.0, 15.0, 16.0],
            "TiO2": [2.0, 2.5, 1.0, 1.4],
            "MgO": [18.0, 17.0, 21.0, 20.0],
            "FeO": [10.0, 11.0, 7.0, 8.0],
            "Source": ["own", "own", "paper", "paper"],
        })
        styles = {
            "own": {"alpha": 1.0, "display_mode": "points"},
            "paper": {"alpha": 0.25, "display_mode": "points"},
        }
        fig = build_multi_panel_scatter(
            frame,
            [
                {"x": "Al2O3", "y": "TiO2", "title": "A"},
                {"x": "MgO", "y": "FeO", "title": "B"},
            ],
            group_column="Source",
            style_map=styles,
            columns=2,
        )
        self.assertEqual(len(fig.axes), 2)
        self.assertEqual([axis.get_title() for axis in fig.axes], ["A", "B"])
        plt.close(fig)

    def test_pearce_coordinates_and_transforms_are_locked_to_verified_presets(self):
        ynb = TECTONIC_PRESETS["pearce_y_nb"]
        self.assertEqual(ynb.boundaries[0][1], (1.0, 2000.0))
        self.assertEqual(ynb.boundaries[0][2], (50.0, 10.0))
        rb = TECTONIC_PRESETS["pearce_rb_ynb"]
        self.assertEqual(rb.boundaries[0][1], (2.0, 80.0))
        self.assertEqual(rb.boundaries[-1][2], (2000.0, 400.0))

        frame = pd.DataFrame({
            "Y [µg/g]": [20.0, 40.0],
            "Nb [µg/g]": [10.0, 15.0],
            "Rb [µg/g]": [100.0, 150.0],
        })
        y_nb = prepare_tectonic_dataframe(frame, "pearce_y_nb")
        self.assertEqual(y_nb["_tectonic_x"].tolist(), [20.0, 40.0])
        self.assertEqual(y_nb["_tectonic_y"].tolist(), [10.0, 15.0])
        rb_ynb = prepare_tectonic_dataframe(frame, "pearce_rb_ynb")
        self.assertEqual(rb_ynb["_tectonic_x"].tolist(), [30.0, 55.0])
        self.assertEqual(rb_ynb["_tectonic_y"].tolist(), [100.0, 150.0])


if __name__ == "__main__":
    unittest.main()
