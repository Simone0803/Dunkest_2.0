import numpy as np
import pandas as pd

from dunkest.backtest.metrics import compute_backtest_metrics


def test_backtest_metrics_do_not_score_missing_or_unmeasurable_outcomes():
    results = pd.DataFrame(
        {
            "gameweek": [1, 1],
            "rank": [1, 1],
            "realized_team_score": [40.0, np.nan],
            "ex_post_optimum": [np.nan, np.nan],
            "captain_hit": [1.0, np.nan],
            "coach_hit": [np.nan, np.nan],
            "num_transfers": [0, 0],
        }
    )

    report = compute_backtest_metrics(results)

    assert report.average_team_score == 40.0
    assert np.isnan(report.regret_vs_ex_post)
    assert np.isnan(report.top1_hit_rate)
    assert np.isnan(report.top3_hit_rate)
    assert report.captain_accuracy == 1.0
    assert np.isnan(report.coach_accuracy)