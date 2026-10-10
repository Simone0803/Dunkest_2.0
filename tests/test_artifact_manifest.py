import hashlib
import json
import json

import pandas as pd

from dunkest.config import Settings
from dunkest.report.artifacts import save_run_artifacts


def test_run_manifest_captures_reproducibility_metadata(tmp_path):
    settings = Settings(
        data_dir=str(tmp_path),
        target_gameweek=2,
        random_state=19,
        rolling_windows=[3, 7],
    )
    processed = tmp_path / "processed"
    processed.mkdir()
    player_cache = processed / f"player_game_logs_{settings.season}.parquet"
    player_cache.write_bytes(b"captured-input")
    player_cache.with_suffix(player_cache.suffix + ".meta.json").write_text(
        json.dumps({"fetched_at": "2026-10-01T12:00:00+00:00", "source": "test", "rows": 12}),
        encoding="utf-8",
    )
    market_file = tmp_path / "current_lineups_market.csv"
    market_file.write_text("player_name,cr\nPlayer One,8.0\n", encoding="utf-8")
    models = {
        "ridge": object(),
        "rf": object(),
        "_feature_cols": ["pdk_mean_5", "rest_days"],
        "_weights": {"ridge": 0.75, "rf": 0.25},
        "_projection_weights": {"minutes": 0.6, "ensemble": 0.4, "prior": 0.0},
        "_calibration_samples": 120,
        "_interval_diagnostics": [
            {"dimension": "history_games", "cohort": "0-4", "n": 40}
        ],
        "_interval_diagnostic_scope": "cross-fitted cohort diagnostic",
    }

    output = save_run_artifacts(settings, pd.DataFrame(), [], models)
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["configuration"]["random_state"] == 19
    assert manifest["random_seed"] == 19
    assert len(manifest["config_sha256"]) == 64
    assert manifest["source_fingerprint"]["python_files"] > 0
    assert len(manifest["source_fingerprint"]["sha256"]) == 64
    assert manifest["optimizer_parameters"]["budget"] == settings.budget
    assert manifest["dataset_identifier"] == hashlib.sha256(
        json.dumps(manifest["inputs"], sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()
    if manifest["git_hash"] is None:
        assert manifest["git_hash_unavailable_reason"]
    assert manifest["configuration"]["rolling_windows"] == [3, 7]
    assert manifest["model_details"]["effective_models"] == ["rf", "ridge"]
    assert manifest["model_details"]["feature_columns"] == ["pdk_mean_5", "rest_days"]
    assert manifest["model_details"]["model_weights"] == {"ridge": 0.75, "rf": 0.25}
    assert manifest["model_details"]["calibration_samples"] == 120
    assert manifest["model_details"]["interval_diagnostics"] == [
        {"dimension": "history_games", "cohort": "0-4", "n": 40}
    ]
    assert manifest["model_details"]["interval_diagnostic_scope"] == (
        "cross-fitted cohort diagnostic"
    )
    assert manifest["runtime"]["packages"]["pandas"]

    input_hashes = {entry["path"]: entry["sha256"] for entry in manifest["inputs"]}
    player_input = next(
        entry for entry in manifest["inputs"]
        if entry["path"] == f"processed/player_game_logs_{settings.season}.parquet"
    )
    assert player_input["cache_metadata"]["source"] == "test"
    assert player_input["cache_metadata"]["fetched_at"] == "2026-10-01T12:00:00+00:00"
    assert input_hashes["processed/player_game_logs_2026-27.parquet"] == hashlib.sha256(
        b"captured-input"
    ).hexdigest()
    assert input_hashes["current_lineups_market.csv"] == hashlib.sha256(
        b"player_name,cr\nPlayer One,8.0\n"
    ).hexdigest()
