"""Audit manifest I/O (TODO.md Path T1).

One YAML file, one entry per title (keyed by the candidate folder's name).
Re-auditing replaces the measurements and the recommendation but never the
user's `decision` block, which is the part later stages act on.
"""
from pathlib import Path
from typing import Any, Dict

import yaml

EMPTY_DECISION = {"file": None, "extraction": None, "notes": ""}


def load_manifest(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"titles": {}}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    data.setdefault("titles", {})
    return data


def merge_title(manifest: Dict[str, Any], slug: str, candidates: Dict[str, Any],
                recommendation: Dict[str, Any], audited_at: str) -> Dict[str, Any]:
    previous = manifest["titles"].get(slug) or {}
    manifest["titles"][slug] = {
        "audited_at": audited_at,
        "decision": previous.get("decision") or dict(EMPTY_DECISION),
        "recommendation": recommendation,
        "candidates": candidates,
    }
    return manifest


def save_manifest(path: Path, manifest: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = ("# Source audit manifest (TODO.md Path T1), written by audit_sources.py.\n"
              "# Fill in each title's `decision`; re-running the audit keeps it.\n")
    path.write_text(header + yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True, width=120),
                    encoding="utf-8")
