from pathlib import Path

path = Path("petrolab/column_schema.py")
text = path.read_text(encoding="utf-8")
old = '''_CONCENTRATION_UNIT_RE = re.compile(\n    r"(?:\\(|\\[)?\\s*(ppm|ppb|ppt|[µμu]g\\s*/\\s*g|mg\\s*/\\s*kg|ng\\s*/\\s*g|pg\\s*/\\s*g|"\n    r"мкг\\s*/\\s*г|мг\\s*/\\s*кг|нг\\s*/\\s*г|пг\\s*/\\s*г|"\n    r"wt\\.?\\s*%|mass\\s*%|мас\\.?\\s*%)\\s*(?:\\)|\\])?\\s*$",\n    flags=re.IGNORECASE,\n)\n'''
new = '''_CONCENTRATION_UNIT_RE = re.compile(\n    r"(?:\\(|\\[)?\\s*(ppm|ppb|ppt|[µμu]g\\s*/\\s*g|mg\\s*/\\s*kg|ng\\s*/\\s*g|pg\\s*/\\s*g|"\n    r"[µμu]g\\s+g(?:\\^?[-−]?1|[⁻−-]¹)|mg\\s+kg(?:\\^?[-−]?1|[⁻−-]¹)|"\n    r"ng\\s+g(?:\\^?[-−]?1|[⁻−-]¹)|pg\\s+g(?:\\^?[-−]?1|[⁻−-]¹)|"\n    r"мкг\\s*/\\s*г|мг\\s*/\\s*кг|нг\\s*/\\s*г|пг\\s*/\\s*г|"\n    r"мкг\\s+г(?:\\^?[-−]?1|[⁻−-]¹)|мг\\s+кг(?:\\^?[-−]?1|[⁻−-]¹)|"\n    r"нг\\s+г(?:\\^?[-−]?1|[⁻−-]¹)|пг\\s+г(?:\\^?[-−]?1|[⁻−-]¹)|"\n    r"wt\\.?\\s*%|mass\\s*%|мас\\.?\\s*%)\\s*(?:\\)|\\])?\\s*$",\n    flags=re.IGNORECASE,\n)\n'''
if old not in text:
    raise SystemExit("concentration regex target not found")
text = text.replace(old, new, 1)
old2 = '''    unit = _nfkc(raw).lower().replace("μ", "µ").replace("u", "µ")\n    unit = re.sub(r"\\s+", "", unit)\n    if unit in {"ppm", "µg/g", "мкг/г", "mg/kg", "мг/кг"}:\n        return raw, "µg/g", 1.0\n    if unit in {"ppb", "ng/g", "нг/г"}:\n        return raw, "µg/g", 1e-3\n    if unit in {"ppt", "pg/g", "пг/г"}:\n        return raw, "µg/g", 1e-6\n'''
new2 = '''    unit = _nfkc(raw).lower().replace("μ", "µ").replace("u", "µ")\n    unit = unit.replace("−", "-").replace("⁻", "-").replace("¹", "1").replace("^", "")\n    unit = re.sub(r"\\s+", "", unit)\n    if unit in {"ppm", "µg/g", "мкг/г", "mg/kg", "мг/кг", "µgg-1", "мкгг-1", "mgkg-1", "мгкг-1"}:\n        return raw, "µg/g", 1.0\n    if unit in {"ppb", "ng/g", "нг/г", "ngg-1", "нгг-1"}:\n        return raw, "µg/g", 1e-3\n    if unit in {"ppt", "pg/g", "пг/г", "pgg-1", "пгг-1"}:\n        return raw, "µg/g", 1e-6\n'''
if old2 not in text:
    raise SystemExit("unit normalization target not found")
text = text.replace(old2, new2, 1)
path.write_text(text, encoding="utf-8")

# Add focused tests without rewriting the whole test file.
test = Path("tests_column_schema.py")
t = test.read_text(encoding="utf-8")
anchor = '''assert canonicalize_header("Yb, мкг/г") == "Yb [µg/g]"\nassert canonicalize_header("Ba ppb") == "Ba [µg/g]"\n'''
replacement = '''assert canonicalize_header("Yb, мкг/г") == "Yb [µg/g]"\nassert canonicalize_header("Yb µg g⁻¹") == "Yb [µg/g]"\nassert canonicalize_header("La mg kg-1") == "La [µg/g]"\nassert canonicalize_header("Ba ng g⁻¹") == "Ba [µg/g]"\nassert canonicalize_header("Ba ppb") == "Ba [µg/g]"\n'''
if anchor not in t:
    raise SystemExit("trace unit test anchor not found")
test.write_text(t.replace(anchor, replacement, 1), encoding="utf-8")
print("inverse-mass unit aliases applied")
