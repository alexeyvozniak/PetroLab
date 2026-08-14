from __future__ import annotations

"""Build the GEOROC holdout through stable file-level persistent identifiers.

The dataset-level GRO Dataverse endpoint intermittently returns HTTP 500. GEOROC publishes
stable file DOIs for every mineral CSV, so release validation must not depend on that metadata
endpoint being healthy. This adapter keeps the same sampling/QC logic as the v1 builder while
recording each file DOI explicitly in the manifest.
"""

import argparse
import hashlib
import json
from pathlib import Path
import time

import pandas as pd
import requests

from build_georoc_mineral_validation import _sample_file, _sha256


DATASET_DOI = "doi:10.25625/SGFTFN"
DATAVERSE = "https://data.goettingen-research-online.de"
ACCESS_PERSISTENT = f"{DATAVERSE}/api/access/datafile/:persistentId/"
CORPUS_SCHEMA_VERSION = "2"

# File-level persistent IDs are exposed by the official GEOROC compilation page.
FILES = (
    ("APATITES", "apatite", "2024-12-SGFTFN_APATITES.csv", "doi:10.25625/SGFTFN/7CYN6P"),
    ("CARBONATES", "carbonate", "2024-12-SGFTFN_CARBONATES.csv", "doi:10.25625/SGFTFN/ZLEUVH"),
    ("FELDSPATHOIDES", "feldspathoid", "2024-12-SGFTFN_FELDSPATHOIDES.csv", "doi:10.25625/SGFTFN/SVBJ7F"),
    ("GARNETS", "garnet", "2024-12-SGFTFN_GARNETS.csv", "doi:10.25625/SGFTFN/YRWA7J"),
    ("ILMENITES", "oxide", "2024-12-SGFTFN_ILMENITES.csv", "doi:10.25625/SGFTFN/11MQXF"),
    ("MICA", "mica", "2024-12-SGFTFN_MICA.csv", "doi:10.25625/SGFTFN/PKXZKM"),
    ("PEROVSKITES", "oxide", "2024-12-SGFTFN_PEROVSKITES.csv", "doi:10.25625/SGFTFN/JFSEFH"),
    ("QUARTZ", "silica", "2024-12-SGFTFN_QUARTZ.csv", "doi:10.25625/SGFTFN/NJDWC5"),
    ("TITANITES", "accessory", "2024-12-SGFTFN_TITANITES.csv", "doi:10.25625/SGFTFN/S9HSLL"),
)


def _stable_seed(token: str, base_seed: int) -> int:
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    return base_seed + int.from_bytes(digest[:4], "big")


def _download_persistent(persistent_id: str, destination: Path) -> None:
    if destination.exists() and destination.stat().st_size > 0:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    for attempt in range(1, 5):
        try:
            with requests.get(
                ACCESS_PERSISTENT,
                params={"persistentId": persistent_id},
                stream=True,
                timeout=(30, 300),
                headers={"User-Agent": "PetroLab-mineral-validation/1.0"},
            ) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").lower()
                if "text/html" in content_type:
                    raise RuntimeError(f"Unexpected HTML response for {persistent_id}")
                with destination.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            handle.write(chunk)
                if destination.stat().st_size == 0:
                    raise RuntimeError(f"Empty response for {persistent_id}")
                return
        except Exception as exc:
            last_error = exc
            if destination.exists():
                destination.unlink()
            if attempt < 4:
                time.sleep(2 ** (attempt - 1))
    raise RuntimeError(f"Unable to download {persistent_id} after retries") from last_error


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="validation/mineral_recognition/georoc_holdout.csv")
    parser.add_argument("--cache", default=".cache/georoc-minerals")
    parser.add_argument("--per-family", type=int, default=400)
    parser.add_argument("--seed", type=int, default=20260814)
    args = parser.parse_args()

    output = Path(args.output)
    cache = Path(args.cache)
    frames: list[pd.DataFrame] = []
    manifest_files: list[dict] = []

    for token, truth_family, filename, persistent_id in FILES:
        path = cache / filename
        print(f"Downloading/reading {filename} via {persistent_id} …", flush=True)
        _download_persistent(persistent_id, path)
        sample, stats = _sample_file(
            path,
            source_token=token,
            truth_family=truth_family,
            per_family=args.per_family,
            seed=_stable_seed(token, args.seed),
        )
        if sample.empty:
            raise RuntimeError(f"No usable rows from {filename}")
        frames.append(sample)
        manifest_files.append({
            "filename": filename,
            "persistent_id": persistent_id,
            "size": path.stat().st_size,
            "sha256": _sha256(path),
            "truth_family": truth_family,
            **stats,
        })

    corpus = pd.concat(frames, ignore_index=True)
    corpus = corpus.sample(frac=1.0, random_state=args.seed).reset_index(drop=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    corpus.to_csv(output, index=False)

    manifest = {
        "schema_version": CORPUS_SCHEMA_VERSION,
        "dataset": "GEOROC Compilation: Minerals",
        "persistent_id": DATASET_DOI,
        "version": "10.0",
        "production_date": "2024-12-01",
        "license": "CC BY-SA 4.0",
        "citation": "DIGIS Team, 2024, GEOROC Compilation: Minerals, GRO.data, V10, doi:10.25625/SGFTFN",
        "seed": args.seed,
        "requested_per_family": args.per_family,
        "rows": len(corpus),
        "files": manifest_files,
        "note": (
            "External family-level holdout built from stable GEOROC file DOIs. Where an analytical-method "
            "column exists, only EPMA/EMPA/electron-probe/WDS rows are retained; otherwise the rows remain "
            "family-labeled chemistry benchmarks and are not described as EPMA-only."
        ),
    }
    manifest_path = output.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(corpus)} rows to {output}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
