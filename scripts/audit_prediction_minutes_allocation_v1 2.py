from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROLE_CAPACITY = {"G": 96.0, "F": 96.0, "C": 48.0}


def proportional_minutes(frame: pd.DataFrame) -> pd.Series:
    requested = pd.to_numeric(frame["requested_min"], errors="coerce").fillna(0.0).clip(lower=0.0)
    caps = pd.to_numeric(frame.get("role_minutes_cap", pd.Series(np.nan, index=frame.index)), errors="coerce")
    requested = caps.where(caps.notna(), requested).combine(requested, min)
    playable = pd.to_numeric(frame["p_play"], errors="coerce").fillna(0.0).gt(0.0)
    requested = requested.where(playable, 0.0)
    allocated = requested.copy()
    work = frame.assign(_requested=requested)
    for _, group in work.loc[playable].groupby(["team", "role"], dropna=False, sort=False):
        capacity = ROLE_CAPACITY.get(str(group["role"].iloc[0]), 96.0)
        total = float(group["_requested"].sum())
        if total <= capacity or total <= 0.0:
            continue
        values = group["_requested"] * (capacity / total)
        excess = float(values.sum() - capacity)
        if excess > 0.0:
            values.loc[values.idxmax()] -= excess
        allocated.loc[group.index] = values
    return allocated


def reconstruct_expected_score(frame: pd.DataFrame, minutes: pd.Series) -> pd.Series:
    rate = pd.to_numeric(frame["pdk_rate_for_projection"], errors="coerce").fillna(0.0)
    implied = pd.to_numeric(frame["implied_min"], errors="coerce").replace(0.0, np.nan).clip(lower=8.0)
    minute_component = minutes * rate
    components = pd.DataFrame(
        {
            "minutes": minute_component,
            "ensemble": pd.to_numeric(frame["ensemble_pdk"], errors="coerce") * (minutes / implied),
            "prior": pd.to_numeric(frame["prior_pdk"], errors="coerce") * (minutes / implied),
        },
        index=frame.index,
    )
    weights = pd.DataFrame(
        {
            "minutes": pd.to_numeric(frame["projection_weight_minutes"], errors="coerce").fillna(0.0),
            "ensemble": pd.to_numeric(frame["projection_weight_ensemble"], errors="coerce").fillna(0.0),
            "prior": pd.to_numeric(frame["projection_weight_prior"], errors="coerce").fillna(0.0),
        },
        index=frame.index,
    )
    weighted_sum = components.fillna(0.0).mul(weights).sum(axis=1)
    available_weight = components.notna().mul(weights).sum(axis=1).replace(0.0, np.nan)
    blended = (weighted_sum / available_weight).fillna(minute_component)
    has_history = frame["has_history"].fillna(False).astype(bool)
    blended.loc[~has_history] = minute_component.loc[~has_history]

    historical = pd.to_numeric(frame["historical_rf_pdk"], errors="coerce")
    historical_weight = pd.to_numeric(frame["historical_rf_blend_weight"], errors="coerce").fillna(0.0).clip(0.0, 1.0)
    historical_denominator = implied.fillna(minutes.where(minutes.gt(0.0)))
    ratio = (minutes / historical_denominator).replace([np.inf, -np.inf], np.nan)
    historical_scaled = (historical * ratio).clip(lower=0.0)
    can_blend = historical_scaled.notna() & historical_weight.gt(0.0)
    blended.loc[can_blend] = (
        (1.0 - historical_weight.loc[can_blend]) * blended.loc[can_blend]
        + historical_weight.loc[can_blend] * historical_scaled.loc[can_blend]
    )
    games = pd.to_numeric(frame["n_games"], errors="coerce").fillna(0.0)
    confidence = (games / (games + 12.0)).clip(0.0, 1.0)
    blended.loc[has_history] = (
        confidence.loc[has_history] * blended.loc[has_history]
        + (1.0 - confidence.loc[has_history]) * minute_component.loc[has_history]
    )
    p_play = pd.to_numeric(frame["p_play"], errors="coerce").fillna(1.0).clip(0.0, 1.0)
    return blended.clip(lower=0.0) * p_play


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay the proportional minutes allocator on a frozen prediction run.")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-dir", default="reports/audit")
    args = parser.parse_args()

    data_dir = Path(args.data_dir).expanduser().resolve()
    run_dir = data_dir / "predictions" / args.run_id
    prediction_path = run_dir / "predictions.parquet"
    if not prediction_path.is_file():
        raise FileNotFoundError(prediction_path)
    frame = pd.read_parquet(prediction_path)
    required = {
        "player_name", "team", "role", "requested_min", "expected_min", "p_play",
        "role_minutes_cap", "pdk_rate_for_projection", "implied_min", "ensemble_pdk",
        "prior_pdk", "projection_weight_minutes", "projection_weight_ensemble",
        "projection_weight_prior", "has_history", "historical_rf_pdk",
        "historical_rf_blend_weight", "n_games", "expected_pdk",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Frozen prediction file lacks required audit columns: {missing}")

    out = frame.copy()
    out["simulated_expected_min"] = proportional_minutes(out)
    out["simulated_expected_pdk"] = reconstruct_expected_score(out, out["simulated_expected_min"])
    out["expected_min_delta"] = out["simulated_expected_min"] - pd.to_numeric(out["expected_min"], errors="coerce")
    out["expected_pdk_delta"] = out["simulated_expected_pdk"] - pd.to_numeric(out["expected_pdk"], errors="coerce")
    old_score = pd.to_numeric(out["expected_pdk"], errors="coerce")
    new_score = pd.to_numeric(out["simulated_expected_pdk"], errors="coerce")
    playable = pd.to_numeric(out["p_play"], errors="coerce").fillna(0.0).gt(0.0)

    budget_violations = []
    for (team, role), group in out.groupby(["team", "role"], dropna=False):
        cap = ROLE_CAPACITY.get(str(role), 96.0)
        total = float(group["simulated_expected_min"].sum())
        if total > cap + 1e-8:
            budget_violations.append({"team": str(team), "role": str(role), "minutes": total, "capacity": cap})

    summary = {
        "run_id": args.run_id,
        "source_predictions": str(prediction_path),
        "rows": int(len(out)),
        "unique_players": int(out["player_name"].nunique()),
        "old_zero_expected_pdk": int(old_score.le(1e-9).sum()),
        "new_zero_expected_pdk": int(new_score.le(1e-9).sum()),
        "old_zero_expected_pdk_playable": int((old_score.le(1e-9) & playable).sum()),
        "new_zero_expected_pdk_playable": int((new_score.le(1e-9) & playable).sum()),
        "old_zero_minutes_playable": int((pd.to_numeric(out["expected_min"], errors="coerce").le(1e-9) & playable).sum()),
        "new_zero_minutes_playable": int((out["simulated_expected_min"].le(1e-9) & playable).sum()),
        "players_with_positive_request_and_play_probability": int((pd.to_numeric(out["requested_min"], errors="coerce").gt(0.0) & playable).sum()),
        "players_still_zero_despite_positive_request": int((out["simulated_expected_min"].le(1e-9) & pd.to_numeric(out["requested_min"], errors="coerce").gt(0.0) & playable).sum()),
        "old_median_expected_pdk": float(old_score.median()),
        "new_median_expected_pdk": float(new_score.median()),
        "old_p95_expected_pdk": float(old_score.quantile(0.95)),
        "new_p95_expected_pdk": float(new_score.quantile(0.95)),
        "max_absolute_player_score_delta": float(out["expected_pdk_delta"].abs().max()),
        "mean_absolute_player_score_delta": float(out["expected_pdk_delta"].abs().mean()),
        "role_budget_violations": budget_violations,
        "scope": "Deterministic replay of the frozen run's saved pre-allocation minute requests and saved model components; not a new end-to-end forecast or an out-of-sample accuracy result.",
    }

    output_dir = Path(args.output_dir).expanduser()
    if not output_dir.is_absolute():
        output_dir = Path.cwd() / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"minutes_allocator_replay_{args.run_id}"
    detail_cols = [
        "player_name", "team", "role", "status", "p_play", "requested_min",
        "role_minutes_cap", "expected_min", "simulated_expected_min",
        "expected_min_delta", "expected_pdk", "simulated_expected_pdk",
        "expected_pdk_delta", "role_depth_rank", "competition_scale", "projection_source",
    ]
    detail = out[[c for c in detail_cols if c in out.columns]].sort_values("expected_pdk_delta", ascending=False)
    detail.to_csv(output_dir / f"{stem}_players.csv", index=False)
    (output_dir / f"{stem}.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [
        f"# Minutes allocator replay — {args.run_id}", "",
        f"- Rows / unique players: {summary['rows']} / {summary['unique_players']}",
        f"- Zero predictions before: {summary['old_zero_expected_pdk']}",
        f"- Zero predictions after proportional allocation: {summary['new_zero_expected_pdk']}",
        f"- Zero predictions among playable players before: {summary['old_zero_expected_pdk_playable']}",
        f"- Zero predictions among playable players after: {summary['new_zero_expected_pdk_playable']}",
        f"- Playable players with zero minutes before: {summary['old_zero_minutes_playable']}",
        f"- Playable players with zero minutes after: {summary['new_zero_minutes_playable']}",
        f"- Median expected PDK before / after: {summary['old_median_expected_pdk']:.3f} / {summary['new_median_expected_pdk']:.3f}",
        f"- Mean absolute per-player score change: {summary['mean_absolute_player_score_delta']:.3f}",
        f"- Role-budget violations: {len(budget_violations)}",
        "",
        "## Scope", "",
        summary["scope"], "",
        "The proportional allocator spreads over-budget requested minutes across all players in the same team/role group in proportion to their capped requests. It preserves zero availability for players with p_play=0 and respects each role's total minute capacity. This audit is a mechanical replay only; it does not establish predictive accuracy.",
    ]
    (output_dir / f"{stem}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({
        "summary": summary,
        "outputs": [
            str(output_dir / f"{stem}.json"),
            str(output_dir / f"{stem}.md"),
            str(output_dir / f"{stem}_players.csv"),
        ],
    }, indent=2, ensure_ascii=False))
    return 0 if not budget_violations else 2


if __name__ == "__main__":
    raise SystemExit(main())
