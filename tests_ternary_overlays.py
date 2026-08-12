from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd

from petrolab.interactive_plotting import selected_analysis_ids
from petrolab.plotting import figure_png_bytes, figure_svg_bytes
from petrolab.ternary_data import TERNARY_A, TERNARY_B, TERNARY_C, prepare_ternary
from petrolab.ternary_overlays import (
    FELDSPAR_GUNDUZ_ASAN_2023,
    GARNET_PRP_ALM_GRS_DOMINANCE,
    GARNET_PRP_ALM_SPS_DOMINANCE,
    PYROXENE_MORIMOTO_1988,
    TERNARY_OVERLAYS,
    attach_ternary_classification,
    classify_feldspar_gunduz_asan,
    classify_garnet_prp_alm_grs,
    classify_garnet_prp_alm_sps,
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


# Every overlay must be valid ternary geometry and carry an auditable literature reference.
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

assert set(TERNARY_OVERLAYS) == {
    "pyroxene_morimoto_1988",
    "feldspar_gunduz_asan_2023",
    "garnet_prp_alm_grs_dominance",
    "garnet_prp_alm_sps_dominance",
}
assert PYROXENE_MORIMOTO_1988.source_doi == "10.1180/minmag.1988.052.367.15"
assert FELDSPAR_GUNDUZ_ASAN_2023.source_doi == "10.1180/mgm.2022.113"
assert FELDSPAR_GUNDUZ_ASAN_2023.verification_doi == "10.1180/minmag.2010.074.3.529"
assert GARNET_PRP_ALM_GRS_DOMINANCE.source_doi == "10.2138/am.2013.4201"
assert GARNET_PRP_ALM_GRS_DOMINANCE.verification_doi == "10.3190/jgeosci.303"
assert GARNET_PRP_ALM_SPS_DOMINANCE.source_doi == "10.2138/am.2013.4201"

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

# Feldspar preset is now connected to the published Ab-An-Or compositional guide.
fsp_preset = TERNARY_PRESETS["feldspar_ab_an_or"]
assert fsp_preset.field_overlay_id == "feldspar_gunduz_asan_2023"
feldspar_ids = {preset.preset_id for preset in available_ternary_presets({"Ab", "An", "Or"})}
assert feldspar_ids == {"feldspar_ab_an_or"}

# The low-Or classification band uses the published conventional An subdivisions.
def fsp_row(ab: float, an: float, or_value: float) -> pd.Series:
    return pd.Series({TERNARY_A: ab, TERNARY_B: an, TERNARY_C: or_value})


assert classify_feldspar_gunduz_asan(fsp_row(93, 5, 2)) == "Albite"
assert classify_feldspar_gunduz_asan(fsp_row(78, 20, 2)) == "Oligoclase"
assert classify_feldspar_gunduz_asan(fsp_row(58, 40, 2)) == "Andesine"
assert classify_feldspar_gunduz_asan(fsp_row(38, 60, 2)) == "Labradorite"
assert classify_feldspar_gunduz_asan(fsp_row(18, 80, 2)) == "Bytownite"
assert classify_feldspar_gunduz_asan(fsp_row(3, 95, 2)) == "Anorthite"
assert "Alkali feldspar" in classify_feldspar_gunduz_asan(fsp_row(45, 5, 50))
assert "Intermediate ternary" in classify_feldspar_gunduz_asan(fsp_row(40, 30, 30))

# Geometry is explicit and regression-tested rather than reconstructed inside a renderer.
fsp_or10 = FELDSPAR_GUNDUZ_ASAN_2023.lines[0]
assert (fsp_or10.points[0].a, fsp_or10.points[0].b, fsp_or10.points[0].c) == (90.0, 0.0, 10.0)
assert (fsp_or10.points[1].a, fsp_or10.points[1].b, fsp_or10.points[1].c) == (0.0, 90.0, 10.0)
fsp_an10 = FELDSPAR_GUNDUZ_ASAN_2023.lines[1]
assert (fsp_an10.points[0].a, fsp_an10.points[0].b, fsp_an10.points[0].c) == (90.0, 10.0, 0.0)
assert (fsp_an10.points[1].a, fsp_an10.points[1].b, fsp_an10.points[1].c) == (80.0, 10.0, 10.0)

# Both garnet presets have projection guides, but the result is deliberately not an IMA species name.
garnet_columns = {"Prp", "Alm", "Grs", "Sps"}
available_ids = {preset.preset_id for preset in available_ternary_presets(garnet_columns)}
assert "garnet_prp_alm_grs" in available_ids
assert "garnet_prp_alm_sps" in available_ids
assert TERNARY_PRESETS["garnet_prp_alm_grs"].field_overlay_id == "garnet_prp_alm_grs_dominance"
assert TERNARY_PRESETS["garnet_prp_alm_sps"].field_overlay_id == "garnet_prp_alm_sps_dominance"
assert "не формальное IMA" in TERNARY_PRESETS["garnet_prp_alm_grs"].description_ru


def grt_row(a: float, b: float, c: float) -> pd.Series:
    return pd.Series({TERNARY_A: a, TERNARY_B: b, TERNARY_C: c})


assert classify_garnet_prp_alm_grs(grt_row(70, 20, 10)) == "Prp-dominant (selected projection)"
assert classify_garnet_prp_alm_grs(grt_row(20, 70, 10)) == "Alm-dominant (selected projection)"
assert classify_garnet_prp_alm_grs(grt_row(20, 10, 70)) == "Grs-dominant (selected projection)"
assert classify_garnet_prp_alm_sps(grt_row(20, 10, 70)) == "Sps-dominant (selected projection)"
assert classify_garnet_prp_alm_grs(grt_row(50, 50, 0)) == "Prp–Alm tie in selected projection"

# Dominance boundaries are pairwise equality lines meeting at the ternary centre.
for overlay in (GARNET_PRP_ALM_GRS_DOMINANCE, GARNET_PRP_ALM_SPS_DOMINANCE):
    assert len(overlay.lines) == 3
    for line in overlay.lines:
        end = line.points[-1]
        assert abs(end.a - 100.0 / 3.0) < 1e-10
        assert abs(end.b - 100.0 / 3.0) < 1e-10
        assert abs(end.c - 100.0 / 3.0) < 1e-10
    assert "не формальное IMA" in overlay.note_ru

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

# Overlay traces render in both engines; only marker traces carry immutable analysis IDs.
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

# Every newly supported preset overlay renders through the same mineral-blind plotting engine.
render_cases = [
    (
        pd.DataFrame({"_analysis_id": ["f1"], "Ab": [58.0], "An": [40.0], "Or": [2.0]}),
        ("Ab", "An", "Or"),
        FELDSPAR_GUNDUZ_ASAN_2023,
    ),
    (
        pd.DataFrame({"_analysis_id": ["g1"], "Prp": [70.0], "Alm": [20.0], "Grs": [10.0]}),
        ("Prp", "Alm", "Grs"),
        GARNET_PRP_ALM_GRS_DOMINANCE,
    ),
    (
        pd.DataFrame({"_analysis_id": ["g2"], "Prp": [20.0], "Alm": [10.0], "Sps": [70.0]}),
        ("Prp", "Alm", "Sps"),
        GARNET_PRP_ALM_SPS_DOMINANCE,
    ),
]
for raw, components, overlay in render_cases:
    prepared_case = prepare_ternary(raw, *components, normalization="already")
    classified_case = attach_ternary_classification(prepared_case.valid, overlay.overlay_id)
    assert classified_case["Классификационное поле"].iloc[0]
    interactive_case = build_interactive_ternary(
        classified_case,
        a_label=components[0],
        b_label=components[1],
        c_label=components[2],
        overlay=overlay,
    )
    assert len(interactive_case.data) > 1
    figure_case = build_publication_ternary(
        classified_case,
        a_label=components[0],
        b_label=components[1],
        c_label=components[2],
        overlay=overlay,
    )
    assert figure_png_bytes(figure_case, dpi=72).startswith(b"\x89PNG")
    plt.close(figure_case)

print("ternary overlay tests: OK")
