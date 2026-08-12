from pathlib import Path

path = Path("petrolab/minerals/formulae.py")
text = path.read_text(encoding="utf-8")
old = '''    allowed = set(allowed_oxides) if allowed_oxides else set(OXIDES)\n    cats: dict[str, pd.Series] = {}\n'''
new = '''    allowed = set(allowed_oxides) if allowed_oxides else set(OXIDES)\n\n    # A duplicated scientific input such as FeO + FeO__2 is ambiguous. The import\n    # layer deliberately keeps both columns instead of merging them, and the formula\n    # engine must not silently choose the first one.\n    formula_inputs = set(allowed) | set(HALOGENS)\n    if "FeO" in allowed:\n        formula_inputs.add("FeOt")\n    duplicate_inputs: list[str] = []\n    for column in df.columns:\n        name = str(column)\n        if "__" not in name:\n            continue\n        base, suffix = name.rsplit("__", 1)\n        if suffix.isdigit() and base in formula_inputs:\n            duplicate_inputs.append(name)\n    if duplicate_inputs:\n        raise ValueError(\n            "Нельзя пересчитать формулу при конфликтующих химических колонках: "\n            + ", ".join(sorted(duplicate_inputs))\n            + ". Сначала выберите правильный исходный столбец."\n        )\n\n    cats: dict[str, pd.Series] = {}\n'''
if old not in text:
    raise SystemExit("formula insertion target not found; refusing non-deterministic patch")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("formula duplicate guard applied")
