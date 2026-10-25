"""Regression checks for production HGB preprocessing and replay parity limits."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import experiment_dunkest_minutes_rate_decomposition_v1 as historical_replay
from dunkest.models.predictor import FEATURE_COLS, _fit_matrix


def _production_train_matrix(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, list[str]]:
    columns = [column for column in FEATURE_COLS if column in frame]
    columns = [
        column
        for column in columns
        if np.isfinite(pd.to_numeric(frame[column], errors="coerce").to_numpy(float)).any()
    ]
    matrix, medians = _fit_matrix(frame, columns)
    return matrix, medians, columns


def _production_inference_matrix(
    frame: pd.DataFrame, columns: list[str], medians: pd.Series
) -> pd.DataFrame:
    for column in columns:
        if column not in frame:
            frame[column] = np.nan
    matrix = frame[columns].apply(pd.to_numeric, errors="coerce")
    matrix = matrix.replace([np.inf, -np.inf], np.nan)
    return matrix.fillna(medians).fillna(0.0)


def test_production_hgb_train_and_inference_preprocessing_are_equivalent():
    train = pd.DataFrame({
        "pdk_mean_5": [10.0, np.nan, 30.0],
        "min_mean_5": [12.0, 20.0, np.inf],
        "pdk_std_5": [np.nan, np.nan, np.nan],  # production drops all-missing columns
    })

    training_matrix, medians, columns = _production_train_matrix(train)
    inference_matrix = _production_inference_matrix(train.copy(), columns, medians)

    assert columns == ["pdk_mean_5", "min_mean_5"]
    assert_frame_equal(training_matrix, inference_matrix)
    assert np.isfinite(inference_matrix.to_numpy()).all()


def test_historical_replay_preprocessor_is_not_equivalent_to_production_matrix():
    row = {column: 1.0 for column in historical_replay.BASE_NUM}
    row.update({column: "TEAM" for column in historical_replay.CAT})
    row["pdk_mean_5"] = np.nan
    row["opponentTeamCode"] = "BOS"
    row["opponentTeamPosition"] = "HOME"
    sample = pd.DataFrame([row, {**row, "pdk_mean_5": 4.0, "opponentTeamCode": "NYK"}])

    production_matrix, medians, production_columns = _production_train_matrix(sample)
    production_inference = _production_inference_matrix(sample.copy(), production_columns, medians)
    historical_pipeline = historical_replay.model("hgb")
    historical_sample = historical_replay.make_features(sample)
    historical_matrix = historical_pipeline.named_steps["prep"].fit_transform(historical_sample)

    assert production_inference.shape[1] == len(production_columns)
    assert historical_matrix.shape[1] > production_inference.shape[1]
    assert not np.array_equal(historical_matrix, production_inference.to_numpy())
