from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

import pandas as pd

from petrolab.alkaline_mineral_recognition import ALKALINE_EXTENSION_VERSION, score_alkaline_candidates
from petrolab.alkaline_mineral_reference import ALKALINE_REFERENCE_VERSION
from petrolab.mineral_recognition import (
    MINERAL_RECOGNITION_CATALOG_HASH,
    MINERAL_RECOGNITION_RULESET_VERSION,
    MineralCandidate,
    MineralRecognition,
    recognize_mineral,
    score_candidates,
)
from petrolab.mineral_reference import MINERAL_REFERENCE_VERSION
from petrolab.oxide_mineral_recognition import OXIDE_EXTENSION_VERSION, score_oxide_candidates


EXTENDED_RULESET_VERSION = (
    f"{MINERAL_RECOGNITION_RULESET_VERSION}+alkaline-{ALKALINE_EXTENSION_VERSION}"
    f"+oxide-{OXIDE_EXTENSION_VERSION}"
)
EXTENDED_REFERENCE_VERSION = f"{MINERAL_REFERENCE_VERSION}+alkaline-{ALKALINE_REFERENCE_VERSION}"


def score_candidates_extended(row: Mapping[str, Any]) -> dict[str, MineralCandidate]:
    """Merge the general scorer with specialist alkaline and conservative oxide layers."""
    merged = dict(score_candidates(row))
    for target, candidate in score_alkaline_candidates(row).items():
        new = MineralCandidate(target=target, score=candidate.score, reasons=candidate.reasons)
        old = merged.get(target)
        if old is None or new.score > old.score:
            merged[target] = new
    for target, candidate in score_oxide_candidates(row).items():
        new = MineralCandidate(target=target, score=candidate.score, reasons=candidate.reasons)
        old = merged.get(target)
        if old is None or new.score > old.score:
            merged[target] = new
    return merged


def recognize_mineral_extended(row: Mapping[str, Any]) -> MineralRecognition:
    """Return a conservative recognition using all specialist rule layers.

    Confidence thresholds intentionally remain conservative. Specialist layers may add
    diagnostic candidates but cannot silently force a phase; ties remain ambiguous.
    """
    candidates = sorted(
        score_candidates_extended(row).values(),
        key=lambda item: (-item.score, item.target),
    )
    if not candidates:
        base = recognize_mineral(row)
        return replace(base, ruleset_version=EXTENDED_RULESET_VERSION)

    best = candidates[0]
    runner_up = candidates[1] if len(candidates) > 1 else None
    margin = best.score - (runner_up.score if runner_up is not None else 0.0)

    # Do not make the extension more permissive than Mineral Recognition v1.
    if best.score >= 9.0 and margin >= 2.0:
        confidence = "high"
    elif best.score >= 7.0 and margin >= 1.5:
        confidence = "medium"
    else:
        confidence = "ambiguous"

    target = best.target if confidence in {"high", "medium"} else ""
    reasons = best.reasons
    if confidence == "ambiguous" and runner_up is not None:
        reasons = reasons + (f"competing candidate: {runner_up.target}",)

    return MineralRecognition(
        target=target,
        confidence=confidence,
        reasons=reasons,
        candidates=tuple(candidates[:5]),
        ruleset_version=EXTENDED_RULESET_VERSION,
    )


def recognize_dataframe_extended(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Attach extended suggestions while preserving explicit provenance and human confirmation."""
    out = dataframe.copy()
    results = [recognize_mineral_extended(row) for row in out.to_dict(orient="records")]
    out["Suggested Mineral"] = [item.target for item in results]
    out["Mineral suggestion confidence"] = [item.confidence for item in results]
    out["Mineral suggestion reason"] = ["; ".join(item.reasons) for item in results]
    out["Mineral suggestion ruleset"] = EXTENDED_RULESET_VERSION
    out["Mineral reference version"] = EXTENDED_REFERENCE_VERSION
    out["Mineral reference hash"] = MINERAL_RECOGNITION_CATALOG_HASH
    out["Mineral alkaline reference version"] = ALKALINE_REFERENCE_VERSION
    out["Mineral candidate ranking"] = [
        "; ".join(f"{candidate.target}:{candidate.score:g}" for candidate in item.candidates)
        for item in results
    ]
    return out
