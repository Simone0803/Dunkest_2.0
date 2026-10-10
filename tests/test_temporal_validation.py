import pandas as pd

from dunkest.models.predictor import _expanding_week_splits
from dunkest.models.capital_gain import _temporal_splits


def test_plusvalenza_validation_uses_only_strictly_earlier_weeks():
    sample = pd.DataFrame(
        {"gameweek": [week for week in (1, 2, 3, 4) for _ in range(25)]}
    )

    splits = _expanding_week_splits(sample, min_train_rows=40)

    assert [week for week, _, _ in splits] == [3.0, 4.0]
    for held_out_week, train, test in splits:
        assert train.any()
        assert test.any()
        assert sample.loc[train, "gameweek"].max() < held_out_week
        assert sample.loc[test, "gameweek"].eq(held_out_week).all()


def test_temporal_validation_skips_weeks_without_enough_past_rows():
    sample = pd.DataFrame({"gameweek": [1] * 39 + [2] * 40 + [3] * 40})

    splits = _expanding_week_splits(sample, min_train_rows=40)

    assert [week for week, _, _ in splits] == [3.0]
    assert int(splits[0][1].sum()) == 79


def test_capital_gain_validation_orders_seasons_then_gameweeks():
    sample = pd.DataFrame([
        {"season_order": season, "gameweek": week}
        for season in (13, 16, 19)
        for week in range(1, 5)
        for _ in range(12)
    ])
    for train, test in _temporal_splits(sample, min_train_rows=12):
        test_key = tuple(sample.loc[test, ["season_order", "gameweek"]].iloc[0])
        train_keys = sample.loc[train, ["season_order", "gameweek"]].drop_duplicates()
        assert all(tuple(key) < test_key for key in train_keys.to_numpy())
