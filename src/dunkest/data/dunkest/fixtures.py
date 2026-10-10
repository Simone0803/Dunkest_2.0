"""Explicit bridge between NBA games and Dunkest scoring fixtures.

NBA schedule weeks and Dunkest matchdays/turns are separate namespaces. This
module never infers one from the other: only an archived, provenance-bearing
bridge may mark a game fantasy eligible.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from dunkest.config import Settings


FIXTURE_COLUMNS = [
    "season_id",
    "nba_season",
    "nba_game_id",
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
    {"home_team_eligible", "away_team_eligible"}
)


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
    # Older saved bridges only had a game-level flag. Preserve their meaning
    # for compatibility, while new browser captures carry independent status
    # for the home and away Dunkest franchises.
    if "home_team_eligible" not in out:
        out["home_team_eligible"] = out["fantasy_eligible"]
    if "away_team_eligible" not in out:
        out["away_team_eligible"] = out["fantasy_eligible"]
    out = out[FIXTURE_COLUMNS].copy()
    for column in ("season_id", "nba_season", "nba_game_id", "home_team", "away_team", "source", "mapping_version"):
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
        mapping["mapping_verified"].fillna(False).astype(bool)
        & (
            mapping["home_team_eligible"].fillna(False).astype(bool)
            | mapping["away_team_eligible"].fillna(False).astype(bool)
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


def build_gameweek1_mapping_from_lineups(
    settings: Settings,
    nba_schedule: pd.DataFrame,
    observations: pd.DataFrame,
    *,
    mapping_version: str = "lineups_browser_gw1_team_status_v2",
) -> pd.DataFrame:
    """Join every fixture shown by Dunkest Lineups to its NBA game identity.

    Browser capture is authoritative for dates, Turni, and each team's
    black/gray validity state. The NBA schedule supplies only fixture identity
    and actual home/away orientation.
    """
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
            # Some Dunkest pages display the local tip-off date while the NBA
            # endpoint labels games by UTC date; use the unique team pairing
            # only when it is unambiguous in the season schedule.
            candidates = schedule.loc[pair]
        if len(candidates) != 1:
            continue
        game = candidates.iloc[0]
        eligibility_by_team = {
            first: _parse_fixture_bool(observation.get("team_a_eligible")),
            second: _parse_fixture_bool(observation.get("team_b_eligible")),
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
            "dunkest_gameweek": 1,
            "dunkest_turn": turn,
            "fantasy_eligible": any_eligible,
            "mapping_verified": True,
            "eligibility_reason": (
                "official_lineups_black_gray_status_observed"
                if home_eligible is not None and away_eligible is not None
                else "official_lineups_status_unknown_fail_closed"
            ),
            "source": "dunkest_lineups_browser",
            "source_url_or_endpoint": "https://fantasy.dunkest.com/1/lineups",
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
        existing_statuses = sum(
            int(existing[column].notna().sum())
            for column in ("home_team_eligible", "away_team_eligible")
            if column in existing
        )
        # Do not demand that every NBA franchise plays in this Giornata: the
        # official rules explicitly allow rest teams. A partial capture can
        # safely guide only the sides whose black/gray state was observed.
        if observed_teams and observed_statuses:
            if existing.empty or observed_statuses > existing_statuses:
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


def _parse_fixture_bool(value: object) -> bool | None:
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

    mapping_path = settings.data_path / "processed" / f"dunkest_fixture_mapping_{sid}_*.parquet"
    mapping = get_fixture_mapping(settings, dunkest_gameweek, season_id=sid)
    mapping_temporally_available = bool(
        not mapping.empty
        and mapping["source_retrieved_at_utc"].le(mapping["game_datetime_utc"]).all()
    )
    mapping_ok = bool(
        not mapping.empty
        and mapping["fantasy_eligible"].notna().all()
        and mapping["mapping_verified"].fillna(False).all()
        and mapping["dunkest_gameweek"].notna().all()
        and mapping["dunkest_turn"].notna().all()
        and mapping_temporally_available
        and mapping["source"].astype(str).str.strip().ne("").all()
        and mapping["raw_payload_sha256"].astype(str).str.strip().ne("").all()
    )
    checks["FIXTURE_MAPPING"] = {
        "pass": bool(mapping_ok),
        "reason": "provenance-bearing bridge known before tipoff" if mapping_ok else (
            f"missing/unknown/late/unproven mapping: {mapping_path}"
        ),
    }

    price_path = processed / f"player_credits_{sid}_gw{dunkest_gameweek}.parquet"
    roster_ok = False
    price_ok = False
    if price_path.is_file():
        market = pd.read_parquet(price_path)
        roster_ok = {"player_name", "team_code", "role", "gameweek"}.issubset(market.columns) and not market.empty
        price_ok = roster_ok and "cr" in market and pd.to_numeric(market["cr"], errors="coerce").notna().all()
    checks["ROSTER_SNAPSHOT"] = {"pass": bool(roster_ok), "reason": str(price_path) if roster_ok else "missing or invalid player roster snapshot"}
    checks["PRICE_SNAPSHOT"] = {"pass": bool(price_ok), "reason": str(price_path) if price_ok else "missing or invalid CR snapshot"}

    injury_path = processed / f"injuries_{sid}_gw{dunkest_gameweek}.parquet"
    injury_ok = False
    if injury_path.is_file():
        injuries = pd.read_parquet(injury_path)
        injury_ok = {"player_name", "team", "status", "gameweek"}.issubset(injuries.columns)
    checks["INJURY_SNAPSHOT"] = {"pass": bool(injury_ok), "reason": str(injury_path) if injury_ok else "missing or invalid timestamped injury snapshot"}

    coach_path = processed / f"coach_market_{sid}_gw{dunkest_gameweek}.parquet"
    coach_ok = False
    if coach_path.is_file():
        coaches = pd.read_parquet(coach_path)
        coach_ok = {"coach", "team", "coach_cr", "opponent", "date"}.issubset(coaches.columns) and not coaches.empty
        # Legacy generated coach rows are not proof of a Dunkest fixture.
        coach_ok = coach_ok and {"nba_game_id", "fixture_source"}.issubset(coaches.columns)
    checks["COACH_SNAPSHOT"] = {"pass": bool(coach_ok), "reason": str(coach_path) if coach_ok else "missing fixture-linked coach snapshot"}

    prematch_ok = bool(mapping_ok and roster_ok and price_ok and injury_ok and coach_ok)
    checks["PRE_MATCH_DATA"] = {"pass": prematch_ok, "reason": "all required pre-match snapshots present" if prematch_ok else "one or more required inputs missing, stale, or not fixture-linked"}

    result_path = processed / f"dunkest_players_{sid}_gw{dunkest_gameweek}.parquet"
    actual_ok = False
    if result_path.is_file():
        actuals = pd.read_parquet(result_path)
        actual_ok = (
            {"player_name", "actual_pdk", "gameweek_stats_available", "nba_game_id"}.issubset(actuals.columns)
            and actuals["gameweek_stats_available"].fillna(False).astype(bool).any()
            and pd.to_numeric(actuals["actual_pdk"], errors="coerce").notna().any()
            and actuals["nba_game_id"].astype(str).isin(set(mapping["nba_game_id"].astype(str))).all()
        )
    actual_coach_path = processed / f"dunkest_coach_results_{sid}_gw{dunkest_gameweek}.parquet"
    actual_coach_ok = False
    if actual_coach_path.is_file():
        actual_coaches = pd.read_parquet(actual_coach_path)
        actual_coach_ok = {"team", "nba_game_id", "actual_coach_pdk"}.issubset(actual_coaches.columns)
        if actual_coach_ok:
            actual_coach_ok = actual_coaches["nba_game_id"].astype(str).isin(
                set(mapping["nba_game_id"].astype(str))
            ).all()
    checks["ACTUAL_RESULTS"] = {
        "pass": bool(actual_ok and actual_coach_ok),
        "reason": "player and coach outcomes linked to verified NBA game IDs" if actual_ok and actual_coach_ok else "player and/or coach actual results missing or not linked to fixture identity",
    }
    return {
        "season_id": sid,
        "dunkest_gameweek": int(dunkest_gameweek),
        "checks": checks,
        "backtest_ready": all(bool(item["pass"]) for item in checks.values()),
    }
