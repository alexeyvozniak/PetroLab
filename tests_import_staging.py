from __future__ import annotations

import unittest

import pandas as pd

from petrolab.import_staging import (
    apply_block_fill,
    assign_value_to_rows,
    detect_block_header_rows,
    detect_role_columns,
    name_similarity,
    normalized_name_key,
    similar_name_candidates,
    source_like_column,
    split_by_column,
)


class ImportStagingTests(unittest.TestCase):
    def test_russian_english_case_and_transliteration_are_similarity_candidates(self):
        self.assertEqual(normalized_name_key("Kandalaksha"), normalized_name_key("Кандалакша"))
        self.assertEqual(name_similarity("Kandalaksha", "kandalaksha"), 1.0)
        candidates = similar_name_candidates(
            ["kandalaksha", "Кандалакша", "Por'ya Guba"],
            ["Kandalaksha", "Porya Guba"],
        )
        pairs = {(item.incoming, item.existing) for item in candidates}
        self.assertIn(("kandalaksha", "Kandalaksha"), pairs)
        self.assertIn(("Кандалакша", "Kandalaksha"), pairs)
        self.assertIn(("Por'ya Guba", "Porya Guba"), pairs)

    def test_neighbouring_sample_ids_are_not_duplicate_candidates(self):
        candidates = similar_name_candidates(["19KL24"], ["19KL23"])
        self.assertEqual(candidates, [])

    def test_role_detection_handles_russian_english_and_passport_headers(self):
        roles = detect_role_columns([
            "SAMPLE ID", "Rock Type", "REFERENCE", "Метод анализа",
            "Лаборатория", "Возраст, млн лет", "широта", "Longitude",
        ])
        self.assertEqual(roles["Sample"], "SAMPLE ID")
        self.assertEqual(roles["Lithology"], "Rock Type")
        self.assertEqual(roles["Source"], "REFERENCE")
        self.assertEqual(roles["Method"], "Метод анализа")
        self.assertEqual(roles["Laboratory"], "Лаборатория")
        self.assertEqual(roles["Age"], "Возраст, млн лет")
        self.assertEqual(roles["Latitude"], "широта")
        self.assertEqual(roles["Longitude"], "Longitude")

        russian = detect_role_columns(["образец", "ПОРОДА", "Источник"])
        self.assertEqual(russian["Sample"], "образец")
        self.assertEqual(russian["Lithology"], "ПОРОДА")
        self.assertEqual(russian["Source"], "Источник")

    def test_source_column_and_split_for_compilation_table(self):
        frame = pd.DataFrame({
            "Sample": ["A", "B", "C"],
            "SiO2": [40.0, 41.0, 42.0],
            "Reference": ["Smith 2014", "Smith 2014", "Jones 2018"],
        })
        self.assertEqual(source_like_column(frame), "Reference")
        groups = split_by_column(frame, "Reference")
        self.assertEqual(set(groups), {"Smith 2014", "Jones 2018"})
        self.assertEqual(len(groups["Smith 2014"]), 2)

    def test_block_header_detection_and_fill_is_non_destructive_until_confirmed(self):
        frame = pd.DataFrame({
            "Label": ["19KL23", "p1", "p2", "19KL24", "p3"],
            "SiO2": [None, 40.0, 41.0, None, 42.0],
            "MgO": [None, 8.0, 7.5, None, 9.0],
        })
        headers = detect_block_header_rows(frame, chemistry_columns=["SiO2", "MgO"])
        self.assertEqual(headers, [(0, "19KL23"), (3, "19KL24")])
        staged = apply_block_fill(frame, dict(headers), field="Sample")
        self.assertEqual(staged["Sample"].tolist(), ["19KL23", "19KL23", "19KL24"])
        self.assertEqual(staged["SiO2"].tolist(), [40.0, 41.0, 42.0])

    def test_mass_assignment_can_create_arbitrary_metadata_field(self):
        frame = pd.DataFrame({"Sample": ["A", "B", "C"], "SiO2": [1, 2, 3]})
        staged = assign_value_to_rows(frame, [0, 2], field="Occurrence", value="Kandalaksha")
        self.assertEqual(staged["Occurrence"].tolist()[0], "Kandalaksha")
        self.assertTrue(pd.isna(staged["Occurrence"].tolist()[1]))
        self.assertEqual(staged["Occurrence"].tolist()[2], "Kandalaksha")


if __name__ == "__main__":
    unittest.main()
