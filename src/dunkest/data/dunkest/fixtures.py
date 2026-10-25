"""Explicit bridge between NBA games and Dunkest scoring fixtures.

NBA schedule weeks and Dunkest matchdays/turns are separate namespaces. This
module never infers one from the other: only an archived, provenance-bearing
bridge may mark a game fantasy eligible.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import numpy as np

from dunkest.config import Settings
from dunkest.data.http_client import get_json


FIXTURE_COLUMNS = [
    "season_id",
    "nba_season",
    "nba_game_id",
    "dunkest_match_id",
    "game_datetime_utc",
    "game_date_local",
    "home_team",
    "away_team",
    "home_team_eligible",
    "away_team_eligible",
    "dunkest_gameweek",
    "dunkest_turn",
    "fantasy_eligible",
    "mapping_verified",
    "eligibility_reason",
    "source",
    "source_url_or_endpoint",
    "source_retrieved_at_utc",
    "mapping_version",
    "raw_payload_sha256",
]

REQUIRED_FIXTURE_COLUMNS = set(FIXTURE_COLUMNS).difference(
    {"home_team_eligible", "away_team_eligible", "dunkest_match_id"}
)

DUNKEST_SCHEDULE_API_BASE = "https://fantaking-api.dunkest.com/api/v1"
DUNKEST_NBA_LEAGUE_ID = 1
DUNKEST_TURN_RULE_URL = (
    "https://www.dunkest.com/it/notizie/fantabasket/8774/"
    "calendario-dunkest-cosa-sono-giornata-turni"
)
DUNKEST_LOCK_RULE_URL = (
    "https://www.dunkest.com/it/nba/notizie/fantabasket/19903/"
    "check-list-giornata-cosa-fare-quando"
)


def _official_timestamp_utc(value: object, *, label: str) -> pd.Timestamp:
    """Parse an official source timestamp only when it carries a timezone."""
    parsed = pd.Timestamp(value)
    if pd.isna(parsed) or parsed.tzinfo is None:
        raise ValueError(f"Official Dunkest {label} timestamp is missing or has no timezone offset.")
    return parsed.tz_convert("UTC")


def _canonical_payload_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def fetch_official_dunkest_gameweek_calendar(
    gameweek: int, *, timeout: float = 20.0
) -> tuple[pd.DataFrame, dict]:
    """Fetch official Dunkest matchday/round/team-validity data read-only.

    The public league config exposes the active schedule and current matchday.
    Candidate matchday IDs are only locators: the returned payload's `number`
    is checked against the requested Dunkest Giornata before any row is used.
    The endpoint does not expose NBA GAME_ID, so a separate identity join is
    required before this calendar can become a fixture bridge.
    """
    gw = int(gameweek)
    if gw < 1:
        raise ValueError("Dunkest gameweek must be a positive integer.")
    config_url = f"{DUNKEST_SCHEDULE_API_BASE}/leagues/{DUNKEST_NBA_LEAGUE_ID}/config"
    config_payload = get_json(config_url, timeout=timeout)
    config_retrieved_at = pd.Timestamp.now(tz="UTC")
    config = config_payload.get("data", config_payload) if isinstance(config_payload, dict) else {}
    current = config.get("current_matchday") or {}
    schedule_id = config.get("current_schedule_id")
    current_id = current.get("id")
    current_number = current.get("number")
    if schedule_id is None or current_id is None or current_number is None:
        raise ValueError("Official Dunkest league config lacks current schedule/matchday identity.")
    candidate_id = int(current_id) + (gw - int(current_number))
    matchday_url = f"{DUNKEST_SCHEDULE_API_BASE}/schedules/{int(schedule_id)}/matchdays/{candidate_id}"
    payload = get_json(matchday_url, timeout=timeout)
    matchday_retrieved_at = pd.Timestamp.now(tz="UTC")
    matchday = payload.get("data", payload) if isinstance(payload, dict) else {}
    if int(matchday.get("number", -1)) != gw:
        raise ValueError(
            f"Official API returned matchday number {matchday.get('number')!r}, expected Giornata {gw}; refusing inferred ID."
        )
    rows: list[dict] = []
    for round_data in matchday.get("rounds", []):
        round_number = round_data.get("number")
        for match in round_data.get("matches", []):
            home = match.get("home_team") or {}
            away = match.get("away_team") or {}
            try:
                started_at = _official_timestamp_utc(
                    match.get("started_at"), label="match started_at"
                )
            except (TypeError, ValueError):
                started_at = pd.NaT
            home_valid = parse_fixture_bool(home.get("is_valid"))
            away_valid = parse_fixture_bool(away.get("is_valid"))
            if (
                pd.isna(started_at)
                or not home.get("abbreviation")
                or not away.get("abbreviation")
                or home.get("abbreviation") == away.get("abbreviation")
                or round_number is None
            ):
                raise ValueError(f"Malformed official Dunkest match record: match_id={match.get('id')!r}.")
            rows.append({
                "dunkest_schedule_id": int(schedule_id),
                "dunkest_matchday_id": int(matchday["id"]),
                "dunkest_gameweek": gw,
                "dunkest_round_id": int(round_data["id"]),
                "dunkest_turn": int(round_number),
                "dunkest_match_id": int(match["id"]),
                "game_datetime_utc": started_at,
                "home_team": str(home["abbreviation"]).strip().upper(),
                "away_team": str(away["abbreviation"]).strip().upper(),
                "home_team_eligible": home_valid,
                "away_team_eligible": away_valid,
                "fantasy_eligible": home_valid is True or away_valid is True,
                "match_status": str(match.get("status", "unknown")),
            })
    if not rows:
        raise ValueError(f"Official Dunkest API returned no matches for Giornata {gw}.")
    calendar = pd.DataFrame(rows)
    if calendar["dunkest_match_id"].duplicated().any():
        raise ValueError(f"Official Dunkest Giornata {gw} contains duplicate match IDs.")
    turn_cutoffs = (
        calendar.groupby("dunkest_turn")["game_datetime_utc"].min()
        - pd.Timedelta(minutes=1)
    )
    calendar["dunkest_turn_cutoff_utc"] = calendar["dunkest_turn"].map(turn_cutoffs)
    config_hash = _canonical_payload_sha256(config_payload)
    matchday_hash = _canonical_payload_sha256(payload)
    metadata = {
        "source": "official_fantaking_dunkest_api",
        "config_url": config_url,
        "matchday_url": matchday_url,
        "turn_rule_url": DUNKEST_TURN_RULE_URL,
        "lock_rule_url": DUNKEST_LOCK_RULE_URL,
        "schedule_id": int(schedule_id),
        "matchday_id": int(matchday["id"]),
        "gameweek": gw,
        "match_count": len(calendar),
        "timezone_semantics": "timezone offsets required in official ISO timestamps; normalized to UTC",
        "cutoff_semantics": "official_rule_derived:first_match_started_at_minus_1_minute",
        "retrieved_at_utc": matchday_retrieved_at.isoformat(),
        "config_retrieved_at_utc": config_retrieved_at.isoformat(),
        "matchday_retrieved_at_utc": matchday_retrieved_at.isoformat(),
        "config_payload_sha256": config_hash,
        "matchday_payload_sha256": matchday_hash,
        "raw_payload_sha256": matchday_hash,
        # Keep the exact parsed response objects for immutable run evidence.
        "evidence_payloads": {"config": config_payload, "matchday": payload},
    }
    return calendar, metadata


def certify_official_gameweek_cutoffs(
    fixture_mapping: pd.DataFrame,
    official_calendar: pd.DataFrame,
    source_metadata: dict,
    *,
    gameweek: int,
) -> dict:
    """Resolve rule-derived turn locks only across unique verified fixtures.

    Dunkest documents that a turn starts one minute before its first game and
    that lineup operations close when the turn starts. The returned status is
    explicitly rule-derived, never an assertion that the API has a dedicated
    lock field.
    """
    result = {
        "status": "uncertified",
        "gameweek": int(gameweek),
        "cutoff_kind": "official_rule_derived",
        "reason": "missing_or_unverifiable_official_cutoff_evidence",
    }
    try:
        metadata_gameweek = int(source_metadata.get("gameweek", -1))
    except (TypeError, ValueError):
        metadata_gameweek = -1
    if (
        source_metadata.get("source") != "official_fantaking_dunkest_api"
        or source_metadata.get("cutoff_semantics") != "official_rule_derived:first_match_started_at_minus_1_minute"
        or metadata_gameweek != int(gameweek)
        or source_metadata.get("turn_rule_url") != DUNKEST_TURN_RULE_URL
        or source_metadata.get("lock_rule_url") != DUNKEST_LOCK_RULE_URL
    ):
        result["reason"] = "official_source_or_gameweek_mismatch"
        return result
    payloads = source_metadata.get("evidence_payloads", {})
    for key in ("config", "matchday"):
        if (
            key not in payloads
            or _canonical_payload_sha256(payloads[key])
            != source_metadata.get(f"{key}_payload_sha256")
        ):
            result["reason"] = f"official_{key}_payload_missing_or_hash_mismatch"
            return result
    config_payload = payloads["config"]
    config_payload = config_payload.get("data", config_payload) if isinstance(config_payload, dict) else {}
    matchday_payload = payloads["matchday"]
    matchday_payload = matchday_payload.get("data", matchday_payload) if isinstance(matchday_payload, dict) else {}
    current_matchday = config_payload.get("current_matchday") or {}
    try:
        expected_matchday_id = int(current_matchday["id"]) + (
            int(gameweek) - int(current_matchday["number"])
        )
        schedule_id = int(config_payload["current_schedule_id"])
        matchday_id = int(matchday_payload["id"])
        matchday_number = int(matchday_payload["number"])
        metadata_schedule_id = int(source_metadata.get("schedule_id", -1))
        metadata_matchday_id = int(source_metadata.get("matchday_id", -1))
    except (KeyError, TypeError, ValueError):
        result["reason"] = "official_gameweek_or_turn_identity_missing"
        return result
    if (
        schedule_id != metadata_schedule_id
        or matchday_id != metadata_matchday_id
        or matchday_id != expected_matchday_id
        or matchday_number != int(gameweek)
    ):
        result["reason"] = "official_payload_gameweek_identity_mismatch"
        return result
    if not {
        "dunkest_turn", "dunkest_gameweek", "game_datetime_utc", "home_team", "away_team",
    }.issubset(official_calendar.columns):
        result["reason"] = "official_calendar_missing_turn_or_match_identity"
        return result
    if fixture_mapping.empty or not {
        "nba_game_id", "dunkest_turn", "game_datetime_utc", "home_team", "away_team",
        "mapping_verified", "fantasy_eligible", "dunkest_gameweek",
    }.issubset(fixture_mapping.columns):
        result["reason"] = "verified_fixture_mapping_missing_required_identity"
        return result
    official = official_calendar.copy()
    official["_turn"] = pd.to_numeric(official["dunkest_turn"], errors="coerce")
    official["_start"] = pd.to_datetime(official["game_datetime_utc"], errors="coerce", utc=True)
    official["_home"] = official["home_team"].astype(str).str.strip().str.upper()
    official["_away"] = official["away_team"].astype(str).str.strip().str.upper()
    official_gameweeks = pd.to_numeric(official["dunkest_gameweek"], errors="coerce")
    if not official_gameweeks.eq(int(gameweek)).all():
        result["reason"] = "official_calendar_gameweek_mismatch"
        return result
    if official["_turn"].isna().any() or official["_start"].isna().any():
        result["reason"] = "official_turn_or_game_start_timestamp_missing"
        return result
    recalculated = (
        official.groupby("_turn")["_start"].min() - pd.Timedelta(minutes=1)
    ).sort_index()
    if "dunkest_turn_cutoff_utc" in official:
        supplied = pd.to_datetime(official["dunkest_turn_cutoff_utc"], errors="coerce", utc=True)
        expected = official["_turn"].map(recalculated)
        if supplied.isna().any() or not supplied.eq(expected).all():
            result["reason"] = "official_turn_cutoff_does_not_match_documented_rule"
            return result

    fixtures = fixture_mapping.copy()
    fixtures["_turn"] = pd.to_numeric(fixtures["dunkest_turn"], errors="coerce")
    fixtures["_start"] = pd.to_datetime(fixtures["game_datetime_utc"], errors="coerce", utc=True)
    fixtures["_home"] = fixtures["home_team"].astype(str).str.strip().str.upper()
    fixtures["_away"] = fixtures["away_team"].astype(str).str.strip().str.upper()
    fixtures = fixtures.loc[
        pd.to_numeric(fixtures["dunkest_gameweek"], errors="coerce").eq(int(gameweek))
        & fixtures["mapping_verified"].map(parse_fixture_bool).fillna(False)
        & fixtures["fantasy_eligible"].map(parse_fixture_bool).fillna(False)
    ]
    if fixtures.empty:
        result["reason"] = "no_verified_eligible_fixtures_for_gameweek"
        return result
    linked_rows = []
    for _, fixture in fixtures.iterrows():
        candidates = official.loc[
            official["_turn"].eq(fixture["_turn"])
            & official["_home"].eq(fixture["_home"])
            & official["_away"].eq(fixture["_away"])
            & (official["_start"] - fixture["_start"]).abs().le(pd.Timedelta(hours=36))
        ]
        if len(candidates) != 1:
            result["reason"] = "fixture_to_official_turn_link_missing_or_ambiguous"
            return result
        official_match = candidates.iloc[0]
        if "dunkest_match_id" in fixtures and pd.notna(fixture.get("dunkest_match_id")):
            if str(fixture["dunkest_match_id"]).strip() != str(official_match.get("dunkest_match_id", "")).strip():
                result["reason"] = "dunkest_match_id_mismatch"
                return result
        for status_column in ("home_team_eligible", "away_team_eligible"):
            if status_column in fixtures:
                fixture_status = parse_fixture_bool(fixture.get(status_column))
                official_status = parse_fixture_bool(official_match.get(status_column))
                if fixture_status is None or official_status is None or fixture_status != official_status:
                    result["reason"] = f"{status_column}_mismatch_or_unverified"
                    return result
        linked_rows.append({
            "nba_game_id": str(fixture["nba_game_id"]),
            "dunkest_match_id": str(official_match.get("dunkest_match_id", "")),
            "dunkest_turn": int(fixture["_turn"]),
            "home_team": str(official_match["_home"]),
            "away_team": str(official_match["_away"]),
        })
    turn_cutoffs = {
        str(int(turn)): cutoff.isoformat()
        for turn, cutoff in recalculated.items()
    }
    try:
        fetched = [
            _official_timestamp_utc(source_metadata.get(key), label=key)
            for key in ("config_retrieved_at_utc", "matchday_retrieved_at_utc")
        ]
    except (TypeError, ValueError):
        result["reason"] = "official_payload_acquisition_timestamp_missing_or_naive"
        return result
    earliest_cutoff = recalculated.min()
    if max(fetched) >= earliest_cutoff:
        result["reason"] = "official_cutoff_evidence_acquired_after_gameweek_lock"
        return result
    evidence_hash = hashlib.sha256(
        json.dumps({
            "config_payload_sha256": source_metadata.get("config_payload_sha256"),
            "matchday_payload_sha256": source_metadata.get("matchday_payload_sha256"),
            "turn_rule_url": DUNKEST_TURN_RULE_URL,
            "lock_rule_url": DUNKEST_LOCK_RULE_URL,
            "gameweek": int(gameweek),
            "turn_cutoffs_utc": turn_cutoffs,
            "fixture_links": sorted(linked_rows, key=lambda item: (item["dunkest_turn"], item["nba_game_id"])),
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        **result,
        "status": "certified",
        "reason": "official_rule_and_calendar_verified",
        "cutoff_utc": recalculated.min().isoformat(),
        "turn_cutoffs_utc": turn_cutoffs,
        "evidence_sha256": evidence_hash,
        "source_urls": [
            source_metadata["config_url"], source_metadata["matchday_url"],
            DUNKEST_TURN_RULE_URL, DUNKEST_LOCK_RULE_URL,
        ],
        "source_payload_sha256": {
            "config": source_metadata.get("config_payload_sha256"),
            "matchday": source_metadata.get("matchday_payload_sha256"),
        },
        "acquired_at_utc": {
            "config": source_metadata["config_retrieved_at_utc"],
            "matchday": source_metadata["matchday_retrieved_at_utc"],
        },
        "timezone": "UTC (source timezone offsets preserved in raw API payload)",
        "fixture_links": linked_rows,
    }


def build_gameweek_mapping_from_official_calendar(
    settings: Settings,
    nba_schedule: pd.DataFrame,
    official_calendar: pd.DataFrame,
    *,
    gameweek: int,
    mapping_version: str | None = None,
) -> pd.DataFrame:
    """Join official Dunkest matchday/turn/eligibility to unique NBA game IDs.

    The official API is authoritative for Giornata, Turno and per-side validity;
    the NBA schedule contributes only the NBA game identity. A team-pair match
    must be unique within 36 hours of the official tipoff. Missing or ambiguous
    identities abort the whole bridge rather than silently creating a partial map.
    """
    gw = int(gameweek)
    required = {
        "dunkest_schedule_id", "dunkest_matchday_id", "dunkest_gameweek", "dunkest_turn",
        "dunkest_match_id", "game_datetime_utc", "home_team", "away_team",
        "home_team_eligible", "away_team_eligible",
    }
    if official_calendar.empty or not required.issubset(official_calendar.columns):
        raise ValueError("Official Dunkest calendar is empty or missing required fields.")
    if not pd.to_numeric(official_calendar["dunkest_gameweek"], errors="coerce").eq(gw).all():
        raise ValueError("Official calendar contains rows from a different Dunkest Giornata.")
    schedule = validate_nba_schedule(nba_schedule).copy()
    schedule["_datetime"] = pd.to_datetime(schedule["GAME_DATE"], errors="coerce", utc=True)
    observed_at = pd.Timestamp.now(tz="UTC")
    version = mapping_version or f"official_api_gw{gw}_v1"
    payload: list[dict] = []
    unmatched: list[int] = []
    for _, official in official_calendar.iterrows():
        start = pd.to_datetime(official["game_datetime_utc"], errors="coerce", utc=True)
        home = str(official["home_team"]).strip().upper()
        away = str(official["away_team"]).strip().upper()
        pair = schedule["HOME_TEAM"].eq(home) & schedule["AWAY_TEAM"].eq(away)
        delta = (schedule["_datetime"] - start).abs()
        candidates = schedule.loc[pair & delta.le(pd.Timedelta(hours=36))].copy()
        if len(candidates) != 1:
            unmatched.append(int(official["dunkest_match_id"]))
            continue
        game = candidates.iloc[0]
        home_valid = parse_fixture_bool(official["home_team_eligible"])
        away_valid = parse_fixture_bool(official["away_team_eligible"])
        eligible = home_valid is True or away_valid is True
        payload.append({
            "season_id": str(settings.season_id),
            "nba_season": str(settings.season),
            "nba_game_id": str(game["GAME_ID"]),
            "dunkest_match_id": str(official["dunkest_match_id"]),
            "game_datetime_utc": start,
            "game_date_local": start.tz_convert("Europe/Rome").date(),
            "home_team": home, "away_team": away,
            "home_team_eligible": home_valid, "away_team_eligible": away_valid,
            "dunkest_gameweek": gw, "dunkest_turn": int(official["dunkest_turn"]),
            "fantasy_eligible": eligible,
            "mapping_verified": home_valid is not None and away_valid is not None,
            "eligibility_reason": f"official_matchday_{int(official['dunkest_matchday_id'])}_match_{int(official['dunkest_match_id'])}",
            "source": "official_fantaking_dunkest_api",
            "source_url_or_endpoint": (
                f"{DUNKEST_SCHEDULE_API_BASE}/schedules/{int(official['dunkest_schedule_id'])}"
                f"/matchdays/{int(official['dunkest_matchday_id'])}"
            ),
            "source_retrieved_at_utc": observed_at,
            "mapping_version": version,
            "raw_payload_sha256": "",
        })
    if unmatched:
        raise ValueError(
            f"Cannot uniquely join official Dunkest matches to NBA GAME_ID for Giornata {gw}; "
            f"unmatched/ambiguous Dunkest match IDs: {unmatched[:20]}"
        )
    frame = pd.DataFrame(payload)
    if frame["nba_game_id"].duplicated().any():
        ids = frame.loc[frame["nba_game_id"].duplicated(keep=False), "nba_game_id"].astype(str).tolist()
        raise ValueError(f"Official Dunkest calendar maps duplicate NBA game IDs: {ids[:20]}")
    digest = hashlib.sha256(
        "|".join(
            f"{row['nba_game_id']}:{row['dunkest_match_id']}:{row['dunkest_turn']}:{row['home_team_eligible']}:{row['away_team_eligible']}"
            for row in frame.sort_values(["game_datetime_utc", "nba_game_id"]).to_dict("records")
        ).encode("utf-8")
    ).hexdigest()
    frame["raw_payload_sha256"] = digest
    return validate_fixture_mapping(frame)


def validate_nba_schedule(schedule: pd.DataFrame) -> pd.DataFrame:
    """Validate an NBA schedule without assigning fantasy semantics."""
    required = {"GAME_ID", "GAME_DATE", "HOME_TEAM", "AWAY_TEAM"}
    missing = sorted(required.difference(schedule.columns))
    if missing:
        raise ValueError(f"NBA schedule missing columns: {', '.join(missing)}")
    out = schedule.copy()
    out["GAME_ID"] = out["GAME_ID"].astype("string").str.strip()
    out["GAME_DATE"] = pd.to_datetime(out["GAME_DATE"], errors="coerce", utc=True)
    for column in ("HOME_TEAM", "AWAY_TEAM"):
        out[column] = out[column].astype("string").str.strip().str.upper()
    invalid = (
        out["GAME_ID"].isna()
        | out["GAME_ID"].eq("")
        | out["GAME_DATE"].isna()
        | out["HOME_TEAM"].isna()
        | out["AWAY_TEAM"].isna()
        | out["HOME_TEAM"].eq(out["AWAY_TEAM"])
    )
    if invalid.any():
        raise ValueError(f"NBA schedule has {int(invalid.sum())} invalid fixture row(s).")
    duplicated = out["GAME_ID"].duplicated(keep=False)
    if duplicated.any():
        ids = sorted(out.loc[duplicated, "GAME_ID"].astype(str).unique())
        raise ValueError(f"Duplicate NBA game identity: {', '.join(ids[:10])}")
    return out


def validate_fixture_mapping(mapping: pd.DataFrame) -> pd.DataFrame:
    """Validate an explicit Dunkest fixture bridge; unknown eligibility stays unknown."""
    missing = sorted(REQUIRED_FIXTURE_COLUMNS.difference(mapping.columns))
    if missing:
        raise ValueError(f"Fixture mapping missing columns: {', '.join(missing)}")
    out = mapping.copy()
    if "dunkest_match_id" not in out:
        out["dunkest_match_id"] = pd.NA
    # Older saved bridges only had a game-level flag. Preserve their meaning
    # for compatibility, while new browser captures carry independent status
    # for the home and away Dunkest franchises.
    if "home_team_eligible" not in out:
        out["home_team_eligible"] = out["fantasy_eligible"]
    if "away_team_eligible" not in out:
        out["away_team_eligible"] = out["fantasy_eligible"]
    out = out[FIXTURE_COLUMNS].copy()
    for column in ("season_id", "nba_season", "nba_game_id", "dunkest_match_id", "home_team", "away_team", "source", "mapping_version"):
        out[column] = out[column].astype("string").str.strip()
    for column in ("home_team", "away_team"):
        out[column] = out[column].str.upper()
    out["game_datetime_utc"] = pd.to_datetime(out["game_datetime_utc"], errors="coerce", utc=True)
    out["game_date_local"] = pd.to_datetime(out["game_date_local"], errors="coerce").dt.date
    out["source_retrieved_at_utc"] = pd.to_datetime(
        out["source_retrieved_at_utc"], errors="coerce", utc=True
    )
    out["dunkest_gameweek"] = pd.to_numeric(out["dunkest_gameweek"], errors="coerce").astype("Int64")
    out["dunkest_turn"] = pd.to_numeric(out["dunkest_turn"], errors="coerce").astype("Int64")
    def _parse_bool(value: object):
        if pd.isna(value):
            return pd.NA
        if isinstance(value, (bool,)):
            return value
        if str(value).strip().lower() in {"true", "1", "yes"}:
            return True
        if str(value).strip().lower() in {"false", "0", "no"}:
            return False
        return pd.NA

    out["fantasy_eligible"] = out["fantasy_eligible"].map(_parse_bool).astype("boolean")
    out["home_team_eligible"] = out["home_team_eligible"].map(_parse_bool).astype("boolean")
    out["away_team_eligible"] = out["away_team_eligible"].map(_parse_bool).astype("boolean")
    out["mapping_verified"] = out["mapping_verified"].map(_parse_bool).astype("boolean")
    out["fantasy_eligible"] = (
        out["home_team_eligible"].eq(True) | out["away_team_eligible"].eq(True)
    ).astype("boolean")
    invalid = (
        out[["season_id", "nba_season", "nba_game_id", "home_team", "away_team", "source", "mapping_version"]]
        .isna().any(axis=1)
        | out["nba_game_id"].eq("")
        | out["home_team"].eq(out["away_team"])
        | out["game_datetime_utc"].isna()
        | out["source_retrieved_at_utc"].isna()
        | (out["fantasy_eligible"].eq(True) & (out["dunkest_gameweek"].isna() | out["dunkest_turn"].isna()))
    )
    if invalid.any():
        raise ValueError(f"Fixture mapping has {int(invalid.sum())} invalid row(s).")
    duplicated = out.duplicated(["season_id", "nba_game_id"], keep=False)
    if duplicated.any():
        ids = sorted(out.loc[duplicated, "nba_game_id"].astype(str).unique())
        raise ValueError(f"Duplicate fixture identity (season_id, nba_game_id): {', '.join(ids[:10])}")
    # A team's multiple NBA games in a fantasy matchday are allowed only when
    # the bridge marks at most one as score-bearing. Unknown rows are retained.
    # Non-eligible and unknown games may repeat for a team; only two confirmed
    # score-bearing games for the same team/GW are contradictory.
    eligible = out.loc[out["fantasy_eligible"].eq(True)]
    teams = pd.concat(
        [
            eligible.loc[eligible["home_team_eligible"].eq(True), ["season_id", "dunkest_gameweek", "nba_game_id", "home_team"]].rename(columns={"home_team": "team"}),
            eligible.loc[eligible["away_team_eligible"].eq(True), ["season_id", "dunkest_gameweek", "nba_game_id", "away_team"]].rename(columns={"away_team": "team"}),
        ], ignore_index=True,
    )
    dup_team = teams.duplicated(["season_id", "dunkest_gameweek", "team"], keep=False)
    # Provisional (unverified) bridges may still list a second NBA game for a
    # team that already opened; official/verified maps must stay one-game/team.
    if dup_team.any() and bool(out["mapping_verified"].fillna(False).any()):
        rows = teams.loc[dup_team]
        raise ValueError(
            "A team has multiple fantasy-eligible games in one Dunkest matchday: "
            + ", ".join(sorted(rows["team"].astype(str).unique()))
        )
    return out.reset_index(drop=True)


def fixture_mapping_path(
    settings: Settings, season_id: str | None = None, mapping_version: str = "v1"
) -> Path:
    selected_season = str(season_id or settings.season_id)
    safe_version = "".join(ch for ch in str(mapping_version) if ch.isalnum() or ch in "-_")
    if not safe_version:
        raise ValueError("Fixture mapping version must contain a safe filename character.")
    return settings.data_path / "processed" / f"dunkest_fixture_mapping_{selected_season}_{safe_version}.parquet"


def get_fixture_mapping(
    settings: Settings,
    dunkest_gameweek: int | None = None,
    *,
    season_id: str | None = None,
) -> pd.DataFrame:
    """Load only a validated, explicitly sourced Dunkest mapping."""
    selected_season = str(season_id or settings.season_id)
    paths = sorted((settings.data_path / "processed").glob(f"dunkest_fixture_mapping_{selected_season}_*.parquet"))
    legacy_path = settings.data_path / "processed" / f"dunkest_fixture_mapping_{selected_season}.parquet"
    if legacy_path.is_file():
        paths.append(legacy_path)
    if not paths:
        return pd.DataFrame(columns=FIXTURE_COLUMNS)
    if len(paths) > 1:
        raise RuntimeError(
            "Multiple fixture mapping revisions exist; select one explicitly before use: "
            + ", ".join(path.name for path in paths)
        )
    mapping = validate_fixture_mapping(pd.read_parquet(paths[0]))
    if dunkest_gameweek is not None:
        mapping = mapping.loc[mapping["dunkest_gameweek"].eq(int(dunkest_gameweek))]
    # Provisional NBA-schedule proxies are useful for diagnostics only. They
    # must not be presented as confirmed Dunkest matchups or drive forecasts.
    mapping = mapping.loc[
        mapping["mapping_verified"].map(parse_fixture_bool).fillna(False).astype(bool)
        & (
            mapping["home_team_eligible"].map(parse_fixture_bool).fillna(False).astype(bool)
            | mapping["away_team_eligible"].map(parse_fixture_bool).fillna(False).astype(bool)
        )
    ]
    return mapping.reset_index(drop=True)


def save_fixture_mapping(
    settings: Settings,
    mapping: pd.DataFrame,
    *,
    season_id: str | None = None,
    source: str,
    replace_existing: bool = False,
) -> Path:
    """Persist an explicit mapping immutably; revisions use a new versioned path."""
    if not str(source).strip():
        raise ValueError("Fixture mapping source must be explicit.")
    clean = validate_fixture_mapping(mapping)
    selected_season = str(season_id or settings.season_id)
    if not clean["season_id"].astype(str).eq(selected_season).all():
        raise ValueError("Fixture mapping season_id does not match the destination season.")
    versions = clean["mapping_version"].astype(str).unique()
    if len(versions) != 1:
        raise ValueError("A fixture mapping file must contain exactly one mapping_version.")
    destination = fixture_mapping_path(settings, selected_season, str(versions[0]))
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not replace_existing:
        old_hash = hashlib.sha256(destination.read_bytes()).hexdigest()
        raise FileExistsError(
            f"Fixture mapping is immutable: {destination} already exists ({old_hash[:12]}). "
            "Archive a revised mapping under a new version instead of overwriting it."
        )
    if replace_existing:
        # Only one active mapping per season is loadable; drop sibling revisions.
        processed = settings.data_path / "processed"
        for old in processed.glob(f"dunkest_fixture_mapping_{selected_season}_*.parquet"):
            old.unlink(missing_ok=True)
        legacy = processed / f"dunkest_fixture_mapping_{selected_season}.parquet"
        legacy.unlink(missing_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    # Write via pyarrow explicitly: some pandas/pyarrow pairings create empty files
    # on this environment when using DataFrame.to_parquet.
    import pyarrow as pa
    import pyarrow.parquet as pq

    pq.write_table(pa.Table.from_pandas(clean, preserve_index=False), temporary)
    temporary.replace(destination)
    return destination


def build_gameweek1_mapping_from_nba_schedule(
    settings: Settings,
    nba_schedule: pd.DataFrame,
    *,
    mapping_version: str = "g1_first_appearance_v1",
) -> pd.DataFrame:
    """Build a Giornata-1 bridge: first regular-season appearance per team.

    Dunkest assigns each team one valid game per Giornata. Until an official
    Lineups/API bridge is archived, the first chronological appearance of each
    franchise is the standard pre-season proxy (Turno = calendar day from tipoff).
    """
    schedule = validate_nba_schedule(nba_schedule)
    schedule = schedule.sort_values(["GAME_DATE", "GAME_ID"]).reset_index(drop=True)
    retrieved = pd.Timestamp.now(tz="UTC")
    season_start = pd.Timestamp(str(settings.nba_season_start), tz="UTC")
    rows: list[dict] = []
    seen_teams: set[str] = set()
    day_to_turn: dict = {}
    next_turn = 1
    payload_bits: list[str] = []
    for _, game in schedule.iterrows():
        if len(seen_teams) >= 30:
            break
        game_ts = pd.Timestamp(game["GAME_DATE"])
        if game_ts.tzinfo is None:
            game_ts = game_ts.tz_localize("UTC")
        else:
            game_ts = game_ts.tz_convert("UTC")
        game_day = game_ts.normalize()
        if game_day < season_start.normalize():
            continue
        home = str(game["HOME_TEAM"]).upper()
        away = str(game["AWAY_TEAM"]).upper()
        eligible_sides = [team for team in (home, away) if team not in seen_teams]
        if not eligible_sides:
            continue
        if game_day not in day_to_turn:
            day_to_turn[game_day] = next_turn
            next_turn += 1
        turn = day_to_turn[game_day]
        for team in eligible_sides:
            seen_teams.add(team)
        game_id = str(game["GAME_ID"])
        payload_bits.append(f"{game_id}:{turn}:{','.join(sorted(eligible_sides))}")
        rows.append({
            "season_id": str(settings.season_id),
            "nba_season": str(settings.season),
            "nba_game_id": game_id,
            "game_datetime_utc": game_ts,
            "game_date_local": game_ts.date(),
            "home_team": home,
            "away_team": away,
            "dunkest_gameweek": 1,
            "dunkest_turn": int(turn),
            "fantasy_eligible": True,
            "mapping_verified": False,
            "eligibility_reason": (
                "first_regular_season_appearance_per_team; "
                f"valid_for={'+'.join(sorted(eligible_sides))}"
            ),
            "source": "nba_schedule_first_appearance",
            "source_url_or_endpoint": "data/processed/future_regular_schedule_2026-27.parquet",
            "source_retrieved_at_utc": retrieved,
            "mapping_version": mapping_version,
            "raw_payload_sha256": "",
        })
    if not rows:
        return pd.DataFrame(columns=FIXTURE_COLUMNS)
    digest = hashlib.sha256("|".join(payload_bits).encode("utf-8")).hexdigest()
    frame = pd.DataFrame(rows)
    frame["raw_payload_sha256"] = digest
    return validate_fixture_mapping(frame)


def build_gameweek_mapping_from_lineups(
    settings: Settings,
    nba_schedule: pd.DataFrame,
    observations: pd.DataFrame,
    *,
    gameweek: int = 1,
    mapping_version: str | None = None,
) -> pd.DataFrame:
    """Join the currently observed Dunkest fixtures to NBA game identities.

    The caller supplies the Dunkest gameweek currently displayed in Lineups.
    Browser capture is authoritative for dates, turns, and team eligibility;
    the NBA schedule supplies only game identity and home/away orientation.
    """
    if int(gameweek) < 1:
        raise ValueError("Dunkest gameweek must be a positive integer.")
    mapping_version = mapping_version or f"lineups_browser_gw{int(gameweek)}_team_status_v2"
    required = {"team_a", "team_b", "display_day", "display_month", "dunkest_turn"}
    if observations.empty or not required.issubset(observations.columns):
        return pd.DataFrame(columns=FIXTURE_COLUMNS)
    schedule = validate_nba_schedule(nba_schedule)
    schedule = schedule.copy()
    schedule["_date"] = schedule["GAME_DATE"].dt.tz_convert("UTC")
    retrieved_default = pd.Timestamp.now(tz="UTC")
    payload = []
    for _, observation in observations.iterrows():
        first = str(observation.get("team_a") or "").strip().upper()
        second = str(observation.get("team_b") or "").strip().upper()
        try:
            day = int(observation["display_day"])
            month = int(observation["display_month"])
            turn = int(observation["dunkest_turn"])
        except (TypeError, ValueError):
            continue
        pair = (
            schedule["HOME_TEAM"].isin([first, second])
            & schedule["AWAY_TEAM"].isin([first, second])
            & schedule["HOME_TEAM"].ne(schedule["AWAY_TEAM"])
        )
        date_match = schedule["_date"].dt.day.eq(day) & schedule["_date"].dt.month.eq(month)
        candidates = schedule.loc[pair & date_match]
        if candidates.empty:
            # Dunkest displays tip-off dates in its own calendar timezone, which
            # can differ by one calendar day from the NBA schedule's game date.
            # Never fall back to the pair across the whole season (teams meet
            # several times): accept only a unique same-pair game within +/-1 day
            # of the displayed date, considering both calendar years of the season.
            schedule_years = sorted(schedule["_date"].dt.year.dropna().astype(int).unique())
            nearby_dates: set[pd.Timestamp] = set()
            for year in schedule_years:
                try:
                    display_date = pd.Timestamp(year=year, month=month, day=day, tz="UTC")
                except ValueError:
                    continue
                nearby_dates.add(display_date.normalize() - pd.Timedelta(days=1))
                nearby_dates.add(display_date.normalize() + pd.Timedelta(days=1))
            normalized_dates = schedule["_date"].dt.normalize()
            candidates = schedule.loc[pair & normalized_dates.isin(nearby_dates)]
        if len(candidates) != 1:
            continue
        game = candidates.iloc[0]
        eligibility_by_team = {
            first: parse_fixture_bool(observation.get("team_a_eligible")),
            second: parse_fixture_bool(observation.get("team_b_eligible")),
        }
        home_eligible = eligibility_by_team.get(str(game["HOME_TEAM"]).upper())
        away_eligible = eligibility_by_team.get(str(game["AWAY_TEAM"]).upper())
        any_eligible = home_eligible is True or away_eligible is True
        retrieved = pd.to_datetime(
            observation.get("observed_at_utc"), errors="coerce", utc=True
        )
        if pd.isna(retrieved):
            retrieved = retrieved_default
        payload.append({
            "season_id": str(settings.season_id),
            "nba_season": str(settings.season),
            "nba_game_id": str(game["GAME_ID"]),
            "game_datetime_utc": game["GAME_DATE"],
            "game_date_local": game["GAME_DATE"].date(),
            "home_team": str(game["HOME_TEAM"]),
            "away_team": str(game["AWAY_TEAM"]),
            "home_team_eligible": home_eligible,
            "away_team_eligible": away_eligible,
            "dunkest_gameweek": int(gameweek),
            "dunkest_turn": turn,
            "fantasy_eligible": any_eligible,
            "mapping_verified": home_eligible is not None and away_eligible is not None,
            "eligibility_reason": (
                "official_lineups_black_gray_status_observed"
                if home_eligible is not None and away_eligible is not None
                else "official_lineups_status_unknown_fail_closed"
            ),
            "source": "dunkest_lineups_browser",
            "source_url_or_endpoint": "https://fantasy.dunkest.com/1/lineups (current gameweek capture)",
            "source_retrieved_at_utc": retrieved,
            "mapping_version": mapping_version,
            "raw_payload_sha256": "",
        })
    if not payload:
        return pd.DataFrame(columns=FIXTURE_COLUMNS)
    frame = pd.DataFrame(payload).drop_duplicates(["season_id", "nba_game_id"], keep="last")
    digest = hashlib.sha256(
        "|".join(
            f"{row['nba_game_id']}:{row['dunkest_turn']}:{row['home_team_eligible']}:{row['away_team_eligible']}"
            for row in frame.sort_values(["game_datetime_utc", "nba_game_id"]).to_dict("records")
        ).encode("utf-8")
    ).hexdigest()
    frame["raw_payload_sha256"] = digest
    return validate_fixture_mapping(frame)


def build_gameweek1_mapping_from_lineups(
    settings: Settings,
    nba_schedule: pd.DataFrame,
    observations: pd.DataFrame,
    *,
    mapping_version: str = "lineups_browser_gw1_team_status_v2",
) -> pd.DataFrame:
    """Backward-compatible Giornata-1 wrapper."""
    return build_gameweek_mapping_from_lineups(
        settings, nba_schedule, observations, gameweek=1, mapping_version=mapping_version
    )


build_gameweek1_mapping_from_lineups_observations = build_gameweek1_mapping_from_lineups


def ensure_gameweek1_fixture_mapping(settings: Settings) -> pd.DataFrame:
    """Load confirmed G1 matchups, including a useful partial official capture.

    A Giornata may contain teams at rest, so requiring 30 score-bearing teams
    incorrectly rejects valid Dunkest calendars. Unknown sides remain unknown;
    only explicitly observed eligible sides are returned to projections.
    """
    existing = get_fixture_mapping(settings, 1)

    schedule = pd.DataFrame()
    schedule_candidates = [
        settings.data_path / "processed" / f"future_regular_schedule_{settings.season}_v2.parquet",
        settings.data_path / "processed" / f"future_regular_schedule_{settings.season}.parquet",
        settings.data_path / "processed" / f"future_schedule_{settings.season}.parquet",
    ]
    for schedule_path in schedule_candidates:
        if not schedule_path.exists() or schedule_path.stat().st_size == 0:
            continue
        try:
            schedule = pd.read_parquet(schedule_path)
        except Exception:
            continue
        if not schedule.empty:
            break

    if schedule.empty:
        try:
            from dunkest.data.nba import collector as nba

            schedule = nba.fetch_future_schedule(settings)
            if not schedule.empty:
                cache_path = settings.data_path / "processed" / (
                    f"future_regular_schedule_{settings.season}.parquet"
                )
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                import pyarrow as pa
                import pyarrow.parquet as pq

                pq.write_table(
                    pa.Table.from_pandas(schedule, preserve_index=False),
                    cache_path,
                )
        except Exception:
            return existing if not existing.empty else pd.DataFrame(columns=FIXTURE_COLUMNS)

    if schedule.empty:
        return existing if not existing.empty else pd.DataFrame(columns=FIXTURE_COLUMNS)

    observations_path = settings.data_path / "lineups_fixtures.csv"
    if observations_path.is_file():
        observations = pd.DataFrame()
        try:
            observations = pd.read_csv(observations_path)
            observed_mapping = build_gameweek1_mapping_from_lineups_observations(
                settings, schedule, observations
            )
        except (OSError, ValueError, pd.errors.ParserError):
            observed_mapping = pd.DataFrame(columns=FIXTURE_COLUMNS)
        observed_teams = _eligible_teams(observed_mapping)
        observed_statuses = sum(
            int(observed_mapping[column].notna().sum())
            for column in ("home_team_eligible", "away_team_eligible")
            if column in observed_mapping
        )
        observed_sides = 2 * len(observed_mapping)
        observed_at = (
            pd.to_datetime(observations.get("observed_at_utc"), utc=True, errors="coerce").dropna()
            if "observed_at_utc" in observations else pd.Series(dtype="datetime64[ns, UTC]")
        )
        now_utc = pd.Timestamp.now(tz="UTC")
        observed_fresh = bool(
            not observed_at.empty
            and -0.01 <= (now_utc - observed_at.max()).total_seconds() / 3600.0 <= 36.0
        )
        existing_retrieved = (
            pd.to_datetime(existing.get("source_retrieved_at_utc"), utc=True, errors="coerce").dropna()
            if "source_retrieved_at_utc" in existing else pd.Series(dtype="datetime64[ns, UTC]")
        )
        existing_stale = bool(
            existing_retrieved.empty
            or (now_utc - existing_retrieved.min()).total_seconds() / 3600.0 > 36.0
        )
        observation_newer = bool(
            not observed_at.empty
            and (existing_retrieved.empty or observed_at.max() > existing_retrieved.max())
        )
        # A complete capture in which every single team side is explicitly
        # marked ineligible is not a usable Giornata-1 calendar. Do not silently
        # fall back to an older partial mapping, which could mislead the coach
        # model. This also surfaces broken black/gray status extraction early.
        if observed_mapping.shape[0] and observed_statuses == observed_sides and not observed_teams:
            raise RuntimeError(
                "Calendario Lineups incoerente: sono state associate "
                f"{len(observed_mapping)} partite NBA, ma tutti i {observed_sides} lati "
                "risultano non eleggibili e nessuna squadra ha un matchup valido. "
                "Non riutilizzo la vecchia mappatura. Riesegui lo scraping Lineups e "
                "verifica che gli stati nero/grigio delle squadre siano letti correttamente."
            )
        existing_statuses = sum(
            int(existing[column].notna().sum())
            for column in ("home_team_eligible", "away_team_eligible")
            if column in existing
        )
        # Do not demand that every NBA franchise plays in this Giornata: the
        # official rules explicitly allow rest teams. A partial capture can
        # safely guide only the sides whose black/gray state was observed.
        if observed_teams and observed_statuses and observed_fresh:
            # A fresh official Lineups capture supersedes a stale mapping even
            # when the number of observed side-statuses is unchanged. Otherwise
            # season-opener can keep using a several-day-old mapping forever.
            should_refresh = (
                existing.empty
                or existing_stale
                or (observation_newer and observed_statuses >= existing_statuses)
            )
            if should_refresh:
                save_fixture_mapping(
                    settings,
                    observed_mapping,
                    source="dunkest_lineups_browser",
                    replace_existing=True,
                )
                return observed_mapping.loc[
                    observed_mapping["fantasy_eligible"].eq(True)
                ].reset_index(drop=True)
        if not existing.empty:
            return existing

    if not existing.empty:
        return existing

    # An NBA schedule alone cannot say which Dunkest game is score-bearing.
    # Wait for the official Lineups fixture capture instead of inventing a
    # Giornata/Turno bridge from calendar order.
    return pd.DataFrame(columns=FIXTURE_COLUMNS)


def save_current_capture_fixture_mapping(
    settings: Settings, dunkest_gameweek: int
) -> pd.DataFrame:
    """Build and persist a verified mapping for the freshly scraped gameweek.

    The observations must come from the current Lineups capture. Existing
    gameweeks are retained in the same active mapping so a refresh for GW2 does
    not erase GW1 fixture identities needed by archived runs.
    """
    gw = int(dunkest_gameweek)
    if gw < 1:
        raise ValueError("Dunkest gameweek must be a positive integer.")
    observations_path = settings.data_path / "lineups_fixtures.csv"
    if not observations_path.is_file():
        raise RuntimeError("Manca la cattura fixture Lineups; aggiorna il mercato prima di ottimizzare.")
    observations = pd.read_csv(observations_path)
    if "observed_at_utc" not in observations or observations.empty:
        raise RuntimeError("La cattura fixture Lineups è vuota o senza timestamp di acquisizione.")
    observed_at = pd.to_datetime(observations["observed_at_utc"], errors="coerce", utc=True).dropna()
    if observed_at.empty:
        raise RuntimeError("La cattura fixture Lineups non contiene timestamp validi.")
    age_hours = (pd.Timestamp.now(tz="UTC") - observed_at.max()).total_seconds() / 3600.0
    if age_hours < -0.01 or age_hours > 36.0:
        raise RuntimeError(
            f"La cattura fixture Lineups non è aggiornata ({age_hours:.1f}h); "
            "ripeti lo scraping della giornata target."
        )

    schedule = pd.DataFrame()
    schedule_candidates = [
        settings.data_path / "processed" / f"future_regular_schedule_{settings.season}_v2.parquet",
        settings.data_path / "processed" / f"future_regular_schedule_{settings.season}.parquet",
        settings.data_path / "processed" / f"future_schedule_{settings.season}.parquet",
    ]
    for schedule_path in schedule_candidates:
        if not schedule_path.is_file() or schedule_path.stat().st_size == 0:
            continue
        try:
            schedule = pd.read_parquet(schedule_path)
        except Exception:
            continue
        if not schedule.empty:
            break
    if schedule.empty:
        from dunkest.data.nba import collector as nba
        schedule = nba.fetch_future_schedule(settings)
    if schedule.empty:
        raise RuntimeError("Calendario NBA futuro non disponibile; non assegno matchup per supposizione.")

    version = f"lineups_browser_gw{gw}_team_status_v2"
    observed_mapping = build_gameweek_mapping_from_lineups(
        settings, schedule, observations, gameweek=gw, mapping_version=version
    )
    if observed_mapping.empty:
        raise RuntimeError(
            f"Nessuna fixture della Giornata {gw} è stata associata in modo univoco al calendario NBA. "
            "Verifica che Lineups mostri la giornata target e ripeti lo scraping."
        )
    known_statuses = sum(
        int(observed_mapping[column].notna().sum())
        for column in ("home_team_eligible", "away_team_eligible")
    )
    total_sides = 2 * len(observed_mapping)
    eligible_teams = _eligible_teams(observed_mapping)
    if known_statuses == total_sides and not eligible_teams:
        raise RuntimeError(
            f"La cattura Lineups della Giornata {gw} marca tutte le squadre come non eleggibili; "
            "non sostituisco la mappatura precedente."
        )
    if not eligible_teams:
        raise RuntimeError(
            f"La cattura Lineups della Giornata {gw} non contiene alcun matchup eleggibile verificato."
        )

    mapping_paths = sorted(
        (settings.data_path / "processed").glob(f"dunkest_fixture_mapping_{settings.season_id}_*.parquet")
    )
    legacy_path = settings.data_path / "processed" / f"dunkest_fixture_mapping_{settings.season_id}.parquet"
    if legacy_path.is_file():
        mapping_paths.append(legacy_path)
    if len(mapping_paths) > 1:
        raise RuntimeError(
            "Sono presenti più revisioni della mappatura fixture; risolvi le revisioni prima di aggiornare il calendario."
        )
    prior_all = pd.read_parquet(mapping_paths[0]) if mapping_paths else pd.DataFrame(columns=FIXTURE_COLUMNS)
    if not prior_all.empty:
        prior_all = validate_fixture_mapping(prior_all)
        other_weeks = prior_all.loc[~prior_all["dunkest_gameweek"].eq(gw)].copy()
        repeated_ids = set(observed_mapping["nba_game_id"].astype(str)) & set(
            other_weeks["nba_game_id"].astype(str)
        )
        if repeated_ids:
            raise RuntimeError(
                f"La cattura dichiarata Giornata {gw} riutilizza partite già assegnate a un'altra giornata "
                f"({', '.join(sorted(repeated_ids)[:5])}); Lineups potrebbe mostrare ancora la giornata precedente."
            )
        # Dunkest gameweeks can overlap on the calendar because different NBA
        # teams reach their next eligible game on different dates. Identity
        # duplication, not global kickoff ordering, is the safe stale-page guard.
        prior = other_weeks
    else:
        prior = pd.DataFrame(columns=FIXTURE_COLUMNS)
    combined = pd.concat([prior, observed_mapping], ignore_index=True, sort=False)
    combined = combined.drop_duplicates(["season_id", "nba_game_id"], keep="last")
    # One active season file may contain multiple gameweeks; all rows therefore
    # share a version while each row retains its original source timestamp/hash.
    combined["mapping_version"] = "lineups_browser_season_multigw_v1"
    combined = validate_fixture_mapping(combined)
    save_fixture_mapping(
        settings, combined, source="dunkest_lineups_browser_current_gameweek", replace_existing=True
    )
    return get_fixture_mapping(settings, gw)


def parse_fixture_bool(value: object) -> bool | None:
    if pd.isna(value):
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().casefold()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def _eligible_teams(mapping: pd.DataFrame) -> set[str]:
    if mapping.empty:
        return set()
    result: set[str] = set()
    if {"home_team", "home_team_eligible"}.issubset(mapping.columns):
        result.update(
            mapping.loc[mapping["home_team_eligible"].eq(True), "home_team"].astype(str).str.upper()
        )
    if {"away_team", "away_team_eligible"}.issubset(mapping.columns):
        result.update(
            mapping.loc[mapping["away_team_eligible"].eq(True), "away_team"].astype(str).str.upper()
        )
    return result


MAX_PREMATCH_SNAPSHOT_AGE_HOURS = 36.0


def _snapshot_freshness(path: Path, *, max_age_hours: float = MAX_PREMATCH_SNAPSHOT_AGE_HOURS) -> tuple[bool, str]:
    """Require timestamped acquisition metadata; file mtime is not source freshness."""
    if not path.is_file():
        return False, "missing"
    sidecar = path.with_name(path.name + ".meta.json")
    if not sidecar.is_file():
        return False, "missing freshness metadata"
    try:
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
        fetched = pd.to_datetime(meta.get("fetched_at"), utc=True, errors="coerce")
    except (OSError, ValueError, json.JSONDecodeError):
        return False, "invalid freshness metadata"
    if pd.isna(fetched):
        return False, "missing or invalid fetched_at"
    age_hours = (pd.Timestamp.now(tz="UTC") - fetched).total_seconds() / 3600.0
    if age_hours < -0.01:
        return False, "snapshot timestamp is in the future"
    if age_hours > max_age_hours:
        return False, f"stale ({age_hours:.1f}h > {max_age_hours:.1f}h)"
    return True, f"fresh ({age_hours:.1f}h)"


def _snapshot_freshness_as_of(
    path: Path,
    cutoff: pd.Timestamp,
    *,
    max_age_hours: float = MAX_PREMATCH_SNAPSHOT_AGE_HOURS,
) -> tuple[bool, str]:
    """Check when a frozen snapshot was acquired relative to its historical lock."""
    if not path.is_file():
        return False, "missing"
    meta_path = path.with_suffix(path.suffix + ".meta.json")
    if not meta_path.is_file():
        return False, "missing freshness metadata"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        fetched = pd.to_datetime(meta.get("fetched_at"), utc=True, errors="coerce")
        lock = pd.to_datetime(cutoff, utc=True, errors="coerce")
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return False, "invalid freshness metadata"
    if pd.isna(fetched) or pd.isna(lock):
        return False, "missing or invalid fetched_at/lock timestamp"
    age_hours = (lock - fetched).total_seconds() / 3600.0
    if age_hours < -0.01:
        return False, "snapshot was acquired after the historical lock"
    if age_hours > max_age_hours:
        return False, f"stale at historical lock ({age_hours:.1f}h > {max_age_hours}h)"
    return True, f"available {max(0.0, age_hours):.1f}h before historical lock"


def _fixture_mapping_temporal_validity(
    mapping: pd.DataFrame,
    *,
    max_age_hours: float = MAX_PREMATCH_SNAPSHOT_AGE_HOURS,
) -> tuple[bool, str]:
    """Require each mapping observation to precede its fixture and be timely."""
    if mapping.empty or not {"game_datetime_utc", "source_retrieved_at_utc"}.issubset(mapping.columns):
        return False, "fixture mapping or source timestamps missing"
    kickoff = pd.to_datetime(mapping["game_datetime_utc"], errors="coerce", utc=True)
    retrieved = pd.to_datetime(mapping["source_retrieved_at_utc"], errors="coerce", utc=True)
    age_hours = (kickoff - retrieved).dt.total_seconds() / 3600.0
    if kickoff.isna().any() or retrieved.isna().any():
        return False, "fixture mapping source timestamp missing or invalid"
    if age_hours.lt(-0.01).any():
        return False, "fixture mapping was captured after a fixture lock"
    if age_hours.gt(max_age_hours).any():
        oldest = float(age_hours.max())
        return False, f"fixture mapping stale at fixture lock ({oldest:.1f}h > {max_age_hours}h)"
    return True, "fixture mapping captured before each fixture lock"


def load_pre_match_snapshot(
    settings: Settings, dunkest_gameweek: int, *, season_id: str | None = None
) -> dict | None:
    """Load the newest hash-verified PRE_MATCH archive captured before tipoff.

    This reader is intentionally strict: a valid hash alone is insufficient if
    the capture occurred after the first fixture started or its mapping cannot
    establish the gameweek and turn. Invalid archives are ignored, never repaired.
    """
    sid = str(season_id or settings.season_id)
    root = settings.data_path / "archive" / sid / f"gw{int(dunkest_gameweek)}"
    if not root.is_dir():
        return None
    valid: list[tuple[pd.Timestamp, Path, dict, dict[str, pd.DataFrame]]] = []
    for archive in root.glob("pre_match_*"):
        try:
            manifest = json.loads((archive / "manifest.json").read_text(encoding="utf-8"))
            if (
                str(manifest.get("season_id")) != sid
                or int(manifest.get("dunkest_gameweek", -1)) != int(dunkest_gameweek)
                or int(manifest.get("schema_version", -1)) not in {1, 2, 3}
                or not str(manifest.get("source", "")).strip()
            ):
                continue
            captured = pd.to_datetime(manifest.get("captured_at_utc"), errors="coerce", utc=True)
            hashes = manifest.get("sha256", {})
            if pd.isna(captured) or not hashes:
                continue
            tables: dict[str, pd.DataFrame] = {}
            valid_hashes = True
            for name, expected_hash in hashes.items():
                path = archive / str(name)
                if (
                    Path(str(name)).name != str(name)
                    or not str(name).endswith(".parquet")
                    or not path.is_file()
                    or hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash
                ):
                    valid_hashes = False
                    break
                tables[str(name)] = pd.read_parquet(path)
            if not valid_hashes or not {
                "player_market.parquet", "fixture_mapping.parquet", "injuries.parquet", "coach_market.parquet"
            }.issubset(tables):
                continue
            mapping = tables["fixture_mapping.parquet"]
            needed_mapping = {"nba_game_id", "game_datetime_utc", "dunkest_gameweek", "dunkest_turn", "mapping_verified", "fantasy_eligible", "home_team", "away_team"}
            if mapping.empty or not needed_mapping.issubset(mapping.columns):
                continue
            mapping = mapping.loc[
                pd.to_numeric(mapping["dunkest_gameweek"], errors="coerce").eq(int(dunkest_gameweek))
            ].copy()
            lock = pd.to_datetime(mapping["game_datetime_utc"], errors="coerce", utc=True)
            if (
                mapping.empty or lock.isna().any() or lock.min() <= captured
                or not mapping["mapping_verified"].map(parse_fixture_bool).fillna(False).astype(bool).all()
                or mapping["dunkest_turn"].isna().any()
                or mapping["nba_game_id"].astype(str).str.strip().eq("").any()
            ):
                continue
            market = tables["player_market.parquet"]
            aliases = {"team_code": "team", "role": "position", "gameweek": "dunkest_gameweek"}
            for destination, source_column in aliases.items():
                if destination not in market and source_column in market:
                    market[destination] = market[source_column]
            if "gameweek" not in market:
                market["gameweek"] = int(dunkest_gameweek)
            if "role" not in market and "position" in market:
                market["role"] = market["position"]
            if "lineup_group" not in market or "status" not in market:
                # Those fields influence lineup eligibility; they cannot be
                # fabricated for an archive and therefore fail readiness.
                continue
            required_market = {"player_name", "team_code", "role", "cr", "gameweek", "lineup_group", "status"}
            if not required_market.issubset(market.columns) or market.empty:
                continue
            valid.append((captured, archive, manifest, tables | {"_normalized_player_market": market, "_verified_fixture_mapping": mapping}))
        except Exception:
            continue
    if not valid:
        return None
    captured, path, manifest, tables = max(valid, key=lambda row: (row[0], row[1].name))
    return {"path": path, "captured_at_utc": captured, "manifest": manifest, "tables": tables}


def load_post_match_results_archive(
    settings: Settings, dunkest_gameweek: int, *, season_id: str | None = None
) -> dict | None:
    """Load a hash-verified immutable archive with explicit usable outcomes."""
    sid = str(season_id or settings.season_id)
    root = (
        settings.data_path / "archive" / sid
        / f"gw{int(dunkest_gameweek)}"
    )
    if not root.is_dir():
        return None
    valid: list[tuple[float, float, pd.Timestamp, Path, pd.DataFrame, pd.DataFrame, dict]] = []
    for archive in root.glob("post_match_*"):
        manifest_path = archive / "manifest.json"
        player_path = archive / "player_results.parquet"
        coach_path = archive / "coach_results.parquet"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if (
                str(manifest.get("season_id")) != sid
                or int(manifest.get("dunkest_gameweek", -1)) != int(dunkest_gameweek)
                or int(manifest.get("schema_version", -1)) not in {1, 2, 3}
                or not str(manifest.get("source", "")).strip()
            ):
                continue
            hashes = manifest.get("sha256", {})
            for name, path in (
                ("player_results.parquet", player_path),
                ("coach_results.parquet", coach_path),
            ):
                if not path.is_file() or hashes.get(name) != hashlib.sha256(path.read_bytes()).hexdigest():
                    raise ValueError(f"{name} missing or hash mismatch")
            coverage = manifest.get("coverage_audit", {})
            player_coverage = float(coverage.get("player", {}).get("prediction_coverage", 0.0))
            coach_coverage = float(coverage.get("coach", {}).get("coverage", 0.0))
            schema_version = int(manifest.get("schema_version", -1))
            if not coverage.get("timing_check_passed", False):
                continue
            if schema_version >= 3:
                if (
                    not np.isfinite(player_coverage) or not 0.0 <= player_coverage <= 1.0
                    or not np.isfinite(coach_coverage) or not 0.0 <= coach_coverage <= 1.0
                ):
                    continue
            elif (
                not np.isfinite(player_coverage) or not 0.0 < player_coverage <= 1.0
                or not np.isfinite(coach_coverage) or not 0.0 < coach_coverage <= 1.0
            ):
                continue
            players = pd.read_parquet(player_path)
            coaches = pd.read_parquet(coach_path)
            if not {"player_name", "nba_game_id", "actual_pdk"}.issubset(players.columns):
                continue
            if not {"coach", "nba_game_id", "actual_coach_pdk"}.issubset(coaches.columns):
                continue
            if int(manifest.get("schema_version", -1)) >= 3:
                # Schema 3 preserves one row per candidate, including unresolved
                # outcomes. Downstream scoring still consumes only explicit
                # finite official labels and must establish lineup completeness.
                retrieved_at = pd.to_datetime(manifest.get("retrieved_at_utc"), errors="coerce", utc=True)
                if pd.isna(retrieved_at) or not coverage.get("timing_check_passed", False):
                    continue
                valid.append((
                    min(player_coverage, coach_coverage) if coach_coverage > 0 else player_coverage,
                    player_coverage + coach_coverage,
                    retrieved_at, archive, players, coaches, manifest,
                ))
                continue
            player_scores = pd.to_numeric(players["actual_pdk"], errors="coerce")
            coach_scores = pd.to_numeric(coaches["actual_coach_pdk"], errors="coerce")
            if (
                players.empty or coaches.empty
                or not np.isfinite(player_scores.to_numpy(dtype=float, na_value=np.nan)).all()
                or not np.isfinite(coach_scores.to_numpy(dtype=float, na_value=np.nan)).all()
                or players["nba_game_id"].isna().any()
                or coaches["nba_game_id"].isna().any()
            ):
                continue
            retrieved_at = pd.to_datetime(manifest.get("retrieved_at_utc"), errors="coerce", utc=True)
            if pd.isna(retrieved_at):
                continue
            valid.append((
                min(player_coverage, coach_coverage),
                player_coverage + coach_coverage,
                retrieved_at, archive, players, coaches, manifest,
            ))
        except Exception:
            # Invalid/partially written archives are evidence failures, not a
            # reason to fall back to current aggregate result tables.
            continue
    if not valid:
        return None
    _, _, retrieved_at, path, players, coaches, manifest = max(
        valid, key=lambda item: (item[0], item[1], item[2], item[3].name)
    )
    return {
        "path": path,
        "players": players,
        "coaches": coaches,
        "manifest": manifest,
        "retrieved_at_utc": retrieved_at,
    }


def check_backtest_readiness(
    settings: Settings,
    dunkest_gameweek: int,
    *,
    season_id: str | None = None,
) -> dict:
    """Report evidence gates; missing/unknown inputs never count as ready."""
    sid = str(season_id or settings.season_id)
    processed = settings.data_path / "processed"
    checks: dict[str, dict[str, str | bool]] = {}

    prematch_archive = load_pre_match_snapshot(settings, dunkest_gameweek, season_id=sid)
    mapping_path = settings.data_path / "processed" / f"dunkest_fixture_mapping_{sid}_*.parquet"
    if prematch_archive is not None:
        mapping = prematch_archive["tables"]["_verified_fixture_mapping"].copy()
        mapping = mapping.rename(columns={
            "nba_game_id": "nba_game_id",
            "game_datetime_utc": "game_datetime_utc",
        })
        mapping_ok = bool(
            mapping["mapping_verified"].map(parse_fixture_bool).fillna(False).astype(bool).all()
            and mapping["dunkest_turn"].notna().all()
            and mapping["nba_game_id"].astype(str).str.strip().ne("").all()
        )
        mapping_fresh, mapping_fresh_reason = True, "verified immutable PRE_MATCH fixture mapping captured before tipoff"
    else:
        mapping = get_fixture_mapping(settings, dunkest_gameweek, season_id=sid)
        mapping_fresh, mapping_fresh_reason = _fixture_mapping_temporal_validity(mapping)
        mapping_ok = bool(
            not mapping.empty
            and mapping["fantasy_eligible"].notna().all()
            and mapping["mapping_verified"].fillna(False).all()
            and mapping["dunkest_gameweek"].notna().all()
            and mapping["dunkest_turn"].notna().all()
            and mapping_fresh
            and mapping["source"].astype(str).str.strip().ne("").all()
            and mapping["raw_payload_sha256"].astype(str).str.strip().ne("").all()
        )
    if mapping_ok:
        mapping_reason = (
            "immutable PRE_MATCH archive verified before tipoff"
            if prematch_archive is not None
            else "provenance-bearing bridge verified before tipoff and fresh within 36h"
        )
    elif not mapping_fresh:
        mapping_reason = f"{mapping_fresh_reason}: {mapping_path}"
    else:
        mapping_reason = f"missing/unknown/late/unproven mapping: {mapping_path}"
    checks["FIXTURE_MAPPING"] = {"pass": bool(mapping_ok), "reason": mapping_reason}

    price_path = processed / f"player_credits_{sid}_gw{dunkest_gameweek}.parquet"
    roster_ok = False
    price_ok = False
    lock_time = (
        pd.to_datetime(mapping["game_datetime_utc"], errors="coerce", utc=True).min()
        if not mapping.empty else pd.NaT
    )
    market_fresh, market_fresh_reason = _snapshot_freshness_as_of(price_path, lock_time)
    if prematch_archive is not None:
        market = prematch_archive["tables"]["_normalized_player_market"].copy()
        roster_ok = {"player_name", "team_code", "role", "gameweek", "lineup_group", "status"}.issubset(market.columns) and not market.empty
        price_ok = roster_ok and "cr" in market and pd.to_numeric(market["cr"], errors="coerce").notna().all()
    elif price_path.is_file():
        market = pd.read_parquet(price_path)
        roster_ok = {"player_name", "team_code", "role", "gameweek"}.issubset(market.columns) and not market.empty and market_fresh
        price_ok = roster_ok and "cr" in market and pd.to_numeric(market["cr"], errors="coerce").notna().all()
    checks["ROSTER_SNAPSHOT"] = {
        "pass": bool(roster_ok),
        "reason": str(price_path) if roster_ok else f"missing, invalid, or stale player roster snapshot ({market_fresh_reason})",
    }
    checks["PRICE_SNAPSHOT"] = {
        "pass": bool(price_ok),
        "reason": str(price_path) if price_ok else f"missing, invalid, or stale CR snapshot ({market_fresh_reason})",
    }

    injury_path = processed / f"injuries_{sid}_gw{dunkest_gameweek}.parquet"
    injury_ok = False
    injury_fresh, injury_fresh_reason = _snapshot_freshness_as_of(injury_path, lock_time)
    if prematch_archive is not None:
        injuries = prematch_archive["tables"]["injuries.parquet"]
        injury_ok = {"player_name", "team", "status"}.issubset(injuries.columns)
    elif injury_path.is_file():
        injuries = pd.read_parquet(injury_path)
        injury_ok = {"player_name", "team", "status", "gameweek"}.issubset(injuries.columns) and injury_fresh
    checks["INJURY_SNAPSHOT"] = {
        "pass": bool(injury_ok),
        "reason": str(injury_path) if injury_ok else f"missing, invalid, or stale timestamped injury snapshot ({injury_fresh_reason})",
    }

    coach_path = processed / f"coach_market_{sid}_gw{dunkest_gameweek}.parquet"
    coach_ok = False
    coach_fresh, coach_fresh_reason = _snapshot_freshness_as_of(coach_path, lock_time)
    if prematch_archive is not None:
        coaches = prematch_archive["tables"]["coach_market.parquet"]
        coach_ok = {"coach", "team", "coach_cr", "opponent", "nba_game_id"}.issubset(coaches.columns) and not coaches.empty
        if coach_ok:
            fixture_ids = set(mapping["nba_game_id"].astype(str))
            coach_ids = coaches["nba_game_id"].astype(str)
            coach_ok = coach_ids.isin(fixture_ids).all() and coaches["opponent"].astype(str).str.strip().ne("").all()
    elif coach_path.is_file():
        coaches = pd.read_parquet(coach_path)
        coach_ok = {"coach", "team", "coach_cr", "opponent", "date"}.issubset(coaches.columns) and not coaches.empty and coach_fresh
        # Legacy generated coach rows are not proof of a Dunkest fixture.
        coach_ok = coach_ok and {"nba_game_id", "fixture_source"}.issubset(coaches.columns)
    checks["COACH_SNAPSHOT"] = {
        "pass": bool(coach_ok),
        "reason": str(coach_path) if coach_ok else f"missing, invalid, or stale fixture-linked coach snapshot ({coach_fresh_reason})",
    }

    live_market_path = settings.data_path / "current_lineups_market.csv"
    live_market_ok, live_market_reason = _snapshot_freshness(live_market_path)
    availability_path = settings.data_path / "lineups_availability.csv"
    availability_ok, availability_reason = _snapshot_freshness(availability_path)
    checks["LINEUPS_MARKET_SNAPSHOT"] = {"pass": bool(live_market_ok), "reason": live_market_reason}
    checks["LINEUPS_AVAILABILITY_SNAPSHOT"] = {"pass": bool(availability_ok), "reason": availability_reason}

    # Current live captures are reported for diagnostics only. A replay of an
    # old gameweek must be reproducible from its frozen historical snapshots.
    prematch_ok = bool(mapping_ok and roster_ok and price_ok and injury_ok and coach_ok)
    checks["PRE_MATCH_DATA"] = {"pass": prematch_ok, "reason": "all required pre-match snapshots present" if prematch_ok else "one or more required inputs missing, stale, or not fixture-linked"}

    archived_results = load_post_match_results_archive(
        settings, dunkest_gameweek, season_id=sid
    )
    actual_ok = False
    actual_coach_ok = False
    if archived_results is not None:
        actuals = archived_results["players"]
        actual_coaches = archived_results["coaches"]
        fixture_ids = set(mapping["nba_game_id"].astype(str))
        player_scores = pd.to_numeric(actuals["actual_pdk"], errors="coerce")
        actual_ok = (
            not actuals.empty
            and np.isfinite(player_scores.to_numpy(dtype=float, na_value=np.nan)).all()
            and actuals["nba_game_id"].astype(str).isin(fixture_ids).all()
        )
        coach_scores = pd.to_numeric(actual_coaches["actual_coach_pdk"], errors="coerce")
        actual_coach_ok = (
            not actual_coaches.empty
            and np.isfinite(coach_scores.to_numpy(dtype=float, na_value=np.nan)).all()
            and actual_coaches["nba_game_id"].astype(str).isin(fixture_ids).all()
        )
    checks["ACTUAL_RESULTS"] = {
        "pass": bool(actual_ok and actual_coach_ok),
        "reason": (
            str(archived_results["path"])
            if actual_ok and actual_coach_ok and archived_results is not None
            else "hash-verified post-match archive with finite fixture-linked player and coach outcomes missing or invalid"
        ),
    }
    return {
        "season_id": sid,
        "dunkest_gameweek": int(dunkest_gameweek),
        "checks": checks,
        "backtest_ready": all(
            bool(checks[name]["pass"])
            for name in (
                "FIXTURE_MAPPING", "ROSTER_SNAPSHOT", "PRICE_SNAPSHOT",
                "INJURY_SNAPSHOT", "COACH_SNAPSHOT", "PRE_MATCH_DATA",
                "ACTUAL_RESULTS",
            )
        ),
    }
