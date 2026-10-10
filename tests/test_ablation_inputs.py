import pandas as pd

import dunkest.pipeline.ablation as ablation
from dunkest.config import Settings


def test_ablation_uses_requested_schedule_and_distinct_feature_variants(monkeypatch):
    observed = []

    def fake_build(settings, player_logs, team_logs, injuries, **kwargs):
        observed.append(
            (
                settings.use_schedule,
                settings.use_matchup,
                settings.target_gameweek,
                kwargs["schedule"],
                kwargs["target_gameweek"],
                kwargs["include_completed_schedule"],
            )
        )
        return pd.DataFrame({"target_pdk": [10.0]}, index=[0])

    def fake_train(settings, features):
        return {}, pd.Series([9.0], index=features.index)

    monkeypatch.setattr(ablation, "build_feature_matrix", fake_build)
    monkeypatch.setattr(ablation, "train_models", fake_train)
    schedule = pd.DataFrame({"WEEK_NUMBER": [8]})

    result = ablation.run_ablation_summary(
        Settings(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
        schedule=schedule, target_gameweek=8,
    )

    assert result["variant"].tolist() == [
        "baseline", "plus_schedule", "plus_matchup", "full"
    ]
    assert [entry[:2] for entry in observed] == [
        (False, False), (True, False), (False, True), (True, True)
    ]
    assert all(entry[2] == 8 and entry[3] is schedule for entry in observed)
    assert all(entry[4:] == (8, True) for entry in observed)
    assert result["player_pdk_mae"].eq(1.0).all()
