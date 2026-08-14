from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import math


ALKALINE_EXTENSION_VERSION = "2026.08.1"


@dataclass(frozen=True)
class AlkalineCandidate:
    target: str
    score: float
    reasons: tuple[str, ...]


def _value(row: Mapping[str, Any], *keys: str) -> float:
    for key in keys:
        try:
            value = float(row.get(key, float("nan")))
        except (TypeError, ValueError):
            continue
        if math.isfinite(value):
            return value
    return float("nan")


def _sum(row: Mapping[str, Any], *keys: str) -> float:
    return sum(v for v in (_value(row, key) for key in keys) if math.isfinite(v))


def _finite_lt(value: float, limit: float) -> bool:
    return (not math.isfinite(value)) or value < limit


def score_alkaline_candidates(row: Mapping[str, Any]) -> dict[str, AlkalineCandidate]:
    """Conservative alkaline/carbonatite EPMA recognition layer.

    These rules intentionally return chemical targets, not IMA species, where routine
    EPMA cannot resolve site occupancy, H2O/OH, oxidation state, structural polymorphs,
    or light elements. They are designed as additive suggestions for the main PetroLab
    recognizer and therefore use strong gates to avoid stealing common rock-forming phases.
    """

    sio2 = _value(row, "SiO2")
    tio2 = _value(row, "TiO2")
    al2o3 = _value(row, "Al2O3")
    feo = _value(row, "FeOt", "FeO")
    mgo = _value(row, "MgO")
    cao = _value(row, "CaO")
    na2o = _value(row, "Na2O")
    k2o = _value(row, "K2O")
    mno = _value(row, "MnO")
    p2o5 = _value(row, "P2O5")
    nbo = _value(row, "Nb2O5", "Nb2O5 [wt.%]")
    ta2o5 = _value(row, "Ta2O5", "Ta2O5 [wt.%]")
    zro2 = _value(row, "ZrO2")
    sro = _value(row, "SrO")
    bao = _value(row, "BaO")
    f = _value(row, "F")
    cl = _value(row, "Cl")
    ree = _sum(row, "La2O3", "Ce2O3", "CeO2", "Pr2O3", "Nd2O3", "Sm2O3", "Gd2O3", "Y2O3")

    out: dict[str, AlkalineCandidate] = {}

    def add(target: str, score: float, *reasons: str) -> None:
        previous = out.get(target)
        candidate = AlkalineCandidate(target, float(score), tuple(reasons))
        if previous is None or candidate.score > previous.score:
            out[target] = candidate

    # Pyrochlore supergroup: a high-Nb/Ta, low-Si oxide. Exact species/subgroup
    # nomenclature additionally requires A/B/Y-site chemistry and anion information.
    nbta = sum(v for v in (nbo, ta2o5) if math.isfinite(v))
    if nbta >= 35 and _finite_lt(sio2, 8) and _finite_lt(p2o5, 8):
        reasons = ["Nb2O5+Ta2O5-dominant, Si-poor oxide"]
        if math.isfinite(cao) and cao >= 5:
            reasons.append("Ca-bearing A-site chemistry")
        if math.isfinite(na2o) and na2o >= 2:
            reasons.append("Na-bearing A-site chemistry")
        if math.isfinite(f) and f >= 1:
            reasons.append("measured F supports pyrochlore-supergroup chemistry")
        add("pyrochlore-supergroup", 12.0, *reasons)

    # Loparite/perovskite-related REE-Na titanate. We deliberately avoid a species
    # call because loparite-(Ce), perovskite and related members form broad solid solutions.
    if math.isfinite(tio2) and tio2 >= 35 and ree >= 8 and math.isfinite(na2o) and na2o >= 4 and _finite_lt(sio2, 8):
        add(
            "REE-Na titanate (loparite-type)",
            11.5,
            "TiO2-rich, REE-bearing, Na-bearing, Si-poor oxide",
        )

    # Melilite group (akermanite-gehlentie solid solutions and related members).
    # Routine chemistry can recognise the group well, while exact end-member naming
    # should follow a structural formula calculation rather than these gates.
    if (
        math.isfinite(sio2)
        and 20 <= sio2 <= 45
        and math.isfinite(cao)
        and 30 <= cao <= 50
        and _sum(row, "MgO", "Al2O3") >= 8
        and _finite_lt(na2o, 8)
        and _finite_lt(k2o, 5)
    ):
        add("melilite-group", 9.0, "Ca-rich Mg-Al silicate in melilite compositional range")

    # Pectolite / Na-Ca pyroxenoid chemistry. H cannot be measured by routine EPMA,
    # therefore the target is explicitly chemical unless OH/H2O is independently known.
    if (
        math.isfinite(sio2)
        and 48 <= sio2 <= 58
        and math.isfinite(cao)
        and 28 <= cao <= 38
        and math.isfinite(na2o)
        and 5 <= na2o <= 12
        and _sum(row, "MgO", "FeO", "FeOt", "Al2O3") < 8
    ):
        add("pectolite-like Na-Ca pyroxenoid", 10.0, "Si-Ca-Na pyroxenoid chemistry; H not resolved by EPMA")

    # Wollastonite and related CaSiO3 chemistry. The rule is intentionally narrow so
    # calcic pyroxenes with substantial Mg/Fe/Al are not captured.
    if (
        math.isfinite(sio2)
        and 48 <= sio2 <= 56
        and math.isfinite(cao)
        and 42 <= cao <= 50
        and _sum(row, "MgO", "FeO", "FeOt", "Al2O3", "Na2O", "K2O") < 6
    ):
        add("wollastonite-type Ca silicate", 10.0, "near-CaSiO3 chemistry")

    # Hydrogarnet chemistry: Ca-Al-rich garnet-like compositions can be recognised,
    # but hydrogarnet substitution itself requires H/OH information not measured by EPMA.
    if (
        math.isfinite(cao)
        and 30 <= cao <= 40
        and math.isfinite(al2o3)
        and 18 <= al2o3 <= 30
        and math.isfinite(sio2)
        and 15 <= sio2 <= 35
        and _sum(row, "MgO", "FeO", "FeOt", "MnO") < 10
    ):
        add("Ca-Al garnet / hydrogarnet-like", 8.5, "Ca-Al garnet-like chemistry; OH substitution unresolved")

    # Natrolite/mesolite/scolecite and many related zeolites cannot be separated reliably
    # by anhydrous EPMA totals alone. Report a hydrous framework chemical family.
    if (
        math.isfinite(sio2)
        and 40 <= sio2 <= 55
        and math.isfinite(al2o3)
        and 20 <= al2o3 <= 32
        and _sum(row, "Na2O", "CaO") >= 8
        and _finite_lt(k2o, 8)
        and _sum(row, "MgO", "FeO", "FeOt", "TiO2") < 5
    ):
        add("Na-Ca zeolite-like framework", 7.5, "Na-Ca-Al-Si hydrous-framework chemistry; H2O not measured")

    # Sr/Ba-rich Ca carbonates are common in evolved carbonatite systems; the broad target
    # is preferable to species names when CO2 is not directly analysed.
    if _finite_lt(sio2, 5) and _finite_lt(p2o5, 5) and _sum(row, "CaO", "SrO", "BaO") >= 35:
        if math.isfinite(sro) and sro >= 10 and math.isfinite(cao) and cao >= 10:
            add("Sr-rich Ca carbonate", 8.5, "Sr-Ca-rich, Si/P-poor carbonate-like chemistry")
        if math.isfinite(bao) and bao >= 10 and math.isfinite(cao) and cao >= 10:
            add("Ba-rich Ca carbonate", 8.5, "Ba-Ca-rich, Si/P-poor carbonate-like chemistry")

    # Eudialyte-group-like Na-Ca-Zr silicate. Exact group-member classification is
    # structurally and compositionally complex, so this target stays broad.
    if (
        math.isfinite(zro2)
        and zro2 >= 8
        and math.isfinite(sio2)
        and 35 <= sio2 <= 55
        and math.isfinite(na2o)
        and na2o >= 8
        and math.isfinite(cao)
        and cao >= 5
    ):
        add("eudialyte-group-like Na-Ca-Zr silicate", 9.0, "Na-Ca-Zr-rich silicate chemistry")

    # Lamprophyllite/astrophyllite-like Ti-bearing alkaline silicates are kept at a broad
    # family level because Fe/Mn/K/Na/Ba end-member relations require formula-based work.
    if (
        math.isfinite(tio2)
        and 8 <= tio2 <= 25
        and math.isfinite(sio2)
        and 25 <= sio2 <= 45
        and _sum(row, "Na2O", "K2O") >= 5
        and _sum(row, "FeO", "FeOt", "MnO", "MgO") >= 8
        and _finite_lt(cao, 15)
    ):
        add("alkaline Ti-silicate (astrophyllite/lamprophyllite-like)", 7.5, "alkali-Ti-Fe/Mn silicate chemistry")

    return out
