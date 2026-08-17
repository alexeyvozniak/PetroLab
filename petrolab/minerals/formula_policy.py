from __future__ import annotations

import re

import numpy as np
import pandas as pd

_CENSORED = re.compile(r"^\s*(?:<=|>=|<|>|≤|≥)\s*[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\s*$")
_ALL_FE2 = {
    "ol_4o_fe2", "px_6o_fe2", "grt_12o_fe2",
    "mica_rieder_11o", "mica_rieder_22o", "sp_4o_fe2", "ilm_3o_fe2",
}
_DROOP = {"ol_droop_4o", "px_morimoto_droop", "grt_grew_droop", "sp_droop_4o", "ilm_droop_3o"}


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _validate_inputs(df: pd.DataFrame, formulae) -> None:
    """Reject chemistry that has no numerical interpretation.

    Finite negative concentrations are not rejected: background correction near a
    detection limit may yield small negative analytical numbers. They are floored to
    zero later in the calculation copy while source values stay untouched.
    """
    scientific = set(formulae.OXIDES) | set(getattr(formulae, "HALOGENS", ()))
    for column in [name for name in df.columns if str(name) in scientific]:
        raw = df[column]
        numeric = _numeric(raw)
        nonempty = raw.notna() & raw.astype("string").str.strip().ne("")
        bad = nonempty & numeric.isna()
        if bad.any():
            value = str(raw.loc[bad].iloc[0])
            row = int(np.flatnonzero(bad.to_numpy())[0]) + 1
            if _CENSORED.match(value):
                raise ValueError(
                    f"{column}, строка {row}: censored/detection-limit значение {value!r} "
                    "нельзя молча подставить в структурную формулу. Сначала задайте явную числовую трактовку."
                )
            raise ValueError(f"{column}, строка {row}: ожидалось числовое значение, получено {value!r}")
        nonfinite = numeric.notna() & ~np.isfinite(numeric)
        if nonfinite.any():
            row = int(np.flatnonzero(nonfinite.to_numpy())[0]) + 1
            raise ValueError(f"{column}, строка {row}: бесконечное значение недопустимо")


def _floor_negative_inputs(df: pd.DataFrame, formulae) -> tuple[pd.DataFrame, dict[str, int]]:
    """Apply the physical zero floor to chemistry only in a calculation copy."""
    work = df.copy()
    scientific = set(formulae.OXIDES) | set(getattr(formulae, "HALOGENS", ()))
    changed: dict[str, int] = {}
    for column in [name for name in work.columns if str(name) in scientific]:
        values = _numeric(work[column])
        negative = values.notna() & values.lt(0)
        count = int(negative.sum())
        if count:
            work.loc[negative, column] = 0.0
            changed[str(column)] = count
    return work, changed


def _factor_fe2o3_to_feo(formulae) -> float:
    return 2.0 * formulae.OXIDES["FeO"].molar_mass / formulae.OXIDES["Fe2O3"].molar_mass


def _as_fe2(df: pd.DataFrame, formulae) -> tuple[pd.DataFrame, str]:
    work = df.copy()
    feo = _numeric(work["FeO"]) if "FeO" in work else pd.Series(np.nan, index=work.index)
    feot = _numeric(work["FeOt"]) if "FeOt" in work else pd.Series(np.nan, index=work.index)
    fe3 = _numeric(work["Fe2O3"]) if "Fe2O3" in work else pd.Series(np.nan, index=work.index)
    if (feo.notna() & feot.notna()).any():
        raise ValueError("Метод «весь Fe как Fe²⁺»: FeO и FeOt одновременно заданы в одной строке")
    if (feot.notna() & fe3.notna()).any():
        raise ValueError("FeOt уже содержит total Fe и не может быть объединён с отдельным Fe2O3")
    base = feo.combine_first(feot)
    converted = fe3 * _factor_fe2o3_to_feo(formulae)
    combined = base.fillna(0.0) + converted.fillna(0.0)
    combined = combined.mask(base.isna() & fe3.isna())
    work["FeO"] = combined
    work = work.drop(columns=[name for name in ("FeOt", "Fe2O3") if name in work])
    note = "Для режима «весь Fe как Fe²⁺» Fe был временно приведён к FeO-equivalent; source-колонки не изменены."
    return work, note


def _titanite_fe3(df: pd.DataFrame, formulae) -> tuple[pd.DataFrame, str]:
    work = df.copy()
    feo = _numeric(work["FeO"]) if "FeO" in work else pd.Series(np.nan, index=work.index)
    feot = _numeric(work["FeOt"]) if "FeOt" in work else pd.Series(np.nan, index=work.index)
    fe3 = _numeric(work["Fe2O3"]) if "Fe2O3" in work else pd.Series(np.nan, index=work.index)
    if (feo.notna() & feot.notna()).any():
        raise ValueError("Титанит MinPlot: FeO и FeOt одновременно заданы в одной строке")
    if (feot.notna() & fe3.notna()).any():
        raise ValueError("Титанит MinPlot: FeOt (total Fe) нельзя объединять с отдельным Fe2O3")
    ferrous = feo.combine_first(feot)
    to_fe2o3 = 1.0 / _factor_fe2o3_to_feo(formulae)
    ferric_equiv = ferrous * to_fe2o3
    total_ferric = fe3.fillna(0.0) + ferric_equiv.fillna(0.0)
    total_ferric = total_ferric.mask(fe3.isna() & ferrous.isna())
    if total_ferric.notna().any():
        work["Fe2O3"] = total_ferric
    work = work.drop(columns=[name for name in ("FeO", "FeOt") if name in work])
    return work, "MinPlot-титанит: Fe временно приведён к Fe³⁺/Fe2O3-equivalent только для расчёта."


def _carbonate_total_fe(df: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    if "FeOt" not in df.columns:
        return df, ""
    work = df.copy()
    feot = _numeric(work["FeOt"])
    feo = _numeric(work["FeO"]) if "FeO" in work else pd.Series(np.nan, index=work.index)
    if (feo.notna() & feot.notna()).any():
        raise ValueError("Карбонат: FeO и FeOt нельзя использовать одновременно в одной строке")
    work["FeO"] = feo.combine_first(feot)
    work = work.drop(columns=["FeOt"])
    return work, "FeOt использован как total Fe expressed as FeO для катионной нормировки карбоната."


def _restore(source: pd.DataFrame, working: pd.DataFrame, calculated: pd.DataFrame) -> pd.DataFrame:
    out = source.copy()
    for column in calculated.columns:
        if column not in working.columns:
            out[column] = calculated[column]
    return out


def install() -> None:
    from petrolab.minerals import formulae
    from petrolab.services import formula_service

    originals = dict(formulae.CALCULATORS)

    def run(mineral_key: str, df: pd.DataFrame, method_id: str):
        _validate_inputs(df, formulae)
        work, floored = _floor_negative_inputs(df, formulae)
        notes: list[str] = []
        if floored:
            summary = ", ".join(f"{name}: {count}" for name, count in sorted(floored.items()))
            notes.append(
                "Отрицательные аналитические концентрации приняты равными 0 только для расчёта "
                f"({summary}). Исходные значения сохранены без изменения."
            )

        if method_id in _DROOP and "Fe2O3" in work and _numeric(work["Fe2O3"]).notna().any():
            raise ValueError("Метод Droop нельзя применять, когда Fe³⁺ уже отдельно задан через Fe2O3")
        if mineral_key == "nepheline":
            for name in ("FeO", "FeOt"):
                if name in work and _numeric(work[name]).notna().any():
                    raise ValueError(
                        "Henderson 32-O для нефелина использует Fe³⁺ в framework/charge balance; "
                        f"колонка {name} не может быть интерпретирована этим методом."
                    )
        if method_id in _ALL_FE2:
            work, note = _as_fe2(work, formulae)
            notes.append(note)
        if mineral_key == "titanite":
            work, note = _titanite_fe3(work, formulae)
            notes.append(note)
        if mineral_key == "carbonate":
            work, note = _carbonate_total_fe(work)
            if note:
                notes.append(note)

        result = originals[mineral_key](work, method_id)
        restored = _restore(df, work, result.data)

        if mineral_key == "apatite":
            full_halogen_columns = "F" in df.columns and "Cl" in df.columns
            full_rows = pd.Series(full_halogen_columns, index=df.index, dtype=bool)
            if full_halogen_columns:
                full_rows &= _numeric(df["F"]).notna() & _numeric(df["Cl"]).notna()
            if "apfu_OH_est" in restored:
                restored.loc[~full_rows, "apfu_OH_est"] = np.nan
            restored["OH_est_basis"] = np.where(full_rows, "F и Cl измерены", "F/Cl измерены не полностью")
            if "QC_Z_site" in restored:
                restored.loc[~full_rows, "QC_Z_site"] = "F/Cl измерены не полностью; X-анион не определён"

        if result.note_ru:
            notes.insert(0, result.note_ru)
        return formulae.CalculationResult(restored, "\n\n".join(note for note in notes if note))

    for key in originals:
        formulae.CALCULATORS[key] = lambda df, method_id, mineral=key: run(mineral, df, method_id)

    original_safe = formula_service.calculate_formula_safe

    def calculate_formula_safe(dataframe: pd.DataFrame, mineral_key: str, method_id: str | None = None):
        result = original_safe(dataframe, mineral_key, method_id)
        final = result.data.copy()
        if "_analysis_id" in dataframe.columns:
            if "_analysis_id" not in final.columns:
                raise ValueError("Результат формулы потерял _analysis_id")
            source_ids = dataframe["_analysis_id"].astype(str)
            result_ids = final["_analysis_id"].astype(str)
            if source_ids.duplicated().any() or result_ids.duplicated().any() or set(source_ids) != set(result_ids):
                raise ValueError("Нельзя безопасно выровнять результат формулы по _analysis_id")
            final = final.assign(_analysis_id=result_ids).set_index("_analysis_id", drop=False).loc[source_ids].reset_index(drop=True)
            final.index = dataframe.index
        if mineral_key == "apatite" and "OH_est_basis" in final.columns:
            unresolved = final["OH_est_basis"].astype(str) != "F и Cl измерены"
            for index in final.index[unresolved]:
                final.at[index, formula_service.SPECIES_COL] = ""
                final.at[index, formula_service.FIELD_COL] = "Apatite X-anion field unresolved"
                final.at[index, formula_service.LEVEL_COL] = "insufficient X-anion data"
                final.at[index, formula_service.NOTE_COL] = "F и Cl должны быть измерены для оценки OH и X-anion dominance."
        return formulae.CalculationResult(final, result.note_ru)

    formula_service.calculate_formula_safe = calculate_formula_safe
