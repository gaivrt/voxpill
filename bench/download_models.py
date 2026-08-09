#!/usr/bin/env python3
"""Download experimental model files/archives and write checksum receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
import tomllib
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BENCH_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BENCH_DIR / "models.toml"
CACHE_DIR = BENCH_DIR / "model_cache"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_extract(archive: Path, destination: Path) -> None:
    destination_resolved = destination.resolve()
    with tarfile.open(archive, "r:*") as tar:
        members = tar.getmembers()
        for member in members:
            if member.issym() or member.islnk():
                raise ValueError(f"Refusing archive link: {member.name}")
            if not (member.isfile() or member.isdir()):
                raise ValueError(f"Refusing special archive entry: {member.name}")
            target = (destination / member.name).resolve()
            if target != destination_resolved and destination_resolved not in target.parents:
                raise ValueError(f"Unsafe archive path: {member.name}")
        tar.extractall(destination, members=members)


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    downloaded = partial.stat().st_size if partial.exists() else 0
    request = urllib.request.Request(url)
    if downloaded:
        request.add_header("Range", f"bytes={downloaded}-")
    print(f"download {url} (resume at {downloaded} bytes)", flush=True)
    with urllib.request.urlopen(request) as response:
        append = downloaded > 0 and getattr(response, "status", None) == 206
        mode = "ab" if append else "wb"
        if not append:
            downloaded = 0
        next_report = downloaded + 32 * 1024 * 1024
        with partial.open(mode) as output:
            while block := response.read(1024 * 1024):
                output.write(block)
                downloaded += len(block)
                if downloaded >= next_report:
                    print(f"  {downloaded / (1024 * 1024):.0f} MiB", flush=True)
                    next_report += 32 * 1024 * 1024
    partial.replace(destination)


def required_paths(spec: dict) -> list[Path]:
    return [PROJECT_ROOT / spec[key] for key in spec.get("required", [])]


def file_receipts(spec: dict) -> list[dict]:
    files = []
    for path in required_paths(spec):
        files.append(
            {
                "path": str(path.relative_to(PROJECT_ROOT)),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return files


def install_direct_model(
    model_id: str, spec: dict, use_origin: bool, previous_receipt: dict | None = None
) -> dict:
    base_key = "download_base" if use_origin else "download_mirror_base"
    base = spec.get(base_key) or spec["download_base"]
    directory = PROJECT_ROOT / spec["download_dir"]
    old_sources = {
        item["path"]: item for item in (previous_receipt or {}).get("sources", [])
    }
    sources = []
    for filename in spec["download_files"]:
        destination = directory / filename
        url = f"{base.rstrip('/')}/{filename}"
        relative = str(destination.relative_to(PROJECT_ROOT))
        downloaded_now = not destination.is_file()
        if downloaded_now:
            download(url, destination)
        source = {"path": relative, "status": "downloaded" if downloaded_now else "cached"}
        if downloaded_now:
            source["url"] = url
        elif relative in old_sources and "url" in old_sources[relative]:
            source["url"] = old_sources[relative]["url"]
        else:
            source["provenance"] = "preexisting-unknown"
        sources.append(source)
    missing = [path for path in required_paths(spec) if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"{model_id}: missing required files: {missing}")
    return {
        "model": model_id,
        "source_page": spec["source_page"],
        "sources": sources,
        "files": file_receipts(spec),
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }


def install_archive_model(
    model_id: str, spec: dict, use_origin: bool, previous_receipt: dict | None = None
) -> dict:
    archive = CACHE_DIR / "archives" / spec["archive_name"]
    url = spec["archive_url"] if use_origin else spec.get("archive_mirror_url", spec["archive_url"])
    downloaded_now = not archive.exists()
    if downloaded_now:
        download(url, archive)
    archive_sha = sha256_file(archive)
    missing = [path for path in required_paths(spec) if not path.is_file()]
    if missing:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        safe_extract(archive, CACHE_DIR)
    missing = [path for path in required_paths(spec) if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"{model_id}: archive missing required files: {missing}")
    receipt = {
        "model": model_id,
        "source_page": spec["source_page"],
        "canonical_archive_url": spec["archive_url"],
        "archive_status": "downloaded" if downloaded_now else "cached",
        "archive": str(archive.relative_to(PROJECT_ROOT)),
        "archive_bytes": archive.stat().st_size,
        "archive_sha256": archive_sha,
        "files": file_receipts(spec),
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }
    if downloaded_now:
        receipt["archive_url"] = url
    elif previous_receipt and "archive_url" in previous_receipt:
        receipt["archive_url"] = previous_receipt["archive_url"]
    else:
        receipt["archive_provenance"] = "preexisting-unknown"
    return receipt


def install_huggingface_model(
    model_id: str,
    spec: dict,
    snapshot_download_fn=None,
) -> dict:
    if snapshot_download_fn is None:
        try:
            from huggingface_hub import snapshot_download as snapshot_download_fn
        except ImportError as exc:
            raise RuntimeError(
                "Hugging Face downloader is missing; run "
                "`uv sync --group qwen-asr` first"
            ) from exc
    destination = PROJECT_ROOT / spec["download_dir"]
    cached = all(path.is_file() for path in required_paths(spec))
    if not cached:
        snapshot_download_fn(
            repo_id=spec["hf_repo"],
            revision=spec["revision"],
            local_dir=str(destination),
            allow_patterns=list(spec["download_files"]),
        )
    missing = [path for path in required_paths(spec) if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"{model_id}: snapshot missing required files: {missing}")
    return {
        "model": model_id,
        "source_page": spec["source_page"],
        "repository": spec["hf_repo"],
        "revision": spec["revision"],
        "download_status": "cached" if cached else "downloaded",
        "files": file_receipts(spec),
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("models", nargs="*", help="model IDs from models.toml")
    parser.add_argument("--all", action="store_true", help="download every external model")
    parser.add_argument("--origin", action="store_true", help="bypass configured mirrors")
    args = parser.parse_args()
    config = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    catalog = {**config.get("models", {}), **config.get("assets", {})}
    external = {
        key: value
        for key, value in catalog.items()
        if "archive_url" in value or "download_base" in value or "hf_repo" in value
    }
    selected = list(external) if args.all else args.models
    if not selected:
        parser.error("pass model IDs or --all")
    unknown = sorted(set(selected) - set(external))
    if unknown:
        parser.error(f"unknown or local-only models: {', '.join(unknown)}")
    receipt_path = CACHE_DIR / "checksums.json"
    previous: dict[str, dict] = {}
    if receipt_path.is_file():
        data = json.loads(receipt_path.read_text(encoding="utf-8"))
        previous = {item["model"]: item for item in data.get("receipts", [])}
    for model_id in selected:
        spec = external[model_id]
        old_receipt = previous.get(model_id)
        if "hf_repo" in spec:
            previous[model_id] = install_huggingface_model(model_id, spec)
        elif "download_base" in spec:
            previous[model_id] = install_direct_model(
                model_id, spec, args.origin, old_receipt
            )
        else:
            previous[model_id] = install_archive_model(
                model_id, spec, args.origin, old_receipt
            )
    receipt_path.write_text(
        json.dumps(
            {"receipts": [previous[key] for key in sorted(previous)]},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {receipt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
