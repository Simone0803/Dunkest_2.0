#!/usr/bin/env python3
"""Read-only audit of Dunkest historical PDK coverage and temporal leakage controls."""
from __future__ import annotations
import json, re
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROC, RAW, REPORTS = ROOT/"data/processed", ROOT/"data/raw", ROOT/"reports/audit"
STAMP = "20261013_v2"
OUT = {
 "json": REPORTS/f"dunkest_temporal_leakage_audit_{STAMP}.json",
 "md": REPORTS/f"dunkest_temporal_leakage_audit_{STAMP}.md",
 "csv": REPORTS/f"dunkest_temporal_leakage_season_coverage_{STAMP}.csv",
}
SEASONS = {"1":"2018-19","3":"2019-20","5":"2020-21","7":"2021-22","9":"2022-23","13":"2023-24","19":"2024-25","25":"2025-26"}
SOURCES = {
 "official_archive": PROC/"official_dunkest_player_games_2018-25_v1.parquet",
 "enriched_official_nba": PROC/"dunkest_nba_player_games_enriched_2018-25_v1.parquet",
 "training_v1": PROC/"dunkest_pdk_game_training_2020-25_v1.parquet",
 "training_v2": PROC/"dunkest_pdk_game_training_2020-25_v2.parquet",
 "training_v3": PROC/"dunkest_pdk_game_training_2020-26_v3.parquet",
 "matched_official_2025_26": PROC/"official_dunkest_vs_nba_matched_2025-26.parquet",
 "overlay_2025_26_v4": PROC/"player_game_logs_2025-26_official_pdk_overlay_v4.parquet",
 "nba_logs_2024_25": PROC/"player_game_logs_2024-25.parquet",
 "nba_logs_2025_26": PROC/"player_game_logs_2025-26.parquet",
 "team_logs_2018_26": PROC/"team_game_logs_2018-26_v1.parquet",
}
CODE_CHECKS = [
 ("rolling_shift", "src/dunkest/features/builder.py", r"numeric\(column\)\.shift\(1\)\.rolling", "PASS", "Player rolling features shift by one game row."),
 ("season_mean_shift", "src/dunkest/features/builder.py", r"pdk\.expanding\(min_periods=1\)\.mean\(\)\.shift\(1\)", "PASS", "Season mean excludes the current game."),
 ("team_prior_rows", "src/dunkest/features/builder.py", r"hist\s*=\s*g\.iloc\[:i\]", "PASS", "Team context uses earlier rows only."),
 ("prematch_denylist", "src/dunkest/data/temporal.py", r"def validate_prematch_features", "PASS", "Post-match columns are explicitly forbidden as features."),
 ("historical_pdk_asof", "src/dunkest/models/historical_pdk.py", r"game_date.*\.lt\(target_date\)", "PASS", "Historical PDK history is filtered strictly before target date."),
 ("historical_nba_asof", "src/dunkest/models/historical_pdk.py", r"_date.*\.lt\(target_date\)", "PASS", "NBA history is filtered strictly before target date."),
 ("nba_join_no_exact_match", "scripts/build_dunkest_pdk_training_dataset_v3.py", r"allow_exact_matches=False", "PASS", "NBA as-of join excludes target-date records."),
 ("fold_local_imputation", "src/dunkest/models/predictor.py", r"fold_X, fold_medians = _fit_matrix\(df\.loc\[train_idx\], cols\)", "PASS", "OOF imputation is fit on each training fold, then applied to validation."),
 ("proxy_fallback", "src/dunkest/models/predictor.py", r"if count >= MIN_OFFICIAL_PDK_TRAINING_ROWS", "REVIEW", "Auto target mode falls back to proxy PDK if official labels are insufficient."),
 ("date_only_sort", "src/dunkest/features/builder.py", r'g = g\.sort_values\("GAME_DATE"\)', "REVIEW", "Rolling order has no explicit game/time tie-break; require unique player/date rows."),
 ("opening_training_scope", "src/dunkest/pipeline/train.py", r"prior_player_path = settings\.data_path / \"processed\" / f\"player_game_logs_\{settings\.feature_season\}\.parquet\"", "REVIEW", "GW1 production trainer loads only the configured prior-season NBA logs; this is not multi-season supervised training."),
 ("proxy_feature_official_target", "src/dunkest/data/dunkest/official_pdk.py", r"out\[OFFICIAL_LABEL\] = joined\[OFFICIAL_LABEL\]\.to_numpy\(\)", "REVIEW", "Official PDK labels are attached in a separate column; the existing PDK proxy column is retained, so production rolling PDK features may be proxy-derived even when labels are official."),
 ("historical_model_inference_blend", "src/dunkest/models/predictor.py", r"predict_historical_pdk", "INFO", "Historical multi-season model is an additional prediction path; inspect its blend weight and training artifact separately from the main season-only trainer."),
 ("holdout_caveat", "scripts/optimize_dunkest_pdk_model_walk_forward_20261012_v1.py", r"not globally untouched", "PASS", "Experiment documents that 2025/26 was already examined project-wide."),
]

def date_series(df):
 for c in ("game_date","gameDate","GAME_DATE","official_game_date"):
  if c in df: return pd.to_datetime(df[c], errors="coerce", utc=True).dt.tz_convert(None)
 return pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns]")

def summarize_source(name, path):
 if not path.exists(): return [{"source":name,"path":str(path.relative_to(ROOT)),"status":"missing"}]
 df=pd.read_parquet(path)
 sc=next((c for c in ("season_label","season_id","SEASON_YEAR","SEASON") if c in df),None)
 season=df[sc].astype("string").str.replace(r"\.0$","",regex=True) if sc else pd.Series("unknown",index=df.index)
 if sc=="season_id": season=season.map(lambda x:SEASONS.get(str(x),str(x)))
 season=season.fillna("unknown")
 dates=date_series(df)
 pid=next((c for c in ("dunkest_player_id","_requested_player_id","PLAYER_ID","Player_ID") if c in df),None)
 gid=next((c for c in ("gameId","game_id_dunkest","GAME_ID","Game_ID") if c in df),None)
 target_col=next((c for c in ("target_pdk","pdk_official","PDK_OFFICIAL_VALID","pdk","PDK") if c in df),None)
 valid_col="gameValidForDunkest" if "gameValidForDunkest" in df else None
 records=[]
 for label, part in df.groupby(season,dropna=False,sort=True):
  d=dates.loc[part.index]
  y=pd.to_numeric(part[target_col],errors="coerce") if target_col else pd.Series(np.nan,index=part.index)
  valid=part[valid_col].astype("string").str.lower().map({"true":True,"false":False,"1":True,"0":False}) if valid_col else pd.Series(pd.NA,index=part.index)
  dup_pg=int(part.duplicated([pid,gid]).sum()) if pid and gid else None
  dup_date=int(pd.DataFrame({"p":part[pid].astype("string"),"d":d}).duplicated(["p","d"]).sum()) if pid else None
  records.append({"source":name,"path":str(path.relative_to(ROOT)),"season":str(label),"rows":len(part),
   "unique_players":int(part[pid].nunique()) if pid else None,"min_date":d.min().isoformat() if d.notna().any() else None,
   "max_date":d.max().isoformat() if d.notna().any() else None,"target_column":target_col,
   "target_nonnull":int(y.notna().sum()) if target_col else None,"target_missing":int(y.isna().sum()) if target_col else None,
   "valid_true":int(valid.eq(True).sum()) if valid_col else None,"valid_false":int(valid.eq(False).sum()) if valid_col else None,
   "valid_unknown":int(valid.isna().sum()) if valid_col else None,"duplicate_player_game_keys":dup_pg,
   "duplicate_player_dates":dup_date,"columns":len(df.columns)})
 return records

def training_integrity(path):
 out={"path":str(path.relative_to(ROOT)),"exists":path.exists()}
 if not path.exists(): return out
 df=pd.read_parquet(path); out.update(rows=len(df),columns=len(df.columns))
 need={"season_id","game_date","dunkest_player_id","gameId","target_pdk","lag1_pdk"}
 if not need.issubset(df): out["missing_columns"]=sorted(need-set(df)); return out
 df["season_id"]=df.season_id.astype("string")
 df["game_date"]=pd.to_datetime(df.game_date,errors="coerce",utc=True).dt.tz_convert(None)
 df["target_pdk"]=pd.to_numeric(df.target_pdk,errors="coerce"); df["lag1_pdk"]=pd.to_numeric(df.lag1_pdk,errors="coerce")
 out["missing_keys_or_target"]=int(df[["season_id","game_date","dunkest_player_id","gameId","target_pdk"]].isna().any(axis=1).sum())
 out["duplicate_season_player_game"]=int(df.duplicated(["season_id","dunkest_player_id","gameId"]).sum())
 out["duplicate_player_dates"]=int(df.duplicated(["dunkest_player_id","game_date"]).sum())
 ordered=df.sort_values(["game_date","season_id","dunkest_player_id","gameId"],kind="stable")
 expected=ordered.groupby("dunkest_player_id",sort=False).target_pdk.shift(1); lag=ordered.lag1_pdk
 both=expected.notna() & lag.notna()
 out["lag1_value_mismatches"]=int(((expected[both]-lag[both]).abs()>1e-9).sum())
 out["lag1_missingness_mismatches"]=int((expected.isna()!=lag.isna()).sum())
 if "prior_nba_history_game_date" in df:
  prior=pd.to_datetime(df.prior_nba_history_game_date,errors="coerce",utc=True).dt.tz_convert(None)
  out["nba_history_same_or_after_target"]=int((prior.notna() & prior.ge(df.game_date)).sum())
  out["nba_history_missing"]=int(prior.isna().sum())
 out["season_rows"]={SEASONS.get(str(s),str(s)):int(n) for s,n in df.season_id.value_counts().sort_index().items()}
 return out

def main():
 REPORTS.mkdir(parents=True,exist_ok=True)
 if any(p.exists() for p in OUT.values()): raise SystemExit("Refusing to overwrite versioned audit outputs.")
 coverage=[]
 for name,path in SOURCES.items(): coverage.extend(summarize_source(name,path))
 hist=RAW/"nba_historical_logs_2018-25_v1"
 if hist.exists():
  for path in sorted(hist.glob("*.parquet")): coverage.extend(summarize_source("raw_nba_"+path.stem.replace("nba_player_game_logs_",""),path))
 cov=pd.DataFrame(coverage); cov.to_csv(OUT["csv"],index=False)
 training={n:training_integrity(SOURCES[n]) for n in ("training_v1","training_v2","training_v3")}
 checks=[]
 for name,rel,pattern,status,detail in CODE_CHECKS:
  p=ROOT/rel; content=p.read_text(encoding="utf-8",errors="replace") if p.exists() else ""
  matches=list(re.finditer(pattern,content,flags=re.I|re.M))
  checks.append({"check":name,"file":rel,"status":status if matches else "NOT_FOUND","line_numbers":[content.count("\n",0,m.start())+1 for m in matches[:5]],"interpretation":detail})
 archive=[r for r in coverage if r.get("source")=="official_archive"]
 older=[r for r in archive if r.get("season") in ("2018-19","2019-20")]
 findings=[
  {"severity":"BLOCKER_FOR_REQUESTED_TRAINING_RANGE","title":"No certified supervised PDK labels for 2018/19 and 2019/20","detail":"The dated official archive has rows for these seasons, but all recorded gameValidForDunkest flags are false. Do not use them as target labels without independent source certification; verified NBA boxscores can still be prior feature history.","evidence":older},
  {"severity":"HIGH","title":"2025/26 is not a globally untouched holdout","detail":"The season has already been examined in prior model comparison, tuning, calibration and error-slice experiments. It can remain a walk-forward fold but must not be called a project-wide untouched final holdout."},
  {"severity":"HIGH","title":"Auto target mode can fall back to proxy PDK","detail":"Production selects official labels only when at least 1,000 finite labels exist; otherwise it silently chooses target_pdk. Official-target experiments should assert label provenance and fail closed."},
  {"severity":"MEDIUM","title":"Rolling features sort only by date","detail":"The production rolling builder sorts by GAME_DATE without a game/time tie-break. shift(1) is safe only when each player has unique dates; dataset duplicate counts are reported below."},
  {"severity":"HIGH","title":"The main GW1 trainer is still prior-season-only","detail":"The production run_train opening-round branch loads player_game_logs_<feature_season>.parquet and builds its primary training matrix from that season. The multi-season V3 dataset is used by a separate historical model path, not as the main supervised training matrix. Therefore the requested 2018/19–2024/25 multi-season training policy is not yet the production trainer's policy."},
  {"severity":"MEDIUM","title":"Official labels and rolling PDK features have different provenance","detail":"attach_official_pdk_labels adds PDK_OFFICIAL_VALID without replacing the original PDK column. build_feature_matrix derives target_pdk from PDK and rolling PDK features from that same column; when train_models selects target_pdk_official as y, the labels are official but PDK-history predictors may remain proxy-derived. This is not future leakage, but it is a feature/target provenance mismatch worth measuring before integration."},
  {"severity":"INFO","title":"Historical certified target set spans 2020/21 onward","detail":"The existing V3 dataset has 112,178 rows from 2020/21–2025/26; 93,766 rows are from 2020/21–2024/25. Earlier two seasons can provide verified NBA history, not certified PDK supervised labels."},
 ]
 report={"created_utc":datetime.now(timezone.utc).isoformat(),"scope":"Read-only audit; source datasets, production weights and frozen prospective run unchanged.",
  "coverage_csv":str(OUT["csv"].relative_to(ROOT)),"coverage_records":coverage,"training_integrity":training,"source_code_checks":checks,"findings":findings,
  "recommended_next_steps":[
   "For the requested 2018/19–2024/25 time span, use verified NBA boxscores from 2018/19–2019/20 as prior features, but train supervised PDK labels on certified 2020/21–2024/25 rows unless authoritative labels are recovered.",
   "Use expanding-origin folds inside 2020/21–2024/25 for model, feature, rookie and calibration selection; treat 2025/26 as a historical final fold with explicit project-wide holdout caveat.",
   "Make player/date uniqueness and lag-integrity checks hard assertions for each dataset build.",
   "For official-target experiments, require a minimum certified label count and fail closed rather than silently switching to proxy labels.",
   "Before production integration, decide whether the primary GW1 trainer should consume the multi-season certified PDK dataset; compare it in chronological folds against the existing prior-season-only trainer.",
   "Measure official-PDK history features versus proxy-PDK history features in walk-forward validation; do not assume that changing the historical features helps without out-of-sample evidence.",
   "Keep player PDK model validation separate from lineup/coach/transfer evaluation, which requires authentic pre-match snapshots and fixture-linked official results."
  ]}
 OUT["json"].write_text(json.dumps(report,indent=2,ensure_ascii=False,default=str),encoding="utf-8")
 lines=["# Dunkest temporal leakage and historical dataset audit — 2026-10-13","",f"Generated: {report['created_utc']}","","**Scope:** read-only audit. Production data, model weights and the frozen prospective run were not changed.","",
 "## Executive summary","","- The certified official PDK supervised dataset currently spans **2020/21–2025/26**, not 2018/19–2025/26.",
 "- The official archive has 2018/19 and 2019/20 rows, but their archived game-valid flags are false; these rows are not certified PDK targets.",
 "- The V3 training dataset has **112,178 rows** (2020/21–2025/26), including **93,766** rows through 2024/25.",
 "- 2025/26 has already been inspected by project experiments and is not globally untouched.",
 "- The main GW1 trainer is prior-season-only; the multi-season historical model is a separate path, not the main training matrix.",
 "- When official labels are selected, the production rolling PDK features still originate from the PDK proxy column unless separately replaced." ,
 "- Lagged rolling features, strict-before-date history filters and fold-local imputation are present; integrity metrics are reported below.","","## Findings",""]
 for f in findings:
  lines += [f"### [{f['severity']}] {f['title']}","",f["detail"],""]
  if f.get("evidence"):
   lines += ["| Season | Rows | Valid true | Valid false | Target non-null | Duplicate player-game |","|---|---:|---:|---:|---:|---:|"]
   for r in f["evidence"]: lines.append(f"| {r.get('season')} | {r.get('rows')} | {r.get('valid_true')} | {r.get('valid_false')} | {r.get('target_nonnull')} | {r.get('duplicate_player_game_keys')} |")
   lines.append("")
 lines += ["## Training dataset integrity","","| Dataset | Rows | Duplicate player-game | Duplicate player/date | Lag1 value mismatches | Lag1 missingness mismatches | NBA history at/after target |","|---|---:|---:|---:|---:|---:|---:|"]
 for name,r in training.items(): lines.append(f"| {name} | {r.get('rows','n/a')} | {r.get('duplicate_season_player_game','n/a')} | {r.get('duplicate_player_dates','n/a')} | {r.get('lag1_value_mismatches','n/a')} | {r.get('lag1_missingness_mismatches','n/a')} | {r.get('nba_history_same_or_after_target','n/a')} |")
 lines += ["","## Static temporal-control checks","","| Check | Status | File:line | Interpretation |","|---|---|---|---|"]
 for c in checks: lines.append(f"| {c['check']} | {c['status']} | {', '.join(c['file']+':'+str(n) for n in c['line_numbers']) or c['file']} | {c['interpretation']} |")
 lines += ["","## Recommended next steps",""]+[f"{i}. {x}" for i,x in enumerate(report["recommended_next_steps"],1)]
 lines += ["","## Artifacts","",f"- JSON: {OUT['json'].relative_to(ROOT)}",f"- CSV: {OUT['csv'].relative_to(ROOT)}",""]
 OUT["md"].write_text("\n".join(lines),encoding="utf-8")
 print("TEMPORAL AUDIT COMPLETE")
 print("JSON",OUT["json"]); print("MARKDOWN",OUT["md"]); print("CSV",OUT["csv"])
 print("\nTRAINING INTEGRITY")
 for n,r in training.items(): print(n,json.dumps({k:v for k,v in r.items() if k in ("rows","duplicate_season_player_game","duplicate_player_dates","lag1_value_mismatches","lag1_missingness_mismatches","nba_history_same_or_after_target","nba_history_missing","season_rows")},ensure_ascii=False))
 print("\nOFFICIAL ARCHIVE COVERAGE")
 print(cov.loc[cov.source.eq("official_archive"),["season","rows","valid_true","valid_false","target_nonnull","duplicate_player_game_keys","duplicate_player_dates"]].to_string(index=False))
 print("\nSOURCE CHECKS")
 print(pd.DataFrame(checks)[["check","status","line_numbers"]].to_string(index=False))
if __name__=="__main__": main()
