#!/usr/bin/env python3
"""Strict-coverage audit of historical Dunkest lineup proxy results."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from dunkest.names import player_key

ROOT = Path(__file__).resolve().parents[1]
LINEUPS = ROOT / "reports/audit/dunkest_historical_lineups_lagged_market_20261013_v5_lineups.csv"
OUTCOMES = ROOT / "data/processed/dunkest_historical_player_week_round_2020-25_v2.parquet"
STEM = "dunkest_historical_lineups_strict_actual_coverage_20261014_v1"
OUT = ROOT / "reports/audit"
REPORT, DETAIL, AUDIT = (OUT / f"{STEM}.md", OUT / f"{STEM}_rounds.csv", OUT / f"{STEM}.json")
PAIRED = OUT / f"{STEM}_paired_rounds.csv"

def bootstrap_ci(values, seed=42, n_boot=20000):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if not len(values):
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    means = np.empty(n_boot)
    for i in range(n_boot):
        means[i] = rng.choice(values, size=len(values), replace=True).mean()
    return tuple(float(x) for x in np.quantile(means, [0.025, 0.975]))

def main():
    for p in (REPORT, DETAIL, AUDIT, PAIRED):
        if p.exists():
            raise SystemExit(f"Refusing to overwrite versioned artifact: {p}")
    lineups = pd.read_csv(LINEUPS)
    raw = pd.read_parquet(OUTCOMES)
    required = {"source_season_id", "source_week", "source_round", "player_name", "target_pdk_round_total"}
    if not required.issubset(raw.columns):
        raise ValueError(f"Outcome archive missing columns: {sorted(required - set(raw.columns))}")
    raw["season_id"] = raw["source_season_id"].astype(str)
    for col in ("source_week", "source_round", "target_pdk_round_total"):
        raw[col] = pd.to_numeric(raw[col], errors="coerce")
    raw["player_key"] = raw["player_name"].astype(str).map(player_key)
    raw = raw.loc[np.isfinite(raw["target_pdk_round_total"])].copy()
    outcome_sets = {}
    for key, g in raw.groupby(["season_id", "source_week", "source_round"], dropna=False):
        outcome_sets[(str(key[0]), int(key[1]), int(key[2]))] = set(g["player_key"].dropna())

    checks = []
    for row in lineups.to_dict("records"):
        try:
            key = (str(row["season_id"]), int(row["source_week"]), int(row["source_round"]))
        except (ValueError, TypeError):
            key = None
        names = [x.strip() for x in str(row.get("selected_players", "")).split(";") if x.strip()]
        keys = [player_key(x) for x in names]
        available = outcome_sets.get(key, set()) if key else set()
        matched = sum(k in available for k in keys)
        checks.append({**row, "selected_count_parsed": len(keys),
            "selected_players_with_target_outcome": matched,
            "selected_player_actual_coverage": matched / len(keys) if keys else np.nan,
            "all_10_target_outcomes_observed": bool(len(keys) == 10 and matched == 10)})
    checked = pd.DataFrame(checks)
    checked.to_csv(DETAIL, index=False)

    eligible = checked.loc[
        checked["strategy"].isin(["model", "previous5_baseline"])
        & checked["all_10_target_outcomes_observed"].astype(bool)
        & checked["roster_valid"].fillna(False).astype(bool)
        & pd.to_numeric(checked["realized_player_score"], errors="coerce").notna()
    ].copy()
    pivot = eligible.pivot_table(
        index=["season_id", "round_index", "source_week", "source_round", "target_date"],
        columns="strategy", values="realized_player_score", aggfunc="first"
    ).reset_index()
    if not {"model", "previous5_baseline"}.issubset(pivot.columns):
        pivot = pd.DataFrame(columns=["season_id", "round_index", "source_week", "source_round", "target_date", "model", "previous5_baseline"])
    else:
        pivot["delta_model_minus_baseline"] = pivot["model"] - pivot["previous5_baseline"]
        pivot = pivot.dropna(subset=["model", "previous5_baseline", "delta_model_minus_baseline"]).copy()
    pivot.to_csv(PAIRED, index=False)

    rounds_count = len(lineups[["season_id", "round_index", "source_week", "source_round"]].drop_duplicates())
    rows = checked.loc[checked["strategy"].isin(["model", "previous5_baseline"])]
    complete_counts = rows.groupby("strategy")["all_10_target_outcomes_observed"].agg(["sum", "count"]).to_dict("index")
    by_season = {}
    for season, g in pivot.groupby("season_id"):
        d = g["delta_model_minus_baseline"].to_numpy(dtype=float)
        lo, hi = bootstrap_ci(d, seed=42 + int(season))
        by_season[str(season)] = {"paired_rounds": int(len(g)),
            "mean_model_player_score": float(g["model"].mean()),
            "mean_baseline_player_score": float(g["previous5_baseline"].mean()),
            "mean_delta": float(d.mean()), "median_delta": float(np.median(d)),
            "model_win_rate": float(np.mean(d > 0)), "bootstrap_95_ci_mean_delta": [lo, hi]}
    d = pivot["delta_model_minus_baseline"].to_numpy(dtype=float) if len(pivot) else np.array([])
    lo, hi = bootstrap_ci(d)
    pooled = ({"mean_model_player_score": float(pivot["model"].mean()),
        "mean_baseline_player_score": float(pivot["previous5_baseline"].mean()),
        "mean_delta": float(d.mean()), "median_delta": float(np.median(d)),
        "model_win_rate": float(np.mean(d > 0)), "bootstrap_95_ci_mean_delta": [lo, hi]} if len(pivot) else {})
    summary = {"generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": "All ten selected players must have a finite target-round outcome row for both strategies on the same round.",
        "input_lineups": str(LINEUPS.relative_to(ROOT)), "input_outcomes": str(OUTCOMES.relative_to(ROOT)),
        "round_keys_in_lineup_archive": rounds_count, "lineup_rows": int(len(checked)),
        "complete_10_player_lineups_by_strategy": complete_counts, "paired_rounds_strict_complete": int(len(pivot)),
        "pooled": pooled, "by_season": by_season,
        "limitations": [
            "Restricted universe: candidates are based on prior observed Dunkest rows, not a complete archived pre-lock market.",
            "No missing selected-player score is imputed as zero in this strict comparison; target-round row presence is the eligibility gate.",
            "The metric isolates realized player-lineup points; historical coach prices, exact coach PDK, and transfer counts/malus are unavailable.",
            "Historical CR and roles are lagged proxies, not certified pre-lock market snapshots.",
            "Results do not establish complete-market optimum or official team-score superiority."]}
    AUDIT.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = ["# Historical Dunkest lineup proxy — strict realized-player coverage", "",
        f"Generated UTC: {summary['generated_at_utc']}", "",
        "## Method", "",
        "The broad proxy run could assign zero realized points when a selected player lacked a target-round row. This audit removes that assumption: each lineup is eligible only when all ten selected players have a finite target-round outcome row. Model and previous-five baseline are compared on the same rounds where both qualify.", "",
        "## Coverage", "", f"- Unique round keys: {rounds_count}",
        f"- Paired rounds with all 10 outcomes observed for both strategies: {len(pivot)}", "",
        "| Strategy | Complete 10-player lineups | Total lineup rows |", "|---|---:|---:|"]
    for strategy, counts in complete_counts.items():
        lines.append(f"| {strategy} | {int(counts['sum'])} | {int(counts['count'])} |")
    lines += ["", "## Strict paired comparison", ""]
    if len(pivot):
        lines += [f"- Mean realized player-lineup score, model: **{pivot['model'].mean():.3f}**",
            f"- Mean realized player-lineup score, baseline: **{pivot['previous5_baseline'].mean():.3f}**",
            f"- Mean paired difference: **{d.mean():.3f}**",
            f"- Median paired difference: **{np.median(d):.3f}**",
            f"- Model win rate: **{np.mean(d > 0):.1%}**",
            f"- Round-bootstrap 95% CI: **[{lo:.3f}, {hi:.3f}]**", "",
            "| Season ID | Paired rounds | Mean model | Mean baseline | Mean delta | Model win rate | 95% CI delta |",
            "|---:|---:|---:|---:|---:|---:|---:|"]
        for season, m in sorted(by_season.items()):
            ci = m["bootstrap_95_ci_mean_delta"]
            lines.append(f"| {season} | {m['paired_rounds']} | {m['mean_model_player_score']:.3f} | {m['mean_baseline_player_score']:.3f} | {m['mean_delta']:.3f} | {m['model_win_rate']:.1%} | [{ci[0]:.3f}, {ci[1]:.3f}] |")
    else:
        lines.append("No paired rounds met the strict coverage rule; no performance estimate is reported.")
    lines += ["", "## Interpretation and limitations", "",
        "This is a stricter historical proxy, not a certified complete Dunkest backtest. It avoids imputing absent outcomes as zero but still uses a reconstructed candidate universe and lagged prices/roles. Historical coach prices and transfer malus remain unavailable. Use this as partial evidence alongside prospective pre-lock capture.", "",
        "## Reproducibility", "",
        "Script: scripts/audit_dunkest_historical_lineups_strict_actual_coverage_v1.py",
        f"Paired rounds: {PAIRED.relative_to(ROOT)}", f"Row-level coverage: {DETAIL.relative_to(ROOT)}",
        f"Machine-readable audit: {AUDIT.relative_to(ROOT)}", ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": "completed", "paired_rounds": int(len(pivot)),
        "complete_lineups_by_strategy": complete_counts, "pooled": pooled, "by_season": by_season,
        "outputs": [str(p.relative_to(ROOT)) for p in (REPORT, DETAIL, AUDIT, PAIRED)]}, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
