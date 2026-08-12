from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from petrolab.ternary_data import TERNARY_A, TERNARY_B, TERNARY_C


@dataclass(frozen=True)
class TernaryVertex:
    """One point in A-left / B-right / C-top percent coordinates."""

    a: float
    b: float
    c: float

    def __post_init__(self) -> None:
        values = (float(self.a), float(self.b), float(self.c))
        if any(value < -1e-9 for value in values):
            raise ValueError("Ternary overlay coordinates cannot be negative")
        if not np.isclose(sum(values), 100.0, atol=1e-7):
            raise ValueError("Ternary overlay coordinates must sum to 100")


@dataclass(frozen=True)
class OverlayLine:
    points: tuple[TernaryVertex, ...]
    width: float = 0.8
    style: str = "-"


@dataclass(frozen=True)
class OverlayLabel:
    text: str
    position: TernaryVertex


@dataclass(frozen=True)
class TernaryOverlay:
    overlay_id: str
    title_ru: str
    source_citation: str
    source_doi: str
    lines: tuple[OverlayLine, ...]
    labels: tuple[OverlayLabel, ...]
    note_ru: str = ""


def _constant_c(c: float) -> OverlayLine:
    remainder = 100.0 - float(c)
    return OverlayLine((TernaryVertex(remainder, 0.0, c), TernaryVertex(0.0, remainder, c)))


def _constant_b_between_c(b: float, c_low: float, c_high: float) -> OverlayLine:
    return OverlayLine(
        (
            TernaryVertex(100.0 - b - c_low, b, c_low),
            TernaryVertex(100.0 - b - c_high, b, c_high),
        )
    )


def _a_equals_b_between_c(c_low: float, c_high: float) -> OverlayLine:
    low_side = (100.0 - c_low) / 2.0
    high_side = (100.0 - c_high) / 2.0
    return OverlayLine(
        (
            TernaryVertex(low_side, low_side, c_low),
            TernaryVertex(high_side, high_side, c_high),
        )
    )


PYROXENE_MORIMOTO_1988 = TernaryOverlay(
    overlay_id="pyroxene_morimoto_1988",
    title_ru="IMA · Ca–Mg–Fe pyroxenes (Morimoto et al., 1988)",
    source_citation=(
        "Morimoto N., Fabries J., Ferguson A.K., Ginzburg I.V., Ross M., Seifert F.A., "
        "Zussman J., Aoki K., Gottardi G. (1988). Nomenclature of pyroxenes. "
        "Mineralogical Magazine 52, 535–550."
    ),
    source_doi="10.1180/minmag.1988.052.367.15",
    lines=(
        _constant_c(5.0),
        _constant_c(20.0),
        _constant_c(45.0),
        _constant_c(50.0),
        _a_equals_b_between_c(0.0, 5.0),
        _a_equals_b_between_c(45.0, 50.0),
    ),
    labels=(
        OverlayLabel("Enstatite-side\nlow-Ca field", TernaryVertex(72.0, 25.0, 3.0)),
        OverlayLabel("Ferrosilite-side\nlow-Ca field", TernaryVertex(25.0, 72.0, 3.0)),
        OverlayLabel("Pigeonite", TernaryVertex(44.0, 44.0, 12.0)),
        OverlayLabel("Augite", TernaryVertex(35.0, 35.0, 30.0)),
        OverlayLabel("Diopside", TernaryVertex(30.0, 23.0, 47.0)),
        OverlayLabel("Hedenbergite", TernaryVertex(23.0, 30.0, 47.0)),
    ),
    note_ru=(
        "Поля применимы к Ca–Mg–Fe (Quad) пироксенам после Q–J проверки. "
        "Низкокальциевые En/Fs поля не задают структурный полиморф только по химии."
    ),
)


FELDSPAR_DEER_1992 = TernaryOverlay(
    overlay_id="feldspar_deer_1992",
    title_ru="Ab–An–Or · схема по Deer et al. (1992)",
    source_citation=(
        "Deer W.A., Howie R.A., Zussman J. (1992). An Introduction to the Rock-Forming "
        "Minerals, 2nd ed.; implementation cross-checked against Gündüz & Asan (2023), "
        "Mineralogical Magazine 87, 1–9."
    ),
    source_doi="10.1180/mgm.2022.113",
    lines=(
        _constant_c(10.0),
        _constant_b_between_c(10.0, 0.0, 10.0),
        _constant_b_between_c(30.0, 0.0, 10.0),
        _constant_b_between_c(50.0, 0.0, 10.0),
        _constant_b_between_c(70.0, 0.0, 10.0),
        _constant_b_between_c(90.0, 0.0, 10.0),
    ),
    labels=(
        OverlayLabel("Albite", TernaryVertex(94.0, 3.0, 3.0)),
        OverlayLabel("Oligoclase", TernaryVertex(77.0, 20.0, 3.0)),
        OverlayLabel("Andesine", TernaryVertex(57.0, 40.0, 3.0)),
        OverlayLabel("Labradorite", TernaryVertex(37.0, 60.0, 3.0)),
        OverlayLabel("Bytownite", TernaryVertex(17.0, 80.0, 3.0)),
        OverlayLabel("Anorthite", TernaryVertex(3.0, 94.0, 3.0)),
        OverlayLabel("Alkali feldspar\n(structure-dependent)", TernaryVertex(45.0, 5.0, 50.0)),
    ),
    note_ru=(
        "Plagioclase subdivisions are shown in the low-Or band. Sanidine, orthoclase and "
        "microcline are not assigned from chemistry alone because structural state is required."
    ),
)


TERNARY_OVERLAYS: dict[str, TernaryOverlay] = {
    overlay.overlay_id: overlay
    for overlay in (PYROXENE_MORIMOTO_1988, FELDSPAR_DEER_1992)
}


def get_ternary_overlay(overlay_id: str | None) -> TernaryOverlay | None:
    if not overlay_id:
        return None
    return TERNARY_OVERLAYS.get(str(overlay_id))


def pyroxene_qj_group(row: pd.Series) -> str:
    """Return the Morimoto Q–J major chemical group for one calculated pyroxene row."""
    try:
        q = float(row.get("Q"))
        j = float(row.get("J"))
    except (TypeError, ValueError):
        return "Q–J недоступен"
    if not np.isfinite(q) or not np.isfinite(j):
        return "Q–J недоступен"
    total = q + j
    if total < 1.5 - 1e-9 or total > 2.0 + 1e-9 or total <= 0:
        return "Others"
    ratio = j / total
    if ratio < 0.2:
        return "Quad"
    if ratio <= 0.8:
        return "Ca–Na"
    return "Na"


def classify_pyroxene_morimoto(row: pd.Series) -> str:
    group = pyroxene_qj_group(row)
    if group != "Quad":
        return f"{group}: Wo–En–Fs field not assigned"

    en = float(row.get(TERNARY_A, np.nan))
    fs = float(row.get(TERNARY_B, np.nan))
    wo = float(row.get(TERNARY_C, np.nan))
    if not all(np.isfinite(value) for value in (en, fs, wo)):
        return "unclassified"
    if wo > 50.0 + 1e-9:
        return "outside Ca–Mg–Fe quadrilateral"
    if wo < 5.0:
        return "Enstatite-side low-Ca field" if en >= fs else "Ferrosilite-side low-Ca field"
    if wo < 20.0:
        return "Pigeonite"
    if wo < 45.0:
        return "Augite"
    if wo <= 50.0 + 1e-9:
        return "Diopside" if en >= fs else "Hedenbergite"
    return "unclassified"


def classify_feldspar_deer(row: pd.Series) -> str:
    ab = float(row.get(TERNARY_A, np.nan))
    an = float(row.get(TERNARY_B, np.nan))
    or_value = float(row.get(TERNARY_C, np.nan))
    if not all(np.isfinite(value) for value in (ab, an, or_value)):
        return "unclassified"

    if or_value <= 10.0 + 1e-9:
        if an < 10.0:
            return "Albite"
        if an < 30.0:
            return "Oligoclase"
        if an < 50.0:
            return "Andesine"
        if an < 70.0:
            return "Labradorite"
        if an < 90.0:
            return "Bytownite"
        return "Anorthite"
    if an <= 10.0 + 1e-9:
        return "Alkali feldspar (structural state required)"
    return "Intermediate Ab–An–Or composition"


_CLASSIFIERS: dict[str, Callable[[pd.Series], str]] = {
    "pyroxene_morimoto_1988": classify_pyroxene_morimoto,
    "feldspar_deer_1992": classify_feldspar_deer,
}


def attach_ternary_classification(dataframe: pd.DataFrame, overlay_id: str | None) -> pd.DataFrame:
    result = dataframe.copy()
    classifier = _CLASSIFIERS.get(str(overlay_id or ""))
    if classifier is None or result.empty:
        result["Классификационное поле"] = ""
        return result
    result["Классификационное поле"] = result.apply(classifier, axis=1)
    return result
