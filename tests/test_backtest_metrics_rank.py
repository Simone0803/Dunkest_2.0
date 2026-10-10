import math

import pandas as pd

from dunkest.backtest.metrics import compute_backtest_metrics


def test_average_scores_and_accuracy_use_rank_one_only():
    results = pd.DataFrame(
        [
            {
                "gameweek": 1, "rank": 1,
                "realized_team_score": 100.0, "ex_post_optimum": 120.0,
                "realized_player_score": 80.0, "ex_post_player_optimum": 90.0,
                "captain_hit": 1.0, "coach_hit": 0.0, "num_transfers": 2,
            },
            {
                "gameweek": 1, "rank": 2,
                "realized_team_score": 200.0, "ex_post_optimum": 220.0,
                "realized_player_score": 180.0, "ex_post_player_optimum": 190.0,
                "captain_hit": 0.0, "coach_hit": 1.0, "num_transfers": 4,
            },
            {
                "gameweek": 1, "rank": 3,
                "realized_team_score": 150.0, "ex_post_optimum": 170.0,
                "realized_player_score": 130.0, "ex_post_player_optimum": 140.0,
                "captain_hit": 0.0, "coach_hit": 0.0, "num_transfers": 6,
            },
            {
                "gameweek": 2, "rank": 1,
                "realized_team_score": 90.0, "ex_post_optimum": 110.0,
                "realized_player_score": 70.0, "ex_post_player_optimum": 80.0,
                "captain_hit": 0.0, "coach_hit": 1.0, "num_transfers": 1,
            },
            {
                "gameweek": 2, "rank": 2,
                "realized_team_score": 95.0, "ex_post_optimum": 115.0,
                "realized_player_score": 75.0, "ex_post_player_optimum": 85.0,
                "captain_hit": 1.0, "coach_hit": 0.0, "num_transfers": 3,
            },
        ]
    )

    report = compute_backtest_metrics(results)

    assert report.average_team_score == 95.0
    assert report.median_team_score == 95.0
    assert report.best_of_3_realized == 150.0
    assert report.regret_vs_ex_post == 20.0
    assert report.average_player_score == 75.0
    assert report.median_player_score == 75.0
    assert report.best_of_3_player_score == 105.0
    assert report.regret_vs_ex_post_player_score == 10.0
    assert report.captain_accuracy == 0.5
    assert report.coach_accuracy == 0.5
    assert report.average_transfers == 1.5


def test_missing_team_scores_remain_unavailable_not_zero():
    results = pd.DataFrame(
        [
            {
                "gameweek": 1, "rank": 1,
                "realized_team_score": float("nan"), "ex_post_optimum": float("nan"),
                "realized_player_score": 55.0, "ex_post_player_optimum": 60.0,
                "captain_hit": float("nan"), "coach_hit": float("nan"),
                "num_transfers": 0,
            }
        ]
    )

    report = compute_backtest_metrics(results)

    assert math.isnan(report.average_team_score)
    assert math.isnan(report.regret_vs_ex_post)
    assert report.average_player_score == 55.0
