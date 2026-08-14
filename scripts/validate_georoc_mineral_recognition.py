from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support

from petrolab.mineral_recognition import MINERAL_RECOGNITION_RULESET_VERSION, recognize_mineral
from petrolab.mineral_reference import MINERALS


UNKNOWN = "__unknown__"

# Map conservative PetroLab chemical targets back to the independent GEOROC compilation buckets.
# This is deliberately a family/class benchmark, not an IMA species-accuracy claim.
TARGET_TO_GEOROC_CLASS = {
    "calcic amphibole": "AMPHIBOLES",
    "Ti-rich calcic amphibole": "AMPHIBOLES",
    "sodic amphibole": "AMPHIBOLES",
    "sodic-calcic amphibole": "AMPHIBOLES",
    "apatite": "APATITES",
    "Ca-carbonate": "CARBONATES",
    "Ca-Mg carbonate": "CARBONATES",
    "Ca-Fe-Mg carbonate": "CARBONATES",
    "Mg-carbonate": "CARBONATES",
    "Fe-carbonate": "CARBONATES",
    "Mn-carbonate": "CARBONATES",
    "Sr-carbonate": "CARBONATES",
    "REE-fluorocarbonate": "CARBONATES",
    "clinopyroxene": "CLINOPYROXENES",
    "Na-Ca clinopyroxene": "CLINOPYROXENES",
    "Na-clinopyroxene": "CLINOPYROXENES",
    "K-feldspar": "FELDSPARS",
    "plagioclase": "FELDSPARS",
    "nepheline": "FELDSPATHOIDES",
    "kalsilite": "FELDSPATHOIDES",
    "leucite": "FELDSPATHOIDES",
    "sodalite-group": "FELDSPATHOIDES",
    "cancrinite-group": "FELDSPATHOIDES",
    "analcime": "FELDSPATHOIDES",
    "garnet": "GARNETS",
    "Ti-rich garnet": "GARNETS",
    "Fe-Ti oxide": "ILMENITES",
    "trioctahedral mica": "MICA",
    "dioctahedral mica": "MICA",
    "Li-mica": "MICA",
    "olivine": "OLIVINES",
    "orthopyroxene": "ORTHOPYROXENES",
    "low-Ca pyroxene": "PYROXENES",
    "silica": "QUARTZ",
    "Cr-spinel": "SPINELS",
    "spinel-group oxide": "SPINELS",
    "zircon": "ZIRCONS",
}

# General pyroxene compilation may include cpx/opx and intermediate-Ca members. When the truth
# bucket is PYROXENES, any pyroxene-family chemical target is accepted in a second-pass scoring
# step rather than pretending GEOROC's broad bucket is a unique species.
PYROXENE_TARGETS = {
    "clinopyroxene", "Na-Ca clinopyroxene", "Na-clinopyroxene",
    "orthopyroxene", "low-Ca pyroxene",
}

# GEOROC compilation buckets are not pure species labels. The published files can contain, for
# example, RUTILE rows inside the ILMENITES compilation. Where GEOROC supplies a mineral name that
# exactly matches PetroLab's reference catalogue, report an independent chemical-target metric in
# addition to bucket-level metrics. Neither metric silently replaces the other.
REFERENCE_NAME_TO_TARGET = {item.name.upper(): item.chemical_target for item in MINERALS}
GENERIC_SOURCE_NAME_TO_TARGET = {
    "AMPHIBOLE": "calcic amphibole",
    "CLINOPYROXENE": "clinopyroxene",
    "ORTHOPYROXENE": "orthopyroxene",
}
REFERENCE_NAME_TO_TARGET.update(GENERIC_SOURCE_NAME_TO_TARGET)


def _predicted_class(target: str, truth_class: str) -> str:
    if truth_class == "PYROXENES" and target in PYROXENE_TARGETS:
        return "PYROXENES"
    return TARGET_TO_GEOROC_CLASS.get(target, UNKNOWN)


def _source_target(value: object) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip().upper()
    return REFERENCE_NAME_TO_TARGET.get(text)


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
    truth = corpus["source_family"].astype(str).reset_index(drop=True)
    predicted_target = pd.Series([item.target for item in results])
    predicted_class = pd.Series([
        _predicted_class(target, truth_class)
        for target, truth_class in zip(predicted_target, truth, strict=True)
    ])
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
    weighted_f1 = float((supported["f1"] * supported["support"]).sum() / supported["support"].sum())
    coverage = float((predicted_class != UNKNOWN).mean())
    high = confidence.eq("high")
    high_precision = float((predicted_class[high].to_numpy() == truth[high].to_numpy()).mean()) if high.any() else 1.0
    high_wrong = int(((predicted_class != truth) & high).sum())

    if "source_mineral_name" in corpus:
        source_target = corpus["source_mineral_name"].map(_source_target)
    else:
        source_target = pd.Series([None] * len(corpus), dtype=object)
    source_named = source_target.notna()
    high_source_named = high & source_named
    source_target_precision = (
        float((predicted_target[source_named].to_numpy() == source_target[source_named].to_numpy()).mean())
        if source_named.any() else None
    )
    high_source_target_precision = (
        float((predicted_target[high_source_named].to_numpy() == source_target[high_source_named].to_numpy()).mean())
        if high_source_named.any() else None
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    matrix.to_csv(output_dir / "confusion_matrix.csv")
    per_class.to_csv(output_dir / "per_class_metrics.csv")
    details = corpus[[column for column in ["validation_id", "source_family", "source_mineral_name", "source_reference"] if column in corpus]].copy()
    details["source_target"] = source_target
    details["predicted_target"] = predicted_target
    details["predicted_class"] = predicted_class
    details["confidence"] = confidence
    details["bucket_correct"] = predicted_class.to_numpy() == truth.to_numpy()
    details["source_target_correct"] = pd.Series(
        [None if expected is None else predicted == expected for predicted, expected in zip(predicted_target, source_target, strict=True)],
        dtype="boolean",
    )
    details.to_csv(output_dir / "predictions.csv", index=False)
    summary = {
        "ruleset_version": MINERAL_RECOGNITION_RULESET_VERSION,
        "rows": len(corpus),
        "classes": labels,
        "macro_f1": macro_f1,
        "weighted_f1": weighted_f1,
        "coverage": coverage,
        "bucket_high_confidence_precision": high_precision,
        "bucket_high_confidence_count": int(high.sum()),
        "bucket_high_confidence_wrong_count": high_wrong,
        "source_name_target_rows": int(source_named.sum()),
        "source_name_target_precision": source_target_precision,
        "source_name_high_confidence_rows": int(high_source_named.sum()),
        "source_name_high_confidence_precision": high_source_target_precision,
        "unknown_count": int((predicted_class == UNKNOWN).sum()),
        "note": (
            "Bucket metrics score the published GEOROC compilation classes. Source-name metrics score "
            "only rows whose supplied mineral name maps exactly to PetroLab's conservative chemical "
            "reference target. The two metrics are kept separate because GEOROC compilation buckets "
            "are not species-pure and some historical rows can be internally inconsistent. Neither is "
            "an IMA species-accuracy claim."
        ),
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
