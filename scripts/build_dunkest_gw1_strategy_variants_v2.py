#!/usr/bin/env python3
"""Create matched, immutable lineup variants from a single frozen pregame forecast."""
from __future__ import annotations
import hashlib, json, shutil
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from dunkest.config import Settings
from dunkest.pipeline.optimize import run_optimize

ROOT = Path(__file__).resolve().parents[1]
SOURCE_RUN_ID = "20261013T184846Z_21d331f5"
WORKSPACE = ROOT / "data/workspaces/dunkest_preflight_20261013"
OUT = ROOT / "reports/audit"
STEM = "dunkest_gw1_strategy_variants_20261013_v2"
VARIANTS = [
    {"key":"risk_adjusted_corrected_gain","objective":"risk_adjusted","gain_mode":"corrected","use_gain":True,"risk_lambda":0.10,"label":"Risk-adjusted + corrected plusvalenza"},
    {"key":"expected_value_corrected_gain","objective":"expected_value","gain_mode":"corrected","use_gain":True,"risk_lambda":0.10,"label":"Expected value + corrected plusvalenza"},
    {"key":"risk_adjusted_uncorrected_gain","objective":"risk_adjusted","gain_mode":"uncorrected","use_gain":True,"risk_lambda":0.10,"label":"Risk-adjusted + reconstructed uncorrected plusvalenza"},
    {"key":"expected_value_uncorrected_gain","objective":"expected_value","gain_mode":"uncorrected","use_gain":True,"risk_lambda":0.10,"label":"Expected value + reconstructed uncorrected plusvalenza"},
    {"key":"risk_adjusted_no_gain","objective":"risk_adjusted","gain_mode":"none","use_gain":False,"risk_lambda":0.10,"label":"Risk-adjusted, plusvalenza excluded"},
    {"key":"expected_value_no_gain","objective":"expected_value","gain_mode":"none","use_gain":False,"risk_lambda":0.10,"label":"Expected value, plusvalenza excluded"},
]

def sha256(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def lineup_frame(solutions, coaches):
    rows=[]
    for rank, sol in enumerate(solutions, start=1):
        sol.rank=rank
        match=coaches.loc[coaches["coach"].astype(str).eq(str(sol.coach))]
        cm={}
        if len(match)==1:
            q=match.iloc[0]
            cm={"coach_team":str(q.get("team","")),"coach_opponent":str(q.get("opponent","")),
                "coach_dunkest_turn":int(q["dunkest_turn"]) if pd.notna(q.get("dunkest_turn")) else None,
                "coach_nba_game_id":str(q.get("nba_game_id",""))}
        turns=sol.meta.get("turn_lineups",{})
        for _,p in sol.players.iterrows():
            name=str(p["player_name"])
            rows.append({"rank":rank,"player_name":p["player_name"],"team":p.get("team"),
                "opponent":p.get("opponent"),"dunkest_turn":p.get("dunkest_turn"),"nba_game_id":p.get("nba_game_id"),
                "slot":p.get("slot"),
                **{f"slot_turn_{t}":v.get("slots",{}).get(name) for t,v in turns.items()},
                **{f"module_turn_{t}":v.get("module") for t,v in turns.items()},
                "expected_team_pdk":sol.expected_team_pdk,"expected_player_pdk":sol.expected_player_pdk,
                "expected_coach_pdk":sol.expected_coach_pdk,"raw_team_pdk":sol.raw_team_pdk,
                "transfer_malus":sol.transfer_malus,"p10_team":sol.p10_team,"p50_team":sol.p50_team,
                "p90_team":sol.p90_team,"budget_used":sol.budget_used,"module":sol.module,
                "num_transfers":sol.num_transfers,"captain":sol.captain,"coach":sol.coach,**cm,
                "solver":sol.meta.get("solver",{}).get("solver"),
                "solver_status":sol.meta.get("solver",{}).get("status"),
                "solver_time_seconds":sol.meta.get("solver",{}).get("solve_time_seconds"),
                "solver_objective_value":sol.meta.get("solver",{}).get("objective_value")})
    return pd.DataFrame(rows)

def main():
    source=ROOT/"data/predictions"/SOURCE_RUN_ID
    if not (source/"manifest.json").is_file(): raise SystemExit(f"Missing frozen run: {source}")
    for p in [OUT/f"{STEM}.json",OUT/f"{STEM}.md",OUT/f"{STEM}_lineups.csv"]:
        if p.exists(): raise SystemExit(f"Refusing to overwrite: {p}")
    manifest=json.loads((source/"manifest.json").read_text())
    cfg=manifest["configuration"]
    if cfg.get("optimizer_objective")!="risk_adjusted" or abs(float(cfg.get("risk_lambda",-1))-0.10)>1e-9:
        raise SystemExit("Source run is not risk_adjusted with lambda=0.10.")
    run_time=pd.to_datetime(manifest.get("timestamp"),utc=True,errors="coerce")
    maps=[e for e in manifest["pre_match_snapshot"]["files"] if e["path"].startswith("dunkest_fixture_mapping_")]
    if not maps: raise SystemExit("Frozen run has no fixture mapping.")
    mp=source/"pre_match_snapshot"/maps[0]["path"]
    if sha256(mp)!=maps[0]["sha256"]: raise SystemExit("Fixture mapping hash mismatch.")
    mapping=pd.read_parquet(mp)
    gw=int(cfg["target_gameweek"])
    mapping=mapping.loc[pd.to_numeric(mapping["dunkest_gameweek"],errors="coerce").eq(gw)]
    kicks=pd.to_datetime(mapping["game_datetime_utc"],utc=True,errors="coerce")
    if mapping.empty or kicks.isna().any() or pd.isna(run_time) or run_time>=kicks.min():
        raise SystemExit("Source run is not strictly pre-kickoff.")
    for e in manifest["pre_match_snapshot"]["files"]:
        p=source/"pre_match_snapshot"/e["path"]
        if not p.is_file() or sha256(p)!=e["sha256"]: raise SystemExit(f"Snapshot hash mismatch: {e['path']}")
    players0=pd.read_parquet(source/"predictions.parquet")
    coaches=pd.read_parquet(source/"coach_predictions.parquet")
    base_cfg=dict(cfg); base_cfg["data_dir"]=str(WORKSPACE)
    variants_root=WORKSPACE/"predictions"/"strategy_variants_20261013_v2"
    variants_root.mkdir(parents=True,exist_ok=True)
    summary=[]
    for v in VARIANTS:
        run_id=f"{SOURCE_RUN_ID}__{v['key']}"
        dest=variants_root/run_id
        if dest.exists(): raise SystemExit(f"Refusing to overwrite variant: {dest}")
        shutil.copytree(source,dest)
        players=players0.copy()
        if v["gain_mode"] == "none":
            players["expected_plusvalenza"]=0.0
        elif v["gain_mode"] == "uncorrected":
            # Reconstruct the pre-calibration expectation from the archived,
            # already-quantized forecast. This is an ablation approximation:
            # CR-grid quantization means it is not bit-identical to refitting
            # the former model on raw pre-calibration samples.
            correction=pd.to_numeric(players.get("plusvalenza_bias_correction_cr",0.0),errors="coerce")
            players["expected_plusvalenza"]=pd.to_numeric(players["expected_plusvalenza"],errors="coerce").fillna(0.0)-correction.fillna(0.0) if isinstance(correction,pd.Series) else pd.to_numeric(players["expected_plusvalenza"],errors="coerce").fillna(0.0)-float(correction)
        cfg2=dict(base_cfg); cfg2["optimizer_objective"]=v["objective"]; cfg2["risk_lambda"]=v["risk_lambda"]
        settings=Settings.from_yaml(ROOT/"config/season_opener.yaml",**cfg2)
        solutions=run_optimize(settings,players,coaches)
        if len(solutions)!=int(cfg.get("optimizer_top_k",3)): raise RuntimeError(f"Wrong lineup count: {v['key']}")
        lf=lineup_frame(solutions,coaches)
        if lf.groupby("rank")["player_name"].nunique().ne(10).any(): raise RuntimeError(f"Invalid roster: {v['key']}")
        lf.to_parquet(dest/"lineups.parquet",index=False)
        m=dict(manifest); m["run_id"]=run_id
        m["strategy_variant"]={**v,"source_run_id":SOURCE_RUN_ID,"forecasts_unchanged":True,
          "snapshot_sha256_verified":True,"notes":(
            "uses the corrected archived expected_plusvalenza forecast" if v["gain_mode"] == "corrected" else
            "reconstructs uncorrected expected_plusvalenza by subtracting the stored CR bias correction; approximate due to 0.1-CR quantization" if v["gain_mode"] == "uncorrected" else
            "sets expected_plusvalenza=0 only in the in-memory optimizer input"
          )}
        m["configuration"]=dict(cfg); m["configuration"]["data_dir"]=str(WORKSPACE)
        m["configuration"]["optimizer_objective"]=v["objective"]; m["configuration"]["risk_lambda"]=v["risk_lambda"]
        m["optimizer_objective"]=v["objective"]; m["risk_lambda"]=v["risk_lambda"]
        m["pre_match_snapshot"]=dict(manifest["pre_match_snapshot"]); m["pre_match_snapshot"]["path"]=str(dest/"pre_match_snapshot")
        (dest/"manifest.json").write_text(json.dumps(m,indent=2,ensure_ascii=False)+"\n")
        agg=lf.groupby("rank",as_index=False).agg(expected_team_pdk=("expected_team_pdk","first"),
          p10_team=("p10_team","first"),p50_team=("p50_team","first"),p90_team=("p90_team","first"),
          coach=("coach","first"),captain=("captain","first"),
          players=("player_name",lambda s:"; ".join(sorted(s.astype(str)))))
        for _,r in agg.iterrows():
            summary.append({"variant":v["key"],"label":v["label"],"run_id":run_id,**r.to_dict()})
    sdf=pd.DataFrame(summary)
    sdf.to_csv(OUT/f"{STEM}_lineups.csv",index=False)
    audit={"generated_at_utc":datetime.now(timezone.utc).isoformat(),"source_run_id":SOURCE_RUN_ID,
      "source_run_timestamp_utc":run_time.isoformat(),"season_id":str(cfg["season_id"]),"gameweek":gw,
      "mapped_fixtures":int(mapping["nba_game_id"].astype(str).nunique()),"player_forecast_rows":len(players0),
      "coach_forecast_rows":len(coaches),"snapshot_files_hash_verified":len(manifest["pre_match_snapshot"]["files"]),
      "variants":VARIANTS,"variant_runs_root":str(variants_root),
      "comparison_policy":"Identical frozen player/coach forecasts and snapshot bytes across variants. Only objective/risk penalty and whether corrected expected plusvalenza enters optimization differ. No actual outcomes read.",
       "limitation":"Uncorrected plusvalenza is reconstructed by subtracting the stored CR bias correction from the archived corrected expectation; because the output was quantized to 0.1 CR, this is an ablation approximation, not an exact refit of the legacy model."}
    (OUT/f"{STEM}.json").write_text(json.dumps(audit,indent=2,ensure_ascii=False)+"\n")
    lines=["# Frozen GW1 strategy variants — 2026/27","",f"- Source run: {SOURCE_RUN_ID}",
      f"- Frozen at UTC: {run_time.isoformat()}",f"- Mapped fixtures: {audit['mapped_fixtures']}",
      f"- Player forecasts: {len(players0)}; coach forecasts: {len(coaches)}",
      f"- Snapshot hashes verified: {audit['snapshot_files_hash_verified']}",
      "- Safe post-game retrieval cutoff: 2026-10-23 12:00 UTC","",
      "## Design","",
       "Six matched variants use the same frozen forecasts: expected-value vs risk-adjusted (lambda=0.10), with corrected plusvalenza, reconstructed uncorrected plusvalenza, or plusvalenza excluded. Forecast files and pregame snapshot bytes are retained unchanged; each variant has its own lineups and manifest.",
       "The no-gain variants set expected_plusvalenza to zero only in the in-memory optimizer input. The uncorrected variants subtract plusvalenza_bias_correction_cr from expected_plusvalenza; due to 0.1-CR quantization this is an approximate ablation. Actual outcomes are not read during generation.","",
      "## Frozen lineup comparison","",sdf[["variant","rank","expected_team_pdk","p10_team","p50_team","p90_team","coach","captain","players"]].to_string(index=False),
      "","## Interpretation","",audit["limitation"],
      "Score only after the safe cutoff with official player and coach outcomes linked to frozen fixture IDs. Missing outcomes must never be replaced with zero.","",
      f"Artifacts: reports/audit/{STEM}.json and reports/audit/{STEM}_lineups.csv",""]
    (OUT/f"{STEM}.md").write_text("\n".join(lines),encoding="utf-8")
    print(json.dumps({"status":"ready_for_prospective_scoring","variant_runs":[str(variants_root/f"{SOURCE_RUN_ID}__{v['key']}") for v in VARIANTS],
      "mapped_fixtures":audit["mapped_fixtures"],"snapshot_files_hash_verified":len(manifest["pre_match_snapshot"]["files"]),
      "outputs":[str(OUT/f"{STEM}.md"),str(OUT/f"{STEM}.json"),str(OUT/f"{STEM}_lineups.csv")]},indent=2))
if __name__=="__main__": main()
