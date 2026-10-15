#!/usr/bin/env python3
"""Render the feature-family report from already completed experiment artifacts."""
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"reports/audit"
STAMP="20261013_v1"
METRICS=OUT/f"dunkest_pdk_feature_families_metrics_{STAMP}.csv"
COHORTS=OUT/f"dunkest_pdk_feature_families_cohorts_{STAMP}.csv"
AUDIT=OUT/f"dunkest_pdk_feature_families_audit_{STAMP}.json"
REPORT=OUT/f"dunkest_pdk_feature_families_{STAMP}.md"

def md_table(df, floatfmt=".4f"):
    if df.empty: return "_No rows._"
    def fmt(v):
        if pd.isna(v): return ""
        if isinstance(v,(float,np.floating)): return format(float(v),floatfmt)
        if isinstance(v,(int,np.integer)): return str(int(v))
        return str(v).replace("|","\\|")
    headers=[str(c) for c in df.columns]
    rows=[[fmt(v) for v in row] for row in df.itertuples(index=False,name=None)]
    widths=[max(len(headers[i]),*(len(row[i]) for row in rows)) for i in range(len(headers))]
    return "\n".join(
        ["| "+" | ".join(headers[i].ljust(widths[i]) for i in range(len(headers)))+" |",
         "| "+" | ".join("-"*widths[i] for i in range(len(headers)))+" |"]+
        ["| "+" | ".join(row[i].ljust(widths[i]) for i in range(len(headers)))+" |" for row in rows]
    )

def main():
    if REPORT.exists(): raise SystemExit("Refusing to overwrite existing report.")
    for p in (METRICS,COHORTS,AUDIT):
        if not p.exists(): raise SystemExit("Missing completed artifact: "+str(p))
    m=pd.read_csv(METRICS); c=pd.read_csv(COHORTS); a=json.loads(AUDIT.read_text())
    v=m[(m.split=="validation") & (m.feature_family!="baseline_prev10_mean")]
    summary=v.groupby("feature_family").apply(lambda g:pd.Series({
        "weighted_mae":np.average(g.mae,weights=g.n),
        "weighted_rmse":np.sqrt(np.average(np.square(g.rmse),weights=g.n)),
        "weighted_bias":np.average(g.bias_pred_minus_actual,weights=g.n),
        "validation_rows":int(g.n.sum()),"folds":int(g.test_season.nunique())
    }),include_groups=False).reset_index().sort_values(["weighted_mae","weighted_rmse"]).reset_index(drop=True)
    a["validation_summary"]=summary.to_dict(orient="records")
    a["chosen_family"]=str(summary.iloc[0].feature_family)
    AUDIT.write_text(json.dumps(a,indent=2,ensure_ascii=False),encoding="utf-8")
    csum=c[c.split=="validation"].groupby(["feature_family","cohort"],as_index=False).apply(lambda g:pd.Series({
        "n":int(g.n.sum()),"weighted_mae":np.average(g.mae,weights=g.n),
        "weighted_rmse":np.sqrt(np.average(np.square(g.rmse),weights=g.n)),
        "weighted_bias":np.average(g.bias_pred_minus_actual,weights=g.n)
    }),include_groups=False).reset_index(drop=True)
    lines=[
      "# Dunkest PDK feature-family comparison — 2026-10-13","",
      "## Protocol","",
      "- Expanding-origin training: all eligible seasons before the test season.",
      "- Feature selection uses 2022/23, 2023/24 and 2024/25 only.",
      "- 2025/26 is a secondary historical comparison, not used for feature selection; it is not a globally untouched holdout.",
      "- Target labels are verified official PDK rows with valid-game flags and verified NBA identity matches.",
      "- All candidates use identical Extra Trees estimator settings; only the feature family changes.",
      "- Baseline: previous-10 valid PDK-game mean, falling back to the training-target median.",
      "- No production model, configuration, or source dataset was changed.","",
      "## Validation summary","",md_table(summary), "",
      "Selected family by row-weighted validation MAE: **"+a["chosen_family"]+"**.","",
      "## Per-fold metrics","",md_table(m, ".4f"),"",
      "## Low-history cohort comparison","",
      "Cohorts use the number of previous valid Dunkest PDK games. They diagnose cold-start behavior and are not an authoritative NBA draft-year rookie label.","",
      md_table(csum, ".4f"),"",
      "## Interpretation","",
      "- The best feature family is selected only on chronological validation seasons; the secondary 2025/26 results are not used for selection.",
      "- The full lineup optimizer is a separate evaluation problem. A lower player-game MAE does not establish better lineups, coach points, credit-budget use, availability decisions or transfer malus.",
      "- The existing proxy-trained versus official-target comparison on 2025/26 is mixed; it does not justify changing production target mode on its own.",
      "- The low-history cohort should not be described as actual NBA rookies. Use the separate draft-year-matched rookie audit for rookie-specific conclusions.",
      "- Historical complete-lineup backtest remains blocked: available evidence has no rounds with both fixture-linked realized player results and coach results tied to authentic frozen pre-match market, credits and availability snapshots.","",
      "## Artifacts","",
      "- Experiment script: scripts/compare_dunkest_pdk_feature_families_walk_forward_v1.py",
      "- Predictions: reports/audit/dunkest_pdk_feature_families_predictions_20261013_v1.csv",
      "- Metrics: reports/audit/dunkest_pdk_feature_families_metrics_20261013_v1.csv",
      "- Cohorts: reports/audit/dunkest_pdk_feature_families_cohorts_20261013_v1.csv",
      "- Audit JSON: reports/audit/dunkest_pdk_feature_families_audit_20261013_v1.json",""
    ]
    REPORT.write_text("\n".join(lines),encoding="utf-8")
    print("REPORT",REPORT)
    print("\nVALIDATION SUMMARY\n",summary.to_string(index=False))
    print("\n2025/26 SECONDARY FOLD\n",m[m.split.eq("secondary_historical_2025_26")].sort_values("mae").to_string(index=False))
    print("\nCOHORT SUMMARY\n",csum.to_string(index=False))
if __name__=="__main__": main()
