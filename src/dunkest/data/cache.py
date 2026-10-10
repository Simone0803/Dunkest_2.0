from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


def _meta_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".meta.json")


def read_parquet(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    return pd.read_parquet(path)


def read_cache_metadata(path: Path) -> dict[str, Any] | None:
    meta_file = _meta_path(path)
    if not meta_file.exists():
        return None
    try:
        metadata = json.loads(meta_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return metadata if isinstance(metadata, dict) else None


def cache_has_complete_collection(path: Path) -> bool:
    metadata = read_cache_metadata(path)
    return metadata is not None and metadata.get("collection_complete") is True


def write_parquet(df: pd.DataFrame, path: Path, source: str, **extra: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    meta = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "rows": len(df),
        "schema_version": 1,
        **extra,
    }
    _meta_path(path).write_text(json.dumps(meta, indent=2), encoding="utf-8")


def cache_valid(path: Path, max_age_hours: float | None = None) -> bool:
    if not path.exists():
        return False
    if max_age_hours is None:
        return True
    meta = read_cache_metadata(path)
    if meta is None:
        return False
    try:
        fetched = datetime.fromisoformat(meta["fetched_at"])
    except (KeyError, TypeError, ValueError):
        return False
    age_h = (datetime.now(timezone.utc) - fetched).total_seconds() / 3600
    return age_h <= max_age_hours
