from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from petrolab.mineral_recognition import recognize_mineral
from petrolab.mineral_recognition_extended import EXTENDED_RULESET_VERSION, recognize_mineral_extended
from scripts.validate_georoc_mineral_recognition import UNKNOWN, _predicted_class


def _metrics(corpus: pd.DataFrame, recognizer) -> tuple[dict[str, float | int], pd.DataFrame]:
    truth = corpus["source_family"].astype(str).reset_index(drop=True)
    results = [recognizer(row) for row in corpus.to_dict(orient="records")]
    target = pd.Series([item.target for item in results])
    predicted = pd.Series([
        _predicted_class(item_target, truth_class)
        for item_target, truth_class in zip(target, truth, strict=True)
    ])
    confidence = pd.Series([item.confidence for item in results])

    known = predicted.ne(UNKNOWN)
    correct = predicted.eq(truth)
    high = confidence.eq("high")
    per_class_f1: list[tuple[float, int]] = []
    for label in sorted(set(truth)):
        actual = truth.eq(label)
        guessed = predicted.eq(label)
        tp = int((actual & guessed).sum())
        fp = int((~actual & guessed).sum())
        fn = int((actual & ~guessed).sum())
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        per_class_f1.append((f1, int(actual.sum())))
    total_support = sum(support for _, support in per_class_f1)
    weighted_f1 = sum(f1 * support for f1, support in per_class_f1) / total_support

    metrics = {
        "rows": int(len(corpus)),
        "coverage": float(known.mean()),
        "weighted_f1": float(weighted_f1),
        "high_count": int(high.sum()),
        "high_precision": float(correct[high].mean()) if high.any() else 1.0,
        "high_wrong": int((high & ~correct).sum()),
    }
    details = pd.DataFrame({
        "truth": truth,
        "target": target,
        "predicted_class": predicted,
        "confidence": confidence,
        "correct": correct,
    })
    return metrics, details


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus")
    parser.add_argument("--output-dir", default="validation/mineral_recognition/alkaline_nonregression")
    parser.add_argument("--minimum-rows", type=int, default=3000)
    parser.add_argument("--max-f1-drop", type=float, default=0.005)
    parser.add_argument("--max-high-precision-drop", type=float, default=0.005)
    parser.add_argument("--max-coverage-drop", type=float, default=0.01)
    args = parser.parse_args()

    corpus = pd.read_csv(args.corpus, low_memory=False)
    if len(corpus) < args.minimum_rows:
        raise AssertionError(f"External holdout too small: {len(corpus)} < {args.minimum_rows}")
    if "source_family" not in corpus:
        raise ValueError("GEOROC holdout lacks source_family")

    base, base_details = _metrics(corpus, recognize_mineral)
    extended, extended_details = _metrics(corpus, recognize_mineral_extended)
    comparison = {
        "ruleset": EXTENDED_RULESET_VERSION,
        "base": base,
        "extended": extended,
        "delta": {
            "weighted_f1": extended["weighted_f1"] - base["weighted_f1"],
            "high_precision": extended["high_precision"] - base["high_precision"],
            "coverage": extended["coverage"] - base["coverage"],
            "high_wrong": extended["high_wrong"] - base["high_wrong"],
        },
        "interpretation": (
            "This is a do-no-harm benchmark on the published 15-family GEOROC/MIST holdout. "
            "It does not claim external validation of alkaline-specific targets absent from those families."
        ),
    }

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "comparison.json").write_text(json.dumps(comparison, indent=2, ensure_ascii=False), encoding="utf-8")
    base_details.add_prefix("base_").to_csv(output / "base_predictions.csv", index=False)
    extended_details.add_prefix("extended_").to_csv(output / "extended_predictions.csv", index=False)

    if comparison["delta"]["weighted_f1"] < -args.max_f1_drop:
        raise AssertionError(f"Extended weighted F1 regressed: {comparison['delta']['weighted_f1']:.6f}")
    if comparison["delta"]["high_precision"] < -args.max_high_precision_drop:
        raise AssertionError(
            f"Extended high-confidence precision regressed: {comparison['delta']['high_precision']:.6f}"
        )
    if comparison["delta"]["coverage"] < -args.max_coverage_drop:
        raise AssertionError(f"Extended coverage regressed: {comparison['delta']['coverage']:.6f}")

    print(json.dumps(comparison, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
