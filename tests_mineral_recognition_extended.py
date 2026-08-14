from __future__ import annotations

from petrolab.mineral_recognition_extended import EXTENDED_RULESET_VERSION, recognize_mineral_extended


cases = [
    ({"Nb2O5": 58.0, "TiO2": 8.0, "CaO": 14.0, "Na2O": 7.0, "F": 2.0, "SiO2": 1.0}, "pyrochlore-supergroup"),
    ({"TiO2": 46.0, "Na2O": 9.0, "CaO": 9.0, "La2O3": 6.0, "Ce2O3": 16.0, "SiO2": 1.0}, "REE-Na titanate (loparite-type)"),
    ({"SiO2": 37.0, "CaO": 41.0, "MgO": 13.0, "Al2O3": 7.0, "Na2O": 2.0}, "melilite-group"),
    ({"SiO2": 52.0, "CaO": 33.0, "Na2O": 9.0, "Al2O3": 1.0, "FeO": 0.5}, "pectolite-like Na-Ca pyroxenoid"),
    ({"SiO2": 51.5, "CaO": 47.0, "MgO": 0.3, "FeO": 0.2, "Al2O3": 0.4}, "wollastonite-type Ca silicate"),
]

for row, target in cases:
    result = recognize_mineral_extended(row)
    assert result.target == target, (target, result)
    assert result.confidence in {"high", "medium"}, result
    assert "alkaline-" in result.ruleset_version

# A common diopside composition must remain a clinopyroxene, not be stolen by melilite/wollastonite.
diopside = recognize_mineral_extended({"SiO2": 52.0, "CaO": 25.0, "MgO": 17.0, "FeO": 4.0, "Al2O3": 2.0})
assert diopside.target == "clinopyroxene", diopside

# Albite remains feldspar rather than zeolite-like framework.
albite = recognize_mineral_extended({"SiO2": 68.0, "Al2O3": 20.0, "Na2O": 11.5, "CaO": 0.3})
assert albite.target == "plagioclase", albite

print(f"extended mineral recognition: OK; ruleset={EXTENDED_RULESET_VERSION}")
