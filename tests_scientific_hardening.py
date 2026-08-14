from __future__ import annotations

import math

import numpy as np
import pandas as pd

from petrolab.extended_plotting import CI_CHONDRITE_1995, PRIMITIVE_MANTLE_1989
from petrolab.minerals.formulae import calculate_formula
from petrolab.phase_suggestions import (
    PHASE_SUGGESTION_RULESET_VERSION,
    SUGGESTION_RULESET_COLUMN,
    attach_phase_suggestions,
    suggest_phase,
)
from petrolab.scientific_contracts import ThermobarometerMethod, validate_thermobarometer_registry
from petrolab.statistics import clr_transform, logratio_variation_matrix, prepare_matrix
from petrolab.tas import prepare_tas_dataframe, tas_major_total


MW = {
    "SiO2": 60.083,
    "MgO": 40.304,
    "CaO": 56.077,
    "Al2O3": 101.961,
    "Na2O": 61.979,
    "K2O": 94.195,
}


def _wt_from_oxide_moles(oxide_moles: dict[str, float]) -> dict[str, float]:
    masses = {oxide: moles * MW[oxide] for oxide, moles in oxide_moles.items()}
    total = sum(masses.values())
    return {oxide: 100.0 * mass / total for oxide, mass in masses.items()}


def _close(value: float, expected: float, tol: float = 2e-3) -> None:
    assert math.isfinite(float(value)), (value, expected)
    assert abs(float(value) - float(expected)) <= tol, (value, expected)


def test_formula_benchmarks() -> None:
    forsterite = pd.DataFrame([_wt_from_oxide_moles({"SiO2": 1.0, "MgO": 2.0})])
    ol = calculate_formula(forsterite, "olivine", "ol_4o_fe2").data.iloc[0]
    _close(ol["apfu_Si"], 1.0); _close(ol["apfu_Mg"], 2.0); _close(ol["Fo"], 100.0)

    diopside = pd.DataFrame([_wt_from_oxide_moles({"SiO2": 2.0, "MgO": 1.0, "CaO": 1.0})])
    cpx = calculate_formula(diopside, "clinopyroxene", "px_6o_fe2").data.iloc[0]
    _close(cpx["apfu_Si"], 2.0); _close(cpx["apfu_Mg"], 1.0); _close(cpx["apfu_Ca"], 1.0)
    _close(cpx["Wo"], 50.0); _close(cpx["En"], 50.0)

    pyrope = pd.DataFrame([_wt_from_oxide_moles({"SiO2": 3.0, "MgO": 3.0, "Al2O3": 1.0})])
    grt = calculate_formula(pyrope, "garnet", "grt_12o_fe2").data.iloc[0]
    _close(grt["apfu_Si"], 3.0); _close(grt["apfu_Mg"], 3.0); _close(grt["apfu_Al"], 2.0); _close(grt["Prp"], 100.0)

    albite = pd.DataFrame([_wt_from_oxide_moles({"SiO2": 3.0, "Al2O3": 0.5, "Na2O": 0.5})])
    fsp = calculate_formula(albite, "feldspar", "fsp_8o").data.iloc[0]
    _close(fsp["apfu_Si"], 3.0); _close(fsp["apfu_Al"], 1.0); _close(fsp["apfu_Na"], 1.0); _close(fsp["Ab"], 100.0)

    phlogopite = pd.DataFrame([_wt_from_oxide_moles({"SiO2": 3.0, "MgO": 3.0, "Al2O3": 0.5, "K2O": 0.5})])
    mica = calculate_formula(phlogopite, "mica", "mica_rieder_11o").data.iloc[0]
    _close(mica["apfu_Si"], 3.0); _close(mica["apfu_Al"], 1.0); _close(mica["apfu_Mg"], 3.0); _close(mica["apfu_K"], 1.0)


def test_coda_contracts() -> None:
    data = pd.DataFrame(
        {
            "SiO2": [1.0, 10.0, 2.0],
            "MgO": [2.0, 20.0, 4.0],
            "CaO": [4.0, 40.0, 8.0],
        }
    )
    columns = ["SiO2", "MgO", "CaO"]
    clr, excluded = clr_transform(data, columns)
    assert excluded == 0
    assert np.allclose(clr.iloc[0].to_numpy(), clr.iloc[1].to_numpy(), atol=1e-12)
    assert np.allclose(clr.iloc[0].to_numpy(), clr.iloc[2].to_numpy(), atol=1e-12)
    assert np.allclose(clr.sum(axis=1).to_numpy(), 0.0, atol=1e-12)

    variation = logratio_variation_matrix(data, columns)
    assert np.nanmax(np.abs(variation.to_numpy(dtype=float))) < 1e-20

    with_zero = pd.concat([data, pd.DataFrame([{"SiO2": 0.0, "MgO": 2.0, "CaO": 4.0}])], ignore_index=True)
    prepared = prepare_matrix(with_zero, columns, transform="clr", scaler="none")
    assert prepared.excluded_rows == 1 and prepared.transform_name == "clr" and len(prepared.index) == 3

    trace = pd.DataFrame({"La [µg/g]": [10.0, 20.0], "Ce [µg/g]": [20.0, 40.0]})
    trace_clr, _ = clr_transform(trace, ["La [µg/g]", "Ce [µg/g]"])
    assert np.allclose(trace_clr.iloc[0], trace_clr.iloc[1])

    mixed = pd.DataFrame({"SiO2": [50.0, 51.0], "La [µg/g]": [10.0, 11.0]})
    try:
        clr_transform(mixed, ["SiO2", "La [µg/g]"])
    except ValueError as exc:
        assert "Нельзя смешивать" in str(exc)
    else:
        raise AssertionError("CLR must reject mixed wt.% and µg/g domains")

    derived = pd.DataFrame({"SiO2": [50.0, 51.0], "Mg#": [0.7, 0.8]})
    try:
        clr_transform(derived, ["SiO2", "Mg#"])
    except ValueError:
        pass
    else:
        raise AssertionError("CLR must reject derived ratios mixed with compositional components")


def test_tas_volatile_free_normalization_and_iron_semantics() -> None:
    frame = pd.DataFrame([
        {
            "Rock": "TAS-test", "SiO2": 45.0, "TiO2": 1.0, "Al2O3": 15.0,
            "FeOt": 10.0, "FeO": 7.0, "Fe2O3": 3.0, "MnO": 0.2,
            "MgO": 8.0, "CaO": 10.0, "Na2O": 3.0, "K2O": 2.0,
            "P2O5": 0.8, "LOI": 10.0,
        }
    ])
    expected_total = 45.0 + 1.0 + 15.0 + 10.0 + 0.2 + 8.0 + 10.0 + 3.0 + 2.0 + 0.8
    _close(tas_major_total(frame).iloc[0], expected_total, 1e-9)
    prepared = prepare_tas_dataframe(frame, normalize_volatile_free=True).iloc[0]
    factor = 100.0 / expected_total
    _close(prepared["TAS_SiO2"], 45.0 * factor, 1e-9)
    _close(prepared["TAS_Total_alkalis"], 5.0 * factor, 1e-9)
    _close(prepared["TAS_original_major_total"], expected_total, 1e-9)
    assert prepared["TAS_major_suite_complete"] and prepared["TAS_normalized_volatile_free"]
    assert prepared["TAS_normalization_QC"] == "OK"

    incomplete = pd.DataFrame([{"SiO2": 50.0, "Na2O": 4.0, "K2O": 3.0}])
    blocked = prepare_tas_dataframe(incomplete, normalize_volatile_free=True).iloc[0]
    assert not blocked["TAS_major_suite_complete"]
    assert pd.isna(blocked["TAS_SiO2"])
    assert "missing:" in blocked["TAS_normalization_QC"]


def test_reference_normalization_constants_are_locked() -> None:
    expected_ci = {
        "La": 0.237, "Ce": 0.613, "Pr": 0.0928, "Nd": 0.457, "Sm": 0.148,
        "Eu": 0.0563, "Gd": 0.199, "Tb": 0.0361, "Dy": 0.246, "Ho": 0.0546,
        "Er": 0.160, "Tm": 0.0247, "Yb": 0.161, "Lu": 0.0246,
    }
    expected_pm = {
        "Rb": 0.635, "Ba": 6.989, "Th": 0.085, "U": 0.021, "Nb": 0.713,
        "Ta": 0.041, "K": 250.0, "La": 0.687, "Ce": 1.775, "Pb": 0.185,
        "Pr": 0.276, "Sr": 21.1, "P": 95.0, "Nd": 1.354, "Zr": 11.2,
        "Hf": 0.309, "Sm": 0.444, "Eu": 0.168, "Ti": 1300.0, "Gd": 0.596,
        "Tb": 0.108, "Dy": 0.737, "Y": 4.55, "Ho": 0.164, "Er": 0.480,
        "Tm": 0.074, "Yb": 0.493, "Lu": 0.074,
    }
    assert CI_CHONDRITE_1995 == expected_ci
    assert PRIMITIVE_MANTLE_1989 == expected_pm


def test_phase_suggestion_ruleset_is_versioned_and_conservative() -> None:
    assert PHASE_SUGGESTION_RULESET_VERSION.count(".") >= 2
    canonical_cases = [
        ({"P2O5": 42.0, "CaO": 55.0, "SiO2": 0.0}, "apatite"),
        ({"ZrO2": 66.0, "SiO2": 33.0}, "zircon"),
        ({"TiO2": 58.0, "CaO": 41.0, "SiO2": 0.0}, "perovskite"),
        ({"SiO2": 41.0, "MgO": 49.0, "FeO": 10.0, "CaO": 0.0, "Al2O3": 0.0}, "olivine"),
        ({"SiO2": 40.0, "Al2O3": 13.0, "K2O": 10.0, "MgO": 22.0, "FeO": 10.0}, "mica"),
    ]
    for row, expected in canonical_cases:
        mineral, confidence, reason = suggest_phase(row)
        assert mineral == expected, (row, mineral, confidence, reason)
        assert confidence in {"high", "medium"}
    attached = attach_phase_suggestions(pd.DataFrame([canonical_cases[0][0]]))
    assert attached[SUGGESTION_RULESET_COLUMN].iloc[0] == PHASE_SUGGESTION_RULESET_VERSION


def test_future_thermobarometry_requires_full_scientific_contract() -> None:
    valid = ThermobarometerMethod(
        method_id="example_v1", title="Example calibration", equation_version="Eq. 1, published form",
        source_citation="Author et al. (2026), Journal", source_doi="10.1234/example.2026.1",
        required_components=("SiO2", "MgO"), calibration_range="900–1200 °C; stated calibration composition range",
        uncertainty="±30 °C, 1σ as reported by calibration", equilibrium_test="Explicit mineral-pair equilibrium criterion",
        assumptions="No extrapolation outside calibration range.",
    )
    validate_thermobarometer_registry((valid,))
    incomplete = ThermobarometerMethod(
        method_id="bad", title="Bad", equation_version="Eq. 1", source_citation="Some paper", source_doi="",
        required_components=("SiO2",), calibration_range="", uncertainty="", equilibrium_test="",
    )
    try:
        incomplete.validate()
    except ValueError:
        pass
    else:
        raise AssertionError("Incomplete thermobarometer contract must be rejected")


if __name__ == "__main__":
    test_formula_benchmarks()
    test_coda_contracts()
    test_tas_volatile_free_normalization_and_iron_semantics()
    test_reference_normalization_constants_are_locked()
    test_phase_suggestion_ruleset_is_versioned_and_conservative()
    test_future_thermobarometry_requires_full_scientific_contract()
    print("scientific hardening benchmarks: OK")
