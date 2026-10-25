"""Safely attach verified official Dunkest PDK labels to NBA game logs."""
from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from dunkest.names import player_key

KEYS = ["PLAYER_ID", "GAME_ID", "GAME_DATE", "TEAM_ABBREVIATION"]
OFFICIAL_LABEL = "PDK_OFFICIAL_VALID"
ROUND_BOX_SCORE_COLUMNS = {
    "PTS": "pts",
    "AST": "ast",
    "REB": "reb",
    "STL": "stl",
    "BLK": "blk",
    "OREB": "oreb",
    "DREB": "dreb",
    "TOV": "tov",
}


def _normalize_identifier(value: object) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text or None


def _canonical_keys(frame: pd.DataFrame, *, source: str) -> pd.DataFrame:
    out = frame.copy()
    if "GAME_ID" not in out and "Game_ID" in out:
        out = out.rename(columns={"Game_ID": "GAME_ID"})
    missing = sorted(set(KEYS) - set(out.columns))
    if missing:
        raise ValueError(f"{source} lacks official PDK join keys: {missing}")
    out["PLAYER_ID"] = out["PLAYER_ID"].map(_normalize_identifier)
    out["GAME_ID"] = out["GAME_ID"].map(_normalize_identifier)
    out["GAME_DATE"] = (
        pd.to_datetime(out["GAME_DATE"], errors="coerce", utc=True)
        .dt.tz_convert(None)
        .dt.normalize()
    )
    out["TEAM_ABBREVIATION"] = (
        out["TEAM_ABBREVIATION"].astype("string").str.strip().str.upper()
    )
    if out[KEYS].isna().any().any():
        raise ValueError(f"{source} contains missing official PDK join keys.")
    if out.duplicated(KEYS).any():
        raise ValueError(f"{source} has duplicate official PDK join keys.")
    return out[KEYS].reset_index(drop=True)


def official_pdk_overlay_path(data_path: str | Path, season: str) -> Path | None:
    """Return the versioned official-PDK overlay selected for a season, if any."""
    processed = Path(data_path) / "processed"
    candidates = [
        processed / f"player_game_logs_{season}_official_pdk_overlay_v4.parquet",
        processed / f"player_game_logs_{season}_official_pdk_overlay.parquet",
    ]
    return next((path for path in candidates if path.exists()), None)


def attach_official_pdk_labels(
    player_logs: pd.DataFrame,
    data_path: str | Path,
    season: str,
) -> pd.DataFrame:
    """Attach labels from a versioned local overlay, retaining proxy PDK.

    The join is one-to-one on NBA player/game/date/team identity. Missing labels
    remain null, so target selection can safely fall back to the proxy target.
    """
    if player_logs.empty:
        return player_logs.copy()

    overlay_path = official_pdk_overlay_path(data_path, season)
    if overlay_path is None:
        out = player_logs.copy()
        if OFFICIAL_LABEL in out:
            out[OFFICIAL_LABEL] = pd.to_numeric(out[OFFICIAL_LABEL], errors="coerce")
        return out

    if OFFICIAL_LABEL not in player_logs.columns and not set(KEYS).issubset(
        player_logs.columns
    ) and not ({"PLAYER_ID", "Game_ID", "GAME_DATE", "TEAM_ABBREVIATION"} <= set(player_logs.columns)):
        warnings.warn(
            f"Cannot attach official PDK labels from {overlay_path}: player log identity keys are missing; using proxy labels.",
            RuntimeWarning,
            stacklevel=2,
        )
        return player_logs.copy()

    overlay = pd.read_parquet(overlay_path)
    required_overlay = set(KEYS + [OFFICIAL_LABEL])
    if not required_overlay.issubset(overlay.columns):
        raise ValueError(
            f"Official PDK overlay {overlay_path} lacks columns: "
            f"{sorted(required_overlay - set(overlay.columns))}"
        )

    try:
        base_keys = _canonical_keys(player_logs, source="Player logs")
        overlay_keys = _canonical_keys(overlay, source=f"Official overlay {overlay_path}")
    except ValueError as exc:
        warnings.warn(
            f"Cannot safely attach official PDK labels from {overlay_path}: {exc}; using existing targets.",
            RuntimeWarning,
            stacklevel=2,
        )
        return player_logs.copy()

    labels = overlay_keys.copy()
    labels[OFFICIAL_LABEL] = pd.to_numeric(overlay[OFFICIAL_LABEL], errors="coerce").reset_index(drop=True)
    joined = base_keys.merge(
        labels, on=KEYS, how="left", validate="one_to_one", indicator=True, sort=False
    )
    matched = int(joined["_merge"].eq("both").sum())
    if matched == 0:
        warnings.warn(
            f"Official PDK overlay {overlay_path} matched no player-game rows; using existing targets.",
            RuntimeWarning,
            stacklevel=2,
        )
        return player_logs.copy()
    if matched < len(player_logs):
        warnings.warn(
            f"Official PDK overlay matched {matched}/{len(player_logs)} player-game rows for {season}; unmatched rows will retain null official labels.",
            RuntimeWarning,
            stacklevel=2,
        )

    out = player_logs.copy().reset_index(drop=True)
    out[OFFICIAL_LABEL] = joined[OFFICIAL_LABEL].to_numpy()
    return out


def attach_observed_round_pdk_labels(
    player_logs: pd.DataFrame,
    data_path: str | Path,
    *,
    season_id: str,
    target_cutoff_utc: object,
) -> pd.DataFrame:
    """Attach official per-round PDK only after an exact box-score join.

    Dunkest round rows do not include NBA game IDs. They are linked to NBA
    player-game rows by canonical name, team, and all eight basic box-score
    fields. Ambiguous, incomplete, conflicting, and post-cutoff rows are
    skipped. The input frame is never mutated.
    """
    out = player_logs.copy().reset_index(drop=True)
    diagnostics = {
        "snapshots_found": 0,
        "snapshot_rows": 0,
        "eligible_before_cutoff": 0,
        "matched": 0,
        "ambiguous": 0,
        "unmatched": 0,
        "conflicts": 0,
        "missing_signature": 0,
    }
    out.attrs["round_pdk_overlay"] = diagnostics
    if out.empty:
        return out

    cutoff = pd.to_datetime(target_cutoff_utc, errors="coerce", utc=True)
    if pd.isna(cutoff):
        return out

    required_logs = {
        "PLAYER_ID", "PLAYER_NAME", "TEAM_ABBREVIATION", "GAME_ID",
        *ROUND_BOX_SCORE_COLUMNS.keys(),
    }
    if not required_logs.issubset(out.columns):
        return out

    processed = Path(data_path) / "processed"
    paths = sorted(processed.glob(f"dunkest_stats_{season_id}_gw*_round*.parquet"))
    diagnostics["snapshots_found"] = len(paths)
    snapshots = []
    for path in paths:
        frame = pd.read_parquet(path)
        required = {"player_name", "team_code", "pdk", "observed_at_utc", *ROUND_BOX_SCORE_COLUMNS.values()}
        if required.issubset(frame.columns):
            snapshots.append(frame)
    if not snapshots:
        out.attrs["round_pdk_overlay"] = diagnostics
        return out

    stats = pd.concat(snapshots, ignore_index=True, sort=False)
    diagnostics["snapshot_rows"] = len(stats)
    observed = pd.to_datetime(stats["observed_at_utc"], errors="coerce", utc=True)
    available = observed.notna() & observed.lt(cutoff)
    diagnostics["eligible_before_cutoff"] = int(available.sum())
    stats = stats.loc[available].copy().reset_index(drop=True)
    observed = observed.loc[available].reset_index(drop=True)
    if stats.empty:
        out.attrs["round_pdk_overlay"] = diagnostics
        return out

    logs = out.reset_index(drop=True).copy()
    logs["_row_id"] = np.arange(len(logs))
    logs["_name_key"] = logs["PLAYER_NAME"].map(player_key)
    logs["_team_key"] = logs["TEAM_ABBREVIATION"].astype("string").str.strip().str.upper()
    logs["_player_id_key"] = logs["PLAYER_ID"].map(_normalize_identifier)
    logs["_game_id_key"] = logs["GAME_ID"].map(_normalize_identifier)
    for column in ROUND_BOX_SCORE_COLUMNS:
        logs[f"_box_{column}"] = pd.to_numeric(logs[column], errors="coerce")
    stats["_name_key"] = stats["player_name"].map(player_key)
    stats["_team_key"] = stats["team_code"].astype("string").str.strip().str.upper()
    stats["_pdk"] = pd.to_numeric(stats["pdk"], errors="coerce")
    for local, remote in ROUND_BOX_SCORE_COLUMNS.items():
        stats[f"_box_{local}"] = pd.to_numeric(stats[remote], errors="coerce")

    labels: dict[int, tuple[float, str]] = {}
    used_games: set[tuple[str, str]] = set()
    for idx, row in stats.iterrows():
        if not row["_name_key"] or not row["_team_key"] or not np.isfinite(row["_pdk"]):
            diagnostics["missing_signature"] += 1
            continue
        candidate = logs.loc[
            logs["_name_key"].eq(row["_name_key"])
            & logs["_team_key"].eq(row["_team_key"])
        ]
        for column in ROUND_BOX_SCORE_COLUMNS:
            source_value = row[f"_box_{column}"]
            if pd.isna(source_value):
                candidate = candidate.iloc[0:0]
                break
            candidate = candidate.loc[
                candidate[f"_box_{column}"].notna()
                & np.isclose(candidate[f"_box_{column}"], source_value, rtol=0, atol=1e-6)
            ]
        if len(candidate) == 0:
            diagnostics["unmatched"] += 1
            continue
        if len(candidate) != 1:
            diagnostics["ambiguous"] += 1
            continue
        match = candidate.iloc[0]
        if pd.isna(match["_player_id_key"]) or pd.isna(match["_game_id_key"]):
            diagnostics["missing_signature"] += 1
            continue
        game_key = (str(match["_player_id_key"]), str(match["_game_id_key"]))
        if game_key in used_games:
            diagnostics["ambiguous"] += 1
            continue
        existing = pd.to_numeric(
            pd.Series([out.at[int(match["_row_id"]), OFFICIAL_LABEL]])
            if OFFICIAL_LABEL in out else pd.Series([np.nan]), errors="coerce"
        ).iloc[0]
        if pd.notna(existing) and not np.isclose(existing, row["_pdk"], rtol=0, atol=1e-6):
            diagnostics["conflicts"] += 1
            continue
        labels[int(match["_row_id"])] = (float(row["_pdk"]), observed.iloc[idx].isoformat())
        used_games.add(game_key)

    if OFFICIAL_LABEL not in out:
        out[OFFICIAL_LABEL] = np.nan
    if "PDK_OFFICIAL_AVAILABLE_AT_UTC" not in out:
        out["PDK_OFFICIAL_AVAILABLE_AT_UTC"] = pd.NA
    for row_id, (pdk, available_at) in labels.items():
        out.at[row_id, OFFICIAL_LABEL] = pdk
        out.at[row_id, "PDK_OFFICIAL_AVAILABLE_AT_UTC"] = available_at
    diagnostics["matched"] = len(labels)
    out.attrs["round_pdk_overlay"] = diagnostics
    return out
