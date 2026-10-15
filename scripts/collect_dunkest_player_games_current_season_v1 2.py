#!/usr/bin/env python3
"""Collect official Dunkest per-player game results for the active season only.

Writes an append-only JSONL checkpoint and a separate season-specific Parquet.
It never rewrites the historical 2018-25 consolidated dataset.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

from dunkest.names import player_key

ROOT = Path(__file__).resolve().parents[1]
API_URL = "https://www.dunkest.com/api/player/games"
DEFAULT_RAW_DIR = ROOT / "data" / "raw" / "dunkest_player_games_current_2026-27_v1"
DEFAULT_SEASON_ID = "26"
DEFAULT_SEASON_LABEL = "2026-27"

# Explicit aliases are used only when the local official catalogue contains exactly
# one ID for the target slug. Never use fuzzy matching for player identities.
EXPLICIT_MARKET_ALIASES = {
    "alex sarr": "alexandre-sarr",
    "ron holland": "ronald-holland-ii",
    "carlton carrington": "bub-carrington",
    "nahshon hyland": "bones-hyland",
    "kenyon martin": "kj-martin",
    "elijah harkless": "ej-harkless",
}

# Reviewed duplicate-profile disambiguations. The selected ID has official 2025-26
# game-history rows; the competing duplicate profile has an empty history.
# Keep these overrides explicit and evidence-based rather than resolving by order.
EXPLICIT_MARKET_ID_OVERRIDES = {
    "dru smith": "1085",
    "jaylin williams": "1115",
}


def normalize_id(value: object) -> str | None:
    if pd.isna(value):
        return None
    value = str(value).strip()
    if value.endswith(".0"):
        value = value[:-2]
    return value if value.isdigit() else None


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def slug_name(value: object) -> str:
    return " ".join(part.capitalize() for part in str(value or "").split("-") if part)


def identity_keys(value: object) -> set[str]:
    """Generate conservative name variants for initial punctuation and known nickname forms."""
    base = player_key(value)
    if not base:
        return set()
    keys = {base}
    tokens = base.split()
    # Catalogs often store E.J. as EJ while a fantasy market formats it as E.J.
    compact = []
    i = 0
    while i < len(tokens):
        if len(tokens[i]) == 1:
            j = i
            while j < len(tokens) and len(tokens[j]) == 1:
                j += 1
            if j - i > 1:
                compact.append("".join(tokens[i:j]))
            else:
                compact.append(tokens[i])
            i = j
        else:
            compact.append(tokens[i])
            i += 1
    keys.add(" ".join(compact))
    # Explicit, common shortened first names; ambiguous catalog matches remain unresolved.
    if tokens:
        synonyms = {"nicolas": "nic", "nic": "nicolas", "nick": "nicholas", "nicholas": "nick"}
        if tokens[0] in synonyms:
            keys.add(" ".join([synonyms[tokens[0]], *tokens[1:]]))
    return {key for key in keys if key}


def load_catalog(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Player catalogue not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("players"), list):
        raise ValueError(f"Unexpected player catalogue schema: {path}")
    return payload


def resolve_ids(
    market_path: Path, catalog_path: Path
) -> tuple[list[dict[str, str]], pd.DataFrame, dict]:
    """Resolve frozen market names only to uniquely matched numeric Dunkest IDs."""
    market = pd.read_parquet(market_path) if market_path.suffix.lower() == ".parquet" else pd.read_csv(market_path)
    name_col = next((c for c in ("player_name", "name") if c in market.columns), None)
    if not name_col:
        raise ValueError(f"Frozen market has no player_name/name column: {market_path}")
    market_names = market[name_col].dropna().astype(str).str.strip()
    market_names = market_names[market_names.ne("")].drop_duplicates().tolist()

    all_market_names = list(market_names)
    # The Lineups market contains player and coach rows. Coaches have their own
    # score model and must never be queried as player-profile IDs.
    skipped_non_player: list[tuple[str, str]] = []
    if "role" in market.columns:
        role_lookup = {}
        for _, row in market[[name_col, "role"]].dropna(subset=[name_col]).iterrows():
            name = str(row[name_col]).strip()
            role_lookup[name] = str(row["role"] or "").strip().upper()
        player_names = []
        for name in market_names:
            role = role_lookup.get(name, "")
            if role in {"HC", "COACH", "HEAD COACH", "HEAD_COACH"}:
                skipped_non_player.append((name, role))
            else:
                player_names.append(name)
        market_names = player_names

    catalog = load_catalog(catalog_path)
    by_name: dict[str, set[str]] = defaultdict(set)
    name_variants: dict[str, set[str]] = defaultdict(set)
    ids_to_names: dict[str, set[str]] = defaultdict(set)
    by_slug: dict[str, set[str]] = defaultdict(set)
    for item in catalog["players"]:
        player_id = normalize_id(item.get("player_id"))
        if not player_id:
            continue
        slug = str(item.get("slug", "")).strip().lower()
        if slug:
            by_slug[slug].add(player_id)
        variants = {
            str(item.get("display_name", "")).strip(),
            slug_name(item.get("slug")),
        }
        variants.discard("")
        for name in variants:
            for key in identity_keys(name):
                if key:
                    by_name[key].add(player_id)
                    name_variants[key].add(name)
            ids_to_names[player_id].add(name)

    tasks: list[dict[str, str]] = []
    audit_rows: list[dict[str, Any]] = [
        {
            "market_player_name": name,
            "normalized_key": player_key(name),
            "candidate_ids": "",
            "candidate_names": "",
            "resolution": "skipped_non_player_role",
            "resolved_player_id": "",
            "market_role": role,
        }
        for name, role in skipped_non_player
    ]
    for name in market_names:
        key = player_key(name)
        candidate_ids_set = set().union(*(by_name.get(alias, set()) for alias in identity_keys(name)))
        alias_slug = EXPLICIT_MARKET_ALIASES.get(key)
        alias_ids = by_slug.get(alias_slug, set()) if alias_slug else set()
        explicit_id = EXPLICIT_MARKET_ID_OVERRIDES.get(key)
        # Explicit aliases are authoritative only if they identify one catalogue ID.
        if explicit_id and explicit_id in ids_to_names:
            candidate_ids_set = {explicit_id}
        elif alias_ids:
            candidate_ids_set = set(alias_ids)
        candidate_ids = sorted(candidate_ids_set, key=int)
        candidate_names = sorted({
            catalog_name
            for candidate_id in candidate_ids
            for catalog_name in ids_to_names.get(candidate_id, set())
        })
        if len(candidate_ids) == 1:
            player_id = candidate_ids[0]
            canonical = sorted(ids_to_names.get(player_id, {name}))[0]
            tasks.append({
                "player_id": player_id,
                "player_name": name,
                "catalog_name": canonical,
            })
            audit_rows.append({
                "market_player_name": name,
                "normalized_key": key,
                "candidate_ids": ";".join(candidate_ids),
                "candidate_names": ";".join(candidate_names),
                "resolution": (
                    "explicit_id_override" if explicit_id and player_id == explicit_id
                    else "explicit_alias_match" if alias_ids and player_id in alias_ids
                    else "unique_name_match"
                ),
                "resolved_player_id": player_id,
            })
        else:
            audit_rows.append({
                "market_player_name": name,
                "normalized_key": key,
                "candidate_ids": ";".join(candidate_ids),
                "candidate_names": ";".join(candidate_names),
                "resolution": "unmatched" if not candidate_ids else "ambiguous",
                "resolved_player_id": "",
            })
    audit = pd.DataFrame(audit_rows)
    resolved_ids = {x["player_id"] for x in tasks}
    if len(resolved_ids) != len(tasks):
        # One Dunkest ID must not silently stand for multiple market players.
        repeated: dict[str, list[str]] = defaultdict(list)
        for task in tasks:
            repeated[task["player_id"]].append(task["player_name"])
        collisions = {k: v for k, v in repeated.items() if len(v) > 1}
        if collisions:
            raise ValueError(f"Different market names resolve to the same Dunkest IDs: {collisions}")
    summary = {
        "market_path": str(market_path),
        "catalog_path": str(catalog_path),
        "market_unique_names": len(all_market_names),
        "player_names_considered": len(market_names),
        "skipped_non_player_names": len(skipped_non_player),
        "resolved_unique_ids": len(tasks),
        "unmatched_names": int(audit["resolution"].eq("unmatched").sum()),
        "ambiguous_names": int(audit["resolution"].eq("ambiguous").sum()),
        "catalog_entries": len(catalog["players"]),
    }
    return tasks, audit, summary


def select_pending_tasks(
    tasks: list[dict[str, str]],
    latest: dict[str, dict[str, Any]],
    *,
    resume: bool = False,
    refresh: bool = False,
    limit: int = 0,
) -> list[dict[str, str]]:
    """Select requests; by default refresh the full-season API response every run.

    Dunkest returns a player's season-to-date game list, so a cached successful
    response becomes stale as soon as a new game is played. The --resume flag
    is an explicit opt-in to reusing successful checkpoint responses after an
    interrupted run. --refresh remains a compatibility alias that forces
    requests even when resume was also supplied.
    """
    pending = []
    for task in tasks:
        prior = latest.get(task["player_id"])
        if resume and not refresh and prior and prior.get("status") in {"ok", "empty"}:
            continue
        pending.append(task)
    return pending[:limit] if limit > 0 else pending


def should_publish_normalized_output(data: pd.DataFrame, limit: int) -> bool:
    """Do not publish diagnostic --limit runs to the canonical season dataset."""
    return not data.empty and limit <= 0


def publish_normalized_output(data: pd.DataFrame, output_path: Path, limit: int) -> str:
    """Publish complete non-empty output; otherwise leave any existing file untouched."""
    if limit > 0:
        return "suppressed_due_to_limit"
    if data.empty:
        return "no_rows_no_publish"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data.to_parquet(output_path, index=False)
    return "published"


def load_checkpoint(path: Path) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return latest
    content = path.read_bytes()
    end = content.rfind(b"\n")
    if end < 0:
        return latest
    for line in content[: end + 1].splitlines():
        try:
            item = json.loads(line)
            if item.get("season_id") == DEFAULT_SEASON_ID and normalize_id(item.get("player_id")):
                player_id = str(item["player_id"])
                previous = latest.get(player_id)
                previous_is_success = previous and previous.get("status") in {"ok", "empty"}
                current_is_success = item.get("status") in {"ok", "empty"}
                # A failed refresh must not erase the last usable response.
                if current_is_success or not previous_is_success:
                    latest[player_id] = item
        except (json.JSONDecodeError, TypeError):
            continue
    return latest


async def fetch_one(
    client: httpx.AsyncClient, semaphore: asyncio.Semaphore,
    task: dict[str, str], delay: float,
) -> dict[str, Any]:
    async with semaphore:
        last_error = ""
        last_status = None
        for attempt in range(1, 4):
            try:
                response = await client.get(
                    API_URL,
                    params={"player_id": task["player_id"], "season_id": DEFAULT_SEASON_ID},
                )
                last_status = response.status_code
                if response.status_code in {408, 425, 429} or response.status_code >= 500:
                    last_error = f"HTTP {response.status_code}: {response.text[:250]}"
                    if attempt < 3:
                        await asyncio.sleep(0.5 * attempt)
                        continue
                    break
                if response.status_code != 200:
                    return {
                        **task, "season_id": DEFAULT_SEASON_ID, "season_label": DEFAULT_SEASON_LABEL,
                        "status": "error", "http_status": response.status_code, "returned_rows": 0,
                        "records": [], "error": response.text[:500],
                    }
                payload = response.json()
                if not isinstance(payload, list) or any(not isinstance(x, dict) for x in payload):
                    return {
                        **task, "season_id": DEFAULT_SEASON_ID, "season_label": DEFAULT_SEASON_LABEL,
                        "status": "error", "http_status": response.status_code, "returned_rows": 0,
                        "records": [], "error": "Unexpected API schema; expected a list of game objects.",
                    }
                await asyncio.sleep(delay)
                return {
                    **task, "season_id": DEFAULT_SEASON_ID, "season_label": DEFAULT_SEASON_LABEL,
                    "status": "ok" if payload else "empty", "http_status": response.status_code,
                    "returned_rows": len(payload), "records": payload, "error": None,
                    "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
                }
            except (httpx.HTTPError, ValueError) as exc:
                last_error = repr(exc)
                if attempt < 3:
                    await asyncio.sleep(0.5 * attempt)
        await asyncio.sleep(delay)
        return {
            **task, "season_id": DEFAULT_SEASON_ID, "season_label": DEFAULT_SEASON_LABEL,
            "status": "error", "http_status": last_status, "returned_rows": 0,
            "records": [], "error": last_error or "request failed after retries",
            "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        }


def normalize_results(latest: dict[str, dict[str, Any]]) -> tuple[pd.DataFrame, list[dict]]:
    records = []
    coverage = []
    for player_id, result in latest.items():
        if result.get("status") not in {"ok", "empty"}:
            continue
        for raw in result.get("records", []):
            row = dict(raw)
            row["_requested_player_id"] = str(player_id)
            row["_requested_player_name"] = result.get("player_name", "")
            row["season_id"] = DEFAULT_SEASON_ID
            row["season_label"] = DEFAULT_SEASON_LABEL
            row["source_api"] = API_URL
            row["source_fetched_at_utc"] = result.get("fetched_at_utc")
            records.append(row)
    data = pd.DataFrame(records)
    if not data.empty:
        if "gameDate" in data:
            data["gameDate"] = pd.to_datetime(data["gameDate"], errors="coerce").dt.strftime("%Y-%m-%d")
        if "pdk" in data:
            data["pdk"] = pd.to_numeric(data["pdk"], errors="coerce")
        if "gameValidForDunkest" in data:
            # Never filter false/missing official validity flags out of the saved output.
            data["gameValidForDunkest"] = data["gameValidForDunkest"].astype("boolean")
        keys = [c for c in ("season_id", "_requested_player_id", "gameId") if c in data]
        if keys and data.duplicated(keys, keep=False).any():
            duplicates = data.loc[data.duplicated(keys, keep=False)]
            values = [c for c in data.columns if c not in keys]
            conflicts = []
            for key, group in duplicates.groupby(keys, dropna=False):
                diff = [c for c in values if group[c].astype("string").fillna("<NA>").nunique(dropna=False) > 1]
                if diff:
                    conflicts.append({"key": list(key) if isinstance(key, tuple) else [key], "columns": diff})
            if conflicts:
                raise ValueError(f"Conflicting official player-game duplicate keys: {conflicts[:5]}")
            data = data.drop_duplicates(keys, keep="first")
        sort = [c for c in ("gameDate", "_requested_player_id", "gameId") if c in data]
        data = data.sort_values(sort, kind="stable").reset_index(drop=True)
    return data, coverage


async def collect(args: argparse.Namespace) -> None:
    data_dir = Path(args.data_dir).expanduser().resolve()
    market_path = Path(args.market).expanduser().resolve()
    catalog_path = Path(args.catalog).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser()
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    response_path = output_dir / "player_game_responses.jsonl"
    manifest_path = output_dir / "collection_manifest.json"
    mapping_path = output_dir / "player_id_resolution.csv"
    output_path = data_dir / "processed" / f"official_dunkest_player_games_{DEFAULT_SEASON_LABEL}.parquet"
    audit_path = data_dir / "processed" / f"official_dunkest_player_games_{DEFAULT_SEASON_LABEL}_audit.json"

    tasks, resolution_audit, resolution_summary = resolve_ids(market_path, catalog_path)
    resolution_audit.to_csv(mapping_path, index=False)
    latest = load_checkpoint(response_path)
    requested_ids = {task["player_id"] for task in tasks}
    latest = {key: value for key, value in latest.items() if key in requested_ids}
    pending = select_pending_tasks(
        tasks,
        latest,
        resume=args.resume,
        refresh=args.refresh,
        limit=args.limit,
    )
    request_mode = "resume_checkpoint" if args.resume and not args.refresh else "refresh_all"
    print(json.dumps({
        "resolution": resolution_summary,
        "request_mode": request_mode,
        "checkpoint_completed": sum(x.get("status") in {"ok", "empty"} for x in latest.values()),
        "pending_requests": len(pending),
        "resolution_audit": str(mapping_path),
    }, indent=2), flush=True)

    semaphore = asyncio.Semaphore(max(1, args.concurrency))
    lock = asyncio.Lock()
    start = time.monotonic()
    completed_new = 0
    error_attempts_this_run: list[dict[str, Any]] = []
    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0 (compatible; DunkestCurrentSeasonResults/1.0)", "Accept": "application/json"},
        timeout=httpx.Timeout(30.0), follow_redirects=True,
        limits=httpx.Limits(max_connections=max(4, args.concurrency), max_keepalive_connections=max(4, args.concurrency)),
    ) as client:
        with response_path.open("a", encoding="utf-8") as stream:
            async def one(task: dict[str, str]) -> None:
                nonlocal completed_new
                result = await fetch_one(client, semaphore, task, args.delay)
                async with lock:
                    stream.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
                    stream.flush()
                    prior = latest.get(task["player_id"])
                    if result.get("status") == "error":
                        error_attempts_this_run.append({
                            "player_id": task["player_id"],
                            "player_name": task.get("player_name"),
                            "error": result.get("error"),
                            "http_status": result.get("http_status"),
                        })
                        if not prior or prior.get("status") not in {"ok", "empty"}:
                            latest[task["player_id"]] = result
                    else:
                        latest[task["player_id"]] = result
                    completed_new += 1
                    if completed_new % 25 == 0 or completed_new == len(pending):
                        manifest = {
                            "updated_utc": datetime.now(timezone.utc).isoformat(),
                            "season_id": DEFAULT_SEASON_ID, "season_label": DEFAULT_SEASON_LABEL,
                            "source_api": API_URL,
                            "request_mode": request_mode,
                            "requested_ids": len(tasks),
                            "completed_responses": sum(x.get("status") in {"ok", "empty"} for x in latest.values()),
                            "error_responses": sum(x.get("status") == "error" for x in latest.values()),
                            "error_attempts_this_run": len(error_attempts_this_run),
                            "catalog_resolution": resolution_summary,
                            "checkpoint_sha256": sha256_bytes(response_path.read_bytes()),
                        }
                        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
                        print(f"progress={completed_new}/{len(pending)} total_success={manifest['completed_responses']} errors={manifest['error_responses']} elapsed_min={(time.monotonic()-start)/60:.1f}", flush=True)
            await asyncio.gather(*(one(task) for task in pending))

    data, _ = normalize_results(latest)
    data_dir.joinpath("processed").mkdir(parents=True, exist_ok=True)
    # Write a separate, season-specific output only. Do not touch 2018-25 assets.
    # Diagnostic --limit runs and empty collections must leave any existing canonical output untouched.
    normalized_output_status = publish_normalized_output(data, output_path, args.limit)
    if normalized_output_status != "published":
        output_path = None
    fetched_ok = sum(x.get("status") in {"ok", "empty"} for x in latest.values())
    errors = [{"player_id": pid, "player_name": x.get("player_name"), "error": x.get("error"), "http_status": x.get("http_status")} for pid, x in latest.items() if x.get("status") == "error"]
    audit = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "season_id": DEFAULT_SEASON_ID, "season_label": DEFAULT_SEASON_LABEL,
        "source_api": API_URL,
        "request_mode": request_mode,
        "market_id_resolution": resolution_summary,
        "requests": {
            "unique_player_ids_resolved": len(tasks),
            "successful_or_empty": fetched_ok,
            "errors": len(errors),
            "error_attempts_this_run": len(error_attempts_this_run),
            "new_requests_this_run": completed_new,
        },
        "refresh_errors_this_run": error_attempts_this_run,
        "game_rows": len(data),
        "official_validity_counts": {
            "true": int(data["gameValidForDunkest"].eq(True).sum()) if not data.empty and "gameValidForDunkest" in data else 0,
            "false": int(data["gameValidForDunkest"].eq(False).sum()) if not data.empty and "gameValidForDunkest" in data else 0,
            "missing": int(data["gameValidForDunkest"].isna().sum()) if not data.empty and "gameValidForDunkest" in data else 0,
        },
        "date_min": data["gameDate"].min() if not data.empty and "gameDate" in data else None,
        "date_max": data["gameDate"].max() if not data.empty and "gameDate" in data else None,
        "checkpoint": str(response_path),
        "checkpoint_sha256": sha256_bytes(response_path.read_bytes()) if response_path.exists() else None,
        "normalized_output": str(output_path) if output_path else None,
        "normalized_output_status": normalized_output_status,
        "id_resolution_audit": str(mapping_path),
        "errors": errors,
        "policy": "Preserve gameValidForDunkest true/false/null; never infer NBA fixture IDs from Dunkest gameId.",
    }
    audit_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"audit": str(audit_path), "normalized_output": audit["normalized_output"], "normalized_output_status": normalized_output_status, "game_rows": len(data), "id_resolution": resolution_summary, "requests": audit["requests"]}, indent=2, ensure_ascii=False), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data", help="Project data directory.")
    parser.add_argument("--market", default="data/processed/player_credits_26_gw1.parquet", help="Frozen market/roster with Dunkest player names.")
    parser.add_argument("--catalog", default="data/raw/dunkest_player_games_history_v1/player_catalog_current.json")
    parser.add_argument("--output-dir", default=str(DEFAULT_RAW_DIR), help="Dedicated raw checkpoint directory.")
    parser.add_argument("--delay", type=float, default=0.08)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0, help="Request only the first N pending IDs; 0 means all unresolved IDs.")
    parser.add_argument("--resume", action="store_true", help="Reuse successful checkpoint responses; may be stale if new games have been played.")
    parser.add_argument("--refresh", action="store_true", help="Force refresh even when --resume is also supplied (default behavior without --resume).")
    args = parser.parse_args()
    asyncio.run(collect(args))


if __name__ == "__main__":
    main()
