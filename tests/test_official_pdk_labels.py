from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from dunkest.config import Settings
from dunkest.data.dunkest.official_pdk import (
    attach_official_pdk_labels,
    official_pdk_overlay_path,
)
from dunkest.models.predictor import (
    MIN_OFFICIAL_PDK_TRAINING_ROWS,
    _resolve_training_target,
)


def _logs_with_proxy_scores() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "PLAYER_ID": [1001, 1001],
            "Game_ID": ["002", "003"],
            "GAME_DATE": pd.to_datetime(["2025-10-20", "2025-10-22"]),
            "TEAM_ABBREVIATION": ["nyk", "NYK"],
            "PDK": [12.5, 21.0],
        }
    )


def test_official_pdk_overlay_joins_by_identity_and_preserves_proxy(tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir()
    overlay = pd.DataFrame(
        {
            "PLAYER_ID": ["1001", "1001"],
            "GAME_ID": ["002", "003"],
            "GAME_DATE": pd.to_datetime(["2025-10-20", "2025-10-22"]),
            "TEAM_ABBREVIATION": ["NYK", "NYK"],
            "PDK_OFFICIAL_VALID": [14.0, np.nan],
        }
    )
    overlay.to_parquet(
        processed / "player_game_logs_2025-26_official_pdk_overlay_v4.parquet",
        index=False,
    )

    base = _logs_with_proxy_scores()
    actual = attach_official_pdk_labels(base, tmp_path, "2025-26")

    assert actual["PDK"].tolist() == [12.5, 21.0]
    assert actual["PDK_OFFICIAL_VALID"].iloc[0] == 14.0
    assert pd.isna(actual["PDK_OFFICIAL_VALID"].iloc[1])
    assert len(actual) == len(base)


def test_official_pdk_overlay_path_prefers_v4_and_falls_back_to_legacy(tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir()
    v4 = processed / "player_game_logs_2025-26_official_pdk_overlay_v4.parquet"
    legacy = processed / "player_game_logs_2025-26_official_pdk_overlay.parquet"
    legacy.write_bytes(b"legacy")
    assert official_pdk_overlay_path(tmp_path, "2025-26") == legacy
    v4.write_bytes(b"v4")
    assert official_pdk_overlay_path(tmp_path, "2025-26") == v4


def test_official_pdk_overlay_without_matches_is_not_applied(tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir()
    pd.DataFrame(
        {
            "PLAYER_ID": [9999],
            "GAME_ID": ["unrelated"],
            "GAME_DATE": pd.to_datetime(["2025-10-20"]),
            "TEAM_ABBREVIATION": ["BOS"],
            "PDK_OFFICIAL_VALID": [40.0],
        }
    ).to_parquet(
        processed / "player_game_logs_2025-26_official_pdk_overlay_v4.parquet",
        index=False,
    )

    base = _logs_with_proxy_scores()
    with pytest.warns(RuntimeWarning, match="matched no player-game rows"):
        actual = attach_official_pdk_labels(base, tmp_path, "2025-26")

    assert actual["PDK"].tolist() == [12.5, 21.0]
    assert "PDK_OFFICIAL_VALID" not in actual.columns


def test_auto_training_target_uses_official_labels_only_above_threshold():
    rows = MIN_OFFICIAL_PDK_TRAINING_ROWS
    features = pd.DataFrame(
        {
            "target_pdk": np.full(rows, 20.0),
            "target_pdk_official": np.full(rows, 18.0),
        }
    )

    assert _resolve_training_target(Settings(), features) == "target_pdk_official"


def test_auto_training_target_fails_closed_when_official_coverage_is_small():
    features = pd.DataFrame(
        {
            "target_pdk": [10.0] * 100,
            "target_pdk_official": [11.0] * 99 + [np.nan],
        }
    )

    with pytest.raises(ValueError, match="Refusing to silently train on proxy PDK labels"):
        _resolve_training_target(Settings(), features)


def test_auto_training_target_fails_when_official_column_is_absent():
    features = pd.DataFrame({"target_pdk": [10.0] * 100})

    with pytest.raises(ValueError, match="target_pdk_official column, but it is missing") as exc:
        _resolve_training_target(Settings(), features)

    assert "training_target='target_pdk'" in str(exc.value)


def test_explicit_training_target_overrides_auto_selection():
    features = pd.DataFrame(
        {
            "target_pdk": [10.0] * MIN_OFFICIAL_PDK_TRAINING_ROWS,
            "target_pdk_official": [11.0] * MIN_OFFICIAL_PDK_TRAINING_ROWS,
        }
    )

    assert (
        _resolve_training_target(Settings(training_target="target_pdk"), features)
        == "target_pdk"
    )
    assert (
        _resolve_training_target(
            Settings(training_target="target_pdk_official"), features
        )
        == "target_pdk_official"
    )
