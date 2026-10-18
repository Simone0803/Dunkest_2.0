#!/usr/bin/env python3
"""Audit certified multi-season training features against production inference."""
from __future__ import annotations

import json
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from dunkest.config import Settings
from dunkest.data.dunkest.official_pdk import attach_official_pdk_labels
from dunkest.features.builder import build_feature_matrix
from dunkest.models.multiseason_training import DEFAULT_DATASET, adapt_certified_training_rows
from dunkest.models.predictor import FEATURE_COLS


ROOT = Path(__file__).resolve().parents[1]
STEM = "dunkest_training_inference_schema_20261018_v1"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-stem", default=STEM,
        help="Versioned output stem under reports/audit (refuses to overwrite existing files).",
    )
    args = parser.parse_args()
    output_stem = str(args.output_stem).strip()
    if not output_stem or Path(output_stem).name != output_stem:
        parser.error("--output-stem must be a non-empty filename stem without directory separators")
    output = ROOT / "reports/audit"
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / f"{output_stem}.json"
    md_path = output / f"{output_stem}.md"
    if json_path.exists() or md_path.exists():
        raise SystemExit(f"Refusing to overwrite versioned output: {output_stem}")

    settings = Settings.from_yaml(ROOT / "config/season_opener.yaml")
    dataset = settings.data_path / DEFAULT_DATASET
    minute_labels_path = settings.data_path / "processed/dunkest_nba_player_games_enriched_2018-25_v1.parquet"
    logs_path = settings.data_path / "processed/player_game_logs_2025-26.parquet"
    for path in (dataset, minute_labels_path, logs_path):
        if not path.exists():
            raise FileNotFoundError(f"Required schema-audit input is missing: {path}")

    source = pd.read_parquet(dataset)
    minute_labels = pd.read_parquet(
        minute_labels_path,
        columns=["nba_GAME_ID", "nba_PLAYER_ID", "nba_MIN", "nba_match_status"],
    )
    training = adapt_certified_training_rows(source, minutes_labels=minute_labels)
    selected = [
        column
        for column in FEATURE_COLS
        if column in training
        and np.isfinite(
            pd.to_numeric(training[column], errors="coerce").to_numpy(dtype=float, na_value=np.nan)
        ).any()
    ]

    player_logs = pd.read_parquet(logs_path)
    player_logs = attach_official_pdk_labels(player_logs, settings.data_path, "2025-26")
    features = build_feature_matrix(settings, player_logs)
    inference = features.loc[
        features.get("is_inference", pd.Series(False, index=features.index))
        .fillna(False)
        .astype(bool)
    ]
    missing = [column for column in selected if column not in inference]
    coverage = {
        column: int(pd.to_numeric(inference[column], errors="coerce").notna().sum())
        for column in selected
        if column in inference
    }
    all_null = [column for column in selected if coverage.get(column, 0) == 0]
    result = {
        "audit_version": 1,
        "training_dataset": str(dataset.relative_to(ROOT)),
        "inference_log": str(logs_path.relative_to(ROOT)),
        "official_pdk_label_certification": "verified_official_dunkest_pdk_valid_rows",
        "training_seasons": sorted(training["season_label"].astype(str).unique().tolist()),
        "training_rows": int(len(training)),
        "selected_feature_count": len(selected),
        "selected_features": selected,
        "inference_rows": int(len(inference)),
        "missing_inference_columns": missing,
        "all_null_inference_columns": all_null,
        "official_pdk_overlay_rows": int(
            pd.to_numeric(
                player_logs.get("PDK_OFFICIAL_VALID", pd.Series(dtype=float)), errors="coerce"
            ).notna().sum()
        ),
        "feature_non_null_inference_rows": coverage,
        "result": "pass" if selected and not missing and not all_null else "fail",
    }
    json_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Training and inference feature schema audit — 2026-10-18 V1",
        "",
        f"Result: **{result['result'].upper()}**",
        "",
        "The selected features are the `FEATURE_COLS` that contain at least one finite value in certified 2020/21–2024/25 training rows. Inference coverage is counted only on production builder rows marked `is_inference`, using the archived 2025/26 player logs and official PDK overlay. This is a schema and data-availability check; it does not refit or select a model.",
        "",
        f"- Training rows: {result['training_rows']:,}",
        f"- Selected training features: {result['selected_feature_count']}",
        f"- Production inference rows: {result['inference_rows']:,}",
        f"- Official PDK labels attached: {result['official_pdk_overlay_rows']:,}",
        f"- Selected columns absent from inference: {result['missing_inference_columns']}",
        f"- Selected columns entirely null at inference: {result['all_null_inference_columns']}",
        "",
        "## Feature coverage",
        "",
        "| Feature | Non-null next-game rows |",
        "|---|---:|",
        *[f"| `{column}` | {coverage[column]:,} |" for column in selected],
        "",
        "## Reproduction",
        "",
        "```bash",
        f"PYTHONPATH=src .venv/bin/python scripts/{Path(__file__).name} --output-stem {output_stem}",
        "```",
        "",
        "The source data is historical 2025/26 input, not the frozen 2026/27 GW1 test. No outcome metrics or model choices are computed here.",
        "",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({key: result[key] for key in (
        "result", "training_rows", "selected_feature_count", "inference_rows",
        "missing_inference_columns", "all_null_inference_columns",
    )}, indent=2))
    print(f"Wrote {md_path.relative_to(ROOT)} and {json_path.relative_to(ROOT)}")
    if result["result"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
