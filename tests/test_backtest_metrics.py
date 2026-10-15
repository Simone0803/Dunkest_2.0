import numpy as np
import pandas as pd

from dunkest.backtest.metrics import compute_backtest_metrics, compute_lineup_coverage


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


def test_lineup_coverage_reports_missing_actuals_against_requested_weeks():
    results = pd.DataFrame(
        {
            "gameweek": [1, 1, 1, 2, 2],
            "rank": [1, 2, 3, 1, 2],
            "actual_score_complete": [True, True, False, False, False],
        }
    )

    coverage = compute_lineup_coverage(results, [1, 2, 3])

    assert coverage == {
        "requested_gameweeks": 3,
        "gameweeks_with_results": 2,
        "gameweeks_with_complete_rank1": 1,
        "gameweeks_with_three_complete_lineups": 0,
        "generated_lineups": 5,
        "complete_lineups": 2,
        "incomplete_lineups": 3,
    }


def test_lineup_coverage_marks_all_requested_weeks_missing_for_empty_results():
    assert compute_lineup_coverage(pd.DataFrame(), [4, 5]) == {
        "requested_gameweeks": 2,
        "gameweeks_with_results": 0,
        "gameweeks_with_complete_rank1": 0,
        "gameweeks_with_three_complete_lineups": 0,
        "generated_lineups": 0,
        "complete_lineups": 0,
        "incomplete_lineups": 0,
    }
