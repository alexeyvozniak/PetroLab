from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support

from petrolab.mineral_recognition import recognize_mineral


UNKNOWN_LABEL = "__unknown__"


@dataclass(frozen=True)
class ValidationReport:
    ruleset_version: str
    n_rows: int
    labels: tuple[str, ...]
    confusion: pd.DataFrame
    per_class: pd.DataFrame
    macro_f1: float
    weighted_f1: float
    coverage: float
    high_confidence_precision: float
    high_confidence_wrong_rate: float


def evaluate_labeled_corpus(
    dataframe: pd.DataFrame,
    *,
    truth_column: str = "truth_target",
    family_column: str | None = None,
) -> ValidationReport:
    if truth_column not in dataframe.columns:
        raise ValueError(f"Missing truth column: {truth_column}")
    rows = dataframe.copy()
    truth = rows[truth_column].astype(str).str.strip()
    if (truth == "").any():
        raise ValueError("Truth labels must be non-empty")

    results = [recognize_mineral(row) for row in rows.to_dict(orient="records")]
    predicted = pd.Series([item.target if item.target else UNKNOWN_LABEL for item in results], index=rows.index)
    confidences = pd.Series([item.confidence for item in results], index=rows.index)
    rulesets = {item.ruleset_version for item in results}
    if len(rulesets) != 1:
        raise AssertionError("A validation run must use exactly one ruleset version")
    ruleset_version = next(iter(rulesets))

    labels = tuple(sorted(set(truth) | set(predicted)))
    matrix = confusion_matrix(truth, predicted, labels=list(labels))
    confusion = pd.DataFrame(matrix, index=labels, columns=labels)
    precision, recall, f1, support = precision_recall_fscore_support(
        truth,
        predicted,
        labels=list(labels),
        zero_division=0,
    )
    per_class = pd.DataFrame(
        {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": support,
        },
        index=labels,
    )
    supported = per_class[per_class["support"] > 0]
    macro_f1 = float(supported["f1"].mean()) if not supported.empty else 0.0
    weighted_f1 = float(np.average(supported["f1"], weights=supported["support"])) if not supported.empty else 0.0
    coverage = float((predicted != UNKNOWN_LABEL).mean()) if len(rows) else 0.0

    high = confidences == "high"
    if bool(high.any()):
        high_correct = predicted[high].to_numpy() == truth[high].to_numpy()
        high_precision = float(np.mean(high_correct))
        high_wrong = float(1.0 - high_precision)
    else:
        high_precision = 1.0
        high_wrong = 0.0

    report = ValidationReport(
        ruleset_version=ruleset_version,
        n_rows=len(rows),
        labels=labels,
        confusion=confusion,
        per_class=per_class,
        macro_f1=macro_f1,
        weighted_f1=weighted_f1,
        coverage=coverage,
        high_confidence_precision=high_precision,
        high_confidence_wrong_rate=high_wrong,
    )
    if family_column and family_column in rows.columns:
        # Validate caller's corpus schema early; family-level reporting is generated separately.
        if rows[family_column].astype(str).str.strip().eq("").any():
            raise ValueError("Family labels must be non-empty when supplied")
    return report


def family_confusion(
    truth_targets: Iterable[str],
    predicted_targets: Iterable[str],
    target_to_family: dict[str, str],
) -> pd.DataFrame:
    truth_family = [target_to_family.get(str(item), UNKNOWN_LABEL) for item in truth_targets]
    pred_family = [target_to_family.get(str(item), UNKNOWN_LABEL) for item in predicted_targets]
    labels = sorted(set(truth_family) | set(pred_family))
    matrix = confusion_matrix(truth_family, pred_family, labels=labels)
    return pd.DataFrame(matrix, index=labels, columns=labels)


def assert_release_gate(
    report: ValidationReport,
    *,
    minimum_rows: int = 3000,
    minimum_high_confidence_precision: float = 0.95,
    maximum_high_confidence_wrong_rate: float = 0.05,
    minimum_coverage: float = 0.55,
) -> None:
    """Conservative release gate: confident wrong answers are penalized more than abstention."""
    failures: list[str] = []
    if report.n_rows < minimum_rows:
        failures.append(f"validation corpus too small: {report.n_rows} < {minimum_rows}")
    if report.high_confidence_precision < minimum_high_confidence_precision:
        failures.append(
            "high-confidence precision too low: "
            f"{report.high_confidence_precision:.3f} < {minimum_high_confidence_precision:.3f}"
        )
    if report.high_confidence_wrong_rate > maximum_high_confidence_wrong_rate:
        failures.append(
            "high-confidence wrong rate too high: "
            f"{report.high_confidence_wrong_rate:.3f} > {maximum_high_confidence_wrong_rate:.3f}"
        )
    if report.coverage < minimum_coverage:
        failures.append(f"coverage too low: {report.coverage:.3f} < {minimum_coverage:.3f}")
    if failures:
        raise AssertionError("; ".join(failures))


def report_tables(report: ValidationReport) -> dict[str, pd.DataFrame]:
    summary = pd.DataFrame(
        [
            {
                "ruleset_version": report.ruleset_version,
                "n_rows": report.n_rows,
                "macro_f1": report.macro_f1,
                "weighted_f1": report.weighted_f1,
                "coverage": report.coverage,
                "high_confidence_precision": report.high_confidence_precision,
                "high_confidence_wrong_rate": report.high_confidence_wrong_rate,
            }
        ]
    )
    return {"summary": summary, "per_class": report.per_class, "confusion": report.confusion}
