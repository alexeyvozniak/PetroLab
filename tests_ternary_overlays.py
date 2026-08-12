from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd

from petrolab.interactive_plotting import selected_analysis_ids
from petrolab.plotting import figure_png_bytes, figure_svg_bytes
from petrolab.ternary_data import TERNARY_A, TERNARY_B, TERNARY_C, prepare_ternary
from petrolab.ternary_overlays import (
    PYROXENE_MORIMOTO_1988,
    TERNARY_OVERLAYS,
    attach_ternary_classification,
    classify_pyroxene_morimoto,
    pyroxene_qj_group,
)
from petrolab.ternary_plotting import build_interactive_ternary, build_publication_ternary
from petrolab.ternary_presets import (
    MORIMOTO_EN,
    MORIMOTO_FS,
    MORIMOTO_WO,
    TERNARY_PRESETS,
    apply_preset_projection,
    available_ternary_presets,
)


# Overlay geometry is always valid ternary percent space and carries an auditable source.
for overlay in TERNARY_OVERLAYS.values():
    assert overlay.source_citation
    assert overlay.has_reference_identifier
    for line in overlay.lines:
        assert len(line.points) >= 2
        for point in line.points:
            assert abs(point.a + point.b + point.c - 100.0) < 1e-8
            assert min(point.a, point.b, point.c) >= 0
    for label in overlay.labels:
        point = label.position
        assert abs(point.a + point.b + point.c - 100.0) < 1e-8

assert set(TERNARY_OVERLAYS) == {"pyroxene_morimoto_1988"}
assert PYROXENE_MORIMOTO_1988.source_doi == "10.1180/minmag.1988.052.367.15"

# Pyroxene preset uses conventional En-left / Fs-right / Wo-top orientation and
# a Morimoto-specific source projection rather than the legacy Fe2-only Wo/En/Fs columns.
px_preset = TERNARY_PRESETS["pyroxene_wo_en_fs"]
assert (px_preset.a_label, px_preset.b_label, px_preset.c_label) == ("En", "Fs", "Wo")
assert (px_preset.a_col, px_preset.b_col, px_preset.c_col) == (MORIMOTO_EN, MORIMOTO_FS, MORIMOTO_WO)
assert px_preset.field_overlay_id == "pyroxene_morimoto_1988"
assert {"Q", "J"}.issubset(px_preset.source_requirements)

px_source = pd.DataFrame(
    {
        "_analysis_id": ["px1"],
        "apfu_Ca": [0.60],
        "apfu_Mg": [0.90],
        "apfu_Fe2": [0.35],
        "apfu_Fe3": [0.10],
        "apfu_Mn": [0.05],
        "Q": [1.85],
        "J": [0.10],
    }
)
projected, components = apply_preset_projection(px_source, px_preset)
assert components == (MORIMOTO_EN, MORIMOTO_FS, MORIMOTO_WO)
assert abs(float(projected.loc[0, MORIMOTO_EN]) - 45.0) < 1e-10
assert abs(float(projected.loc[0, MORIMOTO_FS]) - 25.0) < 1e-10
assert abs(float(projected.loc[0, MORIMOTO_WO]) - 30.0) < 1e-10
assert abs(float(projected.loc[0, "Morimoto ΣFe"]) - 0.50) < 1e-10

# Q-J grouping gates the Wo-En-Fs nomenclature.
assert pyroxene_qj_group(pd.Series({"Q": 1.80, "J": 0.10})) == "Quad"
assert pyroxene_qj_group(pd.Series({"Q": 1.20, "J": 0.50})) == "Ca–Na"
assert pyroxene_qj_group(pd.Series({"Q": 0.20, "J": 1.50})) == "Na"
assert pyroxene_qj_group(pd.Series({"Q": 1.20, "J": 0.10})) == "Others"


def px_row(en: float, fs: float, wo: float, q: float = 1.85, j: float = 0.05) -> pd.Series:
    return pd.Series({TERNARY_A: en, TERNARY_B: fs, TERNARY_C: wo, "Q": q, "J": j})


assert classify_pyroxene_morimoto(px_row(80, 18, 2)) == "Enstatite-side low-Ca field"
assert classify_pyroxene_morimoto(px_row(18, 80, 2)) == "Ferrosilite-side low-Ca field"
assert classify_pyroxene_morimoto(px_row(55, 35, 10)) == "Pigeonite compositional field"
assert classify_pyroxene_morimoto(px_row(40, 30, 30)) == "Augite compositional field"
assert classify_pyroxene_morimoto(px_row(30, 23, 47)) == "Diopside"
assert classify_pyroxene_morimoto(px_row(23, 30, 47)) == "Hedenbergite"
assert "Ca–Na" in classify_pyroxene_morimoto(px_row(40, 30, 30, q=1.2, j=0.5))
assert "outside" in classify_pyroxene_morimoto(px_row(20, 20, 60))

# Feldspar and garnet presets remain available without inventing unsourced overlay geometry.
fsp_preset = TERNARY_PRESETS["feldspar_ab_an_or"]
assert fsp_preset.field_overlay_id is None
assert "эвристическим" in fsp_preset.description_ru
feldspar_ids = {preset.preset_id for preset in available_ternary_presets({"Ab", "An", "Or"})}
assert feldspar_ids == {"feldspar_ab_an_or"}

garnet_columns = {"Prp", "Alm", "Grs", "Sps"}
available_ids = {preset.preset_id for preset in available_ternary_presets(garnet_columns)}
assert "garnet_prp_alm_grs" in available_ids
assert "garnet_prp_alm_sps" in available_ids
assert TERNARY_PRESETS["garnet_prp_alm_grs"].field_overlay_id is None
assert TERNARY_PRESETS["garnet_prp_alm_sps"].field_overlay_id is None

# Classification becomes a local view field and never changes the source columns.
source = pd.DataFrame(
    {
        "_analysis_id": ["a", "b"],
        "Q": [1.85, 1.20],
        "J": [0.05, 0.50],
        "En": [40.0, 40.0],
        "Fs": [30.0, 30.0],
        "Wo": [30.0, 30.0],
    }
)
prepared = prepare_ternary(source, "En", "Fs", "Wo", normalization="already")
classified = attach_ternary_classification(prepared.valid, "pyroxene_morimoto_1988")
assert classified.loc[classified["_analysis_id"] == "a", "Классификационное поле"].iloc[0] == "Augite compositional field"
assert "Ca–Na" in classified.loc[classified["_analysis_id"] == "b", "Классификационное поле"].iloc[0]
assert "Классификационное поле" not in source.columns

# Overlay traces render in both engines; only the marker trace carries analysis customdata.
interactive = build_interactive_ternary(
    classified,
    a_label="En",
    b_label="Fs",
    c_label="Wo",
    overlay=PYROXENE_MORIMOTO_1988,
)
assert len(interactive.data) > 1
marker_traces = [trace for trace in interactive.data if getattr(trace, "mode", "") == "markers"]
assert len(marker_traces) == 1
assert marker_traces[0].customdata[0][0] == "a"

fake_event = {"selection": {"points": [{"customdata": ["a", "A1"]}, {"customdata": None}]}}
assert selected_analysis_ids(fake_event) == ["a"]

publication = build_publication_ternary(
    classified,
    a_label="En",
    b_label="Fs",
    c_label="Wo",
    overlay=PYROXENE_MORIMOTO_1988,
)
png = figure_png_bytes(publication, dpi=120)
svg = figure_svg_bytes(publication)
plt.close(publication)
assert png.startswith(b"\x89PNG")
assert b"<svg" in svg[:1000]

print("ternary overlay tests: OK")
