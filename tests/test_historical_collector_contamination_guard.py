import importlib.util
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "collect_dunkest_historical_player_games",
    ROOT / "scripts" / "collect_dunkest_historical_player_games.py",
)
collector = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(collector)


def test_confirmed_contamination_exclusion_is_scoped_to_exact_season_week_round_and_ids(tmp_path):
    evidence = tmp_path / "confirmed.csv"
    pd.DataFrame({"dunkest_player_id": ["715"]}).to_csv(evidence, index=False)
    frame = pd.DataFrame({
        "id": ["715", "715", "715", "999"],
        "player_name": ["Anthony Edwards", "Anthony Edwards", "Anthony Edwards", "Other Player"],
        "source_season_id": ["5", "5", "7", "5"],
        "source_week": [43, 42, 43, 43],
        "source_round": [2, 2, 2, 2],
    })

    filtered, removed = collector.exclude_confirmed_contaminated_seed_rows(frame, evidence)

    assert removed == 1
    assert len(filtered) == 3
    assert not (
        filtered["id"].eq("715")
        & filtered["source_season_id"].eq("5")
        & filtered["source_week"].eq(43)
        & filtered["source_round"].eq(2)
    ).any()
    assert filtered["id"].eq("715").sum() == 2


def test_missing_contamination_evidence_leaves_seed_rows_unchanged(tmp_path):
    frame = pd.DataFrame({
        "id": ["715"],
        "source_season_id": ["5"],
        "source_week": [43],
        "source_round": [2],
    })

    filtered, removed = collector.exclude_confirmed_contaminated_seed_rows(
        frame, tmp_path / "missing.csv"
    )

    assert removed == 0
    pd.testing.assert_frame_equal(filtered, frame)


def test_row_level_register_excludes_only_exact_keys_across_seasons(tmp_path):
    evidence = tmp_path / "row_level.csv"
    pd.DataFrame({
        "dunkest_player_id": ["715", "1008"],
        "source_season_id": ["5", "13"],
        "source_week": [43, 20],
        "source_round": [2, 1],
    }).to_csv(evidence, index=False)
    frame = pd.DataFrame({
        "id": ["715", "715", "715", "1008", "1008"],
        "player_name": ["Anthony Edwards", "Anthony Edwards", "Anthony Edwards",
                        "Jaden Springer", "Jaden Springer"],
        "source_season_id": ["5", "5", "7", "13", "13"],
        "source_week": [43, 42, 43, 20, 19],
        "source_round": [2, 2, 2, 1, 1],
    })

    filtered, removed = collector.exclude_confirmed_contaminated_seed_rows(frame, evidence)

    assert removed == 2
    assert len(filtered) == 3
    assert not (
        filtered["id"].eq("715")
        & filtered["source_season_id"].eq("5")
        & filtered["source_week"].eq(43)
        & filtered["source_round"].eq(2)
    ).any()
    assert not (
        filtered["id"].eq("1008")
        & filtered["source_season_id"].eq("13")
        & filtered["source_week"].eq(20)
        & filtered["source_round"].eq(1)
    ).any()
    assert filtered["id"].eq("715").sum() == 2
    assert filtered["id"].eq("1008").sum() == 1
