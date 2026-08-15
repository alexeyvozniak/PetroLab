from __future__ import annotations

import ast
import json
import math
import re
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

from petrolab.column_schema import describe_header
from petrolab.db import _utcnow, connect


TARGET_DATASET = "dataset"
TARGET_ROCK_PROJECT = "rock_project"
_DIMENSIONLESS = "1"
_BACKTICK_RE = re.compile(r"`([^`]+)`")


FORMULA_PRESETS: tuple[dict[str, str], ...] = (
    {"label": "Сумма щелочей", "name": "Na2O+K2O", "expression": "Na2O + K2O"},
    {"label": "K2O/Na2O", "name": "K2O/Na2O", "expression": "K2O / Na2O"},
    {"label": "La/Yb", "name": "La/Yb", "expression": "La / Yb"},
    {"label": "La/Sm", "name": "La/Sm", "expression": "La / Sm"},
    {"label": "Gd/Yb", "name": "Gd/Yb", "expression": "Gd / Yb"},
    {"label": "Nb/Y", "name": "Nb/Y", "expression": "Nb / Y"},
    {"label": "Zr/Nb", "name": "Zr/Nb", "expression": "Zr / Nb"},
    {"label": "Th/Yb", "name": "Th/Yb", "expression": "Th / Yb"},
    {"label": "Nb/U", "name": "Nb/U", "expression": "Nb / U"},
    {"label": "Ce/Pb", "name": "Ce/Pb", "expression": "Ce / Pb"},
    {"label": "Rb/Sr", "name": "Rb/Sr", "expression": "Rb / Sr"},
    {"label": "Ba/Rb", "name": "Ba/Rb", "expression": "Ba / Rb"},
    {"label": "Sr/Y", "name": "Sr/Y", "expression": "Sr / Y"},
    {
        "label": "Mg# по APFU (0–1)",
        "name": "Mg#",
        "expression": "apfu_Mg / (apfu_Mg + apfu_Fe2)",
    },
)


@dataclass(frozen=True)
class ExpressionResult:
    values: pd.Series
    unit: str
    dependencies: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class DerivedField:
    id: int
    target_kind: str
    dataset_id: int | None
    project_id: int | None
    name: str
    expression: str
    unit: str
    dependencies: tuple[str, ...]
    description: str
    enabled: bool
    created_at: str
    updated_at: str


class FormulaReferenceError(ValueError):
    def __init__(self, reference: str):
        super().__init__(f"Колонка «{reference}» не найдена")
        self.reference = str(reference)


@dataclass(frozen=True)
class _NodeValue:
    value: pd.Series | float
    unit: str


def ensure_user_derived_schema() -> None:
    with connect() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS user_derived_fields (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_kind TEXT NOT NULL,
                dataset_id INTEGER,
                project_id INTEGER,
                name TEXT NOT NULL,
                expression TEXT NOT NULL,
                unit TEXT NOT NULL DEFAULT '',
                dependencies_json TEXT NOT NULL DEFAULT '[]',
                description TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(dataset_id) REFERENCES datasets(id) ON DELETE CASCADE,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                CHECK(target_kind IN ('dataset', 'rock_project')),
                CHECK(
                    (target_kind='dataset' AND dataset_id IS NOT NULL AND project_id IS NULL)
                    OR
                    (target_kind='rock_project' AND project_id IS NOT NULL AND dataset_id IS NULL)
                )
            )
            """
        )
        con.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_user_derived_dataset_name
            ON user_derived_fields(dataset_id, name)
            WHERE target_kind='dataset'
            """
        )
        con.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_user_derived_rock_project_name
            ON user_derived_fields(project_id, name)
            WHERE target_kind='rock_project'
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_derived_dataset ON user_derived_fields(dataset_id, enabled)"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_derived_project ON user_derived_fields(project_id, enabled)"
        )
        con.commit()


def _row_to_field(row) -> DerivedField:
    try:
        dependencies = tuple(str(value) for value in json.loads(str(row["dependencies_json"])))
    except (TypeError, ValueError, json.JSONDecodeError):
        dependencies = ()
    return DerivedField(
        id=int(row["id"]),
        target_kind=str(row["target_kind"]),
        dataset_id=int(row["dataset_id"]) if row["dataset_id"] is not None else None,
        project_id=int(row["project_id"]) if row["project_id"] is not None else None,
        name=str(row["name"]),
        expression=str(row["expression"]),
        unit=str(row["unit"] or ""),
        dependencies=dependencies,
        description=str(row["description"] or ""),
        enabled=bool(row["enabled"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def list_dataset_fields(dataset_id: int, *, include_disabled: bool = True) -> list[DerivedField]:
    ensure_user_derived_schema()
    query = "SELECT * FROM user_derived_fields WHERE target_kind=? AND dataset_id=?"
    params: list[object] = [TARGET_DATASET, int(dataset_id)]
    if not include_disabled:
        query += " AND enabled=1"
    query += " ORDER BY id"
    with connect() as con:
        rows = con.execute(query, params).fetchall()
    return [_row_to_field(row) for row in rows]


def list_rock_project_fields(project_id: int, *, include_disabled: bool = True) -> list[DerivedField]:
    ensure_user_derived_schema()
    query = "SELECT * FROM user_derived_fields WHERE target_kind=? AND project_id=?"
    params: list[object] = [TARGET_ROCK_PROJECT, int(project_id)]
    if not include_disabled:
        query += " AND enabled=1"
    query += " ORDER BY id"
    with connect() as con:
        rows = con.execute(query, params).fetchall()
    return [_row_to_field(row) for row in rows]


def _validate_field_name(name: str) -> str:
    clean = str(name).strip()
    if not clean:
        raise ValueError("Название вычисляемого поля не может быть пустым")
    if clean.startswith("_"):
        raise ValueError("Название вычисляемого поля не должно начинаться с подчёркивания")
    if len(clean) > 120:
        raise ValueError("Название вычисляемого поля слишком длинное")
    return clean


def _validate_expression(expression: str) -> str:
    clean = str(expression).strip()
    if not clean:
        raise ValueError("Формула не может быть пустой")
    if len(clean) > 2000:
        raise ValueError("Формула слишком длинная")
    return clean


def save_dataset_field(
    dataset_id: int,
    *,
    name: str,
    expression: str,
    unit: str,
    dependencies: Iterable[str],
    description: str = "",
) -> DerivedField:
    ensure_user_derived_schema()
    name = _validate_field_name(name)
    expression = _validate_expression(expression)
    now = _utcnow()
    with connect() as con:
        if con.execute("SELECT 1 FROM datasets WHERE id=?", (int(dataset_id),)).fetchone() is None:
            raise ValueError("Набор данных больше не существует")
        con.execute(
            """
            INSERT INTO user_derived_fields(
                target_kind, dataset_id, project_id, name, expression, unit,
                dependencies_json, description, enabled, created_at, updated_at
            ) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(dataset_id, name) WHERE target_kind='dataset' DO UPDATE SET
                expression=excluded.expression,
                unit=excluded.unit,
                dependencies_json=excluded.dependencies_json,
                description=excluded.description,
                enabled=1,
                updated_at=excluded.updated_at
            """,
            (
                TARGET_DATASET,
                int(dataset_id),
                name,
                expression,
                str(unit or ""),
                json.dumps(list(dict.fromkeys(str(value) for value in dependencies)), ensure_ascii=False),
                str(description).strip(),
                now,
                now,
            ),
        )
        row = con.execute(
            "SELECT * FROM user_derived_fields WHERE target_kind=? AND dataset_id=? AND name=?",
            (TARGET_DATASET, int(dataset_id), name),
        ).fetchone()
        con.commit()
    return _row_to_field(row)


def save_rock_project_field(
    project_id: int,
    *,
    name: str,
    expression: str,
    unit: str,
    dependencies: Iterable[str],
    description: str = "",
) -> DerivedField:
    ensure_user_derived_schema()
    name = _validate_field_name(name)
    expression = _validate_expression(expression)
    now = _utcnow()
    with connect() as con:
        if con.execute("SELECT 1 FROM projects WHERE id=?", (int(project_id),)).fetchone() is None:
            raise ValueError("Проект больше не существует")
        con.execute(
            """
            INSERT INTO user_derived_fields(
                target_kind, dataset_id, project_id, name, expression, unit,
                dependencies_json, description, enabled, created_at, updated_at
            ) VALUES (?, NULL, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(project_id, name) WHERE target_kind='rock_project' DO UPDATE SET
                expression=excluded.expression,
                unit=excluded.unit,
                dependencies_json=excluded.dependencies_json,
                description=excluded.description,
                enabled=1,
                updated_at=excluded.updated_at
            """,
            (
                TARGET_ROCK_PROJECT,
                int(project_id),
                name,
                expression,
                str(unit or ""),
                json.dumps(list(dict.fromkeys(str(value) for value in dependencies)), ensure_ascii=False),
                str(description).strip(),
                now,
                now,
            ),
        )
        row = con.execute(
            "SELECT * FROM user_derived_fields WHERE target_kind=? AND project_id=? AND name=?",
            (TARGET_ROCK_PROJECT, int(project_id), name),
        ).fetchone()
        con.commit()
    return _row_to_field(row)


def set_field_enabled(field_id: int, enabled: bool) -> None:
    ensure_user_derived_schema()
    with connect() as con:
        con.execute(
            "UPDATE user_derived_fields SET enabled=?, updated_at=? WHERE id=?",
            (1 if enabled else 0, _utcnow(), int(field_id)),
        )
        con.commit()


def delete_field(field_id: int) -> None:
    ensure_user_derived_schema()
    with connect() as con:
        con.execute("DELETE FROM user_derived_fields WHERE id=?", (int(field_id),))
        con.commit()


def _column_unit(dataframe: pd.DataFrame, column: str) -> str:
    derived_units = dataframe.attrs.get("derived_units", {})
    if isinstance(derived_units, dict) and column in derived_units:
        return str(derived_units[column] or "")
    if str(column).startswith("apfu_"):
        return "apfu"
    descriptor = describe_header(column)
    if descriptor.quantity_kind == "oxide":
        return descriptor.canonical_unit or descriptor.source_unit or "wt%"
    if descriptor.quantity_kind in {"trace_element", "element_concentration"}:
        return descriptor.canonical_unit or descriptor.source_unit
    return ""


def _base_analyte(column: str) -> str:
    text = str(column).strip()
    if " [" in text and text.endswith("]"):
        return text.split(" [", 1)[0]
    return text


def _resolve_column(dataframe: pd.DataFrame, reference: str) -> str:
    reference = str(reference).strip()
    if reference in dataframe.columns:
        return reference
    candidates = [
        str(column) for column in dataframe.columns
        if _base_analyte(str(column)).casefold() == reference.casefold()
    ]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        raise ValueError(
            f"Ссылка «{reference}» неоднозначна: " + ", ".join(candidates[:8])
            + ". Укажите точное имя колонки в обратных кавычках."
        )
    raise FormulaReferenceError(reference)


def _preprocess_backticks(expression: str) -> tuple[str, dict[str, str]]:
    mapping: dict[str, str] = {}

    def replace(match: re.Match) -> str:
        key = f"__petrolab_col_{len(mapping)}"
        mapping[key] = str(match.group(1)).strip()
        return key

    return _BACKTICK_RE.sub(replace, expression), mapping


def _combine_add_units(left: str, right: str) -> str:
    if left == right:
        return left
    if not left and not right:
        return ""
    if not left or not right:
        raise ValueError(
            "Нельзя надёжно сложить/вычесть величины, если единица одной из них неизвестна"
        )
    raise ValueError(f"Несовместимые единицы для сложения/вычитания: {left} и {right}")


def _combine_mul_units(left: str, right: str) -> str:
    if left in {"", _DIMENSIONLESS} and right in {"", _DIMENSIONLESS}:
        return "" if not left or not right else _DIMENSIONLESS
    if left == _DIMENSIONLESS:
        return right
    if right == _DIMENSIONLESS:
        return left
    if not left or not right:
        return ""
    return f"{left}·{right}"


def _combine_div_units(left: str, right: str) -> str:
    if left and right and left == right:
        return _DIMENSIONLESS
    if right == _DIMENSIONLESS:
        return left
    if left == _DIMENSIONLESS and right:
        return f"1/{right}"
    if not left or not right:
        return ""
    return f"{left}/{right}"


def _as_numeric_series(dataframe: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(dataframe[column], errors="coerce").astype(float)


def evaluate_expression(dataframe: pd.DataFrame, expression: str) -> ExpressionResult:
    expression = _validate_expression(expression)
    parsed_text, quoted = _preprocess_backticks(expression)
    try:
        tree = ast.parse(parsed_text, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Ошибка синтаксиса формулы: {exc.msg}") from exc

    dependencies: list[str] = []
    warnings: list[str] = []

    def evaluate(node: ast.AST) -> _NodeValue:
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise ValueError("В формулах разрешены только числовые константы")
            numeric = float(node.value)
            if not math.isfinite(numeric):
                raise ValueError("Числовые константы должны быть конечными")
            return _NodeValue(numeric, _DIMENSIONLESS)
        if isinstance(node, ast.Name):
            requested = quoted.get(node.id, node.id)
            column = _resolve_column(dataframe, requested)
            if str(column).startswith("_"):
                raise ValueError("Служебные identity-поля нельзя использовать как химические переменные")
            if column not in dependencies:
                dependencies.append(column)
            return _NodeValue(_as_numeric_series(dataframe, column), _column_unit(dataframe, column))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            inner = evaluate(node.operand)
            return _NodeValue(+inner.value if isinstance(node.op, ast.UAdd) else -inner.value, inner.unit)
        if isinstance(node, ast.BinOp):
            left = evaluate(node.left)
            right = evaluate(node.right)
            with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
                if isinstance(node.op, ast.Add):
                    unit = _combine_add_units(left.unit, right.unit)
                    value = left.value + right.value
                elif isinstance(node.op, ast.Sub):
                    unit = _combine_add_units(left.unit, right.unit)
                    value = left.value - right.value
                elif isinstance(node.op, ast.Mult):
                    unit = _combine_mul_units(left.unit, right.unit)
                    value = left.value * right.value
                elif isinstance(node.op, ast.Div):
                    unit = _combine_div_units(left.unit, right.unit)
                    value = left.value / right.value
                elif isinstance(node.op, ast.Pow):
                    if isinstance(right.value, pd.Series):
                        raise ValueError("Показатель степени должен быть числовой константой")
                    exponent = float(right.value)
                    if not math.isfinite(exponent) or abs(exponent) > 8:
                        raise ValueError("Недопустимый показатель степени")
                    if left.unit not in {"", _DIMENSIONLESS} and not exponent.is_integer():
                        raise ValueError("Дробная степень величины с единицей не поддерживается")
                    if left.unit in {"", _DIMENSIONLESS}:
                        unit = left.unit
                    elif exponent == 0:
                        unit = _DIMENSIONLESS
                    elif exponent == 1:
                        unit = left.unit
                    else:
                        unit = f"{left.unit}^{int(exponent)}"
                    value = left.value ** exponent
                else:
                    raise ValueError("Разрешены только +, −, ×, / и степень **")
            return _NodeValue(value, unit)
        raise ValueError("Формула содержит неподдерживаемую операцию")

    result = evaluate(tree)
    if isinstance(result.value, pd.Series):
        values = pd.to_numeric(result.value, errors="coerce").astype(float)
    else:
        values = pd.Series(float(result.value), index=dataframe.index, dtype=float)
    finite = np.isfinite(values.to_numpy(dtype=float, na_value=np.nan))
    nonfinite = pd.Series(~finite, index=values.index)
    invalid_count = int(nonfinite.sum())
    values = values.where(~nonfinite, np.nan)
    if invalid_count:
        warnings.append(
            f"{invalid_count} строк оставлены пустыми из-за пропусков, деления на ноль или нечисловых значений."
        )
    if not result.unit:
        warnings.append("Единицу результата нельзя вывести однозначно; она сохранена как неизвестная.")
    return ExpressionResult(
        values=values,
        unit=result.unit,
        dependencies=tuple(dependencies),
        warnings=tuple(dict.fromkeys(warnings)),
    )


def _apply_fields(dataframe: pd.DataFrame, fields: Iterable[DerivedField]) -> pd.DataFrame:
    work = dataframe.copy()
    inherited_units = dict(dataframe.attrs.get("derived_units", {}) or {})
    warnings: list[str] = list(dataframe.attrs.get("user_derived_warnings", []) or [])
    definitions = [field for field in fields if field.enabled]
    pending = list(definitions)
    formula_names = {field.name for field in definitions}

    while pending:
        progress = False
        next_pending: list[DerivedField] = []
        for field in pending:
            try:
                result = evaluate_expression(work, field.expression)
            except FormulaReferenceError as exc:
                if exc.reference in formula_names and exc.reference not in work.columns:
                    next_pending.append(field)
                    continue
                work[field.name] = np.nan
                warnings.append(f"{field.name}: {exc}")
                inherited_units[field.name] = field.unit
                progress = True
                continue
            except ValueError as exc:
                work[field.name] = np.nan
                warnings.append(f"{field.name}: {exc}")
                inherited_units[field.name] = field.unit
                progress = True
                continue
            work[field.name] = result.values
            inherited_units[field.name] = result.unit or field.unit
            if field.unit and result.unit and field.unit != result.unit:
                warnings.append(
                    f"{field.name}: текущая единица {result.unit} отличается от сохранённой {field.unit}."
                )
            warnings.extend(f"{field.name}: {warning}" for warning in result.warnings)
            progress = True
        if not next_pending:
            break
        if not progress:
            for field in next_pending:
                work[field.name] = np.nan
                inherited_units[field.name] = field.unit
                warnings.append(
                    f"{field.name}: циклическая зависимость или ссылка на вычисляемое поле, которое не удалось рассчитать."
                )
            break
        pending = next_pending

    work.attrs.update(dataframe.attrs)
    work.attrs["derived_units"] = inherited_units
    work.attrs["user_derived_fields"] = {
        field.name: {
            "id": field.id,
            "expression": field.expression,
            "unit": inherited_units.get(field.name, field.unit),
            "dependencies": list(field.dependencies),
            "updated_at": field.updated_at,
        }
        for field in definitions
    }
    work.attrs["user_derived_warnings"] = list(dict.fromkeys(warnings))
    return work


def apply_dataset_fields(dataframe: pd.DataFrame, dataset_id: int) -> pd.DataFrame:
    if dataframe.empty:
        return dataframe.copy()
    return _apply_fields(dataframe, list_dataset_fields(int(dataset_id), include_disabled=False))


def apply_rock_project_fields(dataframe: pd.DataFrame, project_id: int) -> pd.DataFrame:
    if dataframe.empty:
        return dataframe.copy()
    return _apply_fields(dataframe, list_rock_project_fields(int(project_id), include_disabled=False))
