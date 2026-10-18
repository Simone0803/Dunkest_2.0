#!/usr/bin/env python3
"""Historical OOS diagnostics for Dunkest player uncertainty and lineup risk.

This audit deliberately excludes 2025/26 and the frozen 2026/27 GW1 bundle.
It never selects a production risk parameter: complete historical pre-lock
lineups are not available for certified lineup-level tuning.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/audit"
PRED = OUT / "dunkest_multiseason_production_ensemble_walk_forward_20261018_v2_predictions.csv"
STEM = "dunkest_lineup_uncertainty_four_workstreams_20261018_v2"
FILES = [OUT/f"{STEM}.json", OUT/f"{STEM}.md", OUT/f"{STEM}_interval_metrics.csv", OUT/f"{STEM}_game_cluster_metrics.csv"]
BINS = [-np.inf, 5, 10, 15, 20, 25, np.inf]
LABELS = ["<5", "5-10", "10-15", "15-20", "20-25", "25+"]
SEASONS = ["2022-23", "2023-24", "2024-25"]


def metrics_for(g: pd.DataFrame, q: np.ndarray, method: str, season: str, band: str) -> dict:
    # Residual is forecast - actual. To obtain actual-score interval endpoints,
    # subtract q90 from forecast for lower bound and q10 for upper bound.
    pred = g.predicted_pdk.to_numpy(float)
    actual = g.actual_pdk.to_numpy(float)
    lo, med, hi = pred - q[2], pred - q[1], pred - q[0]
    return {
        "test_season": season, "method": method, "forecast_band": band, "n": len(g),
        "lower_tail_coverage": float(np.mean(actual >= lo)),
        "upper_tail_coverage": float(np.mean(actual <= hi)),
        "central_80_coverage": float(np.mean((actual >= lo) & (actual <= hi))),
        "mean_interval_width": float(np.mean(hi-lo)),
        "mae_after_median_residual_offset": float(np.mean(np.abs(med-actual))),
    }


def cluster_metrics(g: pd.DataFrame, season: str) -> dict:
    # Estimate the common game-shock component using cross-fitted forecast errors.
    # ICC is a method-of-moments diagnostic; it is not a full player-pair correlation model.
    sizes = g.groupby("game_id").size()
    keep = sizes[sizes >= 8].index
    x = g[g.game_id.isin(keep)].copy()
    if x.empty:
        return {"test_season": season, "games": 0, "rows": 0}
    group = x.groupby("game_id").error
    n_g = group.size()
    mean_g = group.mean()
    var_g = group.var(ddof=1).fillna(0.0)
    grand = float(x.error.mean())
    kbar = float(n_g.mean())
    ms_between = float((n_g * (mean_g-grand)**2).sum() / max(len(n_g)-1, 1))
    ms_within = float(var_g.mul(n_g-1).sum() / max((n_g-1).sum(), 1))
    icc = (ms_between-ms_within)/(ms_between+(kbar-1)*ms_within) if ms_between+(kbar-1)*ms_within > 0 else float("nan")
    # Distribution of game-level average residuals is a directly interpretable
    # common-shock diagnostic; bootstrap uncertainty is by game cluster.
    rng = np.random.default_rng(20261018 + sum(map(ord, season)))
    vals = mean_g.to_numpy(float)
    boot = np.array([rng.choice(vals, size=len(vals), replace=True).mean() for _ in range(2000)])
    return {
        "test_season": season, "games_with_at_least_8_players": int(len(n_g)), "player_rows": int(len(x)),
        "mean_players_per_game": kbar, "mean_game_residual_pred_minus_actual": float(mean_g.mean()),
        "sd_game_mean_residual": float(mean_g.std(ddof=1)), "within_game_residual_sd": float(np.sqrt(max(ms_within,0))),
        "anova_icc_approx": float(icc), "game_mean_residual_bootstrap_95_low": float(np.quantile(boot,.025)),
        "game_mean_residual_bootstrap_95_high": float(np.quantile(boot,.975)),
    }


def main() -> None:
    if any(p.exists() for p in FILES):
        raise SystemExit("Refusing to overwrite versioned audit outputs")
    d = pd.read_csv(PRED)
    d = d.loc[d.method.eq("all_prior_seasons_low_history_weighted") & d.test_season.isin(SEASONS)].copy()
    for col in ["predicted_pdk", "actual_pdk", "history_games", "error"]:
        d[col] = pd.to_numeric(d[col], errors="coerce")
    d = d.dropna(subset=["predicted_pdk", "actual_pdk", "game_id", "game_date"])
    # Recompute error so sign is explicit and robust to stale output columns.
    d["error"] = d.predicted_pdk - d.actual_pdk
    d["forecast_band"] = pd.cut(d.predicted_pdk, BINS, labels=LABELS, right=False)
    interval_rows=[]; cluster_rows=[]; fold_payload=[]
    for season in SEASONS[1:]:
        cal = d.loc[d.test_season.lt(season)].copy()
        test = d.loc[d.test_season.eq(season)].copy()
        if cal.empty or test.empty: raise SystemExit(f"Missing chronological calibration fold {season}")
        qglobal = np.quantile(cal.error.to_numpy(float), [.1,.5,.9])
        interval_rows.append(metrics_for(test, qglobal, "pooled_past_only", season, "all"))
        by_band=[]
        for label in LABELS:
            tg = test.loc[test.forecast_band.astype(str).eq(label)]
            if tg.empty: continue
            cg = cal.loc[cal.forecast_band.astype(str).eq(label), "error"].dropna().to_numpy(float)
            # Shrink small band samples to pooled prior residual distribution.
            if len(cg) >= 40:
                alpha = len(cg)/(len(cg)+1000.0)
                qb = np.quantile(cg,[.1,.5,.9])
            else:
                alpha, qb = 0.0, qglobal
            q = alpha*qb + (1-alpha)*qglobal
            interval_rows.append(metrics_for(tg,q,"score_band_shrunk_past_only",season,label))
            by_band.append({"band":label,"n_calibration":int(len(cg)),"n_test":int(len(tg)),"shrinkage_weight":float(alpha),"q10_q50_q90_error":q.tolist()})
        cluster_rows.append(cluster_metrics(test,season))
        fold_payload.append({"test_season":season,"calibration_seasons":sorted(cal.test_season.unique().tolist()),"calibration_rows":len(cal),"test_rows":len(test),"pooled_q10_q50_q90_error":qglobal.tolist(),"bands":by_band})
    # Keep game-cluster diagnostics for all available OOS seasons, but do not use
    # any frozen prospective GW1 records for fitting or selection.
    for season in [SEASONS[0]]:
        cluster_rows.insert(0,cluster_metrics(d.loc[d.test_season.eq(season)],season))
    im = pd.DataFrame(interval_rows); cm = pd.DataFrame(cluster_rows)
    im.to_csv(FILES[2],index=False); cm.to_csv(FILES[3],index=False)
    payload = {
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "source":str(PRED.relative_to(ROOT)), "candidate":"all_prior_seasons_low_history_weighted",
        "test_seasons_used_for_interval_evaluation":["2023-24","2024-25"],
        "calibration_policy":"strictly earlier walk-forward seasons; prediction-score bands chosen from forecast only; band quantiles shrunk toward pooled residual quantiles with n/(n+1000)",
        "prospective_holdout_policy":"2025/26 and frozen 2026/27 GW1 excluded",
        "interval_folds":fold_payload,"game_cluster_diagnostics":cluster_rows,
        "workstream_status":{
            "1_oof_quantile_calibration":"evaluated as an additional strictly past-only score-band challenger; no production promotion without repeated coverage and width gains",
            "2_joint_scenario_simulation":"game-level common-shock diagnostics produced; full joint Monte Carlo awaits a validated dependence model and complete pre-lock inputs",
            "3_risk_objective_tuning":"blocked for certification: historical lineup inputs/outcomes are not complete enough for a leakage-free lineup backtest; no risk_lambda selected",
            "4_minutes_role_stability":"existing walk-forward minute model improves MAE over prev5 (4.983 vs 5.127 min), but prior downstream tests did not justify replacing the PDK projection; retain shadow-only status",
        },
        "production_point_predictions_changed":False,
        "lineup_selection_objective_changed":False,
        "lineup_interval_aggregation_changed":"Within-fixture dependence is now aggregated only for players/coaches sharing the same verified nba_game_id; different fixtures are treated as independent. Provisional within-fixture rho=0.01 is grounded in historical OOS game-cluster ICC diagnostics, but portfolio coverage remains uncertified without authentic full-lineup outcomes.",
        "limitations":["These are player-game OOS diagnostics, not certified historical full-lineup outcomes.","Game-level residual ICC is a method-of-moments diagnostic, not proof of a universal correlation parameter.","A narrower interval is not accepted unless nominal 80% coverage remains near 80%.","The new grouped portfolio interval calculation changes reported lineup uncertainty, not player forecasts or lineup selection; it must be checked against prospective realized lineups after the frozen test cutoff."]
    }
    FILES[0].write_text(json.dumps(payload,indent=2,ensure_ascii=False)+"\n")
    lines=["# Dunkest lineup uncertainty — four-workstream historical audit","",f"Generated UTC: {payload['created_utc']}","","## Scope and leakage controls","",f"- Source: `{payload['source']}`; current production ensemble OOS predictions only.","- Interval calibration tests 2023/24 and 2024/25 using strictly earlier seasons only.","- 2025/26 and the frozen 2026/27 GW1 prospective bundle are excluded from calibration and tuning.","- Player model, expected scores, risk objective, configuration and lineup selection are unchanged; only lineup interval aggregation now applies correlation within a shared verified NBA fixture rather than globally across the roster.","","## 1. Past-only quantile calibration","","Residual = forecast − actual. For an 80% central interval, central coverage should be near 0.80 and marginal lower/upper coverage near 0.90. Width is only compared at acceptable coverage.","","| Test season | Method | Forecast band | N | Lower coverage | Upper coverage | Central 80% | Mean width | Median-offset MAE |","|---|---|---|---:|---:|---:|---:|---:|---:|"]
    for _,r in im.iterrows(): lines.append(f"| {r.test_season} | {r.method} | {r.forecast_band} | {int(r.n)} | {r.lower_tail_coverage:.3f} | {r.upper_tail_coverage:.3f} | {r.central_80_coverage:.3f} | {r.mean_interval_width:.2f} | {r.mae_after_median_residual_offset:.3f} |")
    lines += ["","## 2. Same-game residual dependence","","This is an ANOVA method-of-moments estimate of shared game-level residual dependence from out-of-sample player forecasts. It is diagnostic, not a fitted production correlation coefficient.","","| Season | Games (>=8 rows) | Player rows | Avg players/game | SD game-mean residual | Within-game residual SD | Approx ICC | Bootstrap 95% CI game-mean bias |","|---|---:|---:|---:|---:|---:|---:|---|"]
    for r in cluster_rows:
        if r.get('games_with_at_least_8_players',0): lines.append(f"| {r['test_season']} | {r['games_with_at_least_8_players']} | {r['player_rows']} | {r['mean_players_per_game']:.1f} | {r['sd_game_mean_residual']:.3f} | {r['within_game_residual_sd']:.3f} | {r['anova_icc_approx']:.4f} | [{r['game_mean_residual_bootstrap_95_low']:.3f}, {r['game_mean_residual_bootstrap_95_high']:.3f}] |")
    lines += ["","## 3. Risk-aware lineup objective","","**Not certified / not tuned.** Available historical archives do not establish authentic pre-lock roster, credits, injuries, fixture-linked coach market and realized scores for enough complete rounds. Tuning `risk_lambda`, correlation, or CVaR on reconstructed lineups would select against proxy labels and could introduce look-ahead bias. Keep current production setting until certified lineup-level walk-forward evidence exists.","","## 4. Minutes, role and participation","","The prior walk-forward minutes audit reports HGB MAE 4.983 minutes vs 5.127 for the previous-five baseline over 57,682 player-games, but the low-history and zero-minute cohorts remain difficult. Prior downstream tests did not justify directly scaling PDK by the minutes model. Retain it as an auxiliary/shadow estimate; do not increase its production weight without paired PDK and lineup-level gains.","","## Decision","","- The portfolio interval calculation has been changed to group players and coach by verified `nba_game_id`; distinct fixtures are combined as independent components. Within-fixture correlation is provisionally 0.01 from the historical OOS diagnostics above. This affects reported P10/P90 only, not player forecasts, risk objective or selected lineups. Validate against future complete prospective lineups before treating the intervals as calibrated.","- Run the score-band calibration as a challenger only; promote only if repeated outer-fold coverage is near nominal and intervals are meaningfully tighter without subgroup failures.","- Use the measured game-cluster diagnostics to design a future joint scenario model, not to hardcode a correlation.","- Do not change `risk_lambda` without certified lineup backtests.","- Keep production predictions and the frozen GW1 bundle unchanged.","","## Artifacts",f"- `{FILES[0].relative_to(ROOT)}`",f"- `{FILES[2].relative_to(ROOT)}`",f"- `{FILES[3].relative_to(ROOT)}`","","## Reproduction","```bash",f"PYTHONPATH=src .venv/bin/python {Path(__file__).relative_to(ROOT)}","```"," "]
    FILES[1].write_text("\n".join(lines))
    print(im.to_string(index=False,float_format=lambda x:f"{x:.4f}"))
    print("\nGAME CLUSTERS\n",cm.to_string(index=False,float_format=lambda x:f"{x:.4f}"))
    print("\nREPORT",FILES[1])

if __name__ == "__main__": main()
