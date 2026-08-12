from pathlib import Path

path = Path("petrolab/minerals/formulae.py")
text = path.read_text(encoding="utf-8")
old = '''    cats: dict[str, pd.Series] = {}\n    oxygen_moles = pd.Series(0.0, index=df.index, dtype=float)\n\n    # FeO and FeOt can coexist as columns in historical merged datasets while being\n'''
new = '''    # Fe2O3t is total Fe expressed as Fe2O3, not measured ferric iron. Ignoring it\n    # would silently calculate an iron-poor formula; converting it requires an explicit\n    # reporting-basis conversion and, where needed, a Fe2+/Fe3+ allocation method.\n    if "Fe2O3t" in df.columns:\n        total_fe2o3 = pd.to_numeric(df["Fe2O3t"], errors="coerce")\n        if total_fe2o3.notna().any():\n            raise ValueError(\n                "Обнаружен Fe2O3t (total Fe as Fe2O3). Структурная формула не может "\n                "автоматически считать его измеренным Fe2O3 или игнорировать. "\n                "Сначала выберите явный способ преобразования total Fe."\n            )\n\n    cats: dict[str, pd.Series] = {}\n    oxygen_moles = pd.Series(0.0, index=df.index, dtype=float)\n\n    # FeO and FeOt can coexist as columns in historical merged datasets while being\n'''
if old not in text:
    raise SystemExit("Fe2O3t guard insertion target not found; refusing non-deterministic patch")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("Fe2O3t formula guard applied")
