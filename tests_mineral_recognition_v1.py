from __future__ import annotations

import pandas as pd

from petrolab.mineral_recognition import (
    MINERAL_RECOGNITION_CATALOG_HASH,
    MINERAL_RECOGNITION_RULESET_VERSION,
    recognize_dataframe,
    recognize_mineral,
)
from petrolab.mineral_reference import MINERALS, MINERAL_REFERENCE_VERSION, catalog_hash, references_by_target
from petrolab.mineral_validation import UNKNOWN_LABEL, evaluate_labeled_corpus


def main() -> None:
    assert len(MINERALS) >= 80, f"Expected >=80 reference minerals, got {len(MINERALS)}"
    assert MINERAL_RECOGNITION_CATALOG_HASH == catalog_hash()
    assert MINERAL_REFERENCE_VERSION
    assert MINERAL_RECOGNITION_RULESET_VERSION

    by_name = {item.name: item for item in MINERALS}
    assert by_name["orthoclase"].chemical_target == by_name["sanidine"].chemical_target == by_name["microcline"].chemical_target == "K-feldspar"
    assert by_name["rutile"].chemical_target == by_name["anatase"].chemical_target == by_name["brookite"].chemical_target == "TiO2 phase"
    assert by_name["sillimanite"].chemical_target == by_name["kyanite"].chemical_target == by_name["andalusite"].chemical_target == "Al2SiO5 phase"
    assert len(references_by_target()) < len(MINERALS), "Chemical targets must collapse non-resolvable species"

    examples = pd.DataFrame([
        {"truth_target": "apatite", "SiO2": 0.2, "P2O5": 41.5, "CaO": 54.5, "F": 3.2},
        {"truth_target": "zircon", "SiO2": 32.8, "ZrO2": 66.0, "HfO2": 1.0},
        {"truth_target": "perovskite", "SiO2": 0.1, "TiO2": 58.5, "CaO": 41.0},
        {"truth_target": "titanite", "SiO2": 30.0, "TiO2": 39.0, "CaO": 28.0, "Al2O3": 1.0, "FeO": 1.0},
        {"truth_target": "silica", "SiO2": 99.7, "Al2O3": 0.1},
        {"truth_target": "Al2SiO5 phase", "SiO2": 36.8, "Al2O3": 62.2, "FeO": 0.4},
        {"truth_target": "K-feldspar", "SiO2": 64.8, "Al2O3": 18.4, "K2O": 15.5, "Na2O": 0.8},
        {"truth_target": "plagioclase", "SiO2": 55.0, "Al2O3": 28.0, "CaO": 10.0, "Na2O": 5.5, "K2O": 0.3},
        {"truth_target": "nepheline", "SiO2": 43.0, "Al2O3": 33.5, "Na2O": 16.5, "K2O": 5.5, "FeO": 0.5},
        {"truth_target": "olivine", "SiO2": 40.5, "MgO": 49.0, "FeO": 10.0, "CaO": 0.2, "Al2O3": 0.1},
        {"truth_target": "orthopyroxene", "SiO2": 55.0, "MgO": 32.0, "FeO": 10.0, "CaO": 1.2, "Al2O3": 1.0},
        {"truth_target": "clinopyroxene", "SiO2": 52.0, "MgO": 16.0, "FeO": 7.0, "CaO": 22.0, "Al2O3": 2.0, "Na2O": 0.5},
        {"truth_target": "trioctahedral mica", "SiO2": 40.0, "Al2O3": 13.0, "MgO": 24.0, "FeO": 7.0, "K2O": 10.0, "TiO2": 3.0},
        {"truth_target": "garnet", "SiO2": 40.0, "Al2O3": 21.0, "MgO": 20.0, "FeO": 9.0, "CaO": 8.0},
        {"truth_target": "Ca-carbonate", "SiO2": 0.1, "CaO": 55.0, "MgO": 0.5, "FeO": 0.2, "P2O5": 0.1},
        {"truth_target": "Ca-Mg carbonate", "SiO2": 0.1, "CaO": 31.0, "MgO": 21.0, "FeO": 2.0, "P2O5": 0.1},
        {"truth_target": "Fe-Ti oxide", "SiO2": 0.1, "TiO2": 50.0, "FeO": 46.0, "MgO": 2.0, "MnO": 1.0},
        {"truth_target": "Cr-spinel", "SiO2": 0.1, "Cr2O3": 45.0, "Al2O3": 20.0, "FeO": 20.0, "MgO": 14.0},
    ])
    predictions = recognize_dataframe(examples.drop(columns=["truth_target"]))
    assert set(["Suggested Mineral", "Mineral suggestion confidence", "Mineral suggestion ruleset", "Mineral reference hash"]).issubset(predictions.columns)
    assert predictions["Mineral suggestion ruleset"].eq(MINERAL_RECOGNITION_RULESET_VERSION).all()
    assert predictions["Mineral reference hash"].eq(MINERAL_RECOGNITION_CATALOG_HASH).all()

    for index, row in examples.iterrows():
        result = recognize_mineral(row)
        assert result.target == row["truth_target"], f"{row['truth_target']} -> {result.target or UNKNOWN_LABEL}; {result.candidates}"
        assert result.confidence in {"high", "medium"}

    report = evaluate_labeled_corpus(examples)
    assert report.n_rows == len(examples)
    assert report.high_confidence_wrong_rate == 0.0
    assert report.coverage == 1.0
    assert report.weighted_f1 == 1.0

    ambiguous = recognize_mineral({"SiO2": 50.0, "CaO": 12.0, "MgO": 14.0, "FeO": 8.0, "Al2O3": 10.0, "Na2O": 2.0})
    assert ambiguous.confidence in {"ambiguous", "unresolved"}, "Overlapping cpx/amphibole chemistry must not be forced"
    assert ambiguous.target == ""

    print(f"mineral recognition v1 tests: OK; catalog={len(MINERALS)} minerals, targets={len(references_by_target())}")


if __name__ == "__main__":
    main()
