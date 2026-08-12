from pathlib import Path
import ast

path = Path("petrolab/sources.py")
text = path.read_text(encoding="utf-8")
tree = ast.parse(text)
fn = next((node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_to_source_value"), None)
if fn is None:
    raise SystemExit("_to_source_value not found")
args = [arg.arg for arg in fn.args.args]
if args != ["dataset", "column_name", "value"]:
    raise SystemExit(f"unexpected _to_source_value signature: {args}")

lines = text.splitlines(keepends=True)
start = fn.lineno - 1
end = fn.end_lineno
replacement = '''def _to_source_value(dataset, column_name, value):
    mapping = json.loads(dataset.get("column_map_json") or "{}")
    info = mapping.get(str(column_name), {})
    factor = float(info.get("to_source_factor", 1.0) or 1.0)
    quantity_kind = str(info.get("quantity_kind") or "")
    scientific = quantity_kind in {"oxide", "trace_element", "element_concentration"}

    if value is None or (isinstance(value, str) and not value.strip()):
        return None

    if scientific or factor != 1.0:
        try:
            numeric = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Колонка {column_name} является числовой химической величиной; значение «{value}» не является числом"
            ) from exc
        if math.isnan(numeric):
            return None
        if not math.isfinite(numeric):
            raise ValueError(f"Колонка {column_name}: бесконечные значения нельзя записывать в Excel")
        return numeric * factor

    return value
'''
lines[start:end] = [replacement]
new_text = "".join(lines)
if "import math\n" not in new_text:
    marker = "from __future__ import annotations\n\n"
    if marker not in new_text:
        raise SystemExit("future import marker not found")
    new_text = new_text.replace(marker, marker + "import math\n", 1)
path.write_text(new_text, encoding="utf-8")
print("scientific source numeric validation patch applied")
