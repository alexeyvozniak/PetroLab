from __future__ import annotations

import pandas as pd


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Sample": ["A", "B"],
            "Grain": ["g1", "g2"],
            "SiO2": [40.0, 41.0],
            "TiO2": [3.0, 4.0],
            "MgO": [20.0, 19.0],
            "Rb [µg/g]": [150.0, 200.0],
            "Nb ppm": [15.0, 20.0],
            "La": [20.0, 22.0],
            "Si_apfu": [2.8, 2.9],
            "Al_IV": [1.1, 1.0],
            "Mg#": [0.71, 0.69],
            "QC уровень": ["ok", "warn"],
            "Total": [99.4, 98.9],
            "Comment": ["x", "y"],
            "_analysis_id": ["a1", "a2"],
        }
    )


def test_modes_are_scientific_and_legacy_modes_migrate() -> None:
    from petrolab.ui.field_presets import FIELD_MODES, normalize_field_mode

    assert FIELD_MODES == ("Основное", "Микрозонд", "Trace", "APFU", "QC", "Все", "Свои")
    assert normalize_field_mode("Химия") == "Микрозонд"
    assert normalize_field_mode("Расчёты") == "APFU"
    assert normalize_field_mode("nonsense") == "Основное"


def test_microprobe_and_trace_do_not_mix_units_semantically() -> None:
    from petrolab.ui.field_presets import microprobe_columns, trace_columns

    frame = _frame()
    microprobe = microprobe_columns(frame)
    trace = trace_columns(frame)
    assert {"SiO2", "TiO2", "MgO"}.issubset(microprobe)
    assert "Rb [µg/g]" not in microprobe
    assert "Nb ppm" not in microprobe
    assert {"Rb [µg/g]", "Nb ppm", "La"}.issubset(trace)
    assert "SiO2" not in trace


def test_apfu_and_qc_are_domain_specific() -> None:
    from petrolab.ui.field_presets import apfu_columns, qc_columns

    frame = _frame()
    apfu = apfu_columns(frame)
    qc = qc_columns(frame)
    assert {"Si_apfu", "Al_IV", "Mg#"}.issubset(apfu)
    assert "SiO2" not in apfu
    assert {"QC уровень", "Total"}.issubset(qc)
    assert "Comment" not in qc


def test_basic_view_keeps_identity_and_compact_chemistry() -> None:
    from petrolab.ui.field_presets import columns_for_mode

    frame = _frame()
    columns = columns_for_mode(frame, "Основное", identity_columns=("Sample", "Grain"))
    assert columns[:2] == ["Sample", "Grain"]
    assert "SiO2" in columns
    assert "_analysis_id" not in columns
    assert len(columns) < len(frame.columns)


def main() -> None:
    test_modes_are_scientific_and_legacy_modes_migrate()
    test_microprobe_and_trace_do_not_mix_units_semantically()
    test_apfu_and_qc_are_domain_specific()
    test_basic_view_keeps_identity_and_compact_chemistry()
    print("v0.15.8 scientific field presets: OK")


if __name__ == "__main__":
    main()
