from pathlib import Path
import json
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
from dunkest.config import Settings
from dunkest.data.dunkest.official_pdk import attach_official_pdk_labels
from dunkest.features.builder import build_feature_matrix
from dunkest.models.predictor import train_models

root = Path("/Users/simone/Documents/Dunkest")
data = root / "data"
settings = Settings.from_yaml(
    root / "config/season_opener.yaml",
    data_dir=str(data),
    use_schedule=False,
    use_matchup=False,
    use_injuries=False,
    training_target="target_pdk_official",
)
player_logs = pd.read_parquet(data / "processed/player_game_logs_2025-26.parquet")
labeled = attach_official_pdk_labels(player_logs, data, "2025-26")
official_features = build_feature_matrix(settings, labeled)
proxy_features = build_feature_matrix(
    settings, labeled.drop(columns=["PDK_OFFICIAL_VALID"], errors="ignore")
)
if len(official_features) != len(proxy_features):
    raise RuntimeError("Feature row count changed between official/proxy ablations.")
proxy_features["target_pdk_official"] = official_features["target_pdk_official"].to_numpy()
results = []
for label, frame in (("official_history_features", official_features), ("proxy_history_features", proxy_features)):
    models, oof = train_models(settings, frame, target_column="target_pdk_official")
    target = pd.to_numeric(frame["target_pdk_official"], errors="coerce")
    valid = target.notna() & oof.notna()
    y = target.loc[valid].to_numpy(dtype=float)
    pred = oof.loc[valid].to_numpy(dtype=float)
    results.append({
        "candidate": label,
        "oof_rows": int(valid.sum()),
        "mae": float(mean_absolute_error(y, pred)),
        "rmse": float(mean_squared_error(y, pred) ** 0.5),
        "bias_pred_minus_actual": float(np.mean(pred-y)),
        "mae_actual_ge25": float(np.mean(np.abs(y[y >= 25]-pred[y >= 25]))) if np.any(y >= 25) else None,
        "n_actual_ge25": int(np.sum(y >= 25)),
        "mae_actual_ge30": float(np.mean(np.abs(y[y >= 30]-pred[y >= 30]))) if np.any(y >= 30) else None,
        "n_actual_ge30": int(np.sum(y >= 30)),
        "training_target_source": models.get("_training_target_source"),
        "features": models.get("_feature_cols", []),
    })
out = root / "reports/audit/dunkest_official_vs_proxy_pdk_history_features_20261014_v1.json"
if out.exists():
    raise SystemExit(f"Refusing to overwrite versioned audit artifact: {out}")
payload = {
    "scope": "Exploratory paired ablation on the already-examined 2025-26 season; not a pristine holdout.",
    "target": "verified official Dunkest PDK",
    "feature_difference": "Official variant uses PDK_OFFICIAL_VALID where verified and falls back to proxy PDK only where official history is unavailable; proxy variant uses only PDK proxy. All other settings and rows are held fixed.",
    "settings": {"use_schedule": False, "use_matchup": False, "use_injuries": False},
    "results": results,
    "production_changed": False,
}
out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
print(json.dumps(payload, indent=2, ensure_ascii=False))
