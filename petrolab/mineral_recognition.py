from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from petrolab.mineral_reference import MINERAL_REFERENCE_VERSION, catalog_hash, references_by_target


MINERAL_RECOGNITION_RULESET_VERSION = "2026.08.2"
MINERAL_RECOGNITION_CATALOG_HASH = catalog_hash()


@dataclass(frozen=True)
class MineralCandidate:
    target: str
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class MineralRecognition:
    target: str
    confidence: str
    reasons: tuple[str, ...]
    candidates: tuple[MineralCandidate, ...]
    ruleset_version: str = MINERAL_RECOGNITION_RULESET_VERSION
    reference_version: str = MINERAL_REFERENCE_VERSION
    catalog_hash: str = MINERAL_RECOGNITION_CATALOG_HASH


def _value(row: Mapping[str, Any], *keys: str) -> float:
    for key in keys:
        try:
            value = float(row.get(key, np.nan))
        except (TypeError, ValueError):
            continue
        if np.isfinite(value):
            return value
    return float("nan")


def _sum(row: Mapping[str, Any], *keys: str) -> float:
    values = [_value(row, key) for key in keys]
    return float(sum(value for value in values if np.isfinite(value)))


def _between(value: float, low: float, high: float) -> bool:
    return np.isfinite(value) and low <= value <= high


def _gt(value: float, limit: float) -> bool:
    return np.isfinite(value) and value > limit


def _lt(value: float, limit: float) -> bool:
    return np.isfinite(value) and value < limit


def _fraction(*values: float) -> tuple[float, ...]:
    arr = np.asarray(values, dtype=float)
    arr[~np.isfinite(arr)] = 0.0
    total = float(arr.sum())
    if total <= 0:
        return tuple(0.0 for _ in arr)
    return tuple(float(value / total) for value in arr)


def score_candidates(row: Mapping[str, Any]) -> dict[str, MineralCandidate]:
    """Score conservative EPMA chemical targets.

    The output target is deliberately a chemical phase/family when routine EPMA chemistry
    cannot distinguish crystallographic polymorphs or volatile/Li-dependent species. The
    caller must treat the result as a suggestion, never as an IMA species determination.
    """
    sio2 = _value(row, "SiO2")
    tio2 = _value(row, "TiO2")
    al2o3 = _value(row, "Al2O3")
    cr2o3 = _value(row, "Cr2O3")
    feo = _value(row, "FeOt", "FeO")
    fe2o3 = _value(row, "Fe2O3t", "Fe2O3")
    mno = _value(row, "MnO")
    mgo = _value(row, "MgO")
    cao = _value(row, "CaO")
    sro = _value(row, "SrO")
    bao = _value(row, "BaO")
    na2o = _value(row, "Na2O")
    k2o = _value(row, "K2O")
    p2o5 = _value(row, "P2O5")
    zro2 = _value(row, "ZrO2")
    y2o3 = _value(row, "Y2O3")
    ce2o3 = _value(row, "Ce2O3", "CeO2")
    la2o3 = _value(row, "La2O3")
    so3 = _value(row, "SO3")
    f = _value(row, "F")
    cl = _value(row, "Cl")

    scores: dict[str, list[Any]] = defaultdict(lambda: [0.0, []])

    def add(target: str, points: float, reason: str) -> None:
        scores[target][0] += float(points)
        scores[target][1].append(reason)

    mafic = _sum(row, "MgO", "FeO", "FeOt", "MnO")
    alkalis = _sum(row, "Na2O", "K2O")
    trivalent = _sum(row, "Al2O3", "Cr2O3", "Fe2O3", "Fe2O3t")
    divalent = _sum(row, "CaO", "MgO", "FeO", "FeOt", "MnO")
    ree = _sum(row, "La2O3", "Ce2O3", "CeO2", "Nd2O3", "Pr2O3", "Sm2O3", "Gd2O3")

    # Highly diagnostic accessories / non-silicates first.
    if _gt(p2o5, 20) and _gt(cao, 20):
        add("apatite", 10, "high P2O5 + CaO")
    if _gt(p2o5, 20) and ree > 20:
        add("monazite", 10, "REE-rich phosphate")
    if _gt(p2o5, 20) and (_gt(y2o3, 15) or _sum(row, "Y2O3", "Yb2O3", "Dy2O3", "Er2O3") > 20):
        add("xenotime", 10, "Y-HREE-rich phosphate")
    if _gt(zro2, 45) and (not np.isfinite(sio2) or sio2 < 10):
        add("baddeleyite", 11, "ZrO2-dominant, Si-poor")
    if _gt(zro2, 45) and _between(sio2, 20, 40):
        add("zircon", 11, "ZrO2-rich silicate")
    if _gt(tio2, 45) and _gt(cao, 25) and (not np.isfinite(sio2) or sio2 < 10):
        add("perovskite", 11, "Ca-Ti oxide, Si-poor")
    if _between(tio2, 25, 45) and _between(cao, 20, 35) and _between(sio2, 20, 40):
        add("titanite", 10, "Ca-Ti silicate")
    if _gt(tio2, 80) and (not np.isfinite(sio2) or sio2 < 5):
        add("TiO2 phase", 11, "TiO2-dominant oxide")
    if _gt(so3, 25) and _gt(bao, 35):
        add("barite", 11, "Ba-S sulfate")
    if _gt(so3, 25) and _gt(sro, 25):
        add("celestine", 11, "Sr-S sulfate")
    if _gt(so3, 30) and _gt(cao, 25) and (not np.isfinite(sio2) or sio2 < 5):
        add("Ca-sulfate", 10, "Ca-S sulfate; hydration state unresolved by EPMA")
    if ree > 35 and _gt(f, 2) and (not np.isfinite(sio2) or sio2 < 10):
        add("REE-fluorocarbonate", 9, "REE-rich F-bearing non-silicate")

    # Carbonates. CO2 is commonly not measured; identify from cation dominance + silicate/phosphate exclusion.
    if (not np.isfinite(sio2) or sio2 < 8) and (not np.isfinite(p2o5) or p2o5 < 5) and (not np.isfinite(so3) or so3 < 8):
        ca_f, mg_f, fe_f, mn_f, sr_f = _fraction(cao, mgo, feo, mno, sro)
        if ca_f > 0.80 and divalent > 35:
            add("Ca-carbonate", 8, "Ca-dominant, Si/P/S-poor composition")
        if ca_f > 0.30 and mg_f > 0.25 and divalent > 35:
            add("Ca-Mg carbonate", 8, "Ca-Mg-dominant, Si/P/S-poor composition")
        if ca_f > 0.25 and fe_f > 0.20 and divalent > 35:
            add("Ca-Fe-Mg carbonate", 7.5, "Ca-Fe-Mg carbonate-like cation balance")
        if mg_f > 0.75 and divalent > 30:
            add("Mg-carbonate", 8, "Mg-dominant, Si/P/S-poor composition")
        if fe_f > 0.70 and divalent > 30:
            add("Fe-carbonate", 8, "Fe-dominant, Si/P/S-poor composition")
        if mn_f > 0.65 and divalent > 30:
            add("Mn-carbonate", 8, "Mn-dominant, Si/P/S-poor composition")
        if sr_f > 0.65 and divalent > 25:
            add("Sr-carbonate", 9, "Sr-dominant, Si/P/S-poor composition")

    # Oxides and spinels.
    if (not np.isfinite(sio2) or sio2 < 7) and _sum(row, "Al2O3", "Cr2O3", "FeO", "FeOt", "Fe2O3", "Fe2O3t", "MgO", "TiO2") > 70:
        if _gt(cr2o3, 20):
            add("Cr-spinel", 8, "Cr-rich spinel oxide")
        if _gt(tio2, 12) and _sum(row, "FeO", "FeOt", "Fe2O3", "Fe2O3t") > 25:
            add("Fe-Ti oxide", 8, "Fe-Ti oxide")
        if _sum(row, "FeO", "FeOt", "Fe2O3", "Fe2O3t") > 55 and (not np.isfinite(tio2) or tio2 < 12):
            add("Fe-oxide", 7.5, "Fe-dominant oxide")
        if _gt(al2o3, 20) and _sum(row, "MgO", "FeO", "FeOt") > 10:
            add("spinel-group oxide", 7, "Al-rich spinel-group oxide")

    # Silica / Al2SiO5.
    if _gt(sio2, 92) and _sum(row, "Al2O3", "MgO", "FeO", "FeOt", "CaO", "Na2O", "K2O") < 5:
        add("silica", 11, "SiO2-dominant phase")
    if _between(sio2, 34, 42) and _between(al2o3, 55, 66) and mafic < 5 and alkalis < 3 and (not np.isfinite(cao) or cao < 3):
        add("Al2SiO5 phase", 11, "Al2SiO5 stoichiometry; polymorph unresolved")

    # Feldspars and feldspathoids.
    if _between(sio2, 55, 72) and _between(al2o3, 16, 32) and mafic < 8:
        na_f, k_f, ca_f = _fraction(na2o, k2o, cao)
        if k_f > 0.65 and alkalis > 8:
            add("K-feldspar", 9, "K-dominant feldspar chemistry")
        if na_f + ca_f > 0.65 and (na2o if np.isfinite(na2o) else 0) + (cao if np.isfinite(cao) else 0) > 5:
            add("plagioclase", 9, "Na-Ca feldspar chemistry")
    if _between(sio2, 36, 48) and _between(al2o3, 25, 40) and alkalis > 12 and mafic < 7:
        na_f, k_f = _fraction(na2o, k2o)
        if na_f >= 0.55:
            add("nepheline", 9, "Na-dominant alkali feldspathoid chemistry")
        elif k_f > 0.70 and sio2 < 40:
            add("kalsilite", 9, "K-rich low-Si feldspathoid chemistry")
    if _between(sio2, 48, 58) and _between(al2o3, 20, 28) and _gt(k2o, 15) and mafic < 5:
        add("leucite", 9, "K-rich feldspathoid with leucite-like Si/Al")
    if _between(sio2, 30, 42) and _between(al2o3, 25, 38) and _gt(na2o, 15) and (_gt(cl, 0.5) or _gt(so3, 0.5)):
        add("sodalite-group", 8, "Na-rich feldspathoid with Cl/S")

    # Mafic silicates.
    if _between(sio2, 30, 45) and mafic > 35 and (not np.isfinite(cao) or cao < 8) and (not np.isfinite(al2o3) or al2o3 < 8):
        add("olivine", 9, "Mg-Fe-Mn rich, low-Al low-Ca orthosilicate")
    if _between(sio2, 32, 42) and _between(cao, 20, 40) and mafic > 15 and (not np.isfinite(al2o3) or al2o3 < 8):
        add("monticellite", 8, "Ca-rich olivine-related orthosilicate")
    if _between(sio2, 45, 58) and _between(cao, 10, 28) and mafic > 8 and (not np.isfinite(k2o) or k2o < 2):
        if _gt(na2o, 5) and _gt(al2o3, 8):
            add("Na-Ca clinopyroxene", 7.5, "Na-Ca-Al clinopyroxene chemistry")
        elif _gt(na2o, 7) and (_gt(fe2o3, 8) or (_gt(feo, 8) and _lt(mgo, 8))):
            add("Na-clinopyroxene", 8, "Na-Fe/Al clinopyroxene chemistry")
        else:
            add("clinopyroxene", 7, "Ca-Mg-Fe pyroxene chemistry")
    if _between(sio2, 48, 60) and mafic > 20 and (not np.isfinite(cao) or cao < 5) and (not np.isfinite(na2o) or na2o < 2.5):
        add("orthopyroxene", 8, "low-Ca Mg-Fe pyroxene chemistry")
    if _between(sio2, 45, 58) and _between(cao, 4, 10) and mafic > 18:
        add("low-Ca pyroxene", 6.5, "intermediate-Ca pyroxene chemistry")
    if _between(sio2, 36, 56) and _between(al2o3, 4, 22) and _between(cao, 5, 16) and _sum(row, "Na2O", "K2O") > 1.0 and mafic > 8:
        if _gt(tio2, 3):
            add("Ti-rich calcic amphibole", 7, "Ti-rich calcic amphibole-like chemistry")
        else:
            add("calcic amphibole", 6.5, "Ca-bearing hydrous mafic silicate chemistry")
    if _between(sio2, 45, 60) and _gt(na2o, 5) and (not np.isfinite(cao) or cao < 7) and mafic > 8:
        add("sodic amphibole", 6.5, "Na-rich low-Ca amphibole-like chemistry")
    if _between(sio2, 45, 58) and _gt(na2o, 3) and _between(cao, 4, 10) and mafic > 8:
        add("sodic-calcic amphibole", 6, "Na-Ca amphibole-like chemistry")

    # Micas.
    if _between(sio2, 30, 52) and _gt(k2o, 5) and _between(al2o3, 5, 35):
        if mafic > 10:
            add("trioctahedral mica", 9, "K-rich Mg-Fe mica chemistry")
        elif al2o3 > 20:
            add("dioctahedral mica", 8, "K-rich Al-dominant mica chemistry")

    # Garnet and epidote-group.
    if _between(sio2, 32, 45) and trivalent > 12 and divalent > 20 and alkalis < 4:
        if _gt(tio2, 5) and _gt(cao, 15):
            add("Ti-rich garnet", 7.5, "Ca-Ti-rich garnet chemistry")
        else:
            add("garnet", 8, "alkali-poor divalent + trivalent garnet balance")
    if _between(sio2, 34, 42) and _between(cao, 15, 28) and _between(al2o3, 18, 35) and trivalent > 20 and mafic < 20:
        if ree > 5:
            add("REE-epidote", 7.5, "REE-bearing epidote-group chemistry")
        else:
            add("epidote-group", 7, "Ca-Al-Fe epidote-group chemistry")

    # Common metamorphic accessories.
    if _between(sio2, 42, 52) and _between(al2o3, 28, 38) and _between(mgo, 5, 18) and mafic < 25 and alkalis < 5:
        add("cordierite", 7, "Mg-Al silicate with cordierite-like chemistry")
    if _between(sio2, 25, 35) and _gt(al2o3, 45) and _sum(row, "FeO", "FeOt", "MgO") > 8:
        add("staurolite", 6.5, "Al-rich Fe-Mg silicate")
    if _between(sio2, 28, 42) and _between(al2o3, 20, 38) and _sum(row, "FeO", "FeOt", "MgO", "CaO", "Na2O") > 8 and _value(row, "B2O3") > 3:
        add("tourmaline-group", 8, "B-bearing complex silicate")

    out: dict[str, MineralCandidate] = {}
    for target, (score, reasons) in scores.items():
        if score > 0:
            out[target] = MineralCandidate(target=target, score=float(score), reasons=tuple(reasons))
    return out


def recognize_mineral(row: Mapping[str, Any]) -> MineralRecognition:
    scores = score_candidates(row)
    if not scores:
        return MineralRecognition("", "unresolved", ("no diagnostic chemical target matched",), ())
    ranked = tuple(sorted(scores.values(), key=lambda item: (-item.score, item.target)))
    best = ranked[0]
    second_score = ranked[1].score if len(ranked) > 1 else 0.0
    margin = best.score - second_score
    if best.score >= 9 and margin >= 2:
        confidence = "high"
        target = best.target
    elif best.score >= 7 and margin >= 1.5:
        confidence = "medium"
        target = best.target
    else:
        confidence = "ambiguous"
        target = ""
    reasons = best.reasons
    if confidence == "ambiguous" and len(ranked) > 1:
        reasons = reasons + (f"competing candidate: {ranked[1].target}",)
    return MineralRecognition(target, confidence, reasons, ranked[:5])


def recognize_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    out = dataframe.copy()
    results = [recognize_mineral(row) for row in out.to_dict(orient="records")]
    out["Suggested Mineral"] = [item.target for item in results]
    out["Mineral suggestion confidence"] = [item.confidence for item in results]
    out["Mineral suggestion reason"] = ["; ".join(item.reasons) for item in results]
    out["Mineral suggestion ruleset"] = MINERAL_RECOGNITION_RULESET_VERSION
    out["Mineral reference version"] = MINERAL_REFERENCE_VERSION
    out["Mineral reference hash"] = MINERAL_RECOGNITION_CATALOG_HASH
    out["Mineral candidate ranking"] = [
        "; ".join(f"{candidate.target}:{candidate.score:g}" for candidate in item.candidates)
        for item in results
    ]
    return out


def chemically_resolvable_targets() -> tuple[str, ...]:
    return tuple(sorted(references_by_target()))
