"""Shared corpus/manifest access for the vision judge (stdlib-only).

The calibration corpus (../corpus/) and the goldens store (../goldens/) are
both gitignored-except-manifest: licensed LimeZu-derived pixels never enter
git; the tracked manifest carries sha256 + provenance per image so any
checkout can verify the exact bytes it is judging with. Every read is
integrity-checked against the manifest before use (a poisoned corpus would
poison the judge), and every path is containment-checked against its root
(same guard pattern as ../build_corpus.py).

All functions take explicit dir/manifest paths (defaulting to the real
locations) so tests run against synthetic tmp corpora — the licensed corpus
is never required for the suite to prove the mechanism.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

JUDGE_DIR = Path(__file__).resolve().parent
WA_DIR = JUDGE_DIR.parent
CORPUS_DIR = WA_DIR / "corpus"
CORPUS_MANIFEST = CORPUS_DIR / "manifest.json"
GOLDENS_DIR = WA_DIR / "goldens"
GOLDENS_MANIFEST = GOLDENS_DIR / "manifest.json"
RUNS_DIR = JUDGE_DIR / "runs"


class CorpusError(ValueError):
    """Corpus/manifest integrity or containment violation."""


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def contained(path: Path, root: Path) -> Path:
    """Resolve `path` and require it to live under `root` (anti-traversal)."""
    p = Path(path).resolve()
    root = Path(root).resolve()
    if not p.is_relative_to(root):
        raise CorpusError(f"path escapes {root.name}/: {p}")
    return p


def atomic_write_json(path: Path, obj) -> None:
    """Write JSON via tmp-file + os.replace so a crash never truncates."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.",
                               suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(obj, f, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def load_manifest(manifest_path: Path = CORPUS_MANIFEST) -> dict:
    manifest_path = Path(manifest_path)
    if not manifest_path.exists():
        raise CorpusError(f"corpus manifest missing: {manifest_path}")
    try:
        data = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as e:
        raise CorpusError(f"corpus manifest unreadable: {e}") from e
    if not isinstance(data.get("images"), list):
        raise CorpusError("corpus manifest has no images list")
    return data


def corpus_entries(cls: str | None = None,
                   corpus_dir: Path = CORPUS_DIR,
                   manifest_path: Path | None = None) -> list[dict]:
    """Manifest entries (optionally one class), each with resolved `path`."""
    manifest_path = Path(manifest_path if manifest_path is not None
                         else Path(corpus_dir) / "manifest.json")
    corpus_dir = Path(corpus_dir)
    out = []
    for img in load_manifest(manifest_path)["images"]:
        if cls is not None and img.get("class") != cls:
            continue
        rel = Path(img["file"])
        # Manifest files are recorded corpus-relative as "corpus/<cls>/<f>";
        # anchor at the corpus dir's parent, then containment-check.
        p = contained(corpus_dir.parent / rel, corpus_dir)
        entry = dict(img)
        entry["path"] = p
        out.append(entry)
    return sorted(out, key=lambda e: e["id"])


def verify_entry(entry: dict) -> Path:
    """Require the entry's image to exist with the manifest's exact bytes."""
    p = Path(entry["path"])
    if not p.exists():
        raise CorpusError(
            f"corpus image missing on disk: {entry['file']} "
            f"(gitignored — re-assemble per manifest provenance / "
            f"build_corpus.py)")
    digest = sha256_of(p)
    if digest != entry["sha256"]:
        raise CorpusError(
            f"corpus image hash mismatch: {entry['file']} — on-disk bytes "
            f"differ from the tracked manifest (refusing a poisoned corpus)")
    return p


def append_corpus_entries(new_entries: list[dict],
                          corpus_dir: Path = CORPUS_DIR,
                          manifest_path: Path | None = None) -> dict:
    """Append Captain-verdict entries to the corpus manifest (atomic).

    Duplicate ids are refused — taste accumulation is append-only; replacing
    a recorded verdict is a conscious manual act, not an API default.
    """
    corpus_dir = Path(corpus_dir)
    manifest_path = Path(manifest_path if manifest_path is not None
                         else corpus_dir / "manifest.json")
    data = load_manifest(manifest_path)
    have = {img["id"] for img in data["images"]}
    for e in new_entries:
        if e["id"] in have:
            raise CorpusError(f"corpus entry id already exists: {e['id']}")
        have.add(e["id"])
    data["images"] = sorted(data["images"] + list(new_entries),
                            key=lambda i: i["id"])
    data["counts"] = {
        "positive": sum(1 for i in data["images"]
                        if i["class"] == "positive"),
        "negative": sum(1 for i in data["images"]
                        if i["class"] == "negative"),
    }
    atomic_write_json(manifest_path, data)
    return data


def png_codec():
    """The pure-stdlib PNG codec (gates/_png), via ../_loader.py.

    Reuses the already-loaded module when the gates package is live (tests,
    aesthetic runner in-process) — no duplicate module execution.
    """
    loader = sys.modules.get("world_aesthetic_loader")
    if loader is None:
        spec = importlib.util.spec_from_file_location(
            "world_aesthetic_loader", WA_DIR / "_loader.py")
        loader = importlib.util.module_from_spec(spec)
        sys.modules["world_aesthetic_loader"] = loader
        try:
            spec.loader.exec_module(loader)
        except BaseException:
            sys.modules.pop("world_aesthetic_loader", None)
            raise
    return loader.load_gates()._png
