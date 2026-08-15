from __future__ import annotations

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


def test_russian_english_case_and_transliteration_are_similarity_candidates():
    assert normalized_name_key("Kandalaksha") == normalized_name_key("Кандалакша")
    assert name_similarity("Kandalaksha", "kandalaksha") == 1.0
    candidates = similar_name_candidates(
        ["kandalaksha", "Кандалакша", "Por'ya Guba"],
        ["Kandalaksha", "Porya Guba"],
    )
    pairs = {(item.incoming, item.existing) for item in candidates}
    assert ("kandalaksha", "Kandalaksha") in pairs
    assert ("Кандалакша", "Kandalaksha") in pairs
    assert ("Por'ya Guba", "Porya Guba") in pairs


def test_role_detection_handles_russian_and_english_headers():
    roles = detect_role_columns(["SAMPLE ID", "Rock Type", "REFERENCE", "Метод анализа"])
    assert roles["Sample"] == "SAMPLE ID"
    assert roles["Lithology"] == "Rock Type"
    assert roles["Source"] == "REFERENCE"
    assert roles["Method"] == "Метод анализа"

    russian = detect_role_columns(["образец", "ПОРОДА", "Источник"])
    assert russian["Sample"] == "образец"
    assert russian["Lithology"] == "ПОРОДА"
    assert russian["Source"] == "Источник"


def test_source_column_and_split_for_compilation_table():
    frame = pd.DataFrame({
        "Sample": ["A", "B", "C"],
        "SiO2": [40.0, 41.0, 42.0],
        "Reference": ["Smith 2014", "Smith 2014", "Jones 2018"],
    })
    assert source_like_column(frame) == "Reference"
    groups = split_by_column(frame, "Reference")
    assert set(groups) == {"Smith 2014", "Jones 2018"}
    assert len(groups["Smith 2014"]) == 2


def test_block_header_detection_and_fill_is_non_destructive_until_confirmed():
    frame = pd.DataFrame({
        "Label": ["19KL23", "p1", "p2", "19KL24", "p3"],
        "SiO2": [None, 40.0, 41.0, None, 42.0],
        "MgO": [None, 8.0, 7.5, None, 9.0],
    })
    headers = detect_block_header_rows(frame, chemistry_columns=["SiO2", "MgO"])
    assert headers == [(0, "19KL23"), (3, "19KL24")]
    staged = apply_block_fill(frame, dict(headers), field="Sample")
    assert staged["Sample"].tolist() == ["19KL23", "19KL23", "19KL24"]
    assert staged["SiO2"].tolist() == [40.0, 41.0, 42.0]


def test_mass_assignment_can_create_arbitrary_metadata_field():
    frame = pd.DataFrame({"Sample": ["A", "B", "C"], "SiO2": [1, 2, 3]})
    staged = assign_value_to_rows(frame, [0, 2], field="Occurrence", value="Kandalaksha")
    assert staged["Occurrence"].tolist()[0] == "Kandalaksha"
    assert pd.isna(staged["Occurrence"].tolist()[1])
    assert staged["Occurrence"].tolist()[2] == "Kandalaksha"
