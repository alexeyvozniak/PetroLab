from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

# Стандартные атомные массы, достаточные для рутинного пересчёта EPMA.
AW = {
    "Si": 28.085, "Ti": 47.867, "Al": 26.9815385, "Cr": 51.9961,
    "Fe": 55.845, "Mn": 54.938044, "Mg": 24.305, "Ca": 40.078,
    "Na": 22.98976928, "K": 39.0983, "P": 30.973761998, "Ni": 58.6934,
    "Ba": 137.327, "Sr": 87.62, "Zn": 65.38, "V": 50.9415,
    "Zr": 91.224, "Hf": 178.49, "Nb": 92.90637, "Ta": 180.94788,
    "La": 138.90547, "Ce": 140.116, "Nd": 144.242, "Y": 88.90584,
    "Th": 232.0377, "U": 238.02891, "S": 32.06, "O": 15.999,
    "F": 18.998403163, "Cl": 35.45, "H": 1.008,
}


@dataclass(frozen=True)
class OxideSpec:
    cation: str
    n_cation: int
    n_oxygen: int
    molar_mass: float
    valence: int


def _mw(cation: str, ncat: int, no: int) -> float:
    return AW[cation] * ncat + AW["O"] * no


OXIDES: dict[str, OxideSpec] = {
    "SiO2": OxideSpec("Si", 1, 2, _mw("Si", 1, 2), 4),
    "TiO2": OxideSpec("Ti", 1, 2, _mw("Ti", 1, 2), 4),
    "Al2O3": OxideSpec("Al", 2, 3, _mw("Al", 2, 3), 3),
    "Cr2O3": OxideSpec("Cr", 2, 3, _mw("Cr", 2, 3), 3),
    "Fe2O3": OxideSpec("Fe3", 2, 3, _mw("Fe", 2, 3), 3),
    "FeO": OxideSpec("Fe2", 1, 1, _mw("Fe", 1, 1), 2),
    "MnO": OxideSpec("Mn", 1, 1, _mw("Mn", 1, 1), 2),
    "MgO": OxideSpec("Mg", 1, 1, _mw("Mg", 1, 1), 2),
    "CaO": OxideSpec("Ca", 1, 1, _mw("Ca", 1, 1), 2),
    "Na2O": OxideSpec("Na", 2, 1, _mw("Na", 2, 1), 1),
    "K2O": OxideSpec("K", 2, 1, _mw("K", 2, 1), 1),
    "P2O5": OxideSpec("P", 2, 5, _mw("P", 2, 5), 5),
    "NiO": OxideSpec("Ni", 1, 1, _mw("Ni", 1, 1), 2),
    "BaO": OxideSpec("Ba", 1, 1, _mw("Ba", 1, 1), 2),
    "SrO": OxideSpec("Sr", 1, 1, _mw("Sr", 1, 1), 2),
    "ZnO": OxideSpec("Zn", 1, 1, _mw("Zn", 1, 1), 2),
    "V2O3": OxideSpec("V3", 2, 3, _mw("V", 2, 3), 3),
    "V2O5": OxideSpec("V5", 2, 5, _mw("V", 2, 5), 5),
    "ZrO2": OxideSpec("Zr", 1, 2, _mw("Zr", 1, 2), 4),
    "HfO2": OxideSpec("Hf", 1, 2, _mw("Hf", 1, 2), 4),
    "Nb2O5": OxideSpec("Nb", 2, 5, _mw("Nb", 2, 5), 5),
    "Ta2O5": OxideSpec("Ta", 2, 5, _mw("Ta", 2, 5), 5),
    "La2O3": OxideSpec("La", 2, 3, _mw("La", 2, 3), 3),
    "Ce2O3": OxideSpec("Ce", 2, 3, _mw("Ce", 2, 3), 3),
    "Nd2O3": OxideSpec("Nd", 2, 3, _mw("Nd", 2, 3), 3),
    "Y2O3": OxideSpec("Y", 2, 3, _mw("Y", 2, 3), 3),
    "ThO2": OxideSpec("Th", 1, 2, _mw("Th", 1, 2), 4),
    "UO2": OxideSpec("U", 1, 2, _mw("U", 1, 2), 4),
    "SO3": OxideSpec("S6", 1, 3, _mw("S", 1, 3), 6),
}

HALOGENS = {"F": AW["F"], "Cl": AW["Cl"]}


@dataclass(frozen=True)
class FormulaMethod:
    id: str
    title_ru: str
    normalization_ru: str
    assumptions_ru: str
    references: tuple[str, ...]
    recent_examples: tuple[str, ...] = ()
    warning_ru: str = ""


@dataclass(frozen=True)
class CalculationResult:
    data: pd.DataFrame
    note_ru: str = ""


def _num(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(0.0, index=df.index, dtype=float)
    return pd.to_numeric(df[col], errors="coerce").fillna(0.0)


def oxygen_normalized_apfu(
    df: pd.DataFrame,
    oxygen_basis: float,
    allowed_oxides: tuple[str, ...] | None = None,
) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Возвращает катионы apfu, фактор нормировки и сумму катионов.

    Галогены не участвуют в кислородной нормировке. FeO и Fe2O3 сохраняются
    раздельно как Fe2 и Fe3, если оба измерены.
    """
    allowed = set(allowed_oxides) if allowed_oxides else set(OXIDES)

    # A duplicated scientific input such as FeO + FeO__2 is ambiguous. The import
    # layer deliberately keeps both columns instead of merging them, and the formula
    # engine must not silently choose the first one.
    formula_inputs = set(allowed) | set(HALOGENS)
    if "FeO" in allowed:
        formula_inputs.add("FeOt")
    duplicate_inputs: list[str] = []
    for column in df.columns:
        name = str(column)
        if "__" not in name:
            continue
        base, suffix = name.rsplit("__", 1)
        if suffix.isdigit() and base in formula_inputs:
            duplicate_inputs.append(name)
    if duplicate_inputs:
        raise ValueError(
            "Нельзя пересчитать формулу при конфликтующих химических колонках: "
            + ", ".join(sorted(duplicate_inputs))
            + ". Сначала выберите правильный исходный столбец."
        )

    cats: dict[str, pd.Series] = {}
    oxygen_moles = pd.Series(0.0, index=df.index, dtype=float)

    # FeOt means total Fe expressed as FeO. It may stand in for FeO only when
    # separate FeO is absent. FeOt plus a non-zero Fe2O3 column without FeO is
    # chemically ambiguous and must not be silently double-counted.
    if "FeOt" in df.columns and "FeO" not in df.columns and "Fe2O3" in df.columns:
        measured_fe3 = pd.to_numeric(df["Fe2O3"], errors="coerce").fillna(0.0)
        if (measured_fe3.abs() > 0).any():
            raise ValueError(
                "Одновременно заданы FeOt и Fe2O3 без отдельного FeO. "
                "Нельзя однозначно разделить total Fe и измеренный Fe3+."
            )

    for oxide, spec in OXIDES.items():
        if oxide not in allowed:
            continue
        source_column = oxide
        if oxide == "FeO" and "FeO" not in df.columns and "FeOt" in df.columns:
            source_column = "FeOt"
        if source_column not in df.columns:
            continue
        moles_oxide = _num(df, source_column) / spec.molar_mass
        oxygen_moles = oxygen_moles + moles_oxide * spec.n_oxygen
        cat_moles = moles_oxide * spec.n_cation
        cats[spec.cation] = cats.get(spec.cation, pd.Series(0.0, index=df.index)) + cat_moles

    factor = pd.Series(np.nan, index=df.index, dtype=float)
    valid = oxygen_moles > 0
    factor.loc[valid] = oxygen_basis / oxygen_moles.loc[valid]

    apfu = pd.DataFrame(index=df.index)
    for cat, values in cats.items():
        apfu[cat] = values * factor

    for hal, aw in HALOGENS.items():
        if hal in df.columns:
            apfu[hal] = (_num(df, hal) / aw) * factor

    cation_cols = [c for c in apfu.columns if c not in HALOGENS]
    cation_sum = apfu[cation_cols].sum(axis=1, min_count=1) if cation_cols else pd.Series(np.nan, index=df.index)
    return apfu, factor, cation_sum


def _attach(out: pd.DataFrame, apfu: pd.DataFrame, prefix: str = "apfu_") -> pd.DataFrame:
    for col in apfu.columns:
        out[f"{prefix}{col}"] = apfu[col]
    return out


def _droop_split(apfu: pd.DataFrame, oxygen_basis: float, ideal_cations: float) -> pd.DataFrame:
    """Stoichiometric Fe3+ estimate following Droop (1987).

    F = 2X(1 - T/S), where S is the cation sum on X oxygens assuming all Fe
    is ferrous. After F is estimated, all cations are renormalized by T/S,
    as recommended in Droop's procedure and emphasized by Neave et al. (2024).
    """
    work = apfu.copy()
    measured_fe3 = work.get("Fe3", pd.Series(0.0, index=work.index)).copy()
    measured_fe2 = work.get("Fe2", pd.Series(0.0, index=work.index)).copy()
    total_fe = measured_fe2 + measured_fe3

    # For the stoichiometric estimate, treat all measured Fe as Fe2 first.
    work["Fe2"] = total_fe
    work["Fe3"] = 0.0
    cation_cols = [c for c in work.columns if c not in HALOGENS]
    S = work[cation_cols].sum(axis=1, min_count=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        F = 2.0 * oxygen_basis * (1.0 - ideal_cations / S)
    F = F.clip(lower=0.0)
    F = pd.concat([F, total_fe], axis=1).min(axis=1)

    scale = ideal_cations / S
    for c in cation_cols:
        work[c] = work[c] * scale

    total_fe_scaled = total_fe * scale
    # Droop's F = 2X(1-T/S) is the final Fe3+ apfu after the T/S
    # cation renormalisation; do not multiply F by T/S a second time.
    F_final = pd.concat([F, total_fe_scaled], axis=1).min(axis=1).clip(lower=0.0)
    work["Fe3"] = F_final
    work["Fe2"] = (total_fe_scaled - F_final).clip(lower=0.0)
    return work


def _mg_number(apfu: pd.DataFrame) -> pd.Series:
    mg = apfu.get("Mg", pd.Series(0.0, index=apfu.index))
    fe2 = apfu.get("Fe2", pd.Series(0.0, index=apfu.index))
    den = mg + fe2
    return pd.Series(np.where(den > 0, mg / den, np.nan), index=apfu.index)


def calc_olivine(df: pd.DataFrame, method_id: str) -> CalculationResult:
    out = df.copy()
    apfu, _, _ = oxygen_normalized_apfu(df, 4.0)
    if method_id == "ol_droop_4o":
        apfu = _droop_split(apfu, 4.0, 3.0)
    out = _attach(out, apfu)
    mg = apfu.get("Mg", 0.0); fe2 = apfu.get("Fe2", 0.0); mn = apfu.get("Mn", 0.0); ca = apfu.get("Ca", 0.0)
    den = mg + fe2 + mn + ca
    out["Fo"] = np.where(den > 0, 100 * mg / den, np.nan)
    out["Fa"] = np.where(den > 0, 100 * fe2 / den, np.nan)
    out["Te"] = np.where(den > 0, 100 * mn / den, np.nan)
    out["Ca-ol"] = np.where(den > 0, 100 * ca / den, np.nan)
    out["Mg#_formula"] = _mg_number(apfu)
    return CalculationResult(out)


def calc_pyroxene(df: pd.DataFrame, method_id: str) -> CalculationResult:
    out = df.copy()
    apfu, _, _ = oxygen_normalized_apfu(df, 6.0)
    if method_id == "px_morimoto_droop":
        apfu = _droop_split(apfu, 6.0, 4.0)
    out = _attach(out, apfu)
    ca = apfu.get("Ca", 0.0); mg = apfu.get("Mg", 0.0); fe2 = apfu.get("Fe2", 0.0)
    quad = ca + mg + fe2
    out["Wo"] = np.where(quad > 0, 100 * ca / quad, np.nan)
    out["En"] = np.where(quad > 0, 100 * mg / quad, np.nan)
    out["Fs"] = np.where(quad > 0, 100 * fe2 / quad, np.nan)
    na = apfu.get("Na", 0.0)
    out["J"] = 2 * na
    out["Q"] = ca + mg + fe2
    out["Mg#_formula"] = _mg_number(apfu)
    fe3 = apfu.get("Fe3", 0.0)
    fet = fe2 + fe3
    out["Fe3+/ΣFe"] = np.where(fet > 0, fe3 / fet, np.nan)
    return CalculationResult(out)


def calc_garnet(df: pd.DataFrame, method_id: str) -> CalculationResult:
    out = df.copy()
    apfu, _, _ = oxygen_normalized_apfu(df, 12.0)
    if method_id == "grt_grew_droop":
        apfu = _droop_split(apfu, 12.0, 8.0)
    out = _attach(out, apfu)
    ca = apfu.get("Ca", 0.0); mg = apfu.get("Mg", 0.0); fe2 = apfu.get("Fe2", 0.0); mn = apfu.get("Mn", 0.0)
    xsum = ca + mg + fe2 + mn
    x_prp = np.where(xsum > 0, mg / xsum, np.nan)
    x_alm = np.where(xsum > 0, fe2 / xsum, np.nan)
    x_sps = np.where(xsum > 0, mn / xsum, np.nan)
    x_ca = np.where(xsum > 0, ca / xsum, np.nan)
    fe3 = apfu.get("Fe3", 0.0); cr = apfu.get("Cr", 0.0); al = apfu.get("Al", 0.0)
    ysum = al + fe3 + cr
    y_al = np.where(ysum > 0, al / ysum, np.nan)
    y_fe3 = np.where(ysum > 0, fe3 / ysum, np.nan)
    y_cr = np.where(ysum > 0, cr / ysum, np.nan)
    out["Prp"] = 100 * x_prp
    out["Alm"] = 100 * x_alm
    out["Sps"] = 100 * x_sps
    out["Grs"] = 100 * x_ca * y_al
    out["Adr"] = 100 * x_ca * y_fe3
    out["Uv"] = 100 * x_ca * y_cr
    out["Endmember_sum"] = out[["Prp", "Alm", "Sps", "Grs", "Adr", "Uv"]].sum(axis=1, min_count=1)
    out["Mg#_formula"] = _mg_number(apfu)
    return CalculationResult(out, "Основные Prp–Alm–Sps–Grs–Adr–Uv компоненты рассчитаны из X- и Y-позиционных долей. Для Ti-богатых гранатов и сложных вакансий нужен отдельный специализированный режим.")


def calc_feldspar(df: pd.DataFrame, method_id: str) -> CalculationResult:
    out = df.copy()
    apfu, _, _ = oxygen_normalized_apfu(df, 8.0)
    out = _attach(out, apfu)
    ca = apfu.get("Ca", 0.0); na = apfu.get("Na", 0.0); k = apfu.get("K", 0.0); ba = apfu.get("Ba", 0.0)
    den = ca + na + k
    out["An"] = np.where(den > 0, 100 * ca / den, np.nan)
    out["Ab"] = np.where(den > 0, 100 * na / den, np.nan)
    out["Or"] = np.where(den > 0, 100 * k / den, np.nan)
    out["Cn"] = np.where((den + ba) > 0, 100 * ba / (den + ba), np.nan)
    return CalculationResult(out)


def calc_mica(df: pd.DataFrame, method_id: str) -> CalculationResult:
    out = df.copy()
    basis = 11.0 if method_id == "mica_rieder_11o" else 22.0
    apfu, _, _ = oxygen_normalized_apfu(df, basis)
    out = _attach(out, apfu)
    si_cap = 4.0 if basis == 11 else 8.0
    al = apfu.get("Al", pd.Series(0.0, index=df.index))
    si = apfu.get("Si", pd.Series(0.0, index=df.index))
    al_iv = (si_cap - si).clip(lower=0.0)
    out["apfu_AlIV"] = al_iv
    out["apfu_AlVI"] = (al - al_iv).clip(lower=0.0)
    f = apfu.get("F", 0.0); cl = apfu.get("Cl", 0.0)
    wcap = 2.0 if basis == 11 else 4.0
    out["apfu_OH_max"] = (wcap - f - cl).clip(lower=0.0)
    out["Mg#_formula"] = _mg_number(apfu)
    return CalculationResult(out, "При рутинном EPMA весь Fe принят как Fe²⁺; OH_max — стехиометрический максимум, а не измеренное содержание OH.")


def calc_amphibole(df: pd.DataFrame, method_id: str) -> CalculationResult:
    out = df.copy()
    # Routine IMA-style 23 oxygen-equivalent recast. Species naming is deliberately
    # not attempted when Fe3+/Fe2+ and OH/O2- are unknown.
    apfu, _, _ = oxygen_normalized_apfu(df, 23.0)
    out = _attach(out, apfu)
    out["Mg#_formula"] = _mg_number(apfu)
    fe2 = apfu.get("Fe2", 0.0); fe3 = apfu.get("Fe3", 0.0); fet = fe2 + fe3
    out["Fe3+/ΣFe"] = np.where(fet > 0, fe3 / fet, np.nan)
    return CalculationResult(
        out,
        "Пересчёт на 23 O-экв. пригоден для проверки состава. Автоматическое IMA-имя не выдаётся, если Fe³⁺/Fe²⁺ и W-позиция не определены надёжно."
    )


def calc_spinel(df: pd.DataFrame, method_id: str) -> CalculationResult:
    out = df.copy()
    apfu, _, _ = oxygen_normalized_apfu(df, 4.0)
    if method_id == "sp_droop_4o":
        apfu = _droop_split(apfu, 4.0, 3.0)
    out = _attach(out, apfu)
    cr = apfu.get("Cr", 0.0); al = apfu.get("Al", 0.0); fe3 = apfu.get("Fe3", 0.0)
    den = cr + al + fe3
    out["Cr#"] = np.where((cr + al) > 0, cr / (cr + al), np.nan)
    out["XFe3_B"] = np.where(den > 0, fe3 / den, np.nan)
    out["Mg#_formula"] = _mg_number(apfu)
    return CalculationResult(out)


def calc_ilmenite(df: pd.DataFrame, method_id: str) -> CalculationResult:
    out = df.copy()
    apfu, _, _ = oxygen_normalized_apfu(df, 3.0)
    if method_id == "ilm_droop_3o":
        apfu = _droop_split(apfu, 3.0, 2.0)
    out = _attach(out, apfu)
    fe2 = apfu.get("Fe2", 0.0); fe3 = apfu.get("Fe3", 0.0); fet = fe2 + fe3
    out["Fe3+/ΣFe"] = np.where(fet > 0, fe3 / fet, np.nan)
    return CalculationResult(out)


def calc_apatite(df: pd.DataFrame, method_id: str) -> CalculationResult:
    out = df.copy()
    apfu, _, _ = oxygen_normalized_apfu(df, 25.0)
    out = _attach(out, apfu)
    f = apfu.get("F", 0.0); cl = apfu.get("Cl", 0.0)
    out["apfu_OH_est"] = 2.0 - f - cl
    out["QC_Z_site"] = np.where(out["apfu_OH_est"] < 0, "проверить F/Cl и условия EPMA", "норма")
    return CalculationResult(out, "Схема Ketcham (2015): 25 O-экв.; OH оценивается по заполнению Z-позиции, если редокс-форма S отдельно не задана.")


def calc_perovskite(df: pd.DataFrame, method_id: str) -> CalculationResult:
    out = df.copy()
    apfu, _, _ = oxygen_normalized_apfu(df, 3.0)
    out = _attach(out, apfu)
    # Practical site sums for crustal titanate perovskites. Full IMA end-member
    # decomposition requires explicit valence/speciation for some minor elements.
    A = sum((apfu.get(c, 0.0) for c in ("Ca", "Na", "Sr", "Ba", "La", "Ce", "Nd")), start=0.0)
    B = sum((apfu.get(c, 0.0) for c in ("Ti", "Nb", "Fe3", "Al", "Cr", "Zr")), start=0.0)
    out["A_site_sum_proxy"] = A
    out["B_site_sum_proxy"] = B
    ti = apfu.get("Ti", 0.0)
    out["Ti_B_fraction_proxy"] = np.where(B > 0, ti / B, np.nan)
    return CalculationResult(out, "Нормировка на 3 O соответствует перовскитовой формуле ABO3; полный IMA-разбор эндмемберов будет отдельным режимом Locock–Mitchell.")


def calc_nepheline(df: pd.DataFrame, method_id: str) -> CalculationResult:
    """Nepheline stoichiometry/QC on a 32 O unit-cell basis (Henderson, 2020)."""
    out = df.copy()
    apfu, _, _ = oxygen_normalized_apfu(df, 32.0)
    out = _attach(out, apfu)
    si = apfu.get("Si", pd.Series(0.0, index=df.index))
    ti = apfu.get("Ti", pd.Series(0.0, index=df.index))
    al = apfu.get("Al", pd.Series(0.0, index=df.index))
    fe3 = apfu.get("Fe3", pd.Series(0.0, index=df.index))
    na = apfu.get("Na", pd.Series(0.0, index=df.index))
    k = apfu.get("K", pd.Series(0.0, index=df.index))
    ca = apfu.get("Ca", pd.Series(0.0, index=df.index))

    t_sum = si + ti + al + fe3
    cavity_charge = na + k + 2.0 * ca
    a_trivalent = al + fe3
    delta_al_cc = a_trivalent - cavity_charge
    t_charge = 4.0 * (si + ti) + 3.0 * a_trivalent
    mean_t_charge = t_charge / t_sum.replace(0, np.nan)
    # Henderson (2020) states explicitly that T > 16 corresponds to negative
    # ΔT_charge and T < 16 to positive ΔT_charge. This form follows that sign convention.
    delta_t_charge = mean_t_charge * (16.0 - t_sum)
    ratio = delta_al_cc / delta_t_charge.replace(0, np.nan)

    # Henderson (2020), Table 2: end members on the 32-O / 24-site basis.
    ne = 3.0 * na * 100.0 / 24.0
    ks = 3.0 * k * 100.0 / 24.0
    cane = 6.0 * ca * 100.0 / 24.0
    qxs = (24.0 - 3.0 * na - 3.0 * k - 6.0 * ca) * 100.0 / 24.0
    m2 = apfu.get("Mg", pd.Series(0.0, index=df.index)) + apfu.get("Fe2", pd.Series(0.0, index=df.index)) + apfu.get("Mn", pd.Series(0.0, index=df.index))
    ksm = 6.0 * m2 * 100.0 / 24.0

    out["T_sum_32O"] = t_sum
    out["Cavity_NaK2Ca"] = cavity_charge
    out["DeltaAl_cc"] = delta_al_cc
    out["DeltaT_charge"] = delta_t_charge
    out["Delta_ratio"] = ratio
    out["Si_Al"] = si / a_trivalent.replace(0, np.nan)
    out["Cavity_vacancy_proxy"] = 8.0 - (na + k + ca)
    out["Ne_mol%"] = ne
    out["Ks_mol%"] = ks
    out["CaNe_mol%"] = cane
    out["Qxs_mol%"] = qxs
    out["KsM_mol%"] = ksm

    qc_t = t_sum.between(15.9, 16.1)
    # Henderson initially adopts ±0.25 and ratio 1.0–1.2; we use those strict
    # criteria rather than silently relaxing them.
    qc_delta = delta_al_cc.abs().le(0.25) & delta_t_charge.abs().le(0.25)
    near_zero = delta_al_cc.abs().lt(0.02) & delta_t_charge.abs().lt(0.02)
    qc_ratio = ratio.abs().between(1.0, 1.2) | near_zero
    out["QC_nepheline"] = np.where(qc_t & qc_delta & qc_ratio, "норма", "проверить стехиометрию/Na")
    return CalculationResult(
        out,
        "Henderson (2020): 32 O, 16 T-позиций и 8 полостных позиций. Рассчитаны Ne–Ks–CaNe–Qxs и диагностические ΔAl_cc/ΔT_charge. QC намеренно строгий и чувствителен к потере Na при EPMA."
    )


def calc_carbonate(df: pd.DataFrame, method_id: str) -> CalculationResult:
    out = df.copy()
    # Carbon is normally not measured by EPMA. Normalize divalent/trivalent metal
    # cations directly, which is the most transparent routine approach.
    cats = {}
    for oxide, spec in OXIDES.items():
        if oxide not in df.columns or spec.cation in {"Si", "Ti", "Al", "P", "S6"}:
            continue
        cats[spec.cation] = _num(df, oxide) / spec.molar_mass * spec.n_cation
    if not cats:
        return CalculationResult(out, "Не найдены катионные оксиды для пересчёта карбоната.")
    raw = pd.DataFrame(cats, index=df.index)
    target = 1.0 if method_id == "carb_1cat" else 2.0
    total = raw.sum(axis=1)
    factor = target / total.replace(0, np.nan)
    apfu = raw.mul(factor, axis=0)
    out = _attach(out, apfu)
    for c in ("Ca", "Mg", "Fe2", "Mn", "Sr", "Ba"):
        if c in apfu:
            out[f"X_{c}"] = apfu[c] / target
    return CalculationResult(out, f"Нормировка на {target:g} катион(а); CO2 обычно не измеряется EPMA и в сумму не включён.")


def calc_titanite(df: pd.DataFrame, method_id: str) -> CalculationResult:
    out = df.copy()
    # First obtain a 5-O composition, then rescale so tetrahedral + octahedral
    # cations sum to 2, as in the MinPlot titanite routine.
    apfu, _, _ = oxygen_normalized_apfu(df, 5.0)
    site_cats = [c for c in ("Si", "Al", "Ti", "Fe3", "Mg", "Mn", "Cr") if c in apfu]
    s = apfu[site_cats].sum(axis=1) if site_cats else pd.Series(np.nan, index=df.index)
    scale = 2.0 / s.replace(0, np.nan)
    apfu = apfu.mul(scale, axis=0)
    out = _attach(out, apfu)
    al = apfu.get("Al", 0.0); fe3 = apfu.get("Fe3", 0.0); f = apfu.get("F", 0.0)
    out["apfu_OH_est"] = (al + fe3 - f).clip(lower=0.0) if hasattr(al, "clip") else np.nan
    ti = apfu.get("Ti", 0.0)
    octsum = sum((apfu.get(c, 0.0) for c in ("Ti", "Al", "Fe3", "Mg", "Mn", "Cr")), start=0.0)
    out["X_titanite_proxy"] = np.where(octsum > 0, ti / octsum, np.nan)
    return CalculationResult(out)


def calc_zircon(df: pd.DataFrame, method_id: str) -> CalculationResult:
    out = df.copy()
    apfu, _, _ = oxygen_normalized_apfu(df, 4.0)
    out = _attach(out, apfu)
    return CalculationResult(out)


METHODS_BY_MINERAL: dict[str, tuple[FormulaMethod, ...]] = {
    "olivine": (
        FormulaMethod("ol_4o_fe2", "4 O, весь Fe как Fe²⁺", "4 O", "Подходит, когда Fe³⁺ пренебрежимо мал или не требуется.", ("Deer, Howie & Zussman, 1992", "Gündüz & Asan, 2023, Mineralogical Magazine 87, 1–9, doi:10.1180/mgm.2022.113")),
        FormulaMethod("ol_droop_4o", "4 O + стехиометрический Fe³⁺ (Droop)", "4 O; T=3", "Fe — единственный элемент с переменной валентностью; без катионных вакансий.", ("Droop, 1987, Mineralogical Magazine 51, 431–435", "Walters, 2022, Mineralogia 53, 51–66")),
    ),
    "clinopyroxene": (
        FormulaMethod("px_morimoto_droop", "Morimoto + Fe³⁺ по Droop", "6 O; T=4", "Основной режим для магматических Cpx при качественном EPMA.", ("Morimoto et al., 1988, Mineralogical Magazine 52, 535–550 (IMA)", "Droop, 1987, Mineralogical Magazine 51, 431–435"), ("Neave, Stewart & McCammon, 2024, Contributions to Mineralogy and Petrology 179:5, doi:10.1007/s00410-023-02080-2", "Neave et al., 2024, Contributions to Mineralogy and Petrology 179:67, doi:10.1007/s00410-024-02144-x — природные OIB-Cpx, Fe³⁺ по Droop",)),
        FormulaMethod("px_6o_fe2", "Morimoto, весь Fe как Fe²⁺", "6 O", "Упрощённый режим; Fe³⁺ не оценивается.", ("Morimoto et al., 1988, Mineralogical Magazine 52, 535–550", "Walters, 2022, Mineralogia 53, 51–66")),
    ),
    "orthopyroxene": (
        FormulaMethod("px_morimoto_droop", "Morimoto + Fe³⁺ по Droop", "6 O; T=4", "Для Opx без значимых вакансий; Fe — основной переменно-валентный элемент.", ("Morimoto et al., 1988, Mineralogical Magazine 52, 535–550", "Droop, 1987")),
        FormulaMethod("px_6o_fe2", "Morimoto, весь Fe как Fe²⁺", "6 O", "Упрощённый режим.", ("Morimoto et al., 1988, Mineralogical Magazine 52, 535–550",)),
    ),
    "garnet": (
        FormulaMethod("grt_grew_droop", "IMA-13 + Fe³⁺ по Droop", "12 O; T=8", "Для обычных гранатов без значимых катионных вакансий.", ("Grew et al., 2013, American Mineralogist 98, 785–811, doi:10.2138/am.2013.4201", "Droop, 1987"), ("Yavuz & Yildirim, 2020, Journal of Geosciences 65, 71–95",)),
        FormulaMethod("grt_12o_fe2", "12 O, весь Fe как Fe²⁺", "12 O", "Подходит для Fe²⁺-доминирующих гранатов, но не для андрадитовых/Ti-богатых составов.", ("Grew et al., 2013", "Walters, 2022")),
    ),
    "feldspar": (
        FormulaMethod("fsp_8o", "Полевой шпат: 8 O, An–Ab–Or", "8 O", "Fe не участвует в классическом An–Ab–Or знаменателе.", ("Gündüz & Asan, 2023, Mineralogical Magazine 87, 1–9, doi:10.1180/mgm.2022.113", "Walters, 2022, Mineralogia 53, 51–66")),
    ),
    "mica": (
        FormulaMethod(
            "mica_rieder_11o",
            "IMA: 22 положительных заряда (11 O-экв.)",
            "11 O-экв. = 22 положительных заряда",
            "Рекомендация IMA для EPMA без H2O. В рутинном режиме весь Fe принимается как Fe²⁺; OH оценивается стехиометрически. PCR Li et al. (2020) — отдельная модель, а не стехиометрическая истина.",
            ("Rieder et al., 1998, Canadian Mineralogist 36, 905–912 (IMA)", "Li et al., 2020, Lithos 356–357, 105371"),
            ("Dubacq & Forshaw, 2024, European Journal of Mineralogy 36, 657–685 — 22-charge basis и проверка Ti-rich biotite", "Henderson, 2025, Geochimica et Cosmochimica Acta 406, 57–81 — Ti–Ba-rich phlogopitic micas"),
        ),
        FormulaMethod(
            "mica_rieder_22o",
            "Удвоенная формула: 22 O (флогопит/биотит)",
            "22 O; удвоенная запись относительно 11 O-экв.",
            "Удобный convention для публикаций по флогопиту и биотиту: все apfu вдвое больше, чем при IMA 22-charge нормировке. При отсутствии независимого Fe³⁺ весь Fe принимается как Fe²⁺.",
            ("Henderson, 2025, Geochimica et Cosmochimica Acta 406, 57–81", "Rieder et al., 1998 — IMA-база номенклатуры"),
            ("Tappe et al., 2006, Journal of Petrology 47, 1261–1315 — флогопит в ультрамафических лампрофирах/карбонатитах, 22 O equivalents",),
            "Не сравнивать apfu из режима 22 O напрямую с таблицами, нормированными на 11 O-экв.: значения отличаются в 2 раза.",
        ),
    ),
    "amphibole": (
        FormulaMethod("amp_ima2012_23o", "IMA 2012: 23 O-экв.", "23 O-экв.", "Если Fe³⁺/Fe²⁺ не измерены, формула служит для QC и апfu; имя вида не присваивается автоматически.", ("Hawthorne et al., 2012, American Mineralogist 97, 2031–2048, doi:10.2138/am.2012.4276", "Locock, 2014, Computers & Geosciences 62, 1–11"), ("Siachoque et al., 2024, Geological Magazine — IMA Hawthorne (2012) + spreadsheet Locock (2014)", "Scandio-winchite, American Mineralogist 109 (2024), 940–947 — current Hawthorne et al. (2012) nomenclature",)),
    ),
    "spinel": (
        FormulaMethod("sp_droop_4o", "Шпинель: 4 O + Fe³⁺ по Droop", "4 O; T=3", "Fe — единственный существенно переменно-валентный элемент.", ("Droop, 1987", "Walters, 2022")),
        FormulaMethod("sp_4o_fe2", "Шпинель: 4 O, весь Fe как Fe²⁺", "4 O", "Только упрощённый просмотр; для магнетитовой компоненты нежелателен.", ("Walters, 2022",)),
    ),
    "fe_ti_oxide": (
        FormulaMethod("ilm_droop_3o", "Ильменитовая схема: 3 O + Fe³⁺ по Droop", "3 O; T=2", "Для ильменит-гематитового ряда; не заменяет парный оксидный термометр.", ("Droop, 1987", "Gündüz & Asan, 2023, Mineralogical Magazine 87, 1–9, doi:10.1180/mgm.2022.113")),
        FormulaMethod("ilm_3o_fe2", "3 O, весь Fe как Fe²⁺", "3 O", "Упрощённый режим.", ("Gündüz & Asan, 2023, Mineralogical Magazine 87, 1–9, doi:10.1180/mgm.2022.113",)),
    ),
    "apatite": (
        FormulaMethod("ap_ketcham25", "Ketcham: 25 O-экв.", "25 O-экв.", "F и Cl учитываются отдельно; при неизвестной S-специации OH — оценка.", ("Ketcham, 2015, American Mineralogist 100, 1620–1623, doi:10.2138/am-2015-5171", "Walters, 2022"), ("Reconstructing volatile evolution in melts using apatite, American Mineralogist 110 (2025), 1361ff. — формулы по Ketcham (2015)",)),
    ),
    "perovskite": (
        FormulaMethod("pv_3o", "Перовскит: 3 O, IMA-supergroup", "3 O", "Для полного эндмемберного разложения нужны валентности ряда минорных компонентов.", ("Mitchell, Welch & Chakhmouradian, 2017, Mineralogical Magazine 81, 411–461", "Locock & Mitchell, 2018, Computers & Geosciences 113, 106–114, doi:10.1016/j.cageo.2018.01.012"), ("Lyalina et al., 2025, Zapiski RMO 154(2), 14–51, doi:10.31857/S0869605525020029 — перовскитовая группа Ловозера; используется схема Mitchell/Locock",)),
    ),
    "nepheline": (
        FormulaMethod(
            "ne_henderson32",
            "Нефелин Henderson: 32 O + стехиометрический QC",
            "32 O; 16 T-позиций; 8 полостных позиций",
            "Al+Fe³⁺ сопоставляются с Na+K+2Ca; Fe³⁺ учитывается только если задан отдельно. QC чувствителен к потере Na при EPMA.",
            ("Henderson, 2020, Mineralogical Magazine 84(6), 813–838, doi:10.1180/mgm.2020.78",),
            ("Schmitt et al., 2024, Geochemistry 84, 126211 — эволюционировавшие нефелиниты",),
            "Для содалита, канкринита и аналцима нужны отдельные схемы; не применять этот режим к ним как к нефелину.",
        ),
    ),
    "carbonate": (
        FormulaMethod("carb_1cat", "Кальцитовая группа: 1 катион", "Σ катионов = 1", "Для CaCO3–MgCO3–FeCO3–MnCO3 состава; C обычно не измеряется EPMA.", ("Рутинная стехиометрическая нормировка карбонатов",)),
        FormulaMethod("carb_2cat", "Доломитовая группа: 2 катиона", "Σ октаэдрических катионов = 2", "Для CaMg(CO3)2 и родственных составов.", ("Adami et al., 2025, European Journal of Mineralogy 37, 517–532",)),
    ),
    "titanite": (
        FormulaMethod("ttn_minplot", "Титанит: Σ(T+M)=2", "T + октаэдрические катионы = 2", "OH оценивается как (AlVI + Fe³⁺) – F; без Fe³⁺ измерение ограничивает точность.", ("Walters, 2022, Mineralogia 53, 51–66",)),
    ),
    "zircon": (
        FormulaMethod("zrn_4o", "Циркон: 4 O", "4 O", "Базовый пересчёт ZrSiO4; Hf, Th, U сохраняются как apfu.", ("Gündüz & Asan, 2023, Mineralogical Magazine 87, 1–9, doi:10.1180/mgm.2022.113",)),
    ),
}

CALCULATORS: dict[str, Callable[[pd.DataFrame, str], CalculationResult]] = {
    "olivine": calc_olivine,
    "clinopyroxene": calc_pyroxene,
    "orthopyroxene": calc_pyroxene,
    "garnet": calc_garnet,
    "feldspar": calc_feldspar,
    "mica": calc_mica,
    "amphibole": calc_amphibole,
    "spinel": calc_spinel,
    "fe_ti_oxide": calc_ilmenite,
    "apatite": calc_apatite,
    "perovskite": calc_perovskite,
    "nepheline": calc_nepheline,
    "carbonate": calc_carbonate,
    "titanite": calc_titanite,
    "zircon": calc_zircon,
}


def methods_for(mineral_key: str) -> tuple[FormulaMethod, ...]:
    return METHODS_BY_MINERAL.get(mineral_key, ())


def calculate_formula(df: pd.DataFrame, mineral_key: str, method_id: str | None = None) -> CalculationResult:
    methods = methods_for(mineral_key)
    if mineral_key not in CALCULATORS or not methods:
        return CalculationResult(df.copy(), "Для этого минерала пока нет минералоспецифического пересчёта.")
    ids = {m.id for m in methods}
    chosen = method_id or methods[0].id
    if chosen not in ids:
        raise ValueError(f"Метод {chosen!r} не зарегистрирован для {mineral_key!r}")
    return CALCULATORS[mineral_key](df, chosen)
