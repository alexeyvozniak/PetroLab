from __future__ import annotations

from dataclasses import dataclass

from petrolab.analytical_sessions import ensure_session_schema
from petrolab.db import connect, list_accessible_datasets
from petrolab.derived import formula_status
from petrolab.source_registry import database_health


@dataclass(frozen=True)
class ProjectHealthIssue:
    kind: str
    severity: str
    title: str
    detail: str
    count: int
    route: str
    dataset_id: int | None = None
    optional: bool = False


def project_health(project_id: int) -> dict:
    """Return only actionable project-local work, never a blocking validity score.

    Data Health is guidance. Missing Generation or literature metadata is useful to
    know about but does not make chemistry invalid or block plots.
    """
    ensure_session_schema()
    datasets = list_accessible_datasets(int(project_id))
    issues: list[ProjectHealthIssue] = []

    mixed_rows = 0
    generic_rows = 0
    stale_rows = 0
    for dataset in datasets:
        dataset_id = int(dataset["id"])
        rows = int(dataset.get("row_count") or 0)
        name = str(dataset.get("name") or "").casefold()
        mineral = str(dataset.get("mineral_key") or "generic")
        resolved_raw = "исходный mixed (разобрано)" in name
        is_mixed = rows > 0 and ("неразобран" in name or "mixed" in name or (mineral == "generic" and not resolved_raw))
        if is_mixed:
            mixed_rows += rows
        elif rows > 0 and mineral == "generic":
            generic_rows += rows
        status = formula_status(dataset_id)
        stale_rows += int(status.stale_rows)

    if mixed_rows:
        issues.append(ProjectHealthIssue(
            "mixed", "warning", "Неразобранные фазы / mixed",
            "Точки сохранены и доступны; PetroLab ждёт вашего минералогического решения.",
            mixed_rows, "mixed_minerals",
        ))
    if generic_rows:
        issues.append(ProjectHealthIssue(
            "generic_phase", "info", "Фазы без специализированного расчётного модуля",
            "Это допустимо для редких фаз. Проверьте только если ожидался известный минерал.",
            generic_rows, "analyses", optional=True,
        ))
    if stale_rows:
        issues.append(ProjectHealthIssue(
            "stale_formula", "warning", "Формулы требуют пересчёта",
            "Исходная химия изменилась после расчёта; старые derived-значения не считаются актуальными.",
            stale_rows, "formulae",
        ))

    dataset_ids = [int(item["id"]) for item in datasets]
    no_session_count = 0
    if dataset_ids:
        marks = ",".join("?" for _ in dataset_ids)
        with connect() as con:
            linked = {
                int(row["dataset_id"])
                for row in con.execute(
                    f"""SELECT DISTINCT sd.dataset_id
                        FROM analytical_session_datasets sd
                        JOIN analytical_sessions s ON s.id=sd.session_id
                        WHERE s.project_id=? AND sd.dataset_id IN ({marks})""",
                    [int(project_id), *dataset_ids],
                ).fetchall()
            }
        no_session_count = sum(int(item.get("row_count") or 0) for item in datasets if int(item["id"]) not in linked)
    if no_session_count:
        issues.append(ProjectHealthIssue(
            "no_session", "warning", "Анализы без canonical Sample / аналитической сессии",
            "Химия не теряется, но физический контекст и связь EPMA↔LA будут неполными.",
            no_session_count, "sessions",
        ))

    base = database_health(int(project_id))
    route_by_kind = {
        "sample_duplicate": "database",
        "semantic_unresolved": "intake",
        "study_metadata": "intake",
        "unlinked_source": "intake",
        "analysis_without_sample": "sessions",
    }
    # `analysis_without_sample` from the older health service relies on legacy dataset.sample_id;
    # the project-local session check above is the authoritative current model, so avoid double counting it.
    for issue in base["issues"]:
        if issue.kind == "analysis_without_sample":
            continue
        issues.append(ProjectHealthIssue(
            issue.kind, issue.severity, issue.title, issue.detail, int(issue.count),
            route_by_kind.get(issue.kind, "database"),
            optional=issue.severity == "info",
        ))

    required = [item for item in issues if not item.optional]
    optional = [item for item in issues if item.optional]
    required_units = sum(min(int(item.count), 50) for item in required)
    score = max(0, 100 - min(80, required_units))
    return {
        "score": score,
        "issues": issues,
        "required": required,
        "optional": optional,
        "required_count": len(required),
        "optional_count": len(optional),
    }
