from __future__ import annotations

import math

import pandas as pd

from petrolab.interactive_plotting import selected_analysis_ids
from petrolab.plotting import figure_png_bytes, figure_svg_bytes
from petrolab.ternary_data import (
    TERNARY_A,
    TERNARY_B,
    TERNARY_C,
    TERNARY_REASON,
    TERNARY_X,
    TERNARY_Y,
    prepare_ternary,
    ternary_to_cartesian,
)
from petrolab.ternary_plotting import build_interactive_ternary, build_publication_ternary
from petrolab.ternary_presets import (
    MORIMOTO_QJ_APPLICABLE,
    TERNARY_PRESETS,
    apply_preset_projection,
    available_ternary_presets,
)


def near(actual: float, expected: float, tolerance: float = 1e-9) -> None:
    assert math.isfinite(float(actual))
    assert abs(float(actual) - float(expected)) <= tolerance, (actual, expected)


# Normalization and invalid-row reporting.
raw = pd.DataFrame(
    {
        "_analysis_id": ["a", "b", "c", "d", "e"],
        "Sample": ["A", "B", "C", "D", "E"],
        "Wo": [20.0, 0.2, None, -1.0, "bad"],
        "En": [50.0, 0.5, 50.0, 51.0, 50.0],
        "Fs": [30.0, 0.3, 50.0, 50.0, 50.0],
    }
)
prepared = prepare_ternary(raw, "Wo", "En", "Fs", normalization="normalize")
assert prepared.valid_rows == 2
assert prepared.invalid_rows == 3
assert set(prepared.invalid[TERNARY_REASON]) == {"missing_component", "negative_component", "non_numeric"}
for _, row in prepared.valid.iterrows():
    near(row[TERNARY_A] + row[TERNARY_B] + row[TERNARY_C], 100.0)

# Auto-detection of fractions and already-normalized percentages.
fraction = prepare_ternary(raw.iloc[[1]], "Wo", "En", "Fs", normalization="auto")
assert fraction.normalization_applied == "fraction_to_100"
near(fraction.valid.iloc[0][TERNARY_A], 20.0)
percent = prepare_ternary(raw.iloc[[0]], "Wo", "En", "Fs", normalization="auto")
assert percent.normalization_applied == "already"
near(percent.valid.iloc[0][TERNARY_B], 50.0)

# Cartesian geometry: A-left, B-right, C-top, equal mixture in the center.
x, y = ternary_to_cartesian([100, 0, 0, 1], [0, 100, 0, 1], [0, 0, 100, 1])
near(x[0], 0.0)
near(y[0], 0.0)
near(x[1], 1.0)
near(y[1], 0.0)
near(x[2], 0.5)
near(y[2], math.sqrt(3.0) / 2.0)
near(x[3], 0.5)
near(y[3], math.sqrt(3.0) / 6.0)

# Ready-to-use mineral presets are exposed only when their scientific source inputs exist.
preset_ids = {
    preset.preset_id
    for preset in available_ternary_presets({"apfu_Ca", "apfu_Mg", "apfu_Fe2", "Q", "J"})
}
assert preset_ids == {"pyroxene_wo_en_fs"}
preset_ids = {preset.preset_id for preset in available_ternary_presets({"Wo", "En", "Fs"})}
assert "pyroxene_wo_en_fs" not in preset_ids
preset_ids = {preset.preset_id for preset in available_ternary_presets({"Ab", "An", "Or"})}
assert preset_ids == {"feldspar_ab_an_or"}

# Morimoto Wo-En-Fs is a Quad-pyroxene projection, not a generic projection of every
# pyroxene. Q-J chemistry gates the rows before coordinates are exposed.
px_preset = TERNARY_PRESETS["pyroxene_wo_en_fs"]
px_rows = pd.DataFrame([
    # Quad: Q+J=2.0 and J/(Q+J)=0.05.
    {"apfu_Ca": 0.4, "apfu_Mg": 0.8, "apfu_Fe2": 0.7, "Q": 1.9, "J": 0.1},
    # Ca-Na / Na-rich side: same Q+J band but J fraction is too high for Quad.
    {"apfu_Ca": 0.3, "apfu_Mg": 0.5, "apfu_Fe2": 0.4, "Q": 1.2, "J": 0.8},
])
px_projected, px_components = apply_preset_projection(px_rows, px_preset)
assert px_components == ("Morimoto En", "Morimoto Fs", "Morimoto Wo")
assert bool(px_projected.loc[0, MORIMOTO_QJ_APPLICABLE])
assert not bool(px_projected.loc[1, MORIMOTO_QJ_APPLICABLE])
assert px_projected.loc[0, list(px_components)].notna().all()
assert px_projected.loc[1, list(px_components)].isna().all()
near(px_projected.loc[0, "Morimoto En"] + px_projected.loc[0, "Morimoto Fs"] + px_projected.loc[0, "Morimoto Wo"], 100.0)

# An entirely absent optional Mn/Fe3 column is an explicit reduced analytical panel and
# remains usable; a blank inside a supplied optional column is row-level unknown chemistry.
px_with_mn_hole = px_rows.iloc[[0]].copy()
px_with_mn_hole["apfu_Mn"] = None
px_hole_projected, _ = apply_preset_projection(px_with_mn_hole, px_preset)
assert not bool(px_hole_projected.loc[0, MORIMOTO_QJ_APPLICABLE])
assert px_hole_projected.loc[0, list(px_components)].isna().all()

# Plotly customdata must keep immutable analysis IDs as the first element.
plot_frame = prepared.valid.copy()
plot_frame["Generation"] = ["core", "rim"]
interactive = build_interactive_ternary(
    plot_frame,
    a_label="Wo",
    b_label="En",
    c_label="Fs",
    group_col="Generation",
)
assert len(interactive.data) == 2
ids_from_traces = []
for trace in interactive.data:
    assert trace.type == "scatterternary"
    for row in trace.customdata:
        ids_from_traces.append(str(row[0]))
assert set(ids_from_traces) == set(plot_frame["_analysis_id"].astype(str))

fake_event = {
    "selection": {
        "points": [
            {"customdata": [ids_from_traces[0]]},
            {"customdata": [ids_from_traces[-1]]},
        ]
    }
}
assert set(selected_analysis_ids(fake_event)) == {ids_from_traces[0], ids_from_traces[-1]}

# Publication rendering must generate real raster and vector outputs.
figure = build_publication_ternary(
    plot_frame,
    a_label="Wo",
    b_label="En",
    c_label="Fs",
    group_col="Generation",
    show_grid=True,
)
png = figure_png_bytes(figure, dpi=150)
svg = figure_svg_bytes(figure)
assert png.startswith(b"\x89PNG")
assert b"<svg" in svg[:500]

print("ternary tests: OK")
