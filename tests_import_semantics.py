from __future__ import annotations

import inspect

import pandas as pd

from petrolab.measurement_semantics import apply_measurement_overrides
from petrolab.io_utils import _adapt_wds_report_rows, add_qc_columns
from petrolab.services.import_service import _schema_preview, import_linked_sheets, import_uploaded_sheets


# Current UI passes per-sheet settings; backend must keep this contract.
for function in (import_linked_sheets, import_uploaded_sheets):
    parameters = inspect.signature(function).parameters
    assert "header_rows" in parameters
    assert "mineral_keys" in parameters

# FeO can be explicitly confirmed as total Fe reported on an FeO basis.
source_map = {
    "FeO": {"original": "FeO", "quantity_kind": "oxide"},
    "__schema__": {"semantic": {"Point": "Spot"}},
}
frame = pd.DataFrame({"FeO": [12.5], "MgO": [10.0]})
out, mapped, stored = apply_measurement_overrides(frame, source_map, {"FeO": "FeOt"})
assert "FeOt" in out.columns and "FeO" not in out.columns
assert stored == {"FeO": "FeOt"}
assert mapped["__schema__"]["semantic"] == {"Point": "Spot"}
assert mapped["__schema__"]["measurement"] == {"FeO": "FeOt"}
assert source_map["__schema__"] == {"semantic": {"Point": "Spot"}}, "nested source metadata was mutated"

# Bare Fe2O3 is scientifically ambiguous and must never silently become ferric or total Fe.
fe3 = pd.DataFrame({"Fe2O3": [8.0]})
try:
    apply_measurement_overrides(
        fe3,
        {"Fe2O3": {"original": "Fe2O3", "quantity_kind": "oxide"}, "__schema__": {}},
        {},
    )
except ValueError as exc:
    message = str(exc)
    assert "Fe2O3" in message and "явно" in message and "Fe2O3t" in message
else:
    raise AssertionError("Bare Fe2O3 was accepted without explicit semantics")

# Two physical columns normalised to the same scientific component must not be resolved by order.
duplicate = pd.DataFrame({"La [µg/g]": [100.0], "La [µg/g]__2": [101.0]})
try:
    apply_measurement_overrides(
        duplicate,
        {
            "La [µg/g]": {"original": "La ppm", "quantity_kind": "trace_element"},
            "La [µg/g]__2": {"original": "La ug/g", "quantity_kind": "trace_element"},
            "__schema__": {},
        },
        {},
    )
except ValueError as exc:
    assert "конфликтующие научные колонки" in str(exc).casefold()
else:
    raise AssertionError("Duplicate canonical chemistry was accepted")

report = _schema_preview(
    "Probe",
    pd.DataFrame({"SiO2": [40.0, None], "Ti [µg/g]": ["<DL", 12.0]}),
    {
        "SiO2": {"original": "SiO2", "quantity_kind": "oxide", "source_unit": "wt%", "canonical_unit": "wt%"},
        "Ti [µg/g]": {"original": "Ti [ppm]", "quantity_kind": "trace_element", "source_unit": "ppm", "canonical_unit": "µg/g"},
    },
)
assert report.row_count == 2
assert report.empty_cells == 1
assert report.detection_limit_cells == 1
assert report.recognized_oxides == (("SiO2", "SiO2", "wt%"),)
assert report.recognized_traces == (("Ti [ppm]", "Ti [µg/g]", "µg/g"),)

# Conventional WDS exports can repeat their header between analytical blocks.
# Only numeric analysis rows must survive, and the traditional Comment field
# should offer both sample and textual point identities without overwriting it.
wds, wds_map, wds_rows = _adapt_wds_report_rows(
    pd.DataFrame(
        {
            "No.": [1, "No.", 2],
            "SiO2": [40.0, "SiO2", 41.0],
            "FeO": [8.0, "FeO", 7.5],
            "MgO": [12.0, "MgO", 11.0],
            "Comment": ["19Tp-1 13", "Comment", "19Tp-14 Amph"],
        }
    ),
    {
        "No.": {"original": "No.", "quantity_kind": "unknown"},
        "SiO2": {"original": "SiO2", "quantity_kind": "oxide"},
        "FeO": {"original": "FeO", "quantity_kind": "oxide"},
        "MgO": {"original": "MgO", "quantity_kind": "oxide"},
        "Comment": {"original": "Comment", "quantity_kind": "unknown"},
    },
    [12, 13, 14],
)
assert wds_rows == [12, 14]
assert wds["Sample"].tolist() == ["19Tp-1", "19Tp-14"]
assert wds["Point"].tolist() == ["13", "Amph"]
assert wds["Comment"].tolist() == ["19Tp-1 13", "19Tp-14 Amph"]
assert wds_map["Comment"]["wds_protocol"] is True

# QC keeps imperfect analyses visible but marks the risk; it never drops the row.
quality = add_qc_columns(pd.DataFrame({"SiO2": [50.0, 80.0], "FeO": [5.0, 4.0]}))
assert quality["QC уровень"].tolist() == ["Исключить по умолчанию", "Требует проверки"]
assert quality["QC решение"].tolist() == ["Авто", "Авто"]

print("import semantics tests: OK")
