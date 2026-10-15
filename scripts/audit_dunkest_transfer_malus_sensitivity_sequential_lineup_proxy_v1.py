#!/usr/bin/env python3
"""Ex-post transfer-malus sensitivity using sequential proxy lineups.

Not an exact Dunkest transfer backtest: historical carried rosters and official
coach prices are missing. This evaluates whether a fresh, independently
optimized proxy lineup outscored carrying the previous round's proxy roster,
using raw player PDK plus neutral-credit coach base score and explicit malus
scenarios. No current-round outcomes enter lineup selection.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from dunkest.names import player_key

ROOT=Path(__file__).resolve().parents[1]
LINEUPS=ROOT/"reports/audit/dunkest_historical_lineups_rest_schedule_20261013_v1_lineups.csv"
RAW=ROOT/"data/processed/dunkest_historical_player_week_round_2020-25_v2.parquet"
COACH=ROOT/"reports/audit/dunkest_coach_base_points_walk_forward_2018-26_v1_predictions.csv"
STEM="dunkest_transfer_malus_sensitivity_sequential_lineup_proxy_20261013_v1"
OUT=ROOT/"reports/audit"
DETAIL=OUT/f"{STEM}_transitions.csv"; METRICS=OUT/f"{STEM}_metrics.csv"
AUDIT=OUT/f"{STEM}.json"; REPORT=OUT/f"{STEM}.md"
PENALTIES=[0.0,1.0,2.0,3.5,5.0]

def main():
    for p in (DETAIL,METRICS,AUDIT,REPORT):
        if p.exists(): raise SystemExit(f"Refusing to overwrite existing artifact: {p}")
    lineups=pd.read_csv(LINEUPS)
    raw=pd.read_parquet(RAW)
    raw["season_id"]=raw.source_season_id.astype(str)
    raw["player_key"]=raw.player_name.astype(str).map(player_key)
    raw["source_week"]=pd.to_numeric(raw.source_week,errors="coerce")
    raw["source_round"]=pd.to_numeric(raw.source_round,errors="coerce")
    raw["target_pdk_round_total"]=pd.to_numeric(raw.target_pdk_round_total,errors="coerce")
    raw=raw.dropna(subset=["target_pdk_round_total"])
    score_maps={}
    for (sid,week,rnd),g in raw.groupby(["season_id","source_week","source_round"],dropna=False):
        score_maps[(str(sid),int(week),int(rnd))]=dict(zip(g.player_key,g.target_pdk_round_total.astype(float)))
    coach=pd.read_csv(COACH)
    coach=coach.loc[coach.method.eq("model_pregame_team_form")].copy()
    coach["season"]=coach.season.astype(str)
    coach["game_date"]=pd.to_datetime(coach.game_date,errors="coerce").dt.strftime("%Y-%m-%d")
    coach["team"]=coach.team.astype(str).str.upper().str.strip()
    coach_actual={}
    for r in coach.itertuples(index=False):
        val=pd.to_numeric(getattr(r,"actual_base_coach_pdk",np.nan),errors="coerce")
        if np.isfinite(val): coach_actual[(str(r.season),str(r.game_date),str(r.team))]=float(val)
    rows=[]
    for (sid,strategy),g in lineups.groupby(["season_id","strategy"],sort=False):
        g=g.sort_values(["round_index","target_date"]).reset_index(drop=True)
        for i in range(1,len(g)):
            prev,cur=g.iloc[i-1],g.iloc[i]
            if str(prev.season)!=str(cur.season): continue
            prev_names=[player_key(x.strip()) for x in str(prev.selected_players).split(";") if x.strip()]
            cur_names=[player_key(x.strip()) for x in str(cur.selected_players).split(";") if x.strip()]
            if len(prev_names)!=10 or len(cur_names)!=10: continue
            oldset,newset=set(prev_names),set(cur_names)
            transfers_players=len(newset-oldset)
            coach_changed=str(prev.selected_coach_proxy_team).upper()!=str(cur.selected_coach_proxy_team).upper()
            transfers=transfers_players+int(coach_changed)
            scores=score_maps.get((str(sid),int(cur.source_week),int(cur.source_round)),{})
            old_player_score=float(sum(scores.get(k,0.0) for k in oldset))
            new_player_score=float(sum(scores.get(k,0.0) for k in newset))
            season=str(cur.season); date=str(cur.target_date)
            old_coach=coach_actual.get((season,date,str(prev.selected_coach_proxy_team).upper()),np.nan)
            new_coach=coach_actual.get((season,date,str(cur.selected_coach_proxy_team).upper()),np.nan)
            if not np.isfinite(old_coach) or not np.isfinite(new_coach): continue
            delta=(new_player_score+new_coach)-(old_player_score+old_coach)
            row={"season_id":str(sid),"season":season,"strategy":strategy,"round_index":int(cur.round_index),
              "target_date":date,"previous_roster":prev.selected_players,"recommended_roster":cur.selected_players,
              "player_transfers":transfers_players,"coach_changed":bool(coach_changed),"transfer_count_proxy":transfers,
              "old_roster_raw_player_score":old_player_score,"new_roster_raw_player_score":new_player_score,
              "old_coach_neutral_base_score":float(old_coach),"new_coach_neutral_base_score":float(new_coach),
              "gross_gain_vs_carry":float(delta),"score_scope":"raw player PDK + neutral-credit coach base; no captain/starter/bench multipliers"}
            for penalty in PENALTIES:
                row[f"net_gain_penalty_{penalty:g}"]=float(delta-transfers*penalty)
                row[f"switch_better_penalty_{penalty:g}"]=bool(delta-transfers*penalty>0)
            rows.append(row)
    detail=pd.DataFrame(rows)
    if detail.empty: raise RuntimeError("No sequential transitions could be evaluated.")
    metric_rows=[]
    for keys,g in detail.groupby(["season_id","season","strategy"],dropna=False):
        base={"season_id":keys[0],"season":keys[1],"strategy":keys[2],"transitions":len(g),
          "mean_transfer_count":float(g.transfer_count_proxy.mean()),"median_transfer_count":float(g.transfer_count_proxy.median()),
          "mean_gross_gain_vs_carry":float(g.gross_gain_vs_carry.mean()),
          "median_gross_gain_vs_carry":float(g.gross_gain_vs_carry.median()),
          "mean_gross_gain_per_transfer":float((g.gross_gain_vs_carry/g.transfer_count_proxy.replace(0,np.nan)).mean())}
        for p in PENALTIES:
            base[f"switch_better_rate_penalty_{p:g}"]=float(g[f"switch_better_penalty_{p:g}"].mean())
            base[f"mean_net_gain_penalty_{p:g}"]=float(g[f"net_gain_penalty_{p:g}"].mean())
        metric_rows.append(base)
    for strategy,g in detail.groupby("strategy"):
        base={"season_id":"POOLED","season":"2022-23–2024-25","strategy":strategy,"transitions":len(g),
          "mean_transfer_count":float(g.transfer_count_proxy.mean()),"median_transfer_count":float(g.transfer_count_proxy.median()),
          "mean_gross_gain_vs_carry":float(g.gross_gain_vs_carry.mean()),
          "median_gross_gain_vs_carry":float(g.gross_gain_vs_carry.median()),
          "mean_gross_gain_per_transfer":float((g.gross_gain_vs_carry/g.transfer_count_proxy.replace(0,np.nan)).mean())}
        for p in PENALTIES:
            base[f"switch_better_rate_penalty_{p:g}"]=float(g[f"switch_better_penalty_{p:g}"].mean())
            base[f"mean_net_gain_penalty_{p:g}"]=float(g[f"net_gain_penalty_{p:g}"].mean())
        metric_rows.append(base)
    metrics=pd.DataFrame(metric_rows)
    detail.to_csv(DETAIL,index=False); metrics.to_csv(METRICS,index=False)
    audit={"generated_at_utc":datetime.now(timezone.utc).isoformat(),"input_lineups":str(LINEUPS.relative_to(ROOT)),
      "penalty_scenarios":PENALTIES,"transition_rows":len(detail),"metrics":metrics.to_dict("records"),
      "production_changed":False,"method":"Sequential previous-round proxy roster vs current fresh optimized proxy roster; transfer count is 10 minus player overlap plus one if coach team changes.",
      "limitations":["Historical rosters/transfers are not archived; previous round's independent proxy lineup is used as carried roster.",
       "Current recommendation is not re-optimized under each penalty. This is an ex-post switch-value sensitivity, not a true strategy backtest.",
       "Player scores are unweighted raw PDK; lineup slot/captain multipliers cannot be reconstructed from saved lineup artifact.",
       "Coach score uses neutral-credit base score; historical coach CR and price multiplier are missing.",
       "Missing player target rows contribute zero within this restricted candidate proxy."]}
    AUDIT.write_text(json.dumps(audit,indent=2,ensure_ascii=False,default=str)+"\n",encoding="utf-8")
    report=["# Transfer-malus sensitivity — sequential lineup proxy","",f"Generated UTC: {audit['generated_at_utc']}","","## Method","",
      "For each strategy and historical round, compare the fresh independently optimized proxy lineup with the prior round's proxy lineup carried forward. Score both rosters using current-round raw player PDK plus neutral-credit coach base score. Subtract a transfer penalty of 0, 1, 2, 3.5, or 5 points for each newly selected player and one more if the coach changes.","",
      "## Results","",metrics.to_string(index=False),"","## Interpretation","",
      "This isolates the economic threshold at which a recommended roster change is worth its transfer cost. It does not estimate the exact optimal transfer strategy: the roster is not re-optimized under each penalty, player slot multipliers are omitted, and coach price multipliers are unavailable. Use it to bound sensitivity, not to alter the production penalty without a full lineup-level test.","",
      "## Limitations",""]+[f"- {x}" for x in audit["limitations"]]+["","## Artifacts","",str(DETAIL.relative_to(ROOT)),str(METRICS.relative_to(ROOT)),str(AUDIT.relative_to(ROOT)),""]
    REPORT.write_text("\n".join(report),encoding="utf-8")
    print(json.dumps({"status":"completed","transitions":len(detail),"metrics":metrics.to_dict("records"),
      "outputs":[str(p.relative_to(ROOT)) for p in (DETAIL,METRICS,AUDIT,REPORT)]},indent=2,default=str))
    return 0
if __name__=="__main__": raise SystemExit(main())
