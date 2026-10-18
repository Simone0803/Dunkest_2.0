from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import httpx

from dunkest.config import Settings
from dunkest.data import cache
from dunkest.data.http_client import _is_retryable_http_error
from dunkest.models.predictor import _fit_matrix, train_models


def test_http_retry_policy_retries_only_transient_status_codes():
    def status_error(status_code):
        response = httpx.Response(status_code, request=httpx.Request("GET", "https://example.test"))
        return httpx.HTTPStatusError("status", request=response.request, response=response)

    assert _is_retryable_http_error(httpx.TimeoutException("timeout"))
    assert _is_retryable_http_error(httpx.ConnectError("connection", request=httpx.Request("GET", "https://example.test")))
    assert _is_retryable_http_error(status_error(429))
    assert _is_retryable_http_error(status_error(503))
    assert not _is_retryable_http_error(status_error(404))
    assert not _is_retryable_http_error(status_error(401))
    assert not _is_retryable_http_error(ValueError("bad payload"))


def test_write_parquet_publishes_data_and_metadata(tmp_path, monkeypatch):
    def fake_to_parquet(frame, path, index=False):
        Path(path).write_bytes(b"parquet-placeholder")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", fake_to_parquet)
    target = tmp_path / "nested" / "sample.parquet"

    cache.write_parquet(pd.DataFrame({"x": [1, 2]}), target, "unit-test")

    assert target.read_bytes() == b"parquet-placeholder"
    metadata = cache.read_cache_metadata(target)
    assert metadata is not None
    assert metadata["rows"] == 2
    assert metadata["source"] == "unit-test"
    assert not list(target.parent.glob(".*.tmp"))


def test_corrupt_parquet_is_a_cache_miss(tmp_path, monkeypatch):
    target = tmp_path / "broken.parquet"
    target.write_bytes(b"not parquet")

    def fail_read(_path):
        raise ValueError("corrupt parquet")

    monkeypatch.setattr(pd, "read_parquet", fail_read)
    assert cache.read_parquet(target) is None


def test_cache_valid_rejects_future_timestamps(tmp_path):
    target = tmp_path / "future.parquet"
    target.write_bytes(b"placeholder")
    cache._meta_path(target).write_text(
        '{"fetched_at": "2999-01-01T00:00:00+00:00"}',
        encoding="utf-8",
    )

    assert not cache.cache_valid(target, max_age_hours=6)


def test_settings_reject_unknown_optimizer_objective():
    with pytest.raises(ValueError, match="optimizer_objective"):
        Settings(optimizer_objective="risk-adjustd")


def test_training_rejects_missing_usable_features():
    features = pd.DataFrame({"target_pdk": [10.0, 15.0, np.inf, np.nan]})

    with pytest.raises(ValueError, match="No usable model features"):
        train_models(Settings(training_target="target_pdk"), features)



def test_fit_matrix_replaces_infinite_values_with_training_median():
    frame = pd.DataFrame(
        {
            "feature": [1.0, np.inf, 3.0, -np.inf],
            "target_pdk": [10.0, 12.0, 14.0, 16.0],
        }
    )

    matrix, medians = _fit_matrix(frame, ["feature"])

    assert np.isfinite(matrix.to_numpy()).all()
    assert medians["feature"] == 2.0
    assert matrix["feature"].tolist() == [1.0, 2.0, 3.0, 2.0]
