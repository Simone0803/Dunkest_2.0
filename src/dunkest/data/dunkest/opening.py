from __future__ import annotations

from copy import copy
from pathlib import Path

import pandas as pd

from dunkest.config import Settings
from dunkest.data.dunkest import client as dk_client
from dunkest.names import player_key
from dunkest.rules.eligibility import unavailable_mask
from dunkest.rules.pdk import normalize_position


def _load_credits_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep=None, engine="python")
    cols = {str(c).strip().lower(): c for c in df.columns}
    name_col = cols.get("player_name") or cols.get("coach_name") or cols.get("giocatore") or cols.get("player") or cols.get("name") or cols.get("nome") or cols.get("allenatore")
    cr_col = cols.get("cr") or cols.get("crediti") or cols.get("credits") or cols.get("price") or cols.get("prezzo")
    if not name_col or not cr_col:
        raise ValueError(f"Credits file must have player name and CR columns: {path}")
    out = pd.DataFrame({
        "player_name": df[name_col].astype(str).str.strip(),
        "cr_file": pd.to_numeric(
            df[cr_col].astype(str).str.replace(",", ".", regex=False).str.extract(r"([-+]?\d+(?:\.\d+)?)", expand=False),
            errors="coerce",
        ),
    })
    team_col = cols.get("team_code") or cols.get("team") or cols.get("squadra")
    role_col = cols.get("role") or cols.get("position") or cols.get("ruolo") or cols.get("posizione")
    if team_col:
        out["team_code"] = df[team_col].astype(str).str.strip().str.upper()
    if role_col:
        raw_role = df[role_col].astype(str).str.strip().str.upper()
        # Keep Dunkest's head-coach marker intact; normalizing HC as a player
        # position silently turned coaches into forwards in the old importer.
        out["role"] = raw_role.map(lambda value: "HC" if value in {"HC", "COACH", "ALLENATORE"} else normalize_position(value))
        invalid = ~out["role"].isin({"G", "F", "C", "HC"})
        if invalid.any():
            raise ValueError(f"Ruoli non riconosciuti nel file crediti: {sorted(raw_role[invalid].unique())}")
    group_col = cols.get("lineup_group") or cols.get("lineup")
    if group_col:
        out["lineup_group"] = df[group_col].astype(str).str.strip().str.upper()
    starter_col = cols.get("starter") or cols.get("is_starter")
    if starter_col:
        starter = df[starter_col].astype(str).str.strip().str.casefold()
        out["starter"] = starter.map({"true": True, "1": True, "yes": True, "starter": True,
                                      "false": False, "0": False, "no": False, "bench": False})
    status_col = cols.get("status") or cols.get("availability")
    if status_col:
        out["status"] = df[status_col].astype(str).str.strip().str.upper()
    entity_col = cols.get("entity_type") or cols.get("type") or cols.get("tipo")
    if entity_col:
        out["entity_type"] = df[entity_col].astype(str).str.strip().str.casefold()
    prior_name_col = cols.get("prior_player_name") or cols.get("historical_name")
    if prior_name_col:
        out["prior_player_name"] = df[prior_name_col].astype(str).str.strip()
    return out.dropna(subset=["cr_file"])


def fetch_opening_coach_market(credits_file: Path | None) -> pd.DataFrame:
    """Return exact current coach CR/name/team rows from the Lineups export."""
    snapshot = Path(__file__).resolve().parents[4] / "config" / "dunkest_coaches_2026-27.csv"
    base = pd.DataFrame(columns=["coach", "team", "coach_cr"])
    if snapshot.exists():
        base = _load_credits_csv(snapshot).rename(
            columns={"player_name": "coach", "team_code": "team", "cr_file": "coach_cr"}
        )[["coach", "team", "coach_cr"]]

    if credits_file is not None and credits_file.exists():
        market = _load_credits_csv(credits_file)
        is_coach = market.get("role", pd.Series("", index=market.index)).eq("HC")
        if "entity_type" in market:
            is_coach |= market["entity_type"].isin({"coach", "head coach", "allenatore", "hc"})
        if "team_code" in market:
            out = market.loc[is_coach, ["player_name", "team_code", "cr_file"]].copy()
            if not out.empty:
                out = out.rename(columns={"player_name": "coach", "team_code": "team", "cr_file": "coach_cr"})
                out["team"] = out["team"].astype(str).str.strip().str.upper()
                out["coach_cr"] = pd.to_numeric(out["coach_cr"], errors="coerce")
                overrides = out.dropna(subset=["coach_cr"]).drop_duplicates("team", keep="last")
                base = base[~base["team"].isin(overrides["team"])]
                return pd.concat([base, overrides], ignore_index=True).drop_duplicates("team", keep="last")

    # Snapshot scraped from Dunkest Lineups on 2026-09-29; refreshed rows above
    # replace matching teams while preserving the rest of this complete market.
    return base.drop_duplicates("team", keep="last")


def _lineups_hard_out_keys(settings: Settings) -> set[str]:
    """Current-turn OUT identities from the browser market and its archive."""
    paths = [
        settings.data_path / "current_lineups_market.csv",
        settings.data_path / "lineups_availability.csv",
    ]
    keys: set[str] = set()
    for path in paths:
        if not path.is_file():
            continue
        try:
            frame = pd.read_csv(path)
        except (OSError, pd.errors.ParserError, UnicodeDecodeError):
            continue
        frame.columns = [str(column).strip().lower() for column in frame.columns]
        if "dunkest_turn" in frame:
            if settings.target_dunkest_turn is None:
                continue
            frame = frame.loc[
                pd.to_numeric(frame["dunkest_turn"], errors="coerce").eq(
                    int(settings.target_dunkest_turn)
                )
            ]
        elif "gameweek" in frame:
            # Older scraper exports used gameweek for the selected Turno.
            continue
        if "player_name" not in frame:
            continue
        hard_out = unavailable_mask(frame)
        keys.update(frame.loc[hard_out, "player_name"].dropna().astype(str).map(player_key))
    return {key for key in keys if key}


def fetch_opening_market_pool(
    settings: Settings,
    credits_file: Path | None = None,
    use_pdk_cr_proxy: bool = True,
    pdk_cr_scale: float = 2.75,
) -> pd.DataFrame:
    """
    Pool for Giornata 1 / new team.

    - `prior_pdk` comes from Dunkest's official NBA statistics table for the
      configured completed season, not from the upcoming season or a box-score
      reconstruction.
    - `cr` comes from the target season's API/CSV; prior-season prices are never
      carried forward as if they were current.
    """
    df = dk_client.fetch_nba_season_players(settings)
    file_market = _load_credits_csv(credits_file) if credits_file and credits_file.exists() else pd.DataFrame()
    if not file_market.empty and "role" in file_market:
        file_market = file_market[file_market["role"] != "HC"].copy()
    if not file_market.empty and "entity_type" in file_market:
        file_market = file_market[~file_market["entity_type"].isin({"coach", "head coach", "allenatore", "hc"})].copy()
    if df.empty:
        if file_market.empty:
            return pd.DataFrame()
        if not {"team_code", "role"}.issubset(file_market.columns):
            raise ValueError(
                "Il market Dunkest non è ancora disponibile via API: il CSV deve includere "
                "player_name, cr, team e role (o squadra e ruolo) per applicare i vincoli."
            )
        df = file_market.rename(columns={"cr_file": "cr"}).copy()
        df["position"] = df["role"]
        df["pdk"] = float("nan")
        df["cr_official"] = pd.to_numeric(df["cr"], errors="coerce").fillna(0.0)
    else:
        df = df.copy()
    prior = copy(settings)
    prior.season_id = settings.opening_prior_season_id
    prior.min_cr = 0.0
    prior.max_cr = 100.0
    start_year = int(settings.feature_season[:4])
    end_year = int(settings.feature_season[-2:]) + 2000
    prior.nba_season_start = f"{start_year}-09-01"
    prior.nba_season_end = f"{end_year}-07-01"
    historical = dk_client.fetch_nba_season_players(prior)
    if not historical.empty and "pdk" in historical:
        historical = historical[["player_name", "pdk"]].copy()
        historical["prior_pdk"] = pd.to_numeric(historical["pdk"], errors="coerce")
        historical["key"] = historical["player_name"].map(player_key)
        historical = historical.drop_duplicates("key", keep="first")
        source_names = df.get("prior_player_name", df["player_name"])
        df["key"] = source_names.map(player_key)
        df = df.merge(historical[["key", "prior_pdk"]], on="key", how="left")
    else:
        # The Dunkest table is sometimes unavailable before the season starts.
        # The season-opener pipeline fills this from complete prior-year NBA
        # game logs using the Dunkest box-score scoring formula.
        df["prior_pdk"] = float("nan")
    df["role"] = df["position"].apply(normalize_position)
    df["cr_official"] = pd.to_numeric(df["cr"], errors="coerce").fillna(0.0)
    df["key"] = df["player_name"].map(player_key)

    if not file_market.empty:
        file_cr = file_market
        file_cr["key"] = file_cr["player_name"].map(player_key)
        file_cols = ["key", "cr_file"] + [
            c for c in ("team_code", "role", "prior_player_name", "lineup_group", "starter", "status")
            if c in file_cr.columns
        ]
        df = df.merge(file_cr[file_cols], on="key", how="left", suffixes=("", "_file"))
        if "team_code_file" in df:
            df["team_code"] = df["team_code_file"].fillna(df.get("team_code"))
        if "role_file" in df:
            df["role"] = df["role_file"].fillna(df.get("role"))
        for col in ("lineup_group", "starter", "status"):
            file_col = f"{col}_file"
            if file_col in df:
                if col not in df:
                    df[col] = pd.NA
                df[col] = df[file_col].combine_first(df[col])
    else:
        df["cr_file"] = float("nan")

    # Current prices from the Dunkest lineup/statistics table are the default;
    # an explicitly supplied current list takes precedence.
    df["cr"] = 0.0
    df["cr_source"] = "missing"
    for source_col, source_name in (("cr_official", "dunkest_lineup_api"), ("cr_file", "credits_file")):
        valid = pd.to_numeric(df[source_col], errors="coerce") >= settings.min_cr
        df.loc[valid, "cr"] = pd.to_numeric(df.loc[valid, source_col], errors="coerce")
        df.loc[valid, "cr_source"] = source_name
    df["cr_is_official"] = df["cr_source"] != "missing"

    if use_pdk_cr_proxy:
        proxy = (df["prior_pdk"] / pdk_cr_scale).clip(settings.min_cr, settings.max_cr)
        missing = df["cr"] < settings.min_cr
        df.loc[missing, "cr"] = proxy[missing]
        df.loc[missing, "cr_source"] = "pdk_proxy"

    # Lineups' INDISPONIBILI group is a hard exclusion from the purchase
    # candidates, not merely a zero-point projection. Status fields are also
    # honored for CSVs exported by older scraper versions.
    df = df.loc[~unavailable_mask(df)].copy()
    # OUT names are also stored separately because the Lineups availability
    # panel is league-wide and does not belong in the price export itself.
    hard_out_keys = _lineups_hard_out_keys(settings)
    if hard_out_keys:
        df = df.loc[~df["player_name"].map(player_key).isin(hard_out_keys)].copy()
    df = df[df["cr"] >= settings.min_cr].copy()
    df["pdk"] = df["prior_pdk"]
    df["gameweek"] = 1
    duplicate_names = df["player_name"].map(player_key)
    duplicated = df.loc[duplicate_names.duplicated(keep=False)].copy()
    if not duplicated.empty:
        identity = duplicated.assign(_name=duplicate_names.loc[duplicated.index]).groupby("_name")[
            ["team_code", "role"]
        ].nunique(dropna=False)
        ambiguous = identity[(identity > 1).any(axis=1)]
        if not ambiguous.empty:
            raise ValueError(
                "Il listino contiene nomi giocatore duplicati con team o ruolo diversi: "
                f"{ambiguous.index.tolist()[:8]}. Usa nomi completi/disambiguati."
            )
        df = df.loc[~duplicate_names.duplicated(keep="first")].copy()
    df = df.drop(columns=["key"], errors="ignore")
    return df
