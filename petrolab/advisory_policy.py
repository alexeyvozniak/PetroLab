"""Unified rule for scientific workflows: show limits, do not hide results."""

from __future__ import annotations

ADVISORY_POLICY_ID = "advisory-first-v1"

# Warnings are part of the scientific record, not a permission gate.
ADVISORY_RULES = (
    "Показывать результат вместе с причиной, областью применимости и допущениями.",
    "Не скрывать точки, модели, коэффициенты или расчёты из-за QC-предупреждения.",
    "Сохранять предупреждения и пользовательские допущения в provenance/журнале расчёта.",
    "Не подменять отсутствующие или математически невозможные значения выдуманными числами.",
)

# These are not scientific disagreements and cannot produce a valid saved result.
TECHNICAL_LIMITS = (
    "не читается файл или отсутствует обязательная структура данных",
    "не хватает числовых входов для конкретной формулы",
    "математический результат не определён",
    "не подтверждено удаление данных",
)
