from __future__ import annotations

import pandas as pd

from petrolab.mineral_recognition_extended import EXTENDED_RULESET_VERSION
from petrolab.phase_suggestions import (
    PHASE_SUGGESTION_RULESET_VERSION,
    attach_phase_suggestions,
    suggest_phase,
)


source = pd.DataFrame(
    [
        {
            "_analysis_id": "px-1",
            "SiO2": 1.0,
            "Nb2O5": 58.0,
            "TiO2": 8.0,
            "CaO": 14.0,
            "Na2O": 7.0,
            "F": 2.0,
        },
        {
            "_analysis_id": "cpx-1",
            "SiO2": 52.0,
            "CaO": 25.0,
            "MgO": 17.0,
            "FeO": 4.0,
            "Al2O3": 2.0,
        },
    ]
)
original_columns = tuple(source.columns)

review = attach_phase_suggestions(source)
assert tuple(source.columns) == original_columns, "review must not mutate the source dataframe"
assert PHASE_SUGGESTION_RULESET_VERSION == EXTENDED_RULESET_VERSION
assert review.loc[0, "Suggested Mineral"] == "pyrochlore-supergroup", review.loc[0].to_dict()
assert review.loc[0, "Mineral suggestion confidence"] in {"high", "medium"}
assert review.loc[1, "Suggested Mineral"] == "clinopyroxene", review.loc[1].to_dict()
assert review["Mineral suggestion ruleset"].eq(EXTENDED_RULESET_VERSION).all()
assert "Mineral alkaline reference version" in review.columns

# Suggestions are annotations only: they must not create or overwrite a confirmed mineral field.
assert "mineral_key" not in review.columns
assert "Confirmed Mineral" not in review.columns

legacy_target, legacy_confidence, _ = suggest_phase(source.iloc[0].to_dict())
assert legacy_target == "pyrochlore-supergroup"
assert legacy_confidence in {"high", "medium"}

print("alkaline mixed-mineral review integration: OK")
