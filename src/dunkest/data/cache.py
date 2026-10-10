from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


def _meta_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".meta.json")


def read_parquet(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except (OSError, ValueError, ImportError):
        # A truncated or otherwise unreadable cache must behave like a cache miss.
        return None


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


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def write_parquet(df: pd.DataFrame, path: Path, source: str, **extra: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        df.to_parquet(temp_path, index=False)
        metadata = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "rows": len(df),
            "schema_version": 1,
            **extra,
        }
        # Publish the data file only after the Parquet writer has completed.
        os.replace(temp_path, path)
        _atomic_write_text(
            _meta_path(path),
            json.dumps(metadata, indent=2, allow_nan=False),
        )
    finally:
        temp_path.unlink(missing_ok=True)


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
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
        age_h = (datetime.now(timezone.utc) - fetched.astimezone(timezone.utc)).total_seconds() / 3600
    except (KeyError, TypeError, ValueError):
        return False
    return 0 <= age_h <= max_age_hours
