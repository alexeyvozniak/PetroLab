from __future__ import annotations

"""Build a reproducible external validation corpus from GEOROC mineral compilations.

This script is intentionally NOT part of normal PetroLab startup or unit tests. It downloads
published external data and creates a compact holdout CSV + provenance manifest. Run it when
releasing a new mineral-recognition ruleset.

Source: DIGIS Team (2024), GEOROC Compilation: Minerals, V10,
doi:10.25625/SGFTFN, CC BY-SA 4.0; files generated 2024-12-01.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Iterable

import numpy as np
import pandas as pd
import requests


DATASET_DOI = "doi:10.25625/SGFTFN"
DATAVERSE = "https://data.goettingen-research-online.de"
DATASET_API = f"{DATAVERSE}/api/datasets/:persistentId/"
ACCESS_API = f"{DATAVERSE}/api/access/datafile"
CORPUS_SCHEMA_VERSION = "1"

# A deliberately moderate download set gives >3,000 holdout rows without pulling the 2.4-GB
# complete compilation. The files cover very different chemistries and are useful for detecting
# dangerous cross-family false positives.
SELECTED_FAMILIES = {
    "APATITES": "apatite",
    "CARBONATES": "carbonate",
    "FELDSPATHOIDES": "feldspathoid",
    "GARNETS": "garnet",
    "ILMENITES": "oxide",
    "MICA": "mica",
    "PEROVSKITES": "oxide",
    "QUARTZ": "silica",
    "TITANITES": "accessory",
}

OXIDE_ALIASES = {
    "SIO2": "SiO2", "TIO2": "TiO2", "AL2O3": "Al2O3", "CR2O3": "Cr2O3",
    "FEOT": "FeOt", "FEO": "FeO", "FE2O3T": "Fe2O3t", "FE2O3": "Fe2O3",
    "MNO": "MnO", "MGO": "MgO", "CAO": "CaO", "NA2O": "Na2O", "K2O": "K2O",
    "P2O5": "P2O5", "ZRO2": "ZrO2", "Y2O3": "Y2O3", "SRO": "SrO", "BAO": "BaO",
    "SO3": "SO3", "F": "F", "CL": "Cl", "B2O3": "B2O3",
    "LA2O3": "La2O3", "CE2O3": "Ce2O3", "CEO2": "CeO2", "ND2O3": "Nd2O3",
}

METHOD_COLUMNS = (
    "METHOD", "ANALYTICAL METHOD", "ANALYTICAL_METHOD", "METHOD NAME", "METHOD_NAME",
    "TECHNIQUE", "ANALYSIS METHOD", "ANALYSIS_METHOD",
)
MINERAL_COLUMNS = ("MINERAL", "MINERAL NAME", "MINERAL_NAME", "MINERAL TYPE", "MINERAL_TYPE")
REFERENCE_COLUMNS = ("REFERENCE", "CITATION", "AUTHOR", "AUTHORS", "TITLE", "DOI")


def _norm(text: object) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(text).upper())


def _find_column(columns: Iterable[str], candidates: Iterable[str]) -> str | None:
    normalized = {_norm(column): column for column in columns}
    for candidate in candidates:
        hit = normalized.get(_norm(candidate))
        if hit is not None:
            return hit
    return None


def _canonical_oxide_columns(frame: pd.DataFrame) -> pd.DataFrame:
    rename: dict[str, str] = {}
    used: set[str] = set()
    for column in frame.columns:
        key = _norm(column)
        target = OXIDE_ALIASES.get(key)
        if target and target not in used:
            rename[column] = target
            used.add(target)
    return frame.rename(columns=rename)


def _looks_epma(values: pd.Series) -> pd.Series:
    text = values.astype(str).str.upper()
    return text.str.contains(r"\b(EPMA|EMPA|ELECTRON\s*PROBE|MICROPROBE|WDS)\b", regex=True, na=False)


def _download_file(file_id: int, destination: Path) -> None:
    if destination.exists() and destination.stat().st_size > 0:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(f"{ACCESS_API}/{file_id}", stream=True, timeout=(30, 300)) as response:
        response.raise_for_status()
        with destination.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dataset_files() -> list[dict]:
    response = requests.get(DATASET_API, params={"persistentId": DATASET_DOI}, timeout=60)
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != "OK":
        raise RuntimeError(f"Dataverse returned non-OK status: {payload}")
    return payload["data"]["latestVersion"]["files"]


def _family_from_filename(filename: str) -> tuple[str, str] | None:
    upper = filename.upper()
    for token, family in SELECTED_FAMILIES.items():
        if f"_{token}.CSV" in upper:
            return token, family
    return None


def _sample_file(
    path: Path,
    *,
    source_token: str,
    truth_family: str,
    per_family: int,
    seed: int,
) -> tuple[pd.DataFrame, dict]:
    candidates: list[pd.DataFrame] = []
    method_column_seen = False
    epma_rows = 0
    total_rows = 0
    mineral_column_name: str | None = None
    reference_column_name: str | None = None

    for chunk_index, chunk in enumerate(pd.read_csv(path, low_memory=False, chunksize=25_000)):
        total_rows += len(chunk)
        chunk = _canonical_oxide_columns(chunk)
        method_column = _find_column(chunk.columns, METHOD_COLUMNS)
        mineral_column = _find_column(chunk.columns, MINERAL_COLUMNS)
        reference_column = _find_column(chunk.columns, REFERENCE_COLUMNS)
        mineral_column_name = mineral_column_name or mineral_column
        reference_column_name = reference_column_name or reference_column
        if method_column is not None:
            method_column_seen = True
            mask = _looks_epma(chunk[method_column])
            chunk = chunk.loc[mask].copy()
        # If GEOROC file lacks a method field, keep the row but mark it as family-labeled rather
        # than claiming that it is an EPMA-only species benchmark.
        epma_rows += len(chunk)
        if chunk.empty:
            continue
        numeric_oxides = [column for column in OXIDE_ALIASES.values() if column in chunk.columns]
        if len(numeric_oxides) < 2:
            continue
        keep = list(dict.fromkeys(numeric_oxides + ([mineral_column] if mineral_column else []) + ([reference_column] if reference_column else [])))
        part = chunk[keep].copy()
        part["truth_family"] = truth_family
        part["source_family"] = source_token
        part["source_chunk"] = chunk_index
        if mineral_column:
            part["source_mineral_name"] = chunk[mineral_column].astype(str)
        if reference_column:
            part["source_reference"] = chunk[reference_column].astype(str)
        candidates.append(part)

    if not candidates:
        return pd.DataFrame(), {
            "total_rows": total_rows,
            "eligible_rows": 0,
            "method_column_seen": method_column_seen,
            "mineral_column": mineral_column_name,
            "reference_column": reference_column_name,
        }
    pool = pd.concat(candidates, ignore_index=True)
    # Deduplicate exact analytical chemistry to avoid replicated literature rows dominating metrics.
    chemistry = [column for column in OXIDE_ALIASES.values() if column in pool.columns]
    pool = pool.drop_duplicates(subset=chemistry, keep="first")
    n = min(per_family, len(pool))
    sample = pool.sample(n=n, random_state=seed).reset_index(drop=True)
    sample["validation_id"] = [f"{source_token}-{index:05d}" for index in range(len(sample))]
    return sample, {
        "total_rows": total_rows,
        "eligible_rows": len(pool),
        "sampled_rows": len(sample),
        "method_column_seen": method_column_seen,
        "mineral_column": mineral_column_name,
        "reference_column": reference_column_name,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="validation/mineral_recognition/georoc_holdout.csv")
    parser.add_argument("--cache", default=".cache/georoc-minerals")
    parser.add_argument("--per-family", type=int, default=400)
    parser.add_argument("--seed", type=int, default=20260814)
    args = parser.parse_args()

    output = Path(args.output)
    cache = Path(args.cache)
    metadata = _dataset_files()
    selected = []
    for item in metadata:
        data_file = item.get("dataFile", {})
        filename = str(data_file.get("filename", ""))
        family = _family_from_filename(filename)
        if family:
            selected.append((data_file, family))
    if len(selected) != len(SELECTED_FAMILIES):
        found = {family[0] for _, family in selected}
        missing = sorted(set(SELECTED_FAMILIES) - found)
        raise RuntimeError(f"GEOROC file manifest changed; missing selected families: {missing}")

    frames: list[pd.DataFrame] = []
    manifest_files: list[dict] = []
    for data_file, (token, truth_family) in selected:
        filename = str(data_file["filename"])
        file_id = int(data_file["id"])
        path = cache / filename
        print(f"Downloading/reading {filename} …", flush=True)
        _download_file(file_id, path)
        sample, stats = _sample_file(
            path,
            source_token=token,
            truth_family=truth_family,
            per_family=args.per_family,
            seed=args.seed + file_id,
        )
        if sample.empty:
            raise RuntimeError(f"No usable rows from {filename}")
        frames.append(sample)
        manifest_files.append(
            {
                "filename": filename,
                "dataverse_file_id": file_id,
                "size": path.stat().st_size,
                "sha256": _sha256(path),
                "truth_family": truth_family,
                **stats,
            }
        )

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
            "Rows are an external validation holdout. If a source file exposes an analytical-method "
            "column, only EPMA/EMPA/electron-probe/WDS rows are retained. Files lacking method metadata "
            "remain valid for family-level chemistry benchmarking but must not be described as EPMA-only."
        ),
    }
    manifest_path = output.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(corpus)} rows to {output}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
