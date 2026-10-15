"""Leakage regressions for the final-season game-level H2H feature builder."""
import importlib.util
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/audit_dunkest_h2h_final_holdout_2025-26_v1.py"
SPEC = importlib.util.spec_from_file_location("dunkest_h2h_holdout_v1", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _rows():
    return pd.DataFrame({
        "game_date": pd.to_datetime(["2024-01-01", "2024-01-05", "2024-01-10", "2024-01-10", "2024-01-05"]),
        "season_id": ["19", "19", "19", "19", "19"],
        "dunkest_player_id": ["1"] * 5,
        "dunkest_player_name": ["Test Player"] * 5,
        "gameId": ["a", "b", "c", "d", "e"],
        "opponentTeamCode": ["BOS", "BOS", "BOS", "BOS", "NYK"],
        "target_pdk": [10.0, 20.0, 999.0, 30.0, 50.0],
        "prev5_pdk_mean": [12.0, 12.0, 12.0, 12.0, 12.0],
    })


def test_final_holdout_h2h_excludes_same_day_and_shrinks_prior_history():
    result, audit = MODULE.attach_h2h(_rows())
    target = result.loc[result.gameId.eq("c")].iloc[0]
    assert target.h2h_valid_games_prev5 == 2
    assert target.h2h_pdk_mean_prev5 == 15.0
    assert target.h2h_pdk_last == 20.0
    assert target.h2h_pdk_mean_shrunk_prev5 == 13.2
    assert audit["rows_with_prior_h2h"] >= 2


def test_final_holdout_h2h_does_not_mix_opponents():
    result, _ = MODULE.attach_h2h(_rows())
    target = result.loc[result.gameId.eq("c")].iloc[0]
    assert target.h2h_pdk_mean_prev5 == 15.0
    assert target.h2h_valid_games_prev5 == 2


def test_final_holdout_h2h_falls_back_to_prior_form_without_history():
    rows = _rows().iloc[[2]].copy()
    rows["game_date"] = pd.Timestamp("2023-12-31")
    result, _ = MODULE.attach_h2h(rows)
    target = result.iloc[0]
    assert target.h2h_valid_games_prev5 == 0
    assert pd.isna(target.h2h_pdk_mean_prev5)
    assert target.h2h_pdk_mean_shrunk_prev5 == 12.0
