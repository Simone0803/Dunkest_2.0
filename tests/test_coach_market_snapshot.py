import pandas as pd

from dunkest.config import Settings
from dunkest.data.access import save_coach_market_snapshot


def test_coach_market_snapshot_archives_gameweek_quotes(tmp_path):
    settings = Settings(data_dir=str(tmp_path), season_id="test-season")
    coaches = pd.DataFrame(
        [
            {
                "coach": "Coach One",
                "team": "BOS",
                "coach_cr": "8.5",
                "opponent": "NYK",
                "opponent_coach": "Coach Two",
                "opponent_coach_cr": "7.0",
                "date": "2026-10-20",
                "expected_coach_pdk": 15.0,
            },
            {
                "coach": "Coach Two",
                "team": "NYK",
                "coach_cr": 7.0,
                "opponent": "BOS",
                "opponent_coach": "Coach One",
                "opponent_coach_cr": 8.5,
                "date": "2026-10-20",
                "expected_coach_pdk": 12.0,
            },
        ]
    )

    save_coach_market_snapshot(settings, coaches, gameweek=4)

    path = tmp_path / "processed" / "coach_market_test-season_gw4.parquet"
    archived = pd.read_parquet(path)
    assert set(archived["team"]) == {"BOS", "NYK"}
    assert archived["gameweek"].eq(4).all()
    assert archived["coach_cr"].dtype.kind in "fi"
    assert "expected_coach_pdk" not in archived.columns


def test_coach_market_snapshot_ignores_incomplete_market(tmp_path):
    settings = Settings(data_dir=str(tmp_path), season_id="test-season")

    save_coach_market_snapshot(
        settings,
        pd.DataFrame([{"coach": "Coach One", "team": "BOS"}]),
        gameweek=4,
    )

    assert not (tmp_path / "processed" / "coach_market_test-season_gw4.parquet").exists()
