#!/usr/bin/env python3
"""Paired uncertainty audit for sequential lineup transfer-penalty scenarios."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
INPUT=ROOT/"reports/audit/dunkest_historical_lineups_sequential_transfer_20261013_v2_rounds.csv"
STEM="dunkest_historical_lineups_sequential_transfer_paired_bootstrap_20261013_v1"
OUT=ROOT/"reports/audit"
METRICS=OUT/f"{STEM}.csv"; REPORT=OUT/f"{STEM}.md"; AUDIT=OUT/f"{STEM}.json"
SEED=20261013; REPS=10000
COMPARISONS=[(2.5,5.0),(2.5,0.0),(0.0,5.0)]

def main():
    for p in (METRICS,REPORT,AUDIT):
        if p.exists(): raise SystemExit(f"Refusing to overwrite versioned artifact: {p}")
    d=pd.read_csv(INPUT)
    d=d.loc[d.status.eq("evaluated")].copy()
    d["season_id"]=d["season_id"].astype(str)
    wide=d.pivot_table(index=["season_id","round_index"],columns="transfer_penalty",
                       values="realized_net_team_score",aggfunc="first").dropna()
    seasons=sorted(wide.index.get_level_values("season_id").unique())
    rng=np.random.default_rng(SEED)
    rows=[]; bootstrap_store={}
    for a,b in COMPARISONS:
        delta=(wide[a]-wide[b]).rename("delta")
        by_season={sid:delta.loc[sid].to_numpy(float) for sid in seasons}
        boot=np.empty(REPS,dtype=float)
        for i in range(REPS):
            samples=[]
            for sid in seasons:
                values=by_season[sid]
                if len(values): samples.extend(rng.choice(values,size=len(values),replace=True).tolist())
            boot[i]=float(np.mean(samples))
        bootstrap_store[f"{a:g}_minus_{b:g}"]=boot
        rows.append({"comparison":f"optimizer_penalty_{a:g}_minus_{b:g}",
          "penalty_a":a,"penalty_b":b,"matched_rounds":len(delta),
          "mean_official_net_delta":float(delta.mean()),"median_official_net_delta":float(delta.median()),
          "fraction_rounds_a_better":float((delta>0).mean()),
          "ci95_low":float(np.quantile(boot,.025)),"ci95_high":float(np.quantile(boot,.975)),
          "bootstrap_replicates":REPS,"seed":SEED})
        for sid in seasons:
            x=delta.loc[sid]
            rows.append({"comparison":f"season_{sid}_penalty_{a:g}_minus_{b:g}",
              "penalty_a":a,"penalty_b":b,"matched_rounds":len(x),
              "mean_official_net_delta":float(x.mean()),"median_official_net_delta":float(x.median()),
              "fraction_rounds_a_better":float((x>0).mean()),
              "ci95_low":np.nan,"ci95_high":np.nan,"bootstrap_replicates":0,"seed":SEED})
    metrics=pd.DataFrame(rows)
    metrics.to_csv(METRICS,index=False)
    failed=d.loc[~d.status.eq("evaluated")]
    audit={"generated_at_utc":datetime.now(timezone.utc).isoformat(),"input":str(INPUT.relative_to(ROOT)),
      "matched_rounds_all_scenarios":int(len(wide)),"seasons":seasons,"comparisons":metrics.to_dict("records"),
      "status_counts":pd.read_csv(INPUT).status.value_counts(dropna=False).to_dict(),
      "bootstrap":{"method":"Paired round bootstrap, stratified by season; resample rounds with replacement within each season, preserve paired scenario outcomes.",
                   "replicates":REPS,"seed":SEED},
      "scoring":"All scenarios are evaluated with fixed 5-point official proxy malus; the varied coefficient only changes optimizer selection.",
      "production_changed":False}
    AUDIT.write_text(json.dumps(audit,indent=2,ensure_ascii=False,default=str)+"\n",encoding="utf-8")
    pooled=metrics.loc[metrics.comparison.str.startswith("optimizer_penalty_")]
    lines=["# Sequential transfer-penalty scenarios — paired bootstrap audit","",
      f"Generated UTC: {audit['generated_at_utc']}","","## Method","",
      f"Uses {len(wide)} matched rounds where all three optimizer coefficients (0, 2.5, 5) returned a valid lineup. The score of every lineup uses the same fixed 5-point transfer malus; only the optimizer's transfer-cost coefficient changes. The 95% intervals come from {REPS:,} paired round-bootstrap replicates stratified by season.","",
      "## Pooled paired comparisons","",pooled.to_string(index=False),"",
      "## Season-level comparisons","",metrics.loc[~metrics.comparison.str.startswith("optimizer_penalty_")].to_string(index=False),"",
      "## Interpretation","",
      "A positive delta favours the first optimizer coefficient on official-net proxy score. If the interval includes zero, the observed difference is not robust enough to select a coefficient. These are restricted-universe simulations, not a recommendation to change the official scoring rule or production setting.","",
      "## Coverage","",
      f"- Matched rounds: {len(wide)}",
      f"- Status counts over all scenario-round attempts: {audit['status_counts']}",
      "- Failed/undersized rounds are excluded from paired comparisons; failures are disclosed in the sequential backtest report.","",
      "## Artifacts","",str(METRICS.relative_to(ROOT)),str(AUDIT.relative_to(ROOT)),""]
    REPORT.write_text("\n".join(lines),encoding="utf-8")
    print(json.dumps({"status":"completed","matched_rounds":len(wide),"pooled_comparisons":pooled.to_dict("records"),
      "status_counts":audit["status_counts"],"outputs":[str(p.relative_to(ROOT)) for p in (METRICS,REPORT,AUDIT)]},indent=2,default=str))
    return 0
if __name__=="__main__": raise SystemExit(main())
