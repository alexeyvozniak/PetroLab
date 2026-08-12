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
    lines: tuple[OverlayLine, ...]
    labels: tuple[OverlayLabel, ...]
    source_doi: str = ""
    verification_citation: str = ""
    verification_doi: str = ""
    note_ru: str = ""

    @property
    def has_reference_identifier(self) -> bool:
        return bool(self.source_doi or self.verification_doi)


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


def _dominant_component_lines() -> tuple[OverlayLine, ...]:
    """Boundaries where two normalized ternary components are equal and dominate the third."""
    centre = TernaryVertex(100.0 / 3.0, 100.0 / 3.0, 100.0 / 3.0)
    return (
        OverlayLine((TernaryVertex(50.0, 50.0, 0.0), centre)),
        OverlayLine((TernaryVertex(50.0, 0.0, 50.0), centre)),
        OverlayLine((TernaryVertex(0.0, 50.0, 50.0), centre)),
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
        OverlayLabel("Pigeonite\ncompositional field", TernaryVertex(44.0, 44.0, 12.0)),
        OverlayLabel("Augite\ncompositional field", TernaryVertex(35.0, 35.0, 30.0)),
        OverlayLabel("Diopside", TernaryVertex(30.0, 23.0, 47.0)),
        OverlayLabel("Hedenbergite", TernaryVertex(23.0, 30.0, 47.0)),
    ),
    note_ru=(
        "Поля применимы к Ca–Mg–Fe (Quad) пироксенам после Q–J проверки. "
        "Morimoto et al. подчёркивают, что различение augite/pigeonite в пограничных "
        "составах прежде всего структурное; здесь показывается химическое поле, а не "
        "самостоятельное доказательство структуры. Низкокальциевые En/Fs поля также "
        "не задают структурный полиморф только по химии."
    ),
)


FELDSPAR_GUNDUZ_ASAN_2023 = TernaryOverlay(
    overlay_id="feldspar_gunduz_asan_2023",
    title_ru="Ab–An–Or · compositional classification (Gündüz & Asan, 2023)",
    source_citation=(
        "Gündüz M., Asan K. (2023). MagMin_PT: An Excel-based mineral classification and "
        "geothermobarometry program for magmatic rocks. Mineralogical Magazine 87, 1–9, Fig. 5; "
        "feldspar classification after Deer, Howie & Zussman (1992)."
    ),
    source_doi="10.1180/mgm.2022.113",
    verification_citation=(
        "Parsons I. (2010). Feldspars defined and described: a pair of posters published by the "
        "Mineralogical Society. Sources and supporting information. Mineralogical Magazine 74, 529–551."
    ),
    verification_doi="10.1180/minmag.2010.074.3.529",
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
        OverlayLabel("Alkali feldspar\n(structural species unresolved)", TernaryVertex(45.0, 5.0, 50.0)),
    ),
    note_ru=(
        "Нижняя полоса показывает традиционные compositional subdivisions плагиоклаза на "
        "Ab–An–Or диаграмме; выше неё при низком An показывается только общее поле alkali "
        "feldspar. Sanidine, orthoclase и microcline не назначаются из одной химии: для их "
        "различения требуется структурное состояние. Центральные ternary-составы не получают "
        "искусственного имени."
    ),
)


GARNET_PRP_ALM_GRS_DOMINANCE = TernaryOverlay(
    overlay_id="garnet_prp_alm_grs_dominance",
    title_ru="Prp–Alm–Grs · dominant component in projection",
    source_citation=(
        "Grew E.S., Locock A.J., Mills S.J., Galuskina I.O., Galuskin E.V., Hålenius U. (2013). "
        "Nomenclature of the garnet supergroup. American Mineralogist 98, 785–811."
    ),
    source_doi="10.2138/am.2013.4201",
    verification_citation=(
        "Yavuz F., Yildirim D.K. (2020). WinGrt, a Windows program for garnet supergroup minerals. "
        "Journal of Geosciences 65, 71–95; ternary end-member diagrams are used as compositional projections."
    ),
    verification_doi="10.3190/jgeosci.303",
    lines=_dominant_component_lines(),
    labels=(
        OverlayLabel("Prp-dominant\nprojection", TernaryVertex(68.0, 16.0, 16.0)),
        OverlayLabel("Alm-dominant\nprojection", TernaryVertex(16.0, 68.0, 16.0)),
        OverlayLabel("Grs-dominant\nprojection", TernaryVertex(16.0, 16.0, 68.0)),
    ),
    note_ru=(
        "Это не формальное IMA-имя вида граната. Линии A=B, A=C и B=C лишь показывают, какой "
        "из трёх выбранных и перенормированных end-member компонентов доминирует в данной "
        "проекции. Остальные компоненты и распределение катионов по позициям исключены."
    ),
)


GARNET_PRP_ALM_SPS_DOMINANCE = TernaryOverlay(
    overlay_id="garnet_prp_alm_sps_dominance",
    title_ru="Prp–Alm–Sps · dominant component in projection",
    source_citation=GARNET_PRP_ALM_GRS_DOMINANCE.source_citation,
    source_doi=GARNET_PRP_ALM_GRS_DOMINANCE.source_doi,
    verification_citation=GARNET_PRP_ALM_GRS_DOMINANCE.verification_citation,
    verification_doi=GARNET_PRP_ALM_GRS_DOMINANCE.verification_doi,
    lines=_dominant_component_lines(),
    labels=(
        OverlayLabel("Prp-dominant\nprojection", TernaryVertex(68.0, 16.0, 16.0)),
        OverlayLabel("Alm-dominant\nprojection", TernaryVertex(16.0, 68.0, 16.0)),
        OverlayLabel("Sps-dominant\nprojection", TernaryVertex(16.0, 16.0, 68.0)),
    ),
    note_ru=GARNET_PRP_ALM_GRS_DOMINANCE.note_ru,
)


TERNARY_OVERLAYS: dict[str, TernaryOverlay] = {
    overlay.overlay_id: overlay
    for overlay in (
        PYROXENE_MORIMOTO_1988,
        FELDSPAR_GUNDUZ_ASAN_2023,
        GARNET_PRP_ALM_GRS_DOMINANCE,
        GARNET_PRP_ALM_SPS_DOMINANCE,
    )
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
        return "Pigeonite compositional field"
    if wo < 45.0:
        return "Augite compositional field"
    if wo <= 50.0 + 1e-9:
        return "Diopside" if en >= fs else "Hedenbergite"
    return "unclassified"


def classify_feldspar_gunduz_asan(row: pd.Series) -> str:
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
        return "Alkali feldspar compositional field (structural species unresolved)"
    return "Intermediate ternary feldspar composition (no routine species field)"


def _classify_dominant_projection(row: pd.Series, labels: tuple[str, str, str]) -> str:
    values = np.asarray(
        [row.get(TERNARY_A, np.nan), row.get(TERNARY_B, np.nan), row.get(TERNARY_C, np.nan)],
        dtype=float,
    )
    if not np.all(np.isfinite(values)):
        return "unclassified"
    maximum = float(np.max(values))
    winners = [labels[index] for index, value in enumerate(values) if np.isclose(value, maximum, atol=1e-8)]
    if len(winners) > 1:
        return "–".join(winners) + " tie in selected projection"
    return winners[0] + "-dominant (selected projection)"


def classify_garnet_prp_alm_grs(row: pd.Series) -> str:
    return _classify_dominant_projection(row, ("Prp", "Alm", "Grs"))


def classify_garnet_prp_alm_sps(row: pd.Series) -> str:
    return _classify_dominant_projection(row, ("Prp", "Alm", "Sps"))


_CLASSIFIERS: dict[str, Callable[[pd.Series], str]] = {
    "pyroxene_morimoto_1988": classify_pyroxene_morimoto,
    "feldspar_gunduz_asan_2023": classify_feldspar_gunduz_asan,
    "garnet_prp_alm_grs_dominance": classify_garnet_prp_alm_grs,
    "garnet_prp_alm_sps_dominance": classify_garnet_prp_alm_sps,
}


def attach_ternary_classification(dataframe: pd.DataFrame, overlay_id: str | None) -> pd.DataFrame:
    result = dataframe.copy()
    classifier = _CLASSIFIERS.get(str(overlay_id or ""))
    if classifier is None or result.empty:
        result["Классификационное поле"] = ""
        return result
    result["Классификационное поле"] = result.apply(classifier, axis=1)
    return result
