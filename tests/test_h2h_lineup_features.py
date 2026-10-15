import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "lineup_h2h_experiment", ROOT / "scripts/backtest_dunkest_historical_lineups_h2h_v6.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_candidate_h2h_excludes_same_day_and_shrinks_to_prior_form():
    candidates = pd.DataFrame([{
        "player_key": "playerone", "target_opponent": "BOS", "prev5_pdk_mean": 20.0,
    }])
    histories = {
        ("playerone", "BOS"): (
            np.array(["2024-01-01", "2024-01-03"], dtype="datetime64[ns]"),
            np.array([10.0, 100.0]),
            np.array([25.0, 35.0]),
        )
    }
    out = MODULE.build_candidate_h2h(candidates, "2024-01-03", histories)
    assert out.loc[0, "h2h_pdk_mean_prev5"] == 10.0
    assert out.loc[0, "h2h_pdk_last"] == 10.0
    assert out.loc[0, "h2h_valid_pdk_games_prev5"] == 1.0
    assert out.loc[0, "h2h_pdk_mean_shrunk_prev5"] == 17.5


def test_candidate_h2h_falls_back_to_general_form_without_history():
    candidates = pd.DataFrame([{
        "player_key": "playerone", "target_opponent": "BOS", "prev5_pdk_mean": 14.0,
    }])
    out = MODULE.build_candidate_h2h(candidates, "2024-01-03", {})
    assert out.loc[0, "h2h_pdk_mean_shrunk_prev5"] == 14.0
    assert out.loc[0, "h2h_valid_pdk_games_prev5"] == 0.0
    assert np.isnan(out.loc[0, "h2h_pdk_mean_prev5"])


def test_candidate_h2h_does_not_mix_opponents():
    candidates = pd.DataFrame([{
        "player_key": "playerone", "target_opponent": "BOS", "prev5_pdk_mean": 14.0,
    }])
    histories = {
        ("playerone", "NYK"): (
            np.array(["2024-01-01"], dtype="datetime64[ns]"),
            np.array([99.0]), np.array([30.0]),
        )
    }
    out = MODULE.build_candidate_h2h(candidates, "2024-01-03", histories)
    assert out.loc[0, "h2h_pdk_mean_shrunk_prev5"] == 14.0
    assert out.loc[0, "h2h_valid_pdk_games_prev5"] == 0.0
