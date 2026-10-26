#!/usr/bin/env python3
"""Evaluate immutable pre-lock coach forecasts against registered outcomes."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import evaluate_prospective_forecasts_v1 as player_eval  # noqa: E402
from archive_dunkest_pre_lock_run_v1 import digest, load_json  # noqa: E402
from dunkest.evaluation.coach_prospective import (  # noqa: E402
    evaluate_coach_rows,
    reconcile_coach_forecasts,
)


def _sha(value: object) -> bool:
    token = str(value or "").strip().lower()
    return len(token) == 64 and all(character in "0123456789abcdef" for character in token)


def _fixture_frame(archive_dir: Path, season_id: str, gameweek: int) -> pd.DataFrame:
    paths = list((archive_dir / "pre_match_snapshot").glob("dunkest_fixture_mapping_*.parquet"))
    if len(paths) != 1:
        raise ValueError(f"Expected one immutable fixture mapping, found {len(paths)}")
    fixtures = pd.read_parquet(paths[0])
    required = {"nba_game_id", "home_team", "away_team", "game_datetime_utc", "mapping_verified"}
    if missing := sorted(required - set(fixtures.columns)):
        raise ValueError(f"Frozen fixture mapping lacks fields: {missing}")
    if "season_id" in fixtures and not fixtures["season_id"].astype(str).eq(str(season_id)).all():
        raise ValueError("Fixture mapping contains another season")
    if "dunkest_gameweek" in fixtures:
        fixtures = fixtures.loc[pd.to_numeric(fixtures["dunkest_gameweek"], errors="coerce").eq(int(gameweek))].copy()
    return fixtures


def _coach_outcomes(results_dir: Path, season_id: str, gameweek: int, run_id: str,
                    forecast_at: pd.Timestamp, fixtures: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    outcome_manifest, _, provenance = player_eval._validate_results_archive(
        results_dir, season_id, gameweek, run_id, forecast_at, fixtures
    )
    source_fingerprints = outcome_manifest.get("source_file_fingerprints", {})
    for required_source in ("team_logs", "nba_player_logs_for_overtime"):
        descriptor = source_fingerprints.get(required_source, {})
        if not descriptor.get("path") or not _sha(descriptor.get("sha256")):
            raise player_eval.UnverifiedOutcomeArchive(
                f"Coach outcome archive lacks a fingerprinted {required_source} source."
            )
    coach_path = results_dir / "coach_results.parquet"
    outcomes = pd.read_parquet(coach_path)
    required = {
        "coach", "nba_game_id", "team", "opponent", "actual_coach_pdk",
        "team_final_points", "opponent_final_points",
    }
    if missing := sorted(required - set(outcomes.columns)):
        raise ValueError(f"Official coach outcome table lacks fields: {missing}")
    provenance.update({
        "coach_results_sha256": digest(coach_path),
        "team_logs_source": source_fingerprints["team_logs"],
        "overtime_source": source_fingerprints["nba_player_logs_for_overtime"],
        "status": "verified",
    })
    return outcomes, {**outcome_manifest, "_provenance": provenance}


def evaluate_archive(
    archive_dir: Path,
    *,
    data_dir: Path | None = None,
    results_dir: Path | None = None,
) -> tuple[dict, pd.DataFrame]:
    archive_dir = archive_dir.expanduser().resolve()
    manifest_path = archive_dir / "manifest.json"
    if not manifest_path.is_file():
        return ({
            "evaluator_schema_version": 1, "evaluation_status": "not_evaluable",
            "official_oos_metrics": False, "reason": "run_manifest_missing",
            "metrics": None, "counts": {"forecasted": 0, "reconciled": 0, "excluded": 0},
        }, pd.DataFrame())
    run_manifest = load_json(manifest_path)
    descriptor = run_manifest.get("coach_forecast_snapshot", {})
    try:
        meta, _, _ = player_eval.validate_prelock_archive(archive_dir)
        run_manifest = load_json(manifest_path)
        config = run_manifest.get("configuration", {})
        season_id = str(config.get("season_id", run_manifest.get("season_id", "")))
        gameweek = int(config.get("target_gameweek", run_manifest.get("target_gameweek", -1)))
        run_id = str(run_manifest.get("run_id", archive_dir.name))
        coach_path = archive_dir / Path(str(descriptor.get("path", "coach_forecast_snapshot.parquet"))).name
        coaches = pd.read_parquet(coach_path)
        fixtures = _fixture_frame(archive_dir, season_id, gameweek)
        if results_dir is None and data_dir is not None:
            results_dir = player_eval.resolve_results_dir(data_dir, season_id, gameweek, run_id)
        outcomes = None
        outcome_manifest = None
        outcome_provenance = None
        outcome_verified = True
        if results_dir is not None:
            latest_forecast = pd.to_datetime(coaches["forecast_timestamp_utc"], errors="coerce", utc=True).max()
            try:
                outcomes, outcome_manifest = _coach_outcomes(
                    results_dir.expanduser().resolve(), season_id, gameweek, run_id,
                    latest_forecast, fixtures,
                )
                outcome_provenance = outcome_manifest.pop("_provenance")
            except (OSError, ValueError, RuntimeError) as exc:
                outcome_verified = False
                outcome_provenance = {"status": "unverified", "reason": str(exc)}
                outcome_manifest = None
                outcomes = None
        rows = reconcile_coach_forecasts(
            coaches, outcomes, fixtures,
            bundle_id=str(meta.get("run_id", archive_dir.name)),
            bundle_eligible=True,
            forecast_manifest=run_manifest,
            outcome_manifest=outcome_manifest,
            outcome_verified=outcome_verified,
        )
        metrics = evaluate_coach_rows(rows)
        n_expected = int(len(coaches))
        n_reconciled = int(metrics["reconciled_observations"])
        full = n_expected > 0 and n_reconciled == n_expected and outcome_verified
        row_status = rows["reconciliation_status"]
        without_verified_outcome = row_status.isin({"outcome_missing", "outcome_unverified"})
        structurally_excluded = ~row_status.eq("reconciled_official") & ~without_verified_outcome
        report = {
            "evaluator_schema_version": 1,
            "evaluation_status": "ready" if full else "partial" if n_reconciled else "not_ready",
            "official_oos_metrics": bool(full),
            "metric_scope": "official_oos" if full else "verified_subset_diagnostic_only" if n_reconciled else "withheld_no_verified_observations",
            "run_id": run_id, "bundle_id": str(meta.get("run_id", archive_dir.name)),
            "season_id": season_id, "gameweek": gameweek,
            "model_version": descriptor.get("forecast_model_version", descriptor.get("model_version")),
            "forecast_schema_version": descriptor.get("schema_version"),
            "forecast_snapshot_sha256": digest(coach_path),
            "bundle_archive_manifest_sha256": digest(archive_dir / "archive_manifest.json"),
            "prelock_input_hashes": {str(row.get("path")): row.get("sha256") for row in run_manifest.get("inputs", [])},
            "outcome_archive": str(results_dir) if results_dir else None,
            "outcome_provenance": outcome_provenance,
            "forecast_period": {
                "first_forecast_utc": str(pd.to_datetime(coaches["forecast_timestamp_utc"], utc=True).min()),
                "last_forecast_utc": str(pd.to_datetime(coaches["forecast_timestamp_utc"], utc=True).max()),
                "cutoff_utc": descriptor.get("prediction_cutoff_utc"),
            },
            "counts": {
                "forecasted_team_games": n_expected,
                "reconciled_team_games": n_reconciled,
                "unique_reconciled_games": int(rows.loc[rows["reconciliation_status"].eq("reconciled_official"), "nba_game_id"].nunique()),
                "excluded_or_missing": n_expected - n_reconciled,
                "structurally_excluded_team_games": int(structurally_excluded.sum()),
                "without_verified_outcome_team_games": int(without_verified_outcome.sum()),
                "unique_games_without_verified_outcome": int(rows.loc[without_verified_outcome, "nba_game_id"].nunique()),
                "status_counts": metrics["reconciliation_status_counts"],
            },
            "metrics": metrics,
            "limitations": [] if full else [
                "No quantitative coach OOS result is certified unless the pre-lock reviewer and registered post-match outcome gates pass for every forecast row."
            ],
        }
        return report, rows
    except (OSError, ValueError, RuntimeError) as exc:
        # Structural failures produce an explicit diagnostic report, never valid metrics.
        expected = int(descriptor.get("rows", descriptor.get("candidate_rows", 0)) or 0)
        return ({
            "evaluator_schema_version": 1, "evaluation_status": "not_evaluable",
            "official_oos_metrics": False, "metric_scope": "withheld_bundle_not_certified",
            "run_id": str(run_manifest.get("run_id", archive_dir.name)),
            "bundle_id": archive_dir.name,
            "counts": {"forecasted_team_games": expected, "reconciled_team_games": 0, "excluded_or_missing": expected},
            "metrics": None, "reason": str(exc),
            "limitations": ["Bundle reviewer or required source provenance failed; forecasts were not scored."],
        }, pd.DataFrame())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-dir", type=Path, required=True, help="Immutable reviewed pre-lock archive.")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data", help="Root containing registered post-match archives.")
    parser.add_argument("--results-dir", type=Path, help="Explicit registered post-match result archive.")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports/backtest/coach_prospective_oos")
    args = parser.parse_args()
    report, rows = evaluate_archive(args.archive_dir, data_dir=args.data_dir, results_dir=args.results_dir)
    report_id = f"{report.get('run_id', args.archive_dir.name)}_{Path(report['outcome_archive']).name if report.get('outcome_archive') else 'no_outcomes'}"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / f"coach_oos_{report_id}.json"
    csv_path = args.output_dir / f"coach_oos_{report_id}_observations.csv"
    if json_path.exists() or csv_path.exists():
        parser.exit(2, "Refusing to overwrite an existing coach evaluation report.\n")
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    rows.to_csv(csv_path, index=False, na_rep="")
    print(json.dumps({
        "evaluation_status": report["evaluation_status"],
        "official_oos_metrics": report["official_oos_metrics"],
        "counts": report.get("counts"), "metrics": report.get("metrics"),
        "outputs": [str(json_path), str(csv_path)],
    }, indent=2, ensure_ascii=False, allow_nan=False))
    return 0 if report["official_oos_metrics"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
