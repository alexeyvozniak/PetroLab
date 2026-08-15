from __future__ import annotations

import gc
import json
import tempfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import petrolab.db as db
from petrolab.auto_pipeline import auto_process_dataset
from petrolab.composite_points import composite_points_dataframe, set_physical_point_links, sync_slide_markers_to_physical_points
from petrolab.measurement_registry import create_entity
from petrolab.physical_point_safety import ambiguous_marker_entity_ids, set_slide_marker_entity
from petrolab.services import import_runtime
from petrolab.slides import create_slide_marker, ensure_slide_schema
from petrolab.storage import ensure_storage
from petrolab.ui.work_context import filter_dataframe_to_context


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
            con.execute("INSERT INTO projects(name,description,created_at) VALUES('A','','2026-08-15')")
            con.execute("INSERT INTO projects(name,description,created_at) VALUES('B','','2026-08-15')")
            self.project_id = int(con.execute("SELECT id FROM projects WHERE name='A'").fetchone()["id"])
            self.other_project_id = int(con.execute("SELECT id FROM projects WHERE name='B'").fetchone()["id"])
            con.commit()
        return self

    def add_dataset(self, dataset_id: int, rows: list[tuple[str, dict]], *, link: bool = True):
        with db.connect() as con:
            con.execute(
                """INSERT INTO datasets(id,project_id,name,mineral_key,source_filename,source_sheet,source_sha256,csv_path,row_count,imported_at,source_kind)
                   VALUES(?,?,?,'generic','probe.xlsx','Sheet1',?,'',?,'2026-08-15','managed_copy')""",
                (int(dataset_id), int(self.project_id), f"D{dataset_id}", f"sha-{dataset_id}", len(rows)),
            )
            if link:
                con.execute(
                    """INSERT INTO project_dataset_links(project_id,dataset_id,note,added_at,purpose)
                       VALUES(?,?,'test','2026-08-15','working')""",
                    (int(self.project_id), int(dataset_id)),
                )
            for i, (analysis_id, payload) in enumerate(rows):
                con.execute(
                    """INSERT INTO analysis_rows(analysis_id,dataset_id,row_index,source_row,data_json,updated_at)
                       VALUES(?,?,?,?,?,'2026-08-15')""",
                    (analysis_id, int(dataset_id), i, i + 2, json.dumps(payload, ensure_ascii=False)),
                )
            con.commit()

    def __exit__(self, exc_type, exc, tb):
        # SQLite connections are explicitly closed by db.connect(). On Windows, short-lived
        # sqlite cursor/row objects can nevertheless keep the file handle alive until GC.
        # Collect before restoring the patched DB path so TemporaryDirectory teardown is deterministic.
        gc.collect()
        self.stack.close()
        gc.collect()


def _add_fake_image(project_id: int, thin_section_id: int, title: str) -> int:
    ensure_slide_schema()
    with db.connect() as con:
        cur = con.execute(
            """INSERT INTO slide_images(project_id,thin_section_id,title,image_type,storage_mode,original_filename,
                   source_path,managed_path,preview_path,content_sha256,pixel_width,pixel_height)
               VALUES(?,?,?,'BSE','managed',?,'','','','sha',100,100)""",
            (int(project_id), int(thin_section_id), title, f"{title}.png"),
        )
        con.commit()
        return int(cur.lastrowid)


def test_same_label_on_two_images_is_not_physical_identity():
    with tempfile.TemporaryDirectory() as tmp, Workspace(Path(tmp)) as ws:
        ws.add_dataset(10, [("a1", {"Sample": "S1", "Point": "1", "MgO": 20.0}), ("a2", {"Sample": "S1", "Point": "2", "MgO": 21.0})])
        section = create_entity(ws.project_id, kind="thin_section", name="TS")
        image1 = _add_fake_image(ws.project_id, section, "PPL")
        image2 = _add_fake_image(ws.project_id, section, "BSE")
        m1 = create_slide_marker(ws.project_id, slide_image_id=image1, x_norm=.1, y_norm=.1, label="P-1", analysis_ids=("a1",))
        m2 = create_slide_marker(ws.project_id, slide_image_id=image2, x_norm=.8, y_norm=.8, label="P-1", analysis_ids=("a2",))
        sync_slide_markers_to_physical_points(ws.project_id)
        with db.connect() as con:
            rows = con.execute("SELECT id,entity_id,entity_link_source FROM slide_markers WHERE id IN (?,?) ORDER BY id", (m1, m2)).fetchall()
        assert int(rows[0]["entity_id"]) != int(rows[1]["entity_id"])
        assert {str(row["entity_link_source"]) for row in rows} == {"auto_marker"}
        frame = composite_points_dataframe(ws.project_id, thin_section_id=section)
        assert len(frame) == 2
        assert sorted(frame["Связанных анализов"].astype(int).tolist()) == [1, 1]


def test_explicit_marker_link_can_share_one_physical_point():
    with tempfile.TemporaryDirectory() as tmp, Workspace(Path(tmp)) as ws:
        ws.add_dataset(11, [("b1", {"Sample": "S1", "MgO": 20.0}), ("b2", {"Sample": "S1", "Rb [µg/g]": 800.0})])
        section = create_entity(ws.project_id, kind="thin_section", name="TS")
        point = create_entity(ws.project_id, kind="probe_point", name="P-7", parent_id=section)
        image1 = _add_fake_image(ws.project_id, section, "PPL")
        image2 = _add_fake_image(ws.project_id, section, "LA")
        m1 = create_slide_marker(ws.project_id, slide_image_id=image1, x_norm=.2, y_norm=.2, label="P-7", entity_id=point, analysis_ids=("b1",))
        m2 = create_slide_marker(ws.project_id, slide_image_id=image2, x_norm=.2, y_norm=.2, label="P-7", analysis_ids=("b2",))
        set_slide_marker_entity(ws.project_id, m2, point)
        sync_slide_markers_to_physical_points(ws.project_id)
        with db.connect() as con:
            entities = [int(row["entity_id"]) for row in con.execute("SELECT entity_id FROM slide_markers WHERE id IN (?,?) ORDER BY id", (m1, m2)).fetchall()]
        assert entities == [point, point]
        assert not ambiguous_marker_entity_ids(ws.project_id)


def test_resolving_legacy_collision_removes_moved_analysis_from_old_point():
    with tempfile.TemporaryDirectory() as tmp, Workspace(Path(tmp)) as ws:
        ws.add_dataset(15, [("f1", {"Sample": "S1", "MgO": 20.0}), ("f2", {"Sample": "S1", "Rb [µg/g]": 700.0})])
        section = create_entity(ws.project_id, kind="thin_section", name="TS")
        old_point = create_entity(
            ws.project_id,
            kind="probe_point",
            name="P-1",
            parent_id=section,
            description="Создано из разметки шлифа для composite analysis",
        )
        image1 = _add_fake_image(ws.project_id, section, "PPL")
        image2 = _add_fake_image(ws.project_id, section, "BSE")
        m1 = create_slide_marker(ws.project_id, slide_image_id=image1, x_norm=.1, y_norm=.1, label="P-1", analysis_ids=("f1",))
        m2 = create_slide_marker(ws.project_id, slide_image_id=image2, x_norm=.9, y_norm=.9, label="P-1", analysis_ids=("f2",))
        set_physical_point_links(ws.project_id, old_point, ["f1", "f2"])
        # Give the surviving link distinctive provenance: resolving f2 must not rewrite it.
        with db.connect() as con:
            con.execute(
                "UPDATE physical_point_analysis_links SET link_role='manual_reference', note='keep this provenance' WHERE entity_id=? AND analysis_id='f1'",
                (old_point,),
            )
            con.commit()
        # Recreate the exact legacy v0.15 state: same auto-created entity, no provenance.
        from petrolab.physical_point_safety import _ensure_marker_link_source_schema
        _ensure_marker_link_source_schema()
        with db.connect() as con:
            con.execute(
                "UPDATE slide_markers SET entity_id=?, entity_link_source='' WHERE id IN (?,?)",
                (old_point, m1, m2),
            )
            con.commit()
        assert ambiguous_marker_entity_ids(ws.project_id) == {old_point}

        new_point = create_entity(ws.project_id, kind="probe_point", name="P-1 moved", parent_id=section)
        set_slide_marker_entity(ws.project_id, m2, new_point)
        with db.connect() as con:
            old_rows = con.execute(
                "SELECT analysis_id,link_role,note FROM physical_point_analysis_links WHERE entity_id=? ORDER BY analysis_id",
                (old_point,),
            ).fetchall()
            new_links = [str(row["analysis_id"]) for row in con.execute(
                "SELECT analysis_id FROM physical_point_analysis_links WHERE entity_id=? ORDER BY analysis_id", (new_point,)
            ).fetchall()]
        assert [str(row["analysis_id"]) for row in old_rows] == ["f1"]
        assert str(old_rows[0]["link_role"]) == "manual_reference"
        assert str(old_rows[0]["note"]) == "keep this provenance"
        assert new_links == ["f2"]
        # Confirming the remaining marker on its original point finishes the migration.
        set_slide_marker_entity(ws.project_id, m1, old_point)
        assert not ambiguous_marker_entity_ids(ws.project_id)


def test_composite_sample_comes_from_physical_registry_not_conflicting_rows():
    with tempfile.TemporaryDirectory() as tmp, Workspace(Path(tmp)) as ws:
        from petrolab.sample_registry import create_sample
        sample_id = create_sample(ws.project_id, "CANONICAL")
        ws.add_dataset(12, [("c1", {"Sample": "wrong-A", "MgO": 20.0}), ("c2", {"Sample": "wrong-B", "Rb [µg/g]": 700.0})])
        section = create_entity(ws.project_id, kind="thin_section", name="TS", sample_id=sample_id)
        point = create_entity(ws.project_id, kind="probe_point", name="P-1", parent_id=section, sample_id=sample_id)
        set_physical_point_links(ws.project_id, point, ["c1", "c2"])
        frame = composite_points_dataframe(ws.project_id, thin_section_id=section)
        assert frame.iloc[0]["Sample"] == "CANONICAL"
        assert frame.iloc[0]["Thin Section"] == "TS"
        assert frame.iloc[0]["Physical Point"] == "P-1"


def test_thin_section_context_intersects_and_empty_links_do_not_broaden_to_sample():
    with tempfile.TemporaryDirectory() as tmp, Workspace(Path(tmp)) as ws:
        ws.add_dataset(13, [("d1", {"Sample": "S1"}), ("d2", {"Sample": "S1"}), ("d3", {"Sample": "S2"})])
        section = create_entity(ws.project_id, kind="thin_section", name="TS")
        frame = pd.DataFrame([
            {"_analysis_id": "d1", "_dataset_id": 13, "Sample": "S1"},
            {"_analysis_id": "d2", "_dataset_id": 13, "Sample": "S1"},
            {"_analysis_id": "d3", "_dataset_id": 13, "Sample": "S2"},
        ])
        context = {"project_id": ws.project_id, "thin_section_id": section, "sample": "S1", "analysis_ids": [], "dataset_ids": [13]}
        assert filter_dataframe_to_context(frame, context).empty
        point = create_entity(ws.project_id, kind="probe_point", name="P", parent_id=section)
        set_physical_point_links(ws.project_id, point, ["d2"])
        assert filter_dataframe_to_context(frame, context)["_analysis_id"].tolist() == ["d2"]


def test_auto_pipeline_rejects_cross_project_dataset_before_processing():
    with tempfile.TemporaryDirectory() as tmp, Workspace(Path(tmp)) as ws:
        ws.add_dataset(14, [("e1", {"SiO2": 40.0, "Al2O3": 15.0, "MgO": 20.0, "FeO": 10.0, "K2O": 9.0})])
        try:
            auto_process_dataset(ws.other_project_id, 14)
        except ValueError as exc:
            assert "не входит" in str(exc)
        else:
            raise AssertionError("cross-project auto processing must be blocked")
        with db.connect() as con:
            assert con.execute("SELECT dataset_id FROM analysis_rows WHERE analysis_id='e1'").fetchone()["dataset_id"] == 14


def test_runtime_prepare_persists_detected_method():
    class Svc:
        MINERALS = {"generic": object()}

        @staticmethod
        def _attach_detected_method(frame, column_map):
            from petrolab.services.import_service import _attach_detected_method
            return _attach_detected_method(frame, column_map)

        @staticmethod
        def _calculate_mineral(frame, mineral):
            return frame

    prepared = import_runtime._prepare(
        Svc,
        reader=lambda sheet, header: (
            pd.DataFrame({"SiO2": [40.0]}),
            {"SiO2": {"original": "SiO2", "quantity_kind": "oxide", "wds_protocol": True}, "__schema__": {}},
            [2],
        ),
        sheet_names=["Probe"], default_header=1, default_mineral="generic",
        header_rows=None, mineral_keys=None, semantic_maps=None, measurement_maps=None,
    )
    assert prepared[0].dataframe["Method"].tolist() == ["EPMA-WDS"]


if __name__ == "__main__":
    test_same_label_on_two_images_is_not_physical_identity()
    test_explicit_marker_link_can_share_one_physical_point()
    test_resolving_legacy_collision_removes_moved_analysis_from_old_point()
    test_composite_sample_comes_from_physical_registry_not_conflicting_rows()
    test_thin_section_context_intersects_and_empty_links_do_not_broaden_to_sample()
    test_auto_pipeline_rejects_cross_project_dataset_before_processing()
    test_runtime_prepare_persists_detected_method()
    print("v0.15.1 silent-error tests: OK")
