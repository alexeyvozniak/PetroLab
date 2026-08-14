from __future__ import annotations

from petrolab.alkaline_mineral_recognition import ALKALINE_EXTENSION_VERSION, score_alkaline_candidates


def expect_target(row, target):
    result = score_alkaline_candidates(row)
    assert target in result, (target, result)
    return result[target]


assert ALKALINE_EXTENSION_VERSION == "2026.08.1"

expect_target(
    {"Nb2O5": 58.0, "TiO2": 8.0, "CaO": 14.0, "Na2O": 7.0, "F": 2.0, "SiO2": 1.0},
    "pyrochlore-supergroup",
)
expect_target(
    {"TiO2": 46.0, "Na2O": 9.0, "CaO": 9.0, "La2O3": 6.0, "Ce2O3": 16.0, "SiO2": 1.0},
    "REE-Na titanate (loparite-type)",
)
expect_target(
    {"SiO2": 37.0, "CaO": 41.0, "MgO": 13.0, "Al2O3": 7.0, "Na2O": 2.0},
    "melilite-group",
)
expect_target(
    {"SiO2": 52.0, "CaO": 33.0, "Na2O": 9.0, "Al2O3": 1.0, "FeO": 0.5},
    "pectolite-like Na-Ca pyroxenoid",
)
expect_target(
    {"SiO2": 51.5, "CaO": 47.0, "MgO": 0.3, "FeO": 0.2, "Al2O3": 0.4},
    "wollastonite-type Ca silicate",
)
expect_target(
    {"SiO2": 25.0, "CaO": 35.0, "Al2O3": 24.0, "FeO": 3.0},
    "Ca-Al garnet / hydrogarnet-like",
)
expect_target(
    {"SiO2": 47.0, "Al2O3": 27.0, "Na2O": 14.0, "CaO": 1.0, "FeO": 0.2},
    "Na-Ca zeolite-like framework",
)
expect_target(
    {"SiO2": 45.0, "ZrO2": 12.0, "Na2O": 15.0, "CaO": 8.0, "FeO": 4.0},
    "eudialyte-group-like Na-Ca-Zr silicate",
)

# Hard negatives: common phases must not be stolen by the specialist layer.
assert "pyrochlore-supergroup" not in score_alkaline_candidates(
    {"SiO2": 52.0, "CaO": 20.0, "MgO": 15.0, "FeO": 7.0, "Al2O3": 3.0}
)
assert "melilite-group" not in score_alkaline_candidates(
    {"SiO2": 51.0, "CaO": 22.0, "MgO": 16.0, "FeO": 6.0, "Al2O3": 4.0}
)
assert "Na-Ca zeolite-like framework" not in score_alkaline_candidates(
    {"SiO2": 47.0, "Al2O3": 14.0, "K2O": 10.0, "MgO": 20.0, "FeO": 5.0}
)

print("alkaline-carbonatite mineral recognition extension: OK")
