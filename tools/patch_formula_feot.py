from pathlib import Path

path = Path("petrolab/minerals/formulae.py")
text = path.read_text(encoding="utf-8")
old = '''    for oxide, spec in OXIDES.items():
        if oxide not in allowed or oxide not in df.columns:
            continue
        moles_oxide = _num(df, oxide) / spec.molar_mass
        oxygen_moles = oxygen_moles + moles_oxide * spec.n_oxygen
        cat_moles = moles_oxide * spec.n_cation
        cats[spec.cation] = cats.get(spec.cation, pd.Series(0.0, index=df.index)) + cat_moles
'''
new = '''    # FeOt means total Fe expressed as FeO. It may stand in for FeO only when
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
'''
if old not in text:
    raise SystemExit("formula target block not found; refusing non-deterministic patch")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("formula FeOt patch applied")
