#!/usr/bin/env python3
"""Collect official Dunkest per-player game histories for historical seasons.

The collector writes an append-only JSONL checkpoint and can resume after interruption.
It preserves gameValidForDunkest values without filtering them.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_DIR = ROOT / "data" / "raw" / "dunkest_player_games_history_v1"
PROCESSED_DIR = ROOT / "data" / "processed"
API_URL = "https://www.dunkest.com/api/player/games"
SEASON_LABELS = {
    "1": "2018-19",
    "3": "2019-20",
    "5": "2020-21",
    "7": "2021-22",
    "9": "2022-23",
    "13": "2023-24",
    "19": "2024-25",
}
DEFAULT_SEASONS = list(SEASON_LABELS)


def normalize_id(value: object) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text if text.isdigit() else None


def add_catalog_frame(
    frame: pd.DataFrame,
    ids: set[str],
    name_counts: dict[str, Counter[str]],
    id_col: str,
    name_col: str,
) -> None:
    if id_col not in frame.columns:
        return
    cols = [id_col] + ([name_col] if name_col in frame.columns else [])
    for row in frame[cols].itertuples(index=False, name=None):
        pid = normalize_id(row[0])
        if not pid:
            continue
        ids.add(pid)
        if len(row) > 1 and pd.notna(row[1]):
            name = str(row[1]).strip()
            if name:
                name_counts[pid][name] += 1


def exclude_confirmed_contaminated_seed_rows(
    frame: pd.DataFrame, evidence_path: Path | None = None
) -> tuple[pd.DataFrame, int]:
    """Exclude only independently confirmed bad player-season rows from season ID seeds."""
    evidence_path = evidence_path or (
        ROOT / "reports" / "audit" / "dunkest_week_round_confirmed_contamination_rows_v1.csv"
    )
    required = {"source_season_id", "source_week", "source_round", "id"}
    if not required.issubset(frame.columns) or not evidence_path.is_file():
        return frame.copy(), 0
    evidence = pd.read_csv(evidence_path, dtype={"dunkest_player_id": str})
    if "dunkest_player_id" not in evidence:
        return frame.copy(), 0

    # New row-level register: match exact season/week/round/player keys.
    evidence_key_columns = {"source_season_id", "source_week", "source_round"}
    if evidence_key_columns.issubset(evidence.columns):
        keys = set()
        for _, row in evidence.iterrows():
            pid = normalize_id(row.get("dunkest_player_id"))
            season = str(row.get("source_season_id", "")).strip()
            week = pd.to_numeric(pd.Series([row.get("source_week")]), errors="coerce").iloc[0]
            round_ = pd.to_numeric(pd.Series([row.get("source_round")]), errors="coerce").iloc[0]
            if pid and season and pd.notna(week) and pd.notna(round_):
                keys.add((season, int(week), int(round_), pid))
        row_keys = pd.Series(
            list(zip(
                frame["source_season_id"].astype(str),
                pd.to_numeric(frame["source_week"], errors="coerce"),
                pd.to_numeric(frame["source_round"], errors="coerce"),
                frame["id"].map(normalize_id),
            )),
            index=frame.index,
            dtype=object,
        )
        mask = row_keys.map(lambda key: (
            key[0], int(key[1]), int(key[2]), key[3]
        ) in keys if key[3] and pd.notna(key[1]) and pd.notna(key[2]) else False)
        return frame.loc[~mask].copy(), int(mask.sum())

    # Backward-compatible handling of the earlier cluster-only ID list.
    contaminated_ids = {
        pid for value in evidence["dunkest_player_id"].dropna()
        if (pid := normalize_id(value))
    }
    mask = (
        frame["source_season_id"].astype(str).eq("5")
        & pd.to_numeric(frame["source_week"], errors="coerce").eq(43)
        & pd.to_numeric(frame["source_round"], errors="coerce").eq(2)
        & frame["id"].map(normalize_id).isin(contaminated_ids)
    )
    return frame.loc[~mask].copy(), int(mask.sum())


def discover_players() -> tuple[set[str], dict[str, str], dict[str, set[str]]]:
    """Build a player-ID catalogue and season-specific player sets from local data."""
    all_ids: set[str] = set()
    name_counts: dict[str, Counter[str]] = defaultdict(Counter)
    season_ids: dict[str, set[str]] = defaultdict(set)

    # The API table's season-specific rows are the best per-season seed for 2020/21–2024/25.
    wide_path = PROCESSED_DIR / "dunkest_historical_player_week_round_2020-25_v2.parquet"
    if wide_path.exists():
        df = pd.read_parquet(
            wide_path,
            columns=["id", "player_name", "source_season_id", "source_week", "source_round"],
        )
        # IDs/names remain valid catalogue entries, but confirmed bad rows must not
        # establish that a player belongs to the contaminated historical season.
        add_catalog_frame(df, all_ids, name_counts, "id", "player_name")
        season_seed_df, excluded_rows = exclude_confirmed_contaminated_seed_rows(df)
        if excluded_rows:
            print(
                f"Excluded {excluded_rows} confirmed cross-season player rows from season-ID seeds "
                "using dunkest_week_round_confirmed_contamination_rows_v1.csv",
                flush=True,
            )
        for season, group in season_seed_df.groupby(season_seed_df["source_season_id"].astype(str)):
            if season in SEASON_LABELS:
                for value in group["id"].tolist():
                    pid = normalize_id(value)
                    if pid:
                        season_ids[season].add(pid)

    # Legacy raw Parquets add known historical Dunkest IDs not seen in the new tables.
    legacy_dir = ROOT / "data" / "raw" / "dunkest_history"
    if legacy_dir.exists():
        for path in legacy_dir.glob("season_*.parquet"):
            try:
                cols = pd.read_parquet(path, columns=["id", "player_name"])
                add_catalog_frame(cols, all_ids, name_counts, "id", "player_name")
            except (ValueError, KeyError, OSError):
                continue

    # Existing per-player game-history and daily files provide additional stable ID/name pairs.
    source_specs = [
        (PROCESSED_DIR / "daily_historical_pdk_2025-26.parquet", "id", "player_name"),
        (PROCESSED_DIR / "official_dunkest_player_games_2025-26.parquet",
         "_requested_player_id", "_requested_player_name"),
        (PROCESSED_DIR / "official_dunkest_vs_nba_matched_2025-26.parquet",
         "_requested_player_id", "_requested_player_name"),
    ]
    for path, id_col, name_col in source_specs:
        if not path.exists():
            continue
        try:
            df = pd.read_parquet(path, columns=[id_col, name_col])
            add_catalog_frame(df, all_ids, name_counts, id_col, name_col)
        except (ValueError, KeyError, OSError):
            continue

    # Add the full public Dunkest NBA player directory. Its numeric player IDs
    # provide a wider candidate pool for old seasons than the active-player datasets.
    catalog_path = ROOT / "data" / "raw" / "dunkest_player_games_history_v1" / "player_catalog_current.json"
    if catalog_path.exists():
        try:
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
            for item in catalog.get("players", []):
                pid = normalize_id(item.get("player_id"))
                if not pid:
                    continue
                all_ids.add(pid)
                slug = str(item.get("slug", "")).strip()
                if slug:
                    catalog_name = " ".join(part.capitalize() for part in slug.split("-"))
                else:
                    catalog_name = str(item.get("display_name", "")).strip()
                if catalog_name:
                    name_counts[pid][catalog_name] += 1
        except (OSError, json.JSONDecodeError, AttributeError, TypeError):
            pass

    if not all_ids:
        raise RuntimeError("No Dunkest player IDs found in local historical datasets.")

    names = {
        pid: counts.most_common(1)[0][0] if counts else ""
        for pid, counts in name_counts.items()
    }

    # Older seasons are absent from the stats-table endpoint, so use the union
    # of every locally known official Dunkest player ID for these two seasons.
    season_ids["1"] = set(all_ids)
    season_ids["3"] = set(all_ids)

    for season in ("5", "7", "9", "13", "19"):
        if not season_ids[season]:
            raise RuntimeError(
                f"No season-specific player IDs found for season_id={season}."
            )

    return all_ids, names, season_ids


def load_checkpoint(path: Path) -> dict[str, dict[str, Any]]:
    """Read JSONL records, dropping a possibly incomplete final line after a crash."""
    latest: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return latest
    raw = path.read_bytes()
    end = raw.rfind(b"\n")
    if end < 0:
        path.write_bytes(b"")
        return latest
    valid_bytes = raw[: end + 1]
    if len(valid_bytes) != len(raw):
        path.write_bytes(valid_bytes)
    for line in valid_bytes.splitlines():
        try:
            record = json.loads(line)
            key = f'{record["season_id"]}:{record["player_id"]}'
            latest[key] = record
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
    return latest


def save_manifest(path: Path, content: dict[str, Any]) -> None:
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(content, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)


async def fetch_one(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    season_id: str,
    player_id: str,
    player_name: str,
    delay: float,
) -> dict[str, Any]:
    async with semaphore:
        last_error = ""
        last_status: int | None = None
        for attempt in range(1, 4):
            try:
                response = await client.get(
                    API_URL,
                    params={"player_id": player_id, "season_id": season_id},
                )
                last_status = response.status_code
                if response.status_code in {408, 425, 429} or response.status_code >= 500:
                    last_error = f"HTTP {response.status_code}: {response.text[:250]}"
                    if attempt < 3:
                        await asyncio.sleep(0.5 * attempt)
                        continue
                    break
                if response.status_code != 200:
                    await asyncio.sleep(delay)
                    return {
                        "season_id": season_id, "player_id": player_id,
                        "player_name": player_name, "status": "error",
                        "http_status": response.status_code, "returned_rows": 0,
                        "records": [], "error": response.text[:500],
                    }
                payload = response.json()
                if not isinstance(payload, list) or any(not isinstance(x, dict) for x in payload):
                    await asyncio.sleep(delay)
                    return {
                        "season_id": season_id, "player_id": player_id,
                        "player_name": player_name, "status": "error",
                        "http_status": response.status_code, "returned_rows": 0,
                        "records": [], "error": "Unexpected response schema; expected a list of game objects.",
                        "payload_preview": str(payload)[:500],
                    }
                await asyncio.sleep(delay)
                return {
                    "season_id": season_id, "player_id": player_id,
                    "player_name": player_name,
                    "status": "ok" if payload else "empty",
                    "http_status": response.status_code, "returned_rows": len(payload),
                    "records": payload, "error": None,
                }
            except (httpx.HTTPError, ValueError) as exc:
                last_error = repr(exc)
                if attempt < 3:
                    await asyncio.sleep(0.5 * attempt)
        await asyncio.sleep(delay)
        return {
            "season_id": season_id, "player_id": player_id,
            "player_name": player_name, "status": "error",
            "http_status": last_status, "returned_rows": 0, "records": [],
            "error": last_error or "request failed after retries",
        }


def normalize_responses(
    latest: dict[str, dict[str, Any]],
    seasons: list[str],
    output_dir: Path,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    all_frames = []
    coverage = []
    for season in seasons:
        records: list[dict[str, Any]] = []
        season_responses = [
            value for value in latest.values()
            if str(value.get("season_id")) == season
        ]
        for response in season_responses:
            if response.get("status") not in {"ok", "empty"}:
                continue
            for item in response.get("records", []):
                row = dict(item)
                row["dunkest_player_id"] = str(response["player_id"])
                row["dunkest_player_name"] = response.get("player_name", "")
                row["season_id"] = season
                row["season_label"] = SEASON_LABELS.get(season, season)
                row["source_api"] = API_URL
                records.append(row)

        df = pd.DataFrame(records)
        if not df.empty:
            df["dunkest_player_id"] = df["dunkest_player_id"].astype(str)
            if "gameDate" in df.columns:
                df["gameDate"] = pd.to_datetime(df["gameDate"], errors="coerce").dt.strftime("%Y-%m-%d")
            if "pdk" in df.columns:
                df["pdk"] = pd.to_numeric(df["pdk"], errors="coerce")
            if "gameValidForDunkest" in df.columns:
                # Keep true, false and missing values; do not filter on this field.
                df["gameValidForDunkest"] = df["gameValidForDunkest"].astype("boolean")
            df = df.sort_values(
                [c for c in ["gameDate", "dunkest_player_id", "gameId"] if c in df.columns],
                kind="stable",
            ).reset_index(drop=True)
            season_path = PROCESSED_DIR / f"official_dunkest_player_games_{SEASON_LABELS[season]}_season_id_{season}.parquet"
            df.to_parquet(season_path, index=False)
            all_frames.append(df)

        successful = [x for x in season_responses if x.get("status") in {"ok", "empty"}]
        errors = [x for x in season_responses if x.get("status") == "error"]
        coverage.append({
            "season_id": season,
            "season_label": SEASON_LABELS.get(season, season),
            "player_ids_requested": len(season_responses),
            "players_with_games": sum(int(x.get("returned_rows", 0) > 0) for x in successful),
            "empty_player_responses": sum(x.get("status") == "empty" for x in successful),
            "player_request_errors": len(errors),
            "game_rows": len(df),
            "unique_player_ids_with_games": int(df["dunkest_player_id"].nunique()) if not df.empty else 0,
            "unique_dunkest_game_ids": int(df["gameId"].nunique()) if not df.empty and "gameId" in df else 0,
            "date_min": df["gameDate"].min() if not df.empty and "gameDate" in df else None,
            "date_max": df["gameDate"].max() if not df.empty and "gameDate" in df else None,
            "valid_true": int(df["gameValidForDunkest"].eq(True).sum()) if not df.empty and "gameValidForDunkest" in df else 0,
            "valid_false": int(df["gameValidForDunkest"].eq(False).sum()) if not df.empty and "gameValidForDunkest" in df else 0,
            "valid_missing": int(df["gameValidForDunkest"].isna().sum()) if not df.empty and "gameValidForDunkest" in df else 0,
        })

    combined = pd.concat(all_frames, ignore_index=True, sort=False) if all_frames else pd.DataFrame()
    duplicate_rows = pd.DataFrame()
    duplicate_audit = {
        "duplicate_key_columns": ["season_id", "dunkest_player_id", "gameId"],
        "duplicate_groups": 0,
        "duplicate_extra_rows": 0,
        "duplicate_rows_in_groups": 0,
        "conflicting_duplicate_groups": 0,
        "conflicting_groups": [],
        "per_season": {},
        "resolution": "No duplicate key was discarded without comparison; identical duplicate rows keep the first copy.",
    }
    if not combined.empty:
        keys = duplicate_audit["duplicate_key_columns"]
        duplicate_mask = combined.duplicated(keys, keep=False)
        duplicate_rows = combined.loc[duplicate_mask].copy()
        if not duplicate_rows.empty:
            group_counts = duplicate_rows.groupby(keys, dropna=False).size()
            duplicate_audit["duplicate_groups"] = int(len(group_counts))
            duplicate_audit["duplicate_extra_rows"] = int((group_counts - 1).sum())
            duplicate_audit["duplicate_rows_in_groups"] = int(len(duplicate_rows))
            conflict_groups = []
            conflict_mask = pd.Series(False, index=duplicate_rows.index)
            for group_key, group in duplicate_rows.groupby(keys, dropna=False, sort=False):
                non_keys = [c for c in group.columns if c not in keys]
                differing = [
                    c for c in non_keys
                    if group[c].astype("string").fillna("<NA>").nunique(dropna=False) > 1
                ]
                if differing:
                    conflict_mask.loc[group.index] = True
                    conflict_groups.append({
                        "key": list(group_key) if isinstance(group_key, tuple) else [group_key],
                        "row_count": int(len(group)),
                        "differing_columns": differing,
                    })
            duplicate_rows["duplicate_key_count"] = [
                int(group_counts.loc[tuple(row)] if isinstance(row, tuple) else group_counts.loc[row])
                for row in duplicate_rows[keys].itertuples(index=False, name=None)
            ]
            duplicate_rows["duplicate_has_conflicting_values"] = conflict_mask
            duplicate_audit["conflicting_duplicate_groups"] = len(conflict_groups)
            duplicate_audit["conflicting_groups"] = conflict_groups
            if conflict_groups:
                raise RuntimeError(
                    "Duplicate Dunkest player-game keys have conflicting values; "
                    "inspect raw responses before choosing a row."
                )
            duplicate_audit["per_season"] = {
                str(season): {
                    "duplicate_groups": int(len(group.groupby(keys, dropna=False))),
                    "duplicate_extra_rows": int(
                        sum(len(g) - 1 for _, g in group.groupby(keys, dropna=False))
                    ),
                }
                for season, group in duplicate_rows.groupby("season_id")
            }
        combined = combined.drop_duplicates(subset=keys, keep="first").sort_values(
            ["season_id", "gameDate", "dunkest_player_id"], kind="stable"
        ).reset_index(drop=True)

        # Rewrite the per-season Parquets after de-duplication so they match the
        # consolidated dataset exactly and have no hidden row-count discrepancy.
        for season in seasons:
            season_frame = combined.loc[combined["season_id"].astype(str).eq(str(season))].copy()
            if season_frame.empty:
                continue
            season_path = PROCESSED_DIR / (
                f"official_dunkest_player_games_{SEASON_LABELS[season]}_season_id_{season}.parquet"
            )
            season_frame.to_parquet(season_path, index=False)

        # Keep coverage counts aligned with the de-duplicated outputs, while
        # preserving raw response row counts so the audit is transparent.
        for item in coverage:
            season = str(item["season_id"])
            season_frame = combined.loc[combined["season_id"].astype(str).eq(season)]
            raw_rows = int(item.get("game_rows", 0))
            item["raw_response_game_rows_before_dedup"] = raw_rows
            item["duplicate_extra_rows_removed"] = raw_rows - int(len(season_frame))
            item["game_rows"] = int(len(season_frame))
            item["unique_player_ids_with_games"] = int(season_frame["dunkest_player_id"].nunique()) if not season_frame.empty else 0
            item["unique_dunkest_game_ids"] = int(season_frame["gameId"].nunique()) if not season_frame.empty else 0
            item["date_min"] = str(pd.to_datetime(season_frame["gameDate"], errors="coerce").min().date()) if not season_frame.empty else None
            item["date_max"] = str(pd.to_datetime(season_frame["gameDate"], errors="coerce").max().date()) if not season_frame.empty else None
            item["valid_true"] = int(season_frame["gameValidForDunkest"].eq(True).sum()) if not season_frame.empty else 0
            item["valid_false"] = int(season_frame["gameValidForDunkest"].eq(False).sum()) if not season_frame.empty else 0
            item["valid_missing"] = int(season_frame["gameValidForDunkest"].isna().sum()) if not season_frame.empty else 0
    return combined, coverage, duplicate_rows, duplicate_audit


async def collect(args: argparse.Namespace) -> None:
    all_ids, names, season_ids = discover_players()
    seasons = list(dict.fromkeys(args.seasons))
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    response_path = output_dir / "player_game_responses.jsonl"
    manifest_path = output_dir / "collection_manifest.json"
    latest = load_checkpoint(response_path)

    tasks = []
    for season in seasons:
        if season not in SEASON_LABELS:
            raise SystemExit(f"Unsupported season_id={season}. Allowed: {list(SEASON_LABELS)}")
        ids = sorted(season_ids.get(season, set()), key=int)
        if args.player_ids:
            ids = sorted({normalize_id(x) for x in args.player_ids if normalize_id(x)}, key=int)
        if args.max_players_per_season > 0:
            ids = ids[:args.max_players_per_season]
        for player_id in ids:
            key = f"{season}:{player_id}"
            prior = latest.get(key)
            if prior and prior.get("status") in {"ok", "empty"}:
                continue
            tasks.append((season, player_id, names.get(player_id, "")))

    print("API:", API_URL, flush=True)
    print("Known global player IDs:", len(all_ids), flush=True)
    print("Tasks to fetch:", len(tasks), flush=True)
    print("Already completed response keys:", sum(x.get("status") in {"ok", "empty"} for x in latest.values()), flush=True)
    if not tasks:
        print("No new requests required; normalizing saved checkpoint.", flush=True)

    start = time.monotonic()
    lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(max(1, args.concurrency))
    written = 0
    new_errors = 0

    async with httpx.AsyncClient(
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; DunkestHistoricalResearch/1.0)",
            "Accept": "application/json",
        },
        timeout=httpx.Timeout(30.0),
        follow_redirects=True,
        limits=httpx.Limits(max_connections=max(4, args.concurrency), max_keepalive_connections=max(4, args.concurrency)),
    ) as client:
        with response_path.open("a", encoding="utf-8") as stream:
            async def run_one(task: tuple[str, str, str]) -> None:
                nonlocal written, new_errors
                season, player_id, player_name = task
                rec = await fetch_one(client, semaphore, season, player_id, player_name, args.delay)
                async with lock:
                    stream.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")
                    stream.flush()
                    latest[f"{season}:{player_id}"] = rec
                    written += 1
                    if rec.get("status") == "error":
                        new_errors += 1
                    if written % 25 == 0 or written == len(tasks):
                        completed = [
                            key for key, value in latest.items()
                            if value.get("status") in {"ok", "empty"}
                        ]
                        errors = [
                            {"task": key, "error": value.get("error"), "http_status": value.get("http_status")}
                            for key, value in latest.items() if value.get("status") == "error"
                        ]
                        save_manifest(manifest_path, {
                            "updated_utc": datetime.now(timezone.utc).isoformat(),
                            "source_api": API_URL,
                            "season_labels": SEASON_LABELS,
                            "candidate_pool_notes": {
                                "season_ids_1_and_3": "union of every player ID found in local Dunkest historical datasets; not guaranteed to include every retired player from those seasons",
                                "season_ids_5_7_9_13_19": "season-specific IDs from the new weekly-round history table",
                            },
                            "known_global_player_ids": len(all_ids),
                            "completed_task_count": len(completed),
                            "error_task_count": len(errors),
                            "completed_tasks": sorted(completed),
                            "errors": errors,
                        })
                        elapsed = max(0.001, time.monotonic() - start)
                        print(
                            f"Progress {written}/{len(tasks)} new requests; "
                            f"success/empty={len(completed)} errors={len(errors)} "
                            f"elapsed={elapsed/60:.1f} min",
                            flush=True,
                        )

            await asyncio.gather(*(run_one(task) for task in tasks))

    combined, coverage, duplicate_rows, duplicate_audit = normalize_responses(latest, seasons, output_dir)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    combined_path = PROCESSED_DIR / "official_dunkest_player_games_2018-25_v1.parquet"
    coverage_path = PROCESSED_DIR / "official_dunkest_player_games_2018-25_v1_coverage.csv"
    duplicate_csv_path = PROCESSED_DIR / "official_dunkest_player_games_2018-25_v1_duplicate_rows.csv"
    audit_path = PROCESSED_DIR / "official_dunkest_player_games_2018-25_v1_audit.json"
    if not combined.empty:
        combined.to_parquet(combined_path, index=False)
    pd.DataFrame(coverage).to_csv(coverage_path, index=False)
    if duplicate_rows.empty:
        pd.DataFrame(columns=["season_id", "dunkest_player_id", "gameId", "duplicate_key_count", "duplicate_has_conflicting_values"]).to_csv(duplicate_csv_path, index=False)
    else:
        duplicate_rows.to_csv(duplicate_csv_path, index=False)
    duplicate_keys = 0
    if not combined.empty:
        duplicate_keys = int(combined.duplicated(["season_id", "dunkest_player_id", "gameId"]).sum())
    audit = {
        "source_api": API_URL,
        "seasons_requested": seasons,
        "season_labels": SEASON_LABELS,
        "raw_checkpoint": str(response_path),
        "combined_parquet": str(combined_path),
        "coverage_csv": str(coverage_path),
        "duplicate_rows_csv": str(duplicate_csv_path),
        "duplicate_audit": duplicate_audit,
        "rows": len(combined),
        "columns": combined.columns.tolist() if not combined.empty else [],
        "unique_player_ids_by_season": {
            s: int(g["dunkest_player_id"].nunique())
            for s, g in combined.groupby("season_id")
        } if not combined.empty else {},
        "duplicate_player_game_keys_after_dedup": duplicate_keys,
        "gameValidForDunkest_policy": "Retained true, false and missing values; no filtering applied.",
        "mapping_policy": "Dunkest gameId is retained as supplied and is not assumed to equal NBA GAME_ID.",
        "coverage_caveat": "Season IDs 1 and 3 use only the union of player IDs found in currently available local datasets; retired players absent from that universe may be missing.",
        "run_summary": coverage,
    }
    audit_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n=== GAME-LEVEL COLLECTION SUMMARY ===")
    print("Rows:", len(combined))
    print("Columns:", len(combined.columns) if not combined.empty else 0)
    print("New request errors:", new_errors)
    print(pd.DataFrame(coverage).to_string(index=False))
    print("\nOutputs:")
    print("Raw checkpoint:", response_path)
    print("Combined:", combined_path)
    print("Coverage:", coverage_path)
    print("Duplicate audit groups:", duplicate_audit["duplicate_groups"])
    print("Duplicate extra rows removed:", duplicate_audit["duplicate_extra_rows"])
    print("Conflicting duplicate groups:", duplicate_audit["conflicting_duplicate_groups"])
    print("Duplicate rows CSV:", duplicate_csv_path)
    print("Audit:", audit_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect official Dunkest player game histories for historical seasons.")
    parser.add_argument("--seasons", nargs="+", default=DEFAULT_SEASONS, help="Season IDs: 1 3 5 7 9 13 19.")
    parser.add_argument("--delay", type=float, default=0.08, help="Pause after each request, seconds.")
    parser.add_argument("--concurrency", type=int, default=4, help="Maximum concurrent HTTP requests.")
    parser.add_argument("--max-players-per-season", type=int, default=0, help="Optional test limit; 0 means all candidates.")
    parser.add_argument("--player-ids", nargs="+", default=None, help="Optional explicit player ID list (smoke tests).")
    parser.add_argument("--output-dir", default=str(DEFAULT_RAW_DIR), help="Raw response/checkpoint directory.")
    args = parser.parse_args()
    asyncio.run(collect(args))


if __name__ == "__main__":
    main()
