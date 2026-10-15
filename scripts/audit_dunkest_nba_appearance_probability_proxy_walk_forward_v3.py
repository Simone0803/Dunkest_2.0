#!/usr/bin/env python3
"""Walk-forward NBA appearance-continuity proxy, NOT Dunkest p_play."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score, average_precision_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
TEAM_PATH = ROOT / "data/processed/team_game_logs_2018-26_v1.parquet"
PLAYER_PATH = ROOT / "data/processed/dunkest_nba_player_games_enriched_2018-25_v1.parquet"
STEM = "dunkest_nba_appearance_probability_proxy_walk_forward_20261013_v3"
OUT = ROOT / "reports/audit"
PRED_PATH, METRICS_PATH = OUT / f"{STEM}_predictions.csv", OUT / f"{STEM}_metrics.csv"
AUDIT_PATH, REPORT_PATH = OUT / f"{STEM}.json", OUT / f"{STEM}.md"
TEST_SEASONS = ["2021-22", "2022-23", "2023-24", "2024-25"]
FEATURES = ["appearances_prev5", "appearance_rate_prev5", "appearances_prev10",
 "appearance_rate_prev10", "last_minutes", "mean_minutes_prev5", "starter_rate_prev5",
 "days_since_last_appearance", "team_game_index", "team_rest_days", "last_zero_minutes"]

def auc(y,p):
    return float(roc_auc_score(y,p)) if len(np.unique(y)) > 1 else float("nan")

def build_panel():
    tg=pd.read_parquet(TEAM_PATH); pg=pd.read_parquet(PLAYER_PATH)
    tg["season"]=tg["SEASON"].astype(str); tg["team"]=tg["TEAM_ABBREVIATION"].astype(str).str.upper().str.strip()
    tg["date"]=pd.to_datetime(tg["GAME_DATE"],errors="coerce"); tg["game_id"]=tg["GAME_ID"].astype(str)
    tg=tg.dropna(subset=["date"]).drop_duplicates(["season","team","game_id"])
    pg["season"]=pg["season_label"].astype(str); pg["team"]=pg["nba_TEAM_ABBREVIATION"].astype(str).str.upper().str.strip()
    pg["date"]=pd.to_datetime(pg["nba_NBA_GAME_DATE_PARSED"],errors="coerce"); pg["game_id"]=pg["nba_GAME_ID"].astype(str)
    pg["pid"]=pd.to_numeric(pg["nba_PLAYER_ID"],errors="coerce")
    pg["minutes"]=pd.to_numeric(pg["nba_MIN"],errors="coerce").fillna(0.0)
    pg["starter"]=pd.to_numeric(pg["starter"],errors="coerce").fillna(0.0)
    pg=pg.dropna(subset=["date","pid"]).drop_duplicates(["season","team","game_id","pid"])
    pg["played"]=(pg["minutes"]>0).astype(int)
    rows=[]; total_team_games=0
    for (season,team), games in tg.groupby(["season","team"],sort=False):
        games=games.sort_values(["date","game_id"]).reset_index(drop=True); total_team_games+=len(games)
        pteam=pg.loc[(pg.season==season)&(pg.team==team)]
        if pteam.empty: continue
        obs={}
        for gid,g in pteam.groupby("game_id",sort=False):
            obs[str(gid)]={int(r.pid):(int(r.played),float(r.minutes),float(r.starter)) for r in g.itertuples(index=False)}
        histories={}
        for idx,game in games.iterrows():
            date=pd.Timestamp(game.date); gid=str(game.game_id)
            if idx>0:
                team_rest=(date-pd.Timestamp(games.iloc[idx-1].date)).total_seconds()/86400.0
                for pid,hist in histories.items():
                    played_hist=[x for x in hist if x[3]>0]
                    if not played_hist: continue
                    last=played_hist[-1]
                    if idx-last[0]>5: continue
                    h5=[x for x in hist if idx-x[0]<=5]
                    h10=[x for x in hist if idx-x[0]<=10]
                    h5_played=[x for x in h5 if x[3]>0]
                    if not h5_played: continue
                    denom5=min(5,idx); denom10=min(10,idx)
                    count5=sum(x[3] for x in h5); count10=sum(x[3] for x in h10)
                    target=obs.get(gid,{}).get(pid)
                    y=int(target is not None and target[0]>0)
                    latest_row=hist[-1]
                    rows.append({"season":season,"team":team,"game_id":gid,"game_date":date.strftime("%Y-%m-%d"),
                      "player_id":pid,"target_played":y,"target_row_observed":target is not None,
                      "target_minutes":float(target[1]) if target is not None else np.nan,
                      "appearances_prev5":int(count5),"appearance_rate_prev5":count5/denom5,
                      "appearances_prev10":int(count10),"appearance_rate_prev10":count10/denom10,
                      "last_minutes":last[4],"mean_minutes_prev5":float(np.mean([x[4] for x in h5_played])),
                      "starter_rate_prev5":float(np.mean([x[5] for x in h5_played])),
                      "days_since_last_appearance":max(0.,(date-last[1]).total_seconds()/86400),
                      "team_game_index":idx+1,"team_rest_days":team_rest,
                      "last_zero_minutes":int(latest_row[4]<=0 and latest_row[0]>last[0])})
            # Add target-game rows only after features/labels are emitted.
            for pid,(played,minutes,starter) in obs.get(gid,{}).items():
                histories.setdefault(pid,[]).append((idx,date,gid,played,minutes,starter))
    panel=pd.DataFrame(rows)
    audit={"team_games":int(total_team_games),"player_game_rows":int(len(pg)),"candidate_game_rows":int(len(panel)),
      "target_observed_rows":int(panel.target_row_observed.sum()) if len(panel) else 0,
      "missing_target_rows_excluded_from_model":int((~panel.target_row_observed).sum()) if len(panel) else 0,
      "candidate_policy":"Player had a recorded same-team appearance in the previous five team games; not a complete pre-lock roster.",
      "label_policy":"Positive means an observed player-game row with positive minutes. Missing rows are proxy non-appearances, not verified DNP/OUT."}
    return panel,audit

def main():
    for p in (PRED_PATH,METRICS_PATH,AUDIT_PATH,REPORT_PATH):
        if p.exists(): raise SystemExit(f"Refusing to overwrite existing artifact: {p}")
    panel,audit=build_panel(); predictions=[]; metrics=[]
    for season in TEST_SEASONS:
        train=panel.loc[(panel.season<season)&panel.target_row_observed].copy(); test=panel.loc[(panel.season==season)&panel.target_row_observed].copy()
        if train.empty or test.empty or train.target_played.nunique()<2: continue
        model=Pipeline([("impute",SimpleImputer(strategy="median",add_indicator=True)),
          ("scale",StandardScaler()),("logistic",LogisticRegression(max_iter=1000,C=.5))])
        model.fit(train[FEATURES],train.target_played.astype(int))
        test["p_model"]=model.predict_proba(test[FEATURES])[:,1]
        test["p_prev5"]=test.appearance_rate_prev5.clip(0,1); test["p_prev10"]=test.appearance_rate_prev10.clip(0,1)
        test["p_constant90"]=.90; predictions.append(test)
        y=test.target_played.to_numpy(int)
        for name,probs in [("logistic_lagged_history",test.p_model),("baseline_previous_5_rate",test.p_prev5),
          ("baseline_previous_10_rate",test.p_prev10),("baseline_constant_90pct",test.p_constant90)]:
            p=np.clip(np.asarray(probs,float),1e-5,1-1e-5)
            metrics.append({"season":season,"method":name,"rows":len(y),"positive_rate":float(y.mean()),
              "brier":float(brier_score_loss(y,p)),"log_loss":float(log_loss(y,p,labels=[0,1])),
              "roc_auc":auc(y,p),"average_precision":float(average_precision_score(y,p)),
              "mean_predicted_probability":float(p.mean()),"observed_target_row_coverage":float(test.target_row_observed.mean())})
    pred=pd.concat(predictions,ignore_index=True) if predictions else pd.DataFrame(); met=pd.DataFrame(metrics)
    pred.to_csv(PRED_PATH,index=False); met.to_csv(METRICS_PATH,index=False)
    audit.update({"generated_at_utc":datetime.now(timezone.utc).isoformat(),"test_seasons":TEST_SEASONS,
      "features":FEATURES,"metrics":met.to_dict("records"),"production_changed":False,
      "interpretation":"Experimental NBA appearance-continuity probability evaluated only when a target player-game row is observed; missing rows are excluded, not treated as DNP/OUT.",
      "limitations":["The at-risk cohort is inferred from previous appearances, not the official roster at lock.",
       "Rows missing from the target archive are excluded; observed zero-minute rows remain negative labels, but an observed row is still not a verified pre-lock DNP/OUT snapshot.",
       "The target is appearance in one team's next NBA game, not availability across a Dunkest round.",
       "2025-26 and prospective 2026-27 labels are excluded."]})
    AUDIT_PATH.write_text(json.dumps(audit,indent=2,ensure_ascii=False,default=str)+"\n",encoding="utf-8")
    report=["# NBA appearance-continuity proxy — walk-forward audit","",f"Generated UTC: {audit['generated_at_utc']}","","## What this estimates","",
      "Probability of positive minutes in a team's next NBA game, conditional on a recorded appearance for that team within the previous five team games. It is not a Dunkest pre-lock p_play model.","",
      "## Walk-forward metrics","",met.to_string(index=False),"","## Cohort coverage","",
      f"- Team games: {audit['team_games']:,}",f"- Player-game rows: {audit['player_game_rows']:,}",
      f"- Candidate-game rows: {audit['candidate_game_rows']:,}",f"- Observed target rows: {audit['target_observed_rows']:,}",
      f"- Missing target rows excluded as unlabeled: {audit['missing_target_rows_excluded_from_model']:,}","","## Decision","",
      "This V3 evaluation avoids treating missing target rows as negative labels, at the cost of evaluating only the observed-row subset. Keep experimental: an observed zero-minute row is not a verified pre-lock DNP/OUT snapshot, and this remains NBA next-game continuity rather than Dunkest round availability.","",
      "## Artifacts","",str(PRED_PATH.relative_to(ROOT)),str(METRICS_PATH.relative_to(ROOT)),str(AUDIT_PATH.relative_to(ROOT)),""]
    REPORT_PATH.write_text("\n".join(report),encoding="utf-8")
    print(json.dumps({"status":"completed","predictions":len(pred),"metrics":met.to_dict("records"),
      "outputs":[str(p.relative_to(ROOT)) for p in (PRED_PATH,METRICS_PATH,AUDIT_PATH,REPORT_PATH)]},indent=2,default=str))
    return 0
if __name__=="__main__": raise SystemExit(main())
