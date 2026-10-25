"""Versioned, best-effort collector for the official Dunkest DvP tables.

This module only captures and validates source data. It does not alter forecasts.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from bs4 import BeautifulSoup

from dunkest.config import Settings
from dunkest.data.dunkest.client import INJURY_TEAM_NAMES

SCHEMA_VERSION = 2
SOURCE_TEMPLATE = (
    "https://www.dunkest.com/en/nba/stats/teams/defense-vs-position/"
    "regular-season/{season_slug}"
)
EXPECTED_POSITIONS = {"Guards", "Forwards", "Centers"}
EXPECTED_WINDOWS = ("L3", "L5", "L10", "ALL")
EXPECTED_STATS = {
    "Points", "Rebounds", "Assists", "Steals", "Blocks", "Turnovers",
    "3 Point Field Goals Made", "Fantasy Points",
}
THRESHOLD_TEXT = "calculated on at least 28 minutes played"
DVP_TRANSFORM_VERSION = "dvp_pdk_relative_windows_v1"
# L3/L5/L10 overlap; their combined weight is deliberately smaller than ALL.
DVP_WINDOW_WEIGHTS = {"ALL": 0.65, "L10": 0.20, "L5": 0.10, "L3": 0.05}
POSITION_TO_DVP = {"G": "Guards", "F": "Forwards", "C": "Centers"}


def season_slug(season: str) -> str:
    """Expand the repository's YYYY-YY season notation for the official page."""
    match = re.fullmatch(r"(\d{4})-(\d{2}|\d{4})", str(season).strip())
    if not match:
        raise ValueError(f"Unsupported Dunkest season notation: {season!r}")
    start, end = match.groups()
    end_year = end if len(end) == 4 else start[:2] + end
    if int(end_year) != int(start) + 1:
        raise ValueError(f"Non-consecutive season notation: {season!r}")
    return f"{start}-{end_year}"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_frame_sha256(frame: pd.DataFrame) -> str:
    payload = json.dumps(
        frame.to_dict(orient="records"), sort_keys=True,
        ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")
    return _sha256(payload)


def _source_options(soup: BeautifulSoup, selector: str) -> list[dict[str, str]]:
    element = soup.select_one(selector)
    if element is None:
        raise ValueError(f"DvP page missing selector {selector}")
    return [
        {"label": " ".join(option.get_text(" ", strip=True).split()), "value": str(option.get("value", ""))}
        for option in element.select("option")
        if option.get("value") is not None
    ]


def inspect_source_schema(html: str) -> dict[str, Any]:
    """Read option labels/IDs and source prose from the acquired page itself."""
    soup = BeautifulSoup(html, "html.parser")
    season = _source_options(soup, "select#seasonSelect")
    positions = _source_options(soup, "select#positionSelect")
    stats = _source_options(soup, "select#statsSelect")
    text = " ".join(soup.stripped_strings)
    headers = [" ".join(cell.get_text(" ", strip=True).split()) for cell in soup.select("table thead th")]
    threshold_match = re.search(
        r"Discover the average.*?calculated on at least 28 minutes played",
        text, flags=re.IGNORECASE,
    )
    meaning_match = re.search(
        r"Defences are ranked from the top.*?opposing player\.",
        text, flags=re.IGNORECASE,
    )
    return {
        "seasons": season,
        "positions": positions,
        "statistics": stats,
        "headers": headers,
        "threshold_text": threshold_match.group(0) if threshold_match else None,
        "meaning_text": meaning_match.group(0) if meaning_match else None,
    }


def parse_dvp_table(
    html: str,
    *,
    season_id: str,
    season_label: str,
    position: str,
    position_id: str,
    statistic: str,
    statistic_id: str,
    source_url: str,
    acquired_at_utc: str,
    raw_html_sha256: str | None = None,
) -> list[dict[str, Any]]:
    """Parse one observed table; reject shape/value/mapping errors fail closed."""
    soup = BeautifulSoup(html, "html.parser")
    header = [" ".join(cell.get_text(" ", strip=True).split()) for cell in soup.select("table thead th")]
    if header[:2] != ["#", "Team"] or tuple(header[2:]) != EXPECTED_WINDOWS:
        raise ValueError(f"Unexpected DvP table headers: {header!r}")
    output: list[dict[str, Any]] = []
    seen_teams: set[str] = set()
    seen_ranks: set[int] = set()
    for row in soup.select("table tbody tr"):
        rank_cell = row.select_one("th[scope='row']")
        cells = row.select("td")
        if rank_cell is None or len(cells) != 5:
            raise ValueError("Unexpected DvP row structure; expected rank header and five data cells")
        rank_text = rank_cell.get_text(" ", strip=True)
        team_name = " ".join(cells[0].get_text(" ", strip=True).split())
        team_code = INJURY_TEAM_NAMES.get(team_name)
        if team_code is None:
            raise ValueError(f"Unmapped DvP team name: {team_name!r}")
        if team_code in seen_teams:
            raise ValueError(f"Duplicate DvP team code: {team_code}")
        try:
            rank = int(rank_text)
        except ValueError as exc:
            raise ValueError(f"Invalid DvP rank: {rank_text!r}") from exc
        if rank in seen_ranks:
            raise ValueError(f"Duplicate DvP rank: {rank}")
        seen_teams.add(team_code)
        seen_ranks.add(rank)
        for window, cell in zip(EXPECTED_WINDOWS, cells[1:], strict=True):
            original = cell.get_text(" ", strip=True)
            try:
                value = float(original.replace(",", ""))
            except ValueError as exc:
                raise ValueError(f"Invalid DvP numeric value {original!r}") from exc
            if not math.isfinite(value):
                raise ValueError(f"Non-finite DvP value {original!r}")
            output.append({
                "schema_version": SCHEMA_VERSION,
                "season_id": str(season_id), "season_label": season_label,
                "reference_period": "regular-season", "reference_gameweek": None,
                "position": position, "position_id": str(position_id),
                "statistic": statistic, "statistic_id": str(statistic_id),
                "window": window, "team_name_source": team_name, "team_code": team_code,
                "value_original": original, "value": value,
                "source_rank": rank, "source_rank_window": "ALL",
                "source_sort_order": "desc", "source_url": source_url,
                "acquired_at_utc": acquired_at_utc,
                "raw_html_sha256": raw_html_sha256 or _sha256(html.encode("utf-8")),
                "value_semantics": "source average conceded by defensive team; retain source units",
            })
    if len(seen_teams) != 30 or seen_ranks != set(range(1, 31)):
        raise ValueError(f"Incomplete DvP team table: {len(seen_teams)} teams, ranks={sorted(seen_ranks)}")
    return output


def validate_capture(records: list[dict[str, Any]], schema: dict[str, Any], season_id: str) -> list[str]:
    errors: list[str] = []
    positions = {row["label"] for row in schema["positions"]}
    stats = {row["label"] for row in schema["statistics"]}
    if positions != EXPECTED_POSITIONS:
        errors.append(f"position schema changed: {sorted(positions)}")
    if stats != EXPECTED_STATS:
        errors.append(f"statistic schema changed: {sorted(stats)}")
    if set(schema["headers"]) != {"#", "Team", *EXPECTED_WINDOWS}:
        errors.append(f"table header schema changed: {schema['headers']}")
    if not schema.get("threshold_text"):
        errors.append("source 28-minute threshold text is missing")
    combo_expected = len(positions) * len(stats)
    combos = {(row["position"], row["statistic"]) for row in records}
    if len(combos) != combo_expected:
        errors.append(f"expected {combo_expected} position/statistic combinations, got {len(combos)}")
    if len(records) != combo_expected * 30 * len(EXPECTED_WINDOWS):
        errors.append(f"expected {combo_expected * 30 * len(EXPECTED_WINDOWS)} records, got {len(records)}")
    for position in positions:
        for stat in stats:
            rows = [row for row in records if row["position"] == position and row["statistic"] == stat]
            for window in EXPECTED_WINDOWS:
                subset = [row for row in rows if row["window"] == window]
                if len(subset) != 30 or len({row["team_code"] for row in subset}) != 30:
                    errors.append(f"incomplete/duplicate teams for {position}/{stat}/{window}")
    if any(str(row["season_id"]) != str(season_id) for row in records):
        errors.append("captured season ID differs from requested season")
    return errors


def _capture_tables(settings: Settings, *, source_url: str) -> tuple[list[dict], dict, list[str]]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_default_timeout(settings.http_timeout * 1000)
        response = page.goto(source_url, wait_until="domcontentloaded", timeout=settings.http_timeout * 1000)
        if response is None or response.status != 200:
            raise RuntimeError(f"DvP source returned HTTP {getattr(response, 'status', None)}")
        page.wait_for_selector("select#seasonSelect, table thead th", state="attached")
        initial_html = page.content()
        schema = inspect_source_schema(initial_html)
        requested_season = season_slug(settings.season)
        selected = page.locator("select#seasonSelect option:checked").first
        season_label = selected.inner_text().strip()
        season_id = selected.get_attribute("value")
        if requested_season not in source_url or requested_season not in season_label.replace("/", "-"):
            raise RuntimeError(f"Displayed source season does not match {requested_season}: {season_label!r}")
        records: list[dict] = []
        failures: list[str] = []
        for position in schema["positions"]:
            for stat in schema["statistics"]:
                try:
                    page.locator("select#positionSelect").select_option(position["value"])
                    page.locator("select#statsSelect").select_option(stat["value"])
                    expected_query = f"stats_id={stat['value']}"
                    page.wait_for_function(
                        "([s,p]) => location.search.includes('stats_id='+s) && location.search.includes('position_id='+p)",
                        arg=[stat["value"], position["value"]], timeout=settings.http_timeout * 1000,
                    )
                    page.wait_for_function(
                        "() => document.querySelectorAll('table tbody tr').length === 30",
                        timeout=settings.http_timeout * 1000,
                    )
                    html = page.content()
                    current_url = page.url
                    if expected_query not in current_url or f"position_id={position['value']}" not in current_url:
                        raise ValueError("Selected DvP controls do not match the resulting URL")
                    if "sort_by=all" not in current_url or "sort_order=desc" not in current_url:
                        raise ValueError("Source rank sort changed or is not verifiable from the resulting URL")
                    records.extend(parse_dvp_table(
                        html, season_id=str(season_id), season_label=season_label,
                        position=position["label"], position_id=position["value"],
                        statistic=stat["label"], statistic_id=stat["value"],
                        source_url=current_url,
                        acquired_at_utc=datetime.now(timezone.utc).isoformat(),
                    ))
                except Exception as exc:
                    failures.append(f"{position['label']}/{stat['label']}: {type(exc).__name__}: {exc}")
        browser.close()
    errors = failures + validate_capture(records, schema, str(season_id))
    return records, {**schema, "season_id": str(season_id), "season_label": season_label}, errors


def _persist_capture_diagnostic(
    settings: Settings, *, source_url: str, acquired_at: str, status: str,
    errors: list[str], records: list[dict[str, Any]] | None = None,
    schema: dict[str, Any] | None = None,
) -> Path:
    """Persist a failed/partial attempt as explicitly non-evaluable evidence."""
    records = records or []
    schema = schema or {}
    captured = sorted({(row.get("position"), row.get("statistic")) for row in records})
    expected = {
        (position.get("label"), statistic.get("label"))
        for position in schema.get("positions", [])
        for statistic in schema.get("statistics", [])
    }
    captured_set = set(captured)
    failed = sorted({
        pair for pair in expected - captured_set
        if pair[0] is not None and pair[1] is not None
    })
    diagnostic_payload = json.dumps(
        {"status": status, "errors": errors, "captured": captured, "failed": failed},
        sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")
    digest = _sha256(diagnostic_payload)
    season_id = str(schema.get("season_id") or settings.dunkest_stats_season_id or settings.season_id)
    base = settings.data_path / "processed" / "dunkest_dvp" / season_id
    base.mkdir(parents=True, exist_ok=True)
    snapshot_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}_{digest[:12]}"
    destination = base / snapshot_id
    staging = base / f".{snapshot_id}.tmp"
    staging.mkdir(exist_ok=False)
    try:
        record_info = None
        if records:
            payload = pd.DataFrame.from_records(records).to_parquet(index=False)
            (staging / "partial_records.parquet").write_bytes(payload)
            record_info = {"path": "partial_records.parquet", "rows": len(records), "sha256": _sha256(payload)}
        manifest = {
            "schema_version": SCHEMA_VERSION, "snapshot_id": snapshot_id,
            "status": status, "evaluable": False,
            "season": settings.season, "season_id": season_id,
            "acquired_at_utc": acquired_at,
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_url": source_url, "source": "official_dunkest_defense_vs_position_page",
            "source_schema": schema, "acquired_combinations": [list(pair) for pair in captured],
            "failed_combinations": [list(pair) for pair in failed],
            "errors": errors, "partial_records": record_info,
            "diagnostic_sha256": digest,
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        staging.rename(destination)
    except Exception:
        raise
    return destination / "manifest.json"


def capture_dvp_snapshot(settings: Settings, *, forecast_timestamp_utc: str | None = None) -> dict[str, Any]:
    """Acquire and immutably persist a complete snapshot, or raise with details."""
    acquired = datetime.now(timezone.utc)
    acquired_at = acquired.isoformat()
    forecast_at = None
    if forecast_timestamp_utc:
        forecast_at = pd.Timestamp(forecast_timestamp_utc)
        if forecast_at.tzinfo is None:
            raise ValueError("Forecast timestamp must include a timezone")
        if acquired > forecast_at.to_pydatetime().astimezone(timezone.utc):
            raise ValueError("DvP capture occurred after the forecast timestamp")
    url = SOURCE_TEMPLATE.format(season_slug=season_slug(settings.season))
    try:
        records, schema, errors = _capture_tables(settings, source_url=url)
    except Exception as exc:
        detail = f"{type(exc).__name__}: {str(exc)[:500]}"
        diagnostic_path = _persist_capture_diagnostic(
            settings, source_url=url, acquired_at=acquired_at, status="failed", errors=[detail]
        )
        raise RuntimeError(f"DvP capture failed; diagnostic manifest: {diagnostic_path}; {detail}") from exc
    completed_at = datetime.now(timezone.utc).isoformat()
    if forecast_at is not None and pd.Timestamp(completed_at) > forecast_at:
        raise ValueError("DvP capture completed after the forecast timestamp")
    if errors:
        diagnostic_path = _persist_capture_diagnostic(
            settings, source_url=url, acquired_at=acquired_at, status="incomplete",
            errors=errors, records=records, schema=schema,
        )
        raise RuntimeError(
            f"DvP capture incomplete; diagnostic manifest: {diagnostic_path}; " + "; ".join(errors)
        )
    frame = pd.DataFrame.from_records(records)
    table_bytes = frame.to_parquet(index=False)
    table_hash = _sha256(table_bytes)
    canonical = json.dumps(records, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    content_hash = _sha256(canonical)
    base = settings.data_path / "processed" / "dunkest_dvp" / str(schema["season_id"])
    base.mkdir(parents=True, exist_ok=True)
    snapshot_id = f"{acquired.strftime('%Y%m%dT%H%M%S%fZ')}_{content_hash[:12]}"
    destination = base / snapshot_id
    if destination.exists():
        raise FileExistsError(f"Immutable DvP snapshot already exists: {destination}")
    staging = base / f".{snapshot_id}.tmp"
    staging.mkdir(exist_ok=False)
    try:
        table_path = staging / "records.parquet"
        table_path.write_bytes(table_bytes)
        manifest = {
            "schema_version": SCHEMA_VERSION, "snapshot_id": snapshot_id,
            "status": "complete", "season": settings.season,
            "season_id": schema["season_id"], "season_label": schema["season_label"],
            "acquired_at_utc": acquired_at, "forecast_timestamp_utc": forecast_timestamp_utc,
            "completed_at_utc": completed_at,
            "source_url": url, "final_source_url": records[0]["source_url"],
            "source": "official_dunkest_defense_vs_position_page",
            "source_schema": schema, "threshold_text": schema.get("threshold_text"),
            "semantics": schema.get("meaning_text") or "Official Defense vs Position table; raw values retained.",
            "rank_semantics": "rank displayed by source; source order was observed descending for ALL",
            "records": len(records), "positions": sorted({row["position"] for row in records}),
            "statistics": sorted({row["statistic"] for row in records}),
            "windows": list(EXPECTED_WINDOWS), "team_count_per_combination": 30,
            "content_sha256": content_hash, "records_parquet_sha256": _sha256(table_bytes),
            "records_path": "records.parquet", "errors": [],
        }
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        staging.rename(destination)
    except Exception:
        # Keep any failed temporary contents for diagnosis; never touch prior snapshots.
        raise
    return {
        "status": "complete", "schema_version": SCHEMA_VERSION,
        "snapshot_id": snapshot_id, "path": str(destination / "records.parquet"),
        "manifest_path": str(destination / "manifest.json"),
        "sha256": _sha256(table_bytes), "content_sha256": content_hash,
        "acquired_at_utc": acquired_at, "records": len(records),
        "source_url": url, "season_id": schema["season_id"],
    }


def capture_optional_snapshot(settings: Settings, *, collector=None) -> dict[str, Any]:
    """Best-effort runtime hook; DvP failure is explicit and never blocks forecasts."""
    capture = collector or capture_dvp_snapshot
    try:
        return capture(settings)
    except Exception as exc:
        descriptor = {
            "status": "unavailable",
            "reason": f"{type(exc).__name__}: {str(exc)[:500]}",
        }
        warnings.warn(
            f"DvP snapshot unavailable; forecasts continue without DvP: {descriptor['reason']}",
            RuntimeWarning,
        )
        return descriptor


def latest_eligible_snapshot(
    data_path: Path, *, cutoff_utc: str, season_id: str
) -> dict[str, Any] | None:
    """Return latest complete hash-valid capture strictly before a forecast cutoff."""
    cutoff = pd.Timestamp(cutoff_utc)
    if cutoff.tzinfo is None:
        raise ValueError("Cutoff timestamp must include a timezone")
    root = Path(data_path) / "processed" / "dunkest_dvp"
    candidates = []
    if not root.exists():
        return None
    for manifest_path in root.glob("*/*/manifest.json"):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if str(manifest.get("season_id")) != str(season_id):
                continue
            captured = pd.Timestamp(manifest["acquired_at_utc"])
            completed = pd.Timestamp(manifest["completed_at_utc"])
            record_path = manifest_path.parent / manifest["records_path"]
            if manifest.get("status") != "complete" or manifest.get("schema_version") != SCHEMA_VERSION:
                continue
            if (
                captured.tzinfo is None or completed.tzinfo is None
                or captured >= cutoff or completed >= cutoff or not record_path.is_file()
            ):
                continue
            if _sha256(record_path.read_bytes()) != manifest.get("records_parquet_sha256"):
                continue
            frame = pd.read_parquet(record_path)
            expected_records = int(manifest.get("records", -1))
            if len(frame) != expected_records or frame.empty:
                continue
            if _canonical_frame_sha256(frame) != manifest.get("content_sha256"):
                continue
            required = {"season_id", "position", "statistic", "window", "team_code", "acquired_at_utc"}
            if not required.issubset(frame.columns):
                continue
            record_times = pd.to_datetime(frame["acquired_at_utc"], utc=True, errors="coerce")
            if record_times.isna().any() or (record_times >= cutoff).any():
                continue
            coverage = frame.groupby(["position", "statistic", "window"], dropna=False)["team_code"].nunique()
            expected_combinations = (
                len(manifest.get("positions", []))
                * len(manifest.get("statistics", []))
                * len(manifest.get("windows", []))
            )
            if len(coverage) != expected_combinations or coverage.empty or not coverage.eq(30).all():
                continue
            candidates.append((captured, manifest_path, manifest, record_path))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    if not candidates:
        return None
    _, manifest_path, manifest, record_path = max(candidates, key=lambda item: item[0])
    return {
        "status": "complete", "schema_version": SCHEMA_VERSION,
        "snapshot_id": manifest["snapshot_id"], "path": str(record_path),
        "manifest_path": str(manifest_path),
        "sha256": manifest["records_parquet_sha256"],
        "acquired_at_utc": manifest["acquired_at_utc"],
        "completed_at_utc": manifest["completed_at_utc"], "records": manifest["records"],
        "source_url": manifest["source_url"], "season_id": manifest["season_id"],
    }


def load_eligible_snapshot_for_cutoff(
    settings: Settings, *, cutoff_utc: str | None
) -> tuple[pd.DataFrame | None, dict[str, Any]]:
    """Read only a complete, hash-valid current-season snapshot before cutoff."""
    if not settings.use_dvp_matchup:
        return None, {"status": "disabled", "reason": "use_dvp_matchup=false"}
    if not cutoff_utc:
        return None, {"status": "unavailable", "reason": "verified_cutoff_missing"}
    season_id = settings.dunkest_stats_season_id
    if not season_id:
        return None, {"status": "unavailable", "reason": "dunkest_stats_season_id_not_configured"}
    try:
        descriptor = latest_eligible_snapshot(
            settings.data_path, cutoff_utc=cutoff_utc, season_id=str(season_id)
        )
    except (OSError, ValueError, TypeError) as exc:
        return None, {"status": "unavailable", "reason": f"snapshot_lookup_error:{type(exc).__name__}:{exc}"}
    if descriptor is None:
        return None, {
            "status": "unavailable",
            "reason": "no_complete_hash_valid_current_season_snapshot_completed_before_cutoff",
            "cutoff_utc": cutoff_utc,
            "season_id": str(season_id),
        }
    try:
        frame = pd.read_parquet(descriptor["path"])
        required = {
            "schema_version", "season_id", "position", "statistic", "window",
            "team_code", "value", "source_rank", "acquired_at_utc",
        }
        if not required.issubset(frame.columns):
            raise ValueError(f"snapshot columns missing: {sorted(required - set(frame.columns))}")
        if not frame["schema_version"].eq(SCHEMA_VERSION).all():
            raise ValueError("snapshot row schema version mismatch")
        if not frame["season_id"].astype(str).eq(str(season_id)).all():
            raise ValueError("snapshot rows contain a different DvP season")
        if "Fantasy Points" not in set(frame["statistic"].astype(str)):
            raise ValueError("snapshot lacks the Fantasy Points statistic")
        values = pd.to_numeric(frame["value"], errors="coerce")
        if values.isna().any() or not values.map(math.isfinite).all():
            raise ValueError("snapshot contains missing or non-finite DvP values")
        duplicated = frame.duplicated(["position", "statistic", "window", "team_code"])
        if duplicated.any():
            raise ValueError("snapshot contains duplicate position/statistic/window/team rows")
        return frame, {
            **descriptor, "status": "available", "cutoff_utc": cutoff_utc,
            "selected_pre_cutoff": True,
        }
    except Exception as exc:
        return None, {
            **descriptor, "status": "unavailable",
            "reason": f"snapshot_content_invalid:{type(exc).__name__}:{str(exc)[:300]}",
            "cutoff_utc": cutoff_utc,
        }


def apply_dvp_pdk_adjustment(
    forecasts: pd.DataFrame,
    dvp: pd.DataFrame | None,
    settings: Settings,
    *,
    snapshot_metadata: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Apply a small, bounded relative matchup correction to conditional PDK.

    Relative DvP deviations are measured against the 30-team mean for the same
    position/window. Overlapping rolling windows receive decreasing weights.
    This initial strength is configurable and intentionally uncalibrated.
    """
    out = forecasts.copy()
    meta = dict(snapshot_metadata or {})
    meta.setdefault("transform_version", DVP_TRANSFORM_VERSION)
    meta["configured_scale"] = float(settings.dvp_adjustment_scale)
    meta["configured_max_relative_adjustment"] = float(settings.dvp_max_relative_adjustment)
    meta["window_weights"] = dict(DVP_WINDOW_WEIGHTS)
    meta["validated_oos"] = False
    row_count = len(out)
    out["expected_pdk_base"] = pd.to_numeric(out.get("expected_pdk"), errors="coerce")
    out["dvp_adjustment_fraction"] = 0.0
    out["dvp_adjustment_pdk_conditional"] = 0.0
    out["dvp_adjustment_pdk_expected"] = 0.0
    out["dvp_signal_relative"] = 0.0
    out["dvp_position"] = pd.NA
    out["dvp_values_used"] = pd.NA
    out["dvp_adjustment_status"] = "baseline_fallback"
    out["dvp_fallback_reason"] = "dvp_snapshot_unavailable"
    if "expected_pdk_conditional" in out:
        out["expected_pdk_base_conditional"] = pd.to_numeric(
            out["expected_pdk_conditional"], errors="coerce"
        )
    else:
        probability = pd.to_numeric(out.get("p_play", pd.Series(1.0, index=out.index)), errors="coerce").fillna(1.0)
        base = pd.to_numeric(out.get("expected_pdk"), errors="coerce")
        out["expected_pdk_base_conditional"] = base.div(probability.where(probability.gt(0.0))).fillna(base)
    if not settings.use_dvp_matchup:
        meta.update({"status": "disabled", "fallback_reason": "use_dvp_matchup=false", "player_rows": row_count, "covered_rows": 0})
        out["dvp_fallback_reason"] = "use_dvp_matchup=false"
        return out, meta
    if dvp is None or dvp.empty:
        reason = str(meta.get("reason", "dvp_snapshot_missing_or_invalid"))
        meta.update({"status": "unavailable", "fallback_reason": reason, "player_rows": row_count, "covered_rows": 0})
        out["dvp_fallback_reason"] = reason
        return out, meta

    required = {"position", "window", "team_code", "value", "statistic"}
    if not required.issubset(dvp.columns) or "Fantasy Points" not in set(dvp["statistic"].astype(str)):
        reason = "dvp_schema_or_statistic_invalid"
        meta.update({"status": "unavailable", "fallback_reason": reason, "player_rows": row_count, "covered_rows": 0})
        out["dvp_fallback_reason"] = reason
        return out, meta
    source = dvp.loc[dvp["statistic"].astype(str).eq("Fantasy Points")].copy()
    source["team_code"] = source["team_code"].astype(str).str.strip().str.upper()
    source["value"] = pd.to_numeric(source["value"], errors="coerce")
    if source["value"].isna().any() or source.duplicated(["position", "window", "team_code"]).any():
        reason = "dvp_values_missing_or_ambiguous"
        meta.update({"status": "unavailable", "fallback_reason": reason, "player_rows": row_count, "covered_rows": 0})
        out["dvp_fallback_reason"] = reason
        return out, meta

    source["league_mean"] = source.groupby(["position", "window"])["value"].transform("mean")
    if source["league_mean"].isna().any() or source["league_mean"].le(0.0).any():
        reason = "dvp_league_baseline_invalid"
        meta.update({"status": "unavailable", "fallback_reason": reason, "player_rows": row_count, "covered_rows": 0})
        out["dvp_fallback_reason"] = reason
        return out, meta
    source["relative_deviation"] = source["value"].div(source["league_mean"]) - 1.0
    lookup = source.set_index(["position", "window", "team_code"])
    raw_fraction = float(settings.dvp_adjustment_scale)
    cap = min(float(settings.dvp_max_relative_adjustment), 0.05)
    covered = 0
    fallback_counts: dict[str, int] = {}
    used_values: list[dict[str, Any]] = []
    applied_signals: list[float] = []
    team_codes = set(source["team_code"])

    def _reason(row: pd.Series) -> str | None:
        role = str(row.get("role", "")).strip().upper()
        if role not in POSITION_TO_DVP:
            return "position_missing_or_ambiguous"
        if "fixture_verified" in row.index:
            verified = row.get("fixture_verified")
            verified = verified if isinstance(verified, bool) else str(verified).strip().casefold() in {"true", "1", "yes"}
            if not verified:
                return "fixture_unverified"
        team = str(row.get("opponent", "")).strip().upper()
        if not team or team in {"NAN", "NONE", "<NA>"}:
            return "opponent_missing"
        if team not in team_codes:
            return "opponent_unmapped"
        game_id = row.get("nba_game_id")
        if "nba_game_id" in row.index and (pd.isna(game_id) or not str(game_id).strip()):
            return "game_id_missing"
        base_pdk = pd.to_numeric(pd.Series([row.get("expected_pdk_base_conditional")]), errors="coerce").iloc[0]
        minutes = pd.to_numeric(pd.Series([row.get("expected_min", 0.0)]), errors="coerce").iloc[0]
        play = pd.to_numeric(pd.Series([row.get("p_play", 1.0)]), errors="coerce").iloc[0]
        if pd.isna(base_pdk) or not math.isfinite(float(base_pdk)):
            return "base_pdk_missing"
        if pd.isna(minutes) or float(minutes) <= 0.0 or pd.isna(play) or float(play) <= 0.0:
            return "no_expected_participation"
        return None

    for idx, row in out.iterrows():
        base = pd.to_numeric(pd.Series([row.get("expected_pdk_base_conditional")]), errors="coerce").iloc[0]
        if pd.isna(base):
            reason = "base_pdk_missing"
        else:
            reason = _reason(row)
        if reason:
            out.at[idx, "dvp_fallback_reason"] = reason
            fallback_counts[reason] = fallback_counts.get(reason, 0) + 1
            continue
        position = POSITION_TO_DVP[str(row["role"]).strip().upper()]
        opponent = str(row["opponent"]).strip().upper()
        out.at[idx, "dvp_position"] = position
        deviations = []
        values_used = {}
        for window, weight in DVP_WINDOW_WEIGHTS.items():
            key = (position, window, opponent)
            if key not in lookup.index:
                if window == "ALL":
                    reason = "all_window_value_missing"
                    break
                continue
            cell = lookup.loc[key]
            if isinstance(cell, pd.DataFrame):
                reason = "dvp_mapping_ambiguous"
                break
            value = float(cell["value"])
            league_mean = float(cell["league_mean"])
            if not math.isfinite(value) or not math.isfinite(league_mean) or league_mean <= 0.0:
                reason = "dvp_numeric_value_invalid"
                break
            values_used[window] = {"value": value, "league_mean": league_mean}
            deviations.append((weight, value / league_mean - 1.0))
        if reason:
            out.at[idx, "dvp_fallback_reason"] = reason
            fallback_counts[reason] = fallback_counts.get(reason, 0) + 1
            continue
        weight_total = sum(weight for weight, _ in deviations)
        if weight_total <= 0.0:
            out.at[idx, "dvp_fallback_reason"] = "no_usable_windows"
            fallback_counts["no_usable_windows"] = fallback_counts.get("no_usable_windows", 0) + 1
            continue
        signal = sum(weight * deviation for weight, deviation in deviations) / weight_total
        fraction = max(-cap, min(cap, raw_fraction * signal))
        factor = 1.0 + fraction
        base_conditional = float(base)
        probability = float(pd.to_numeric(pd.Series([row.get("p_play", 1.0)]), errors="coerce").fillna(1.0).iloc[0])
        conditional_delta = base_conditional * fraction
        out.at[idx, "expected_pdk_base"] = float(row.get("expected_pdk", 0.0))
        out.at[idx, "dvp_adjustment_fraction"] = fraction
        out.at[idx, "dvp_adjustment_pdk_conditional"] = conditional_delta
        out.at[idx, "dvp_adjustment_pdk_expected"] = probability * conditional_delta
        out.at[idx, "dvp_signal_relative"] = signal
        out.at[idx, "dvp_values_used"] = json.dumps(values_used, sort_keys=True)
        out.at[idx, "dvp_adjustment_status"] = "applied"
        out.at[idx, "dvp_fallback_reason"] = ""
        out.at[idx, "expected_pdk_conditional"] = base_conditional * factor
        out.at[idx, "expected_pdk_before_play_probability"] = base_conditional * factor
        out.at[idx, "expected_pdk"] = float(row.get("expected_pdk", base_conditional * probability)) * factor
        for column in ("p10", "p50", "p90", "pred_std"):
            if column in out:
                value = pd.to_numeric(pd.Series([row.get(column)]), errors="coerce").iloc[0]
                if pd.notna(value) and math.isfinite(float(value)):
                    out.at[idx, column] = float(value) * factor
        covered += 1
        used_values.append(values_used)
        applied_signals.append(signal)
    meta.update({
        "status": "applied" if covered else "no_player_coverage",
        "player_rows": row_count,
        "covered_rows": covered,
        "coverage_fraction": covered / row_count if row_count else 0.0,
        "fallback_counts": fallback_counts,
        "window_weights": dict(DVP_WINDOW_WEIGHTS),
        "transform_version": DVP_TRANSFORM_VERSION,
        "configured_scale": raw_fraction,
        "configured_max_relative_adjustment": cap,
        "mean_absolute_relative_signal": (
            sum(abs(value) for value in applied_signals) / len(applied_signals)
            if applied_signals else None
        ),
        "sample_used_values": used_values[:5],
        "validated_oos": False,
    })
    return out, meta
