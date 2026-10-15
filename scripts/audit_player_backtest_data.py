#!/usr/bin/env python3
"""Audit the available Dunkest/NBA history before building a player-level backtest.

Run from the repository root:
  ./.venv/bin/python scripts/audit_player_backtest_data.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"

FILES = [
    "plusvalenza_history_25_through_gw91_v2.parquet",
    "plusvalenza_history_nba_25_through_gw91_v3.parquet",
    "player_game_logs_2025-26.parquet",
    "team_game_logs_2025-26.parquet",
    "schedule_2025-26.parquet",
    "schedule.parquet",
]

DATE_HINTS = ("date", "time", "tip", "game_date", "datetime")
ID_HINTS = ("game_id", "gameid", "player_id", "player_name", "team", "season", "gameweek", "gw")
TARGET_HINTS = ("pdk", "pts", "plus", "cr", "min", "starter", "fantasy", "actual")


def show_file(filename: str) -> None:
    path = PROCESSED / filename
    print("\n" + "=" * 90)
    print(f"FILE: {path.relative_to(ROOT)}")
    if not path.exists():
        print("NOT FOUND")
        return

    try:
        df = pd.read_parquet(path)
    except Exception as exc:
        print(f"READ ERROR: {type(exc).__name__}: {exc}")
        return

    print(f"shape: {df.shape}")
    print("columns:", list(df.columns))
    if df.empty:
        print("EMPTY DATAFRAME")
    else:
        print("\nfirst 3 rows:")
        print(df.head(3).to_string(index=False, max_cols=30))

        date_cols = [
            c for c in df.columns
            if any(h in c.lower() for h in DATE_HINTS)
        ]
        if date_cols:
            print("\ndate-like columns:")
            for col in date_cols:
                parsed = pd.to_datetime(df[col], errors="coerce", utc=True)
                print(
                    f"  {col}: non-null={int(df[col].notna().sum())}, "
                    f"parseable={int(parsed.notna().sum())}, "
                    f"min={parsed.min()}, max={parsed.max()}"
                )

        selected = [
            c for c in df.columns
            if any(h in c.lower() for h in ID_HINTS + TARGET_HINTS)
        ]
        if selected:
            print("\nselected value counts / ranges:")
            for col in selected:
                s = df[col]
                if s.nunique(dropna=True) <= 20:
                    print(f"  {col}: {s.value_counts(dropna=False).head(20).to_dict()}")
                elif pd.api.types.is_numeric_dtype(s):
                    print(
                        f"  {col}: non-null={int(s.notna().sum())}, "
                        f"min={s.min()}, max={s.max()}, unique={s.nunique(dropna=True)}"
                    )
                else:
                    print(f"  {col}: non-null={int(s.notna().sum())}, unique={s.nunique(dropna=True)}")

    meta_path = path.with_suffix(path.suffix + ".meta.json")
    if meta_path.exists():
        print("\nmetadata:")
        try:
            print(json.dumps(json.loads(meta_path.read_text()), indent=2, ensure_ascii=False))
        except Exception as exc:
            print(f"Could not parse metadata: {exc}")


def main() -> None:
    if not PROCESSED.exists():
        raise SystemExit(f"Directory not found: {PROCESSED}")
    print(f"Repository root: {ROOT}")
    print(f"Processed data directory: {PROCESSED}")
    for filename in FILES:
        show_file(filename)

    print("\n" + "=" * 90)
    print("OTHER CANDIDATE FILES")
    patterns = ("*schedule*2025-26*.parquet", "*game_logs*2025-26*.parquet",
                "*plusvalenza*25*.parquet", "*fixture*mapping*25*.parquet")
    found: set[Path] = set()
    for pattern in patterns:
        found.update(PROCESSED.glob(pattern))
    for path in sorted(found):
        print(f"  {path.relative_to(ROOT)}")

    print("\nAudit complete. This script only reads files; it does not modify data.")


if __name__ == "__main__":
    main()
