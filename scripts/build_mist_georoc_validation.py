from __future__ import annotations

"""Build an external family-level holdout from the published MIST-filtered GEOROC dataset.

Primary provenance:
Siebach et al. (2025), Compilation of GEOROC Mineral Compositions filtered by MIST,
GFZ Data Services, doi:10.5880/digis.e.2025.002, CC BY-SA 4.0.

GFZ exposes the dataset through an Apache directory index. The actual data are distributed in a
ZIP bundle containing fifteen December-2024 GEOROC mineral compilations with MIST results
appended. PetroLab uses the original GEOROC compilation family as truth; appended MIST
predictions are deliberately not used as ground truth.
"""

import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import unquote, urljoin, urlparse
import zipfile

import pandas as pd
import requests

from build_georoc_mineral_validation import _sample_file, _sha256


GFZ_DOI = "10.5880/digis.e.2025.002"
GFZ_INDEX_URL = "https://datapub.gfz.de/download/10.5880.DIGIS.E.2025.002-aYVBW/"
CORPUS_SCHEMA_VERSION = "6"
USER_AGENT = "PetroLab-mineral-validation/1.0"

# These are exactly the fifteen mineral compilations present in the published GFZ data bundle.
SELECTED_FAMILIES = {
    "AMPHIBOLES": (("AMPHIBOLE", "AMPHIBOLES"), "amphibole"),
    "APATITES": (("APATITE", "APATITES"), "apatite"),
    "CARBONATES": (("CARBONATE", "CARBONATES"), "carbonate"),
    "CLINOPYROXENES": (("CLINOPYROXENE", "CLINOPYROXENES"), "clinopyroxene"),
    "FELDSPARS": (("FELDSPAR", "FELDSPARS"), "feldspar"),
    "FELDSPATHOIDES": (("FELDSPATHOID", "FELDSPATHOIDES", "FELDSPATHOIDS"), "feldspathoid"),
    "GARNETS": (("GARNET", "GARNETS"), "garnet"),
    "ILMENITES": (("ILMENITE", "ILMENITES"), "oxide"),
    "MICA": (("MICA", "MICAS"), "mica"),
    "OLIVINES": (("OLIVINE", "OLIVINES"), "olivine"),
    "ORTHOPYROXENES": (("ORTHOPYROXENE", "ORTHOPYROXENES"), "orthopyroxene"),
    "PYROXENES": (("PYROXENE", "PYROXENES"), "pyroxene"),
    "QUARTZ": (("QUARTZ",), "silica"),
    "SPINELS": (("SPINEL", "SPINELS"), "spinel"),
    "ZIRCONS": (("ZIRCON", "ZIRCONS"), "zircon"),
}


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.links.append(href)


def _stable_seed(token: str, base_seed: int) -> int:
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    return base_seed + int.from_bytes(digest[:4], "big")


def _request(url: str, *, stream: bool = False) -> requests.Response:
    response = requests.get(
        url,
        stream=stream,
        timeout=(30, 900),
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    return response


def _family_for_name(name: str) -> tuple[str, str] | None:
    upper = re.sub(r"[^A-Z0-9]+", "_", name.upper())
    hits: list[tuple[int, str, str]] = []
    for canonical, (aliases, broad_family) in SELECTED_FAMILIES.items():
        for alias in aliases:
            if alias in upper:
                hits.append((len(alias), canonical, broad_family))
    if not hits:
        return None
    _, canonical, broad_family = max(hits)
    return canonical, broad_family


def _discover_zip_urls(index_url: str) -> list[str]:
    root = urlparse(index_url)
    with _request(index_url) as response:
        parser = _LinkParser()
        parser.feed(response.text)
    result: list[str] = []
    for href in parser.links:
        if href.startswith(("?", "#")) or href in {"../", "./", "/"}:
            continue
        child = urljoin(index_url, href)
        parsed = urlparse(child)
        if parsed.netloc == root.netloc and parsed.path.lower().endswith(".zip"):
            result.append(child)
    return sorted(set(result))


def _download_file(url: str, destination: Path) -> None:
    if destination.exists() and destination.stat().st_size > 0:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(destination.suffix + ".part")
    with _request(url, stream=True) as response:
        if "text/html" in response.headers.get("content-type", "").lower():
            raise RuntimeError(f"Expected data file but GFZ returned HTML for {url}")
        with temp.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=4 * 1024 * 1024):
                if chunk:
                    handle.write(chunk)
    if temp.stat().st_size == 0:
        raise RuntimeError(f"GFZ returned empty data file: {url}")
    temp.replace(destination)


def _extract_data_csvs(zip_urls: list[str], cache: Path) -> list[tuple[Path, str]]:
    data_urls = [url for url in zip_urls if "DATA" in unquote(Path(urlparse(url).path).name).upper()]
    if not data_urls:
        raise RuntimeError(f"GFZ index exposes no data ZIP; found: {zip_urls}")
    csv_paths: list[tuple[Path, str]] = []
    extract_dir = cache / "extracted"
    extract_dir.mkdir(parents=True, exist_ok=True)
    for url in data_urls:
        archive_name = unquote(Path(urlparse(url).path).name)
        archive_path = cache / archive_name
        print(f"Downloading GFZ data ZIP: {archive_name}", flush=True)
        _download_file(url, archive_path)
        if not zipfile.is_zipfile(archive_path):
            raise RuntimeError(f"GFZ data link is not a valid ZIP: {url}")
        with zipfile.ZipFile(archive_path) as handle:
            names = [
                name for name in handle.namelist()
                if name.lower().endswith(".csv")
                and not name.endswith("/")
                and not Path(name).name.startswith("._")
            ]
            print(f"  Data ZIP contains {len(names)} real CSV files", flush=True)
            for name in names:
                target = extract_dir / Path(name).name
                if not target.exists() or target.stat().st_size == 0:
                    with handle.open(name) as source, target.open("wb") as sink:
                        while True:
                            chunk = source.read(4 * 1024 * 1024)
                            if not chunk:
                                break
                            sink.write(chunk)
                csv_paths.append((target, url))
    return csv_paths


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="validation/mineral_recognition/georoc_holdout.csv")
    parser.add_argument("--cache", default=".cache/mist-georoc")
    parser.add_argument("--per-family", type=int, default=400)
    parser.add_argument("--seed", type=int, default=20260814)
    args = parser.parse_args()

    output = Path(args.output)
    cache = Path(args.cache)
    print(f"Discovering GFZ MIST-GEOROC files: {GFZ_DOI}", flush=True)
    zip_urls = _discover_zip_urls(GFZ_INDEX_URL)
    print(f"GFZ ZIP assets: {[unquote(Path(urlparse(url).path).name) for url in zip_urls]}", flush=True)
    local_csvs = _extract_data_csvs(zip_urls, cache)

    selected: dict[str, tuple[Path, str, str]] = {}
    for path, source_url in local_csvs:
        family = _family_for_name(path.name)
        if family is None:
            continue
        canonical, broad_family = family
        selected.setdefault(canonical, (path, source_url, broad_family))

    missing = sorted(set(SELECTED_FAMILIES) - set(selected))
    if missing:
        available = sorted(path.name for path, _ in local_csvs)
        raise RuntimeError(f"MIST-GEOROC publication missing selected families {missing}; CSVs={available}")

    frames: list[pd.DataFrame] = []
    manifest_files: list[dict] = []
    for canonical, (path, source_url, broad_family) in sorted(selected.items()):
        print(f"Sampling {path.name} as {canonical}", flush=True)
        sample, stats = _sample_file(
            path,
            source_token=canonical,
            truth_family=broad_family,
            per_family=args.per_family,
            seed=_stable_seed(canonical, args.seed),
        )
        if sample.empty:
            raise RuntimeError(f"No usable chemistry rows from {path.name}")
        frames.append(sample)
        manifest_files.append({
            "filename": path.name,
            "source_url": source_url,
            "sha256": _sha256(path),
            "source_family": canonical,
            "truth_family": broad_family,
            **stats,
        })

    corpus = pd.concat(frames, ignore_index=True)
    corpus = corpus.sample(frac=1.0, random_state=args.seed).reset_index(drop=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    corpus.to_csv(output, index=False)
    manifest = {
        "schema_version": CORPUS_SCHEMA_VERSION,
        "dataset": "Compilation of GEOROC Mineral Compositions filtered by MIST",
        "doi": GFZ_DOI,
        "derived_from": "10.25625/SGFTFN",
        "license": "CC BY-SA 4.0",
        "index_url": GFZ_INDEX_URL,
        "seed": args.seed,
        "requested_per_family": args.per_family,
        "rows": len(corpus),
        "families": sorted(selected),
        "files": manifest_files,
        "truth_policy": "Original GEOROC compilation family; appended MIST result is not used as truth.",
    }
    output.with_suffix(".manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Wrote {len(corpus)} external rows across {len(selected)} families to {output}", flush=True)


if __name__ == "__main__":
    main()
