from __future__ import annotations

import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import petrolab.db as db
import petrolab.source_registry as sources
from petrolab.analysis_groups import WORK_GROUP_COLUMN
from petrolab.storage import ensure_storage
from petrolab.ui.source_controls import (
    apply_plot_visibility_filters,
    available_visibility_dimensions,
    normalize_visibility_filters,
)


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
        self.project_id = db.create_project("Kovdor 2026")
        self.other_project_id = db.create_project("Literature")
        return self

    def __exit__(self, exc_type, exc, tb):
        self.stack.close()

    def add_dataset(self, project_id: int, name: str) -> int:
        return db.add_dataset(
            project_id=project_id,
            name=name,
            mineral_key="phlogopite",
            source_filename=f"{name}.xlsx",
            source_sheet="Sheet1",
            source_sha256="test-sha",
            csv_path=str(self.root / f"{name}.csv"),
            row_count=0,
            source_kind="managed_copy",
        )


class SourceRegistryTests(unittest.TestCase):
    def test_study_scoped_semantic_mappings_do_not_leak(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir, Workspace(Path(temp_dir)) as ws:
            first = sources.create_study(ws.project_id, source_type="article", citation="Author A, 2020")
            second = sources.create_study(ws.project_id, source_type="article", citation="Author B, 2021")
            sources.upsert_semantic_mapping(
                first, domain="generation", source_label="Phl-I",
                normalized_value="core", user_interpretation="primitive core",
            )
            first_rows = sources.list_semantic_mappings(first)
            second_rows = sources.list_semantic_mappings(second)
            self.assertEqual(len(first_rows), 1)
            self.assertEqual(first_rows[0]["source_label"], "Phl-I")
            self.assertEqual(second_rows, [])

    def test_cross_project_dataset_source_link_is_rejected(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir, Workspace(Path(temp_dir)) as ws:
            dataset_id = ws.add_dataset(ws.project_id, "Own data")
            foreign_study = sources.create_study(ws.other_project_id, source_type="article", citation="Foreign")
            with self.assertRaises(ValueError):
                sources.link_dataset_to_study(dataset_id, foreign_study)

    def test_data_health_reports_unlinked_dataset_and_incomplete_source(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir, Workspace(Path(temp_dir)) as ws:
            ws.add_dataset(ws.project_id, "Unlinked")
            sources.create_study(ws.project_id, source_type="other")
            health = sources.database_health(ws.project_id)
            kinds = {issue.kind for issue in health["issues"]}
            self.assertIn("unlinked_source", kinds)
            self.assertIn("study_metadata", kinds)
            self.assertLess(health["score"], 100)

    def test_linked_dataset_is_not_reported_as_unlinked(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir, Workspace(Path(temp_dir)) as ws:
            dataset_id = ws.add_dataset(ws.project_id, "Literature mica")
            study_id = sources.create_study(ws.project_id, source_type="article", citation="Author et al., 2024")
            sources.link_dataset_to_study(dataset_id, study_id, source_table="Table S2")
            health = sources.database_health(ws.project_id)
            self.assertEqual(health["unlinked_datasets"], 0)

    def test_article_source_can_filter_all_linked_datasets_without_deleting_rows(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir, Workspace(Path(temp_dir)) as ws:
            first_table = ws.add_dataset(ws.project_id, "Apatite Table 1")
            second_table = ws.add_dataset(ws.project_id, "Apatite Table S2")
            comparison = ws.add_dataset(ws.project_id, "Comparison apatite")
            unlinked = ws.add_dataset(ws.project_id, "Unlinked apatite")
            first_study = sources.create_study(
                ws.project_id,
                source_type="article",
                citation="Ivanov et al.",
                year="2020",
                doi="10.1000/ivanov",
            )
            second_study = sources.create_study(
                ws.project_id,
                source_type="article",
                citation="Petrov et al., 2024",
            )
            sources.link_dataset_to_study(first_table, first_study, source_table="Table 1")
            sources.link_dataset_to_study(second_table, first_study, source_table="Table S2")
            sources.link_dataset_to_study(comparison, second_study, source_table="Supplement")

            original = pd.DataFrame({
                "_analysis_id": ["a1", "a2", "b1", "u1"],
                "_dataset_id": [first_table, second_table, comparison, unlinked],
                "Минерал": ["apatite"] * 4,
                "P2O5": [41.0, 42.0, 40.5, 39.0],
            })
            enriched = sources.attach_study_metadata(original)

            self.assertNotIn(sources.SOURCE_LABEL_COLUMN, original.columns)
            self.assertEqual(enriched.loc[0, sources.SOURCE_LABEL_COLUMN], "Ivanov et al. (2020)")
            self.assertEqual(enriched.loc[1, sources.SOURCE_TABLE_COLUMN], "Table S2")
            self.assertEqual(enriched.loc[2, sources.SOURCE_LABEL_COLUMN], "Petrov et al., 2024")
            self.assertEqual(enriched.loc[3, sources.SOURCE_LABEL_COLUMN], sources.UNLINKED_SOURCE_LABEL)
            self.assertEqual(enriched.loc[0, sources.SOURCE_DOI_COLUMN], "10.1000/ivanov")

            visible, hidden = sources.filter_visible_sources(enriched, ["Ivanov et al. (2020)"])
            self.assertEqual(visible["_analysis_id"].tolist(), ["a1", "a2"])
            self.assertEqual(hidden["_analysis_id"].tolist(), ["b1", "u1"])
            self.assertEqual(len(enriched), 4, "Source visibility must not mutate or delete analytical rows")

    def test_plot_visibility_combines_source_sample_generation_mineral_and_work_group(self):
        original = pd.DataFrame({
            "_analysis_id": ["a1", "a2", "a3", "a4"],
            sources.SOURCE_LABEL_COLUMN: ["Paper A", "Paper A", "Paper B", "Paper A"],
            "Sample": ["PG-1", "PG-2", "PG-1", "PG-1"],
            "Generation": ["core", "core", "core", "rim"],
            "Минерал": ["apatite", "apatite", "apatite", "phlogopite"],
            WORK_GROUP_COLUMN: ["G1", "G1", "G1", "G2"],
        })
        snapshot = original.copy(deep=True)
        visible, hidden = apply_plot_visibility_filters(
            original,
            {
                "source": ["Paper A"],
                "sample": ["PG-1"],
                "generation": ["core"],
                "mineral": ["apatite"],
                "work_group": ["G1"],
            },
        )
        self.assertEqual(visible["_analysis_id"].tolist(), ["a1"])
        self.assertEqual(set(hidden["_analysis_id"]), {"a2", "a3", "a4"})
        pd.testing.assert_frame_equal(original, snapshot)

    def test_plot_visibility_prefers_interpreted_generation_and_prunes_stale_values(self):
        frame = pd.DataFrame({
            "_analysis_id": ["a1", "a2"],
            "Generation": ["source-1", "source-2"],
            "PetroLab Generation": ["core", "rim"],
            "Sample": ["PG-1", "PG-2"],
        })
        dimensions = {item.key: item for item in available_visibility_dimensions(frame)}
        self.assertEqual(dimensions["generation"].column, "PetroLab Generation")

        normalized = normalize_visibility_filters(
            frame,
            {"sample": ["OLD-SAMPLE"], "generation": ["core"]},
        )
        self.assertNotIn("sample", normalized)
        self.assertEqual(normalized["generation"], ["core"])

    def test_plot_visibility_keeps_explicit_empty_selection(self):
        frame = pd.DataFrame({"Sample": ["PG-1", "PG-2"]})
        visible, hidden = apply_plot_visibility_filters(frame, {"sample": []})
        self.assertTrue(visible.empty)
        self.assertEqual(len(hidden), 2)


if __name__ == "__main__":
    unittest.main()
