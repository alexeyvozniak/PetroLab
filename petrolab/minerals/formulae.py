from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

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
    allowed = set(allowed_oxides) if allowed_oxides else set(OXIDES)
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

    if "Fe2O3t" in df.columns:
        total_fe2o3 = pd.to_numeric(df["Fe2O3t"], errors="coerce")
        if total_fe2o3.notna().any():
            raise ValueError(
                "Обнаружен Fe2O3t (total Fe as Fe2O3). Сначала выберите явный способ "
                "преобразования total Fe."
            )

    cats: dict[str, pd.Series] = {}
    oxygen_moles = pd.Series(0.0, index=df.index, dtype=float)
    feo_raw = pd.to_numeric(df["FeO"], errors="coerce") if "FeO" in df.columns else pd.Series(np.nan, index=df.index, dtype=float)
    feot_raw = pd.to_numeric(df["FeOt"], errors="coerce") if "FeOt" in df.columns else pd.Series(np.nan, index=df.index, dtype=float)
    fe3_raw = pd.to_numeric(df["Fe2O3"], errors="coerce") if "Fe2O3" in df.columns else pd.Series(np.nan, index=df.index, dtype=float)

    both_feo_feot = feo_raw.notna() & feot_raw.notna()
    if both_feo_feot.any():
        raise ValueError("В одной строке нельзя одновременно задавать FeO и FeOt.")
    ambiguous_total_fe = feot_raw.notna() & feo_raw.isna() & fe3_raw.notna()
    if ambiguous_total_fe.any():
        raise ValueError("FeOt + Fe2O3 без отдельного FeO неоднозначны для структурной формулы.")

    for oxide, spec in OXIDES.items():
        if oxide not in allowed:
            continue
        if oxide == "FeO":
            if "FeO" not in df.columns and "FeOt" not in df.columns:
                continue
            values = feo_raw.combine_first(feot_raw).fillna(0.0)
        else:
            if oxide not in df.columns:
                continue
            values = _num(df, oxide)
        moles_oxide = values / spec.molar_mass
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
    work = apfu.copy()
    measured_fe3 = work.get("Fe3", pd.Series(0.0, index=work.index)).fillna(0.0)
    if measured_fe3.gt(1e-12).any():
        raise ValueError(
            "Метод Droop нельзя применять, если Fe3+ уже задан отдельно через Fe2O3. "
            "Выберите метод без стехиометрической оценки Fe3+."
        )
    total_fe = work.get("Fe2", pd.Series(0.0, index=work.index)).fillna(0.0)
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
    out = df.copy(); apfu, _, _ = oxygen_normalized_apfu(df, 4.0)
    if method_id == "ol_droop_4o": apfu = _droop_split(apfu, 4.0, 3.0)
    out = _attach(out, apfu)
    mg = apfu.get("Mg", 0.0); fe2 = apfu.get("Fe2", 0.0); mn = apfu.get("Mn", 0.0); ca = apfu.get("Ca", 0.0)
    den = mg + fe2 + mn + ca
    out["Fo"] = np.where(den > 0, 100 * mg / den, np.nan); out["Fa"] = np.where(den > 0, 100 * fe2 / den, np.nan)
    out["Te"] = np.where(den > 0, 100 * mn / den, np.nan); out["Ca-ol"] = np.where(den > 0, 100 * ca / den, np.nan)
    out["Mg#_formula"] = _mg_number(apfu); return CalculationResult(out)


def calc_pyroxene(df: pd.DataFrame, method_id: str) -> CalculationResult:
    out = df.copy(); apfu, _, _ = oxygen_normalized_apfu(df, 6.0)
    if method_id == "px_morimoto_droop": apfu = _droop_split(apfu, 6.0, 4.0)
    out = _attach(out, apfu); ca = apfu.get("Ca", 0.0); mg = apfu.get("Mg", 0.0); fe2 = apfu.get("Fe2", 0.0)
    quad = ca + mg + fe2; out["Wo"] = np.where(quad > 0, 100 * ca / quad, np.nan); out["En"] = np.where(quad > 0, 100 * mg / quad, np.nan); out["Fs"] = np.where(quad > 0, 100 * fe2 / quad, np.nan)
    na = apfu.get("Na", 0.0); out["J"] = 2 * na; out["Q"] = ca + mg + fe2; out["Mg#_formula"] = _mg_number(apfu)
    fe3 = apfu.get("Fe3", 0.0); fet = fe2 + fe3; out["Fe3+/ΣFe"] = np.where(fet > 0, fe3 / fet, np.nan); return CalculationResult(out)


def calc_garnet(df: pd.DataFrame, method_id: str) -> CalculationResult:
    out = df.copy(); apfu, _, _ = oxygen_normalized_apfu(df, 12.0)
    if method_id == "grt_grew_droop": apfu = _droop_split(apfu, 12.0, 8.0)
    out = _attach(out, apfu); ca = apfu.get("Ca", 0.0); mg = apfu.get("Mg", 0.0); fe2 = apfu.get("Fe2", 0.0); mn = apfu.get("Mn", 0.0)
    xsum = ca + mg + fe2 + mn; x_prp = np.where(xsum > 0, mg / xsum, np.nan); x_alm = np.where(xsum > 0, fe2 / xsum, np.nan); x_sps = np.where(xsum > 0, mn / xsum, np.nan); x_ca = np.where(xsum > 0, ca / xsum, np.nan)
    fe3 = apfu.get("Fe3", 0.0); cr = apfu.get("Cr", 0.0); al = apfu.get("Al", 0.0); ysum = al + fe3 + cr
    out["Prp"] = 100 * x_prp; out["Alm"] = 100 * x_alm; out["Sps"] = 100 * x_sps
    out["Grs"] = 100 * x_ca * np.where(ysum > 0, al / ysum, np.nan); out["Adr"] = 100 * x_ca * np.where(ysum > 0, fe3 / ysum, np.nan); out["Uv"] = 100 * x_ca * np.where(ysum > 0, cr / ysum, np.nan)
    out["Endmember_sum"] = out[["Prp", "Alm", "Sps", "Grs", "Adr", "Uv"]].sum(axis=1, min_count=1); out["Mg#_formula"] = _mg_number(apfu)
    return CalculationResult(out, "Упрощённые end-members; для Ti-богатых гранатов нужен специализированный режим.")


def calc_feldspar(df: pd.DataFrame, method_id: str) -> CalculationResult:
    out = df.copy(); apfu, _, _ = oxygen_normalized_apfu(df, 8.0); out = _attach(out, apfu)
    ca = apfu.get("Ca", 0.0); na = apfu.get("Na", 0.0); k = apfu.get("K", 0.0); ba = apfu.get("Ba", 0.0); den = ca + na + k
    out["An"] = np.where(den > 0, 100 * ca / den, np.nan); out["Ab"] = np.where(den > 0, 100 * na / den, np.nan); out["Or"] = np.where(den > 0, 100 * k / den, np.nan); out["Cn"] = np.where((den + ba) > 0, 100 * ba / (den + ba), np.nan); return CalculationResult(out)


def calc_mica(df: pd.DataFrame, method_id: str) -> CalculationResult:
    out = df.copy(); basis = 11.0 if method_id == "mica_rieder_11o" else 22.0; apfu, _, _ = oxygen_normalized_apfu(df, basis); out = _attach(out, apfu)
    si_cap = 4.0 if basis == 11 else 8.0; al = apfu.get("Al", pd.Series(0.0, index=df.index)); si = apfu.get("Si", pd.Series(0.0, index=df.index)); al_iv = (si_cap - si).clip(lower=0.0)
    out["apfu_AlIV"] = al_iv; out["apfu_AlVI"] = (al - al_iv).clip(lower=0.0); f = apfu.get("F", 0.0); cl = apfu.get("Cl", 0.0); wcap = 2.0 if basis == 11 else 4.0
    out["apfu_OH_max"] = (wcap - f - cl).clip(lower=0.0); out["Mg#_formula"] = _mg_number(apfu); return CalculationResult(out, "OH_max — стехиометрический максимум, не измеренный OH.")


def calc_amphibole(df: pd.DataFrame, method_id: str) -> CalculationResult:
    out = df.copy(); apfu, _, _ = oxygen_normalized_apfu(df, 23.0); out = _attach(out, apfu); out["Mg#_formula"] = _mg_number(apfu)
    fe2 = apfu.get("Fe2", 0.0); fe3 = apfu.get("Fe3", 0.0); fet = fe2 + fe3; out["Fe3+/ΣFe"] = np.where(fet > 0, fe3 / fet, np.nan)
    return CalculationResult(out, "23 O-экв. для QC; автоматическое IMA-имя не выдаётся.")


def calc_spinel(df: pd.DataFrame, method_id: str) -> CalculationResult:
    out = df.copy(); apfu, _, _ = oxygen_normalized_apfu(df, 4.0)
    if method_id == "sp_droop_4o": apfu = _droop_split(apfu, 4.0, 3.0)
    out = _attach(out, apfu); cr = apfu.get("Cr", 0.0); al = apfu.get("Al", 0.0); fe3 = apfu.get("Fe3", 0.0); den = cr + al + fe3
    out["Cr#"] = np.where((cr + al) > 0, cr / (cr + al), np.nan); out["XFe3_B"] = np.where(den > 0, fe3 / den, np.nan); out["Mg#_formula"] = _mg_number(apfu); return CalculationResult(out)


def calc_ilmenite(df: pd.DataFrame, method_id: str) -> CalculationResult:
    out = df.copy(); apfu, _, _ = oxygen_normalized_apfu(df, 3.0)
    if method_id == "ilm_droop_3o": apfu = _droop_split(apfu, 3.0, 2.0)
    out = _attach(out, apfu); fe2 = apfu.get("Fe2", 0.0); fe3 = apfu.get("Fe3", 0.0); fet = fe2 + fe3; out["Fe3+/ΣFe"] = np.where(fet > 0, fe3 / fet, np.nan); return CalculationResult(out)


def calc_apatite(df: pd.DataFrame, method_id: str) -> CalculationResult:
    out = df.copy(); apfu, _, _ = oxygen_normalized_apfu(df, 25.0); out = _attach(out, apfu)
    has_f = "F" in df.columns; has_cl = "Cl" in df.columns
    if has_f and has_cl:
        f = apfu.get("F", pd.Series(0.0, index=df.index)); cl = apfu.get("Cl", pd.Series(0.0, index=df.index)); out["apfu_OH_est"] = 2.0 - f - cl
        out["QC_Z_site"] = np.where(out["apfu_OH_est"] < 0, "проверить F/Cl и условия EPMA", "норма"); out["OH_est_basis"] = "F и Cl измерены"
    else:
        out["apfu_OH_est"] = np.nan; out["QC_Z_site"] = "F/Cl измерены не полностью"; out["OH_est_basis"] = "X-аннон не определён"
    return CalculationResult(out, "OH оценивается только при явно заданных F и Cl.")


def calc_perovskite(df: pd.DataFrame, method_id: str) -> CalculationResult:
    out = df.copy(); apfu, _, _ = oxygen_normalized_apfu(df, 3.0); out = _attach(out, apfu)
    A = sum((apfu.get(c, 0.0) for c in ("Ca", "Na", "Sr", "Ba", "La", "Ce", "Nd")), start=0.0); B = sum((apfu.get(c, 0.0) for c in ("Ti", "Nb", "Fe3", "Al", "Cr", "Zr")), start=0.0)
    out["A_site_sum_proxy"] = A; out["B_site_sum_proxy"] = B; ti = apfu.get("Ti", 0.0); out["Ti_B_fraction_proxy"] = np.where(B > 0, ti / B, np.nan); return CalculationResult(out)


def calc_nepheline(df: pd.DataFrame, method_id: str) -> CalculationResult:
    out = df.copy(); apfu, _, _ = oxygen_normalized_apfu(df, 32.0); out = _attach(out, apfu)
    si = apfu.get("Si", pd.Series(0.0, index=df.index)); ti = apfu.get("Ti", pd.Series(0.0, index=df.index)); al = apfu.get("Al", pd.Series(0.0, index=df.index)); fe3 = apfu.get("Fe3", pd.Series(0.0, index=df.index)); na = apfu.get("Na", pd.Series(0.0, index=df.index)); k = apfu.get("K", pd.Series(0.0, index=df.index)); ca = apfu.get("Ca", pd.Series(0.0, index=df.index))
    t_sum = si + ti + al + fe3; cavity_charge = na + k + 2.0 * ca; a_trivalent = al + fe3; delta_al_cc = a_trivalent - cavity_charge; t_charge = 4.0 * (si + ti) + 3.0 * a_trivalent; mean_t_charge = t_charge / t_sum.replace(0, np.nan); delta_t_charge = mean_t_charge * (16.0 - t_sum); ratio = delta_al_cc / delta_t_charge.replace(0, np.nan)
    ne = 3.0 * na * 100.0 / 24.0; ks = 3.0 * k * 100.0 / 24.0; cane = 6.0 * ca * 100.0 / 24.0; qxs = (24.0 - 3.0 * na - 3.0 * k - 6.0 * ca) * 100.0 / 24.0; m2 = apfu.get("Mg", pd.Series(0.0, index=df.index)) + apfu.get("Fe2", pd.Series(0.0, index=df.index)) + apfu.get("Mn", pd.Series(0.0, index=df.index)); ksm = 6.0 * m2 * 100.0 / 24.0
    out["T_sum_32O"] = t_sum; out["Cavity_NaK2Ca"] = cavity_charge; out["DeltaAl_cc"] = delta_al_cc; out["DeltaT_charge"] = delta_t_charge; out["Delta_ratio"] = ratio; out["Si_Al"] = si / a_trivalent.replace(0, np.nan); out["Cavity_vacancy_proxy"] = 8.0 - (na + k + ca); out["Ne_mol%"] = ne; out["Ks_mol%"] = ks; out["CaNe_mol%"] = cane; out["Qxs_mol%"] = qxs; out["KsM_mol%"] = ksm
    qc_t = t_sum.between(15.9, 16.1); qc_delta = delta_al_cc.abs().le(0.25) & delta_t_charge.abs().le(0.25); near_zero = delta_al_cc.abs().lt(0.02) & delta_t_charge.abs().lt(0.02); qc_ratio = ratio.abs().between(1.0, 1.2) | near_zero; out["QC_nepheline"] = np.where(qc_t & qc_delta & qc_ratio, "норма", "проверить стехиометрию/Na")
    return CalculationResult(out)


def calc_carbonate(df: pd.DataFrame, method_id: str) -> CalculationResult:
    out = df.copy(); cats: dict[str, pd.Series] = {}
    feo_raw = pd.to_numeric(df["FeO"], errors="coerce") if "FeO" in df.columns else pd.Series(np.nan, index=df.index); feot_raw = pd.to_numeric(df["FeOt"], errors="coerce") if "FeOt" in df.columns else pd.Series(np.nan, index=df.index)
    if (feo_raw.notna() & feot_raw.notna()).any(): raise ValueError("Для карбоната нельзя одновременно использовать FeO и FeOt в одной строке.")
    for oxide, spec in OXIDES.items():
        if spec.cation in {"Si", "Ti", "Al", "P", "S6"}: continue
        if oxide == "FeO":
            if "FeO" not in df.columns and "FeOt" not in df.columns: continue
            values = feo_raw.combine_first(feot_raw).fillna(0.0)
        else:
            if oxide not in df.columns: continue
            values = _num(df, oxide)
        cats[spec.cation] = values / spec.molar_mass * spec.n_cation
    if not cats: return CalculationResult(out, "Не найдены катионные оксиды для пересчёта карбоната.")
    raw = pd.DataFrame(cats, index=df.index); target = 1.0 if method_id == "carb_1cat" else 2.0; total = raw.sum(axis=1); factor = target / total.replace(0, np.nan); apfu = raw.mul(factor, axis=0); out = _attach(out, apfu)
    for c in ("Ca", "Mg", "Fe2", "Fe3", "Mn", "Sr", "Ba"):
        if c in apfu: out[f"X_{c}"] = apfu[c] / target
    return CalculationResult(out, f"Нормировка на {target:g} катион(а); FeOt используется как FeO-equivalent total Fe.")


def calc_titanite(df: pd.DataFrame, method_id: str) -> CalculationResult:
    out = df.copy(); apfu, _, _ = oxygen_normalized_apfu(df, 5.0); site_cats = [c for c in ("Si", "Al", "Ti", "Fe3", "Mg", "Mn", "Cr") if c in apfu]
    s = apfu[site_cats].sum(axis=1) if site_cats else pd.Series(np.nan, index=df.index); scale = 2.0 / s.replace(0, np.nan); apfu = apfu.mul(scale, axis=0); out = _attach(out, apfu); al = apfu.get("Al", 0.0); fe3 = apfu.get("Fe3", 0.0); f = apfu.get("F", 0.0); out["apfu_OH_est"] = (al + fe3 - f).clip(lower=0.0) if hasattr(al, "clip") else np.nan; ti = apfu.get("Ti", 0.0); octsum = sum((apfu.get(c, 0.0) for c in ("Ti", "Al", "Fe3", "Mg", "Mn", "Cr")), start=0.0); out["X_titanite_proxy"] = np.where(octsum > 0, ti / octsum, np.nan); return CalculationResult(out)


def calc_zircon(df: pd.DataFrame, method_id: str) -> CalculationResult:
    out = df.copy(); apfu, _, _ = oxygen_normalized_apfu(df, 4.0); return CalculationResult(_attach(out, apfu))


METHODS_BY_MINERAL: dict[str, tuple[FormulaMethod, ...]] = {
    "olivine": (FormulaMethod("ol_4o_fe2", "4 O без оценки Fe³⁺", "4 O", "Сохраняет отдельно заданный Fe³⁺; FeOt используется как FeO-equivalent при отсутствии FeO.", ("Deer, Howie & Zussman, 1992",)), FormulaMethod("ol_droop_4o", "4 O + Fe³⁺ по Droop", "4 O; T=3", "Только если независимый Fe³⁺ не задан.", ("Droop, 1987",))),
    "clinopyroxene": (FormulaMethod("px_morimoto_droop", "Morimoto + Fe³⁺ по Droop", "6 O; T=4", "Только если независимый Fe³⁺ не задан.", ("Morimoto et al., 1988", "Droop, 1987")), FormulaMethod("px_6o_fe2", "Morimoto без оценки Fe³⁺", "6 O", "Сохраняет отдельно заданный Fe³⁺.", ("Morimoto et al., 1988",))),
    "orthopyroxene": (FormulaMethod("px_morimoto_droop", "Morimoto + Fe³⁺ по Droop", "6 O; T=4", "Только если независимый Fe³⁺ не задан.", ("Morimoto et al., 1988", "Droop, 1987")), FormulaMethod("px_6o_fe2", "Morimoto без оценки Fe³⁺", "6 O", "Сохраняет отдельно заданный Fe³⁺.", ("Morimoto et al., 1988",))),
    "garnet": (FormulaMethod("grt_grew_droop", "IMA-13 + Fe³⁺ по Droop", "12 O; T=8", "Только если независимый Fe³⁺ не задан.", ("Grew et al., 2013", "Droop, 1987")), FormulaMethod("grt_12o_fe2", "12 O без оценки Fe³⁺", "12 O", "Сохраняет отдельно заданный Fe³⁺.", ("Grew et al., 2013",))),
    "feldspar": (FormulaMethod("fsp_8o", "Полевой шпат: 8 O, An–Ab–Or", "8 O", "Классический An–Ab–Or.", ("Gündüz & Asan, 2023",)),),
    "mica": (FormulaMethod("mica_rieder_11o", "IMA: 11 O-экв.", "11 O-экв.", "OH_max — стехиометрический максимум.", ("Rieder et al., 1998",)), FormulaMethod("mica_rieder_22o", "Удвоенная формула: 22 O", "22 O", "Удвоенная запись.", ("Rieder et al., 1998",))),
    "amphibole": (FormulaMethod("amp_ima2012_23o", "IMA 2012: 23 O-экв.", "23 O-экв.", "QC/apfu без автоматического species name.", ("Hawthorne et al., 2012",)),),
    "spinel": (FormulaMethod("sp_droop_4o", "Шпинель: 4 O + Fe³⁺ по Droop", "4 O; T=3", "Только если независимый Fe³⁺ не задан.", ("Droop, 1987",)), FormulaMethod("sp_4o_fe2", "Шпинель: 4 O без оценки Fe³⁺", "4 O", "Сохраняет отдельно заданный Fe³⁺.", ("Walters, 2022",))),
    "fe_ti_oxide": (FormulaMethod("ilm_droop_3o", "Ильменит: 3 O + Fe³⁺ по Droop", "3 O; T=2", "Только если независимый Fe³⁺ не задан.", ("Droop, 1987",)), FormulaMethod("ilm_3o_fe2", "3 O без оценки Fe³⁺", "3 O", "Сохраняет отдельно заданный Fe³⁺.", ("Gündüz & Asan, 2023",))),
    "apatite": (FormulaMethod("ap_ketcham25", "Ketcham: 25 O-экв.", "25 O-экв.", "F и Cl нужны для X-anion classification.", ("Ketcham, 2015",)),),
    "perovskite": (FormulaMethod("pv_3o", "Перовскит: 3 O", "3 O", "Базовый пересчёт.", ("Mitchell et al., 2017",)),),
    "nepheline": (FormulaMethod("ne_henderson32", "Нефелин Henderson: 32 O", "32 O", "Стехиометрический QC Henderson.", ("Henderson, 2020",)),),
    "carbonate": (FormulaMethod("carb_1cat", "Кальцитовая группа: 1 катион", "Σ катионов = 1", "FeOt используется как FeO-equivalent, если FeO не задан.", ("Рутинная стехиометрическая нормировка",)), FormulaMethod("carb_2cat", "Доломитовая группа: 2 катиона", "Σ катионов = 2", "FeOt используется как FeO-equivalent, если FeO не задан.", ("Adami et al., 2025",))),
    "titanite": (FormulaMethod("ttn_minplot", "Титанит: Σ(T+M)=2", "T+M=2", "Упрощённый MinPlot-style пересчёт.", ("Walters, 2022",)),),
    "zircon": (FormulaMethod("zrn_4o", "Циркон: 4 O", "4 O", "Базовый пересчёт ZrSiO4.", ("Gündüz & Asan, 2023",)),),
}

CALCULATORS: dict[str, Callable[[pd.DataFrame, str], CalculationResult]] = {
    "olivine": calc_olivine, "clinopyroxene": calc_pyroxene, "orthopyroxene": calc_pyroxene,
    "garnet": calc_garnet, "feldspar": calc_feldspar, "mica": calc_mica, "amphibole": calc_amphibole,
    "spinel": calc_spinel, "fe_ti_oxide": calc_ilmenite, "apatite": calc_apatite, "perovskite": calc_perovskite,
    "nepheline": calc_nepheline, "carbonate": calc_carbonate, "titanite": calc_titanite, "zircon": calc_zircon,
}


def methods_for(mineral_key: str) -> tuple[FormulaMethod, ...]:
    return METHODS_BY_MINERAL.get(mineral_key, ())


def calculate_formula(df: pd.DataFrame, mineral_key: str, method_id: str | None = None) -> CalculationResult:
    methods = methods_for(mineral_key)
    if mineral_key not in CALCULATORS or not methods:
        return CalculationResult(df.copy(), "Для этого минерала пока нет минералоспецифического пересчёта.")
    ids = {m.id for m in methods}; chosen = method_id or methods[0].id
    if chosen not in ids: raise ValueError(f"Метод {chosen!r} не зарегистрирован для минерала {mineral_key!r}")
    return CALCULATORS[mineral_key](df, chosen)
