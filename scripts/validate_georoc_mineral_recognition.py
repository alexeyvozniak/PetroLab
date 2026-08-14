from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support

from petrolab.mineral_recognition import MINERAL_RECOGNITION_RULESET_VERSION, recognize_mineral


UNKNOWN = "__unknown__"

# Map conservative chemical targets back to the independent GEOROC compilation buckets used in
# the external holdout. This is a family/class benchmark; species-level scoring is only valid when
# the source provides an independently curated species label that can be mapped safely.
TARGET_TO_GEOROC_CLASS = {
    "apatite": "APATITES",
    "Ca-carbonate": "CARBONATES",
    "Ca-Mg carbonate": "CARBONATES",
    "Ca-Fe-Mg carbonate": "CARBONATES",
    "Mg-carbonate": "CARBONATES",
    "Fe-carbonate": "CARBONATES",
    "Mn-carbonate": "CARBONATES",
    "Sr-carbonate": "CARBONATES",
    "REE-fluorocarbonate": "CARBONATES",
    "nepheline": "FELDSPATHOIDES",
    "kalsilite": "FELDSPATHOIDES",
    "leucite": "FELDSPATHOIDES",
    "sodalite-group": "FELDSPATHOIDES",
    "cancrinite-group": "FELDSPATHOIDES",
    "garnet": "GARNETS",
    "Ti-rich garnet": "GARNETS",
    "Fe-Ti oxide": "ILMENITES",
    "trioctahedral mica": "MICA",
    "dioctahedral mica": "MICA",
    "Li-mica": "MICA",
    "perovskite": "PEROVSKITES",
    "silica": "QUARTZ",
    "titanite": "TITANITES",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus")
    parser.add_argument("--output-dir", default="validation/mineral_recognition/report")
    parser.add_argument("--minimum-rows", type=int, default=3000)
    args = parser.parse_args()

    corpus = pd.read_csv(args.corpus, low_memory=False)
    if len(corpus) < args.minimum_rows:
        raise AssertionError(f"External holdout too small: {len(corpus)} < {args.minimum_rows}")
    if "source_family" not in corpus:
        raise ValueError("GEOROC holdout lacks source_family")

    results = [recognize_mineral(row) for row in corpus.to_dict(orient="records")]
    truth = corpus["source_family"].astype(str)
    predicted_target = pd.Series([item.target for item in results])
    predicted_class = predicted_target.map(TARGET_TO_GEOROC_CLASS).fillna(UNKNOWN)
    confidence = pd.Series([item.confidence for item in results])

    labels = sorted(set(truth) | set(predicted_class))
    matrix = pd.DataFrame(
        confusion_matrix(truth, predicted_class, labels=labels),
        index=labels,
        columns=labels,
    )
    precision, recall, f1, support = precision_recall_fscore_support(
        truth, predicted_class, labels=labels, zero_division=0
    )
    per_class = pd.DataFrame(
        {"precision": precision, "recall": recall, "f1": f1, "support": support},
        index=labels,
    )
    supported = per_class[per_class["support"] > 0]
    macro_f1 = float(supported["f1"].mean())
    coverage = float((predicted_class != UNKNOWN).mean())
    high = confidence.eq("high")
    high_precision = float((predicted_class[high].to_numpy() == truth[high].to_numpy()).mean()) if high.any() else 1.0

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    matrix.to_csv(output_dir / "confusion_matrix.csv")
    per_class.to_csv(output_dir / "per_class_metrics.csv")
    details = corpus[[column for column in ["validation_id", "source_family", "source_mineral_name", "source_reference"] if column in corpus]].copy()
    details["predicted_target"] = predicted_target
    details["predicted_class"] = predicted_class
    details["confidence"] = confidence
    details["correct"] = predicted_class.to_numpy() == truth.to_numpy()
    details.to_csv(output_dir / "predictions.csv", index=False)
    summary = {
        "ruleset_version": MINERAL_RECOGNITION_RULESET_VERSION,
        "rows": len(corpus),
        "classes": labels,
        "macro_f1": macro_f1,
        "coverage": coverage,
        "high_confidence_precision": high_precision,
        "high_confidence_count": int(high.sum()),
        "unknown_count": int((predicted_class == UNKNOWN).sum()),
        "note": (
            "This confusion matrix scores independent GEOROC compilation classes. It is not an IMA "
            "species-accuracy claim. Species-level validation must use independently curated species "
            "labels and exclude chemistry-indistinguishable polymorphs."
        ),
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
