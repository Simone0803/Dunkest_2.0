#!/usr/bin/env python3
"""Build a versioned audit-only weekly-round derivative with exact row-level quarantine."""
from __future__ import annotations
import json, re
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/dunkest_history_v2"
PROCESSED = ROOT / "data/processed"
REPORTS = ROOT / "reports/audit"
STEM = "dunkest_week_round_audit_derivative_v2"
DERIVATIVE = PROCESSED / f"{STEM}.parquet"
MANIFEST_JSON = REPORTS / f"{STEM}.json"
MANIFEST_MD = REPORTS / f"{STEM}.md"
MANIFEST_CSV = REPORTS / f"{STEM}_files.csv"
ROW_REGISTER = REPORTS / "dunkest_week_round_confirmed_contamination_rows_v1.csv"

def normalize_id(value: object) -> str:
    text = str(value or "").strip()
    return text[:-2] if text.endswith(".0") else text

def main() -> None:
    for p in (DERIVATIVE, MANIFEST_JSON, MANIFEST_MD, MANIFEST_CSV):
        if p.exists():
            raise SystemExit(f"Refusing to overwrite existing output: {p}")
    qpath = REPORTS / "dunkest_week_round_quarantine_manifest_v2.json"
    exact_path = REPORTS / "dunkest_week_round_boxscore_signature_corroboration_v1.csv"
    if not qpath.exists() or not exact_path.exists() or not ROW_REGISTER.exists():
        raise SystemExit("Required quarantine, exact-signature, or row-level register is missing.")
    q = json.loads(qpath.read_text(encoding="utf-8"))
    quarantine = set(q.get("confirmed_quarantine_files", []))
    file_status = {x["source_file"]: x["evidence_status"] for x in q["manifest_rows"]}
    row_register = pd.read_csv(ROW_REGISTER, dtype={"dunkest_player_id": str, "source_season_id": str})
    exact = pd.read_csv(exact_path, dtype={"table_season_id": str, "nba_game_id": str})
    exact_isolated = exact[exact["cluster_status"].eq("isolated_exact_boxscore_signature_candidate")]
    row_candidates = {}
    for _, r in exact_isolated.iterrows():
        for field in ("source_file_avg", "source_file_tot"):
            source = "data/raw/dunkest_history_v2/" + str(r[field])
            row_candidates.setdefault(source, set()).add(str(r["player_name"]).casefold().strip())

    row_quarantine_keys = {
        (str(r.source_season_id), int(r.source_week), int(r.source_round), normalize_id(r.dunkest_player_id))
        for r in row_register.itertuples()
    }
    paths = sorted(RAW.glob("season_*_week_*_round_*_*.parquet"))
    if not paths:
        raise SystemExit(f"No source Parquets found under {RAW}")
    included, file_rows, excluded = [], [], []
    for path in paths:
        rel = path.relative_to(ROOT).as_posix()
        try:
            source_df = pd.read_parquet(path)
        except Exception as e:
            raise RuntimeError(f"Cannot read {rel}: {e}") from e
        source_rows = len(source_df)
        status = file_status.get(rel, "not_flagged_by_current_scan_not_certified")
        if rel in quarantine:
            excluded.append({"source_file": rel, "source_rows": source_rows,
                "status": "confirmed_cross_season_contamination_quarantine",
                "reason": "Source scope contains the confirmed 15-player PHI-MIN cross-season cluster."})
            file_rows.append({"source_file": rel, "source_rows": source_rows,
                "rows_removed_by_row_register": 0, "rows_retained": 0,
                "included_in_derivative": False, "source_audit_status": status,
                "exact_signature_candidate_players": "", "action": "Entire source file omitted by confirmed-scope quarantine"})
            continue

        df = source_df.copy()
        match = re.fullmatch(r"season_(\d+)_week_(\d+)_round_(\d+)_(avg|tot)\.parquet", path.name)
        if not match:
            raise ValueError(f"Unrecognized source filename: {path.name}")
        season, week, round_ = match.group(1), int(match.group(2)), int(match.group(3))
        if "id" not in df:
            raise ValueError(f"Missing player ID in {rel}")
        ids = df["id"].map(normalize_id)
        drop_mask = ids.map(lambda pid: (season, week, round_, pid) in row_quarantine_keys)
        removed_rows = df.loc[drop_mask].copy()
        removed_names = sorted(removed_rows["player_name"].astype(str).unique().tolist()) if "player_name" in removed_rows else []
        df = df.loc[~drop_mask].copy()

        names = df["player_name"].astype(str).str.casefold().str.strip() if "player_name" in df else pd.Series("", index=df.index)
        candidate_names = row_candidates.get(rel, set())
        df["source_file_audit"] = rel
        df["source_audit_status"] = status
        df["row_exact_full_boxscore_candidate"] = names.isin(candidate_names)
        df["row_exact_candidate_player"] = names.where(names.isin(candidate_names), "")
        df["audit_only_not_certified"] = True
        df["eligible_for_training_from_this_derivative"] = False
        included.append(df)
        file_rows.append({
            "source_file": rel, "source_rows": source_rows,
            "rows_removed_by_row_register": int(drop_mask.sum()), "rows_retained": len(df),
            "included_in_derivative": True, "source_audit_status": status,
            "exact_signature_candidate_players": "; ".join(sorted(candidate_names)),
            "row_quarantine_removed_players": "; ".join(removed_names),
            "action": "Retained with audit flags; exact high-confidence contamination rows removed; not certified for training",
        })
    if not included:
        raise SystemExit("No source files remain for derivative.")
    combined = pd.concat(included, ignore_index=True, sort=False)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(DERIVATIVE, index=False)
    file_manifest = pd.DataFrame(file_rows)
    file_manifest.to_csv(MANIFEST_CSV, index=False)
    removed_row_count = int(file_manifest["rows_removed_by_row_register"].sum())
    summary = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "artifact_type": "audit-only derivative; not a certified clean dataset",
        "source_directory": RAW.relative_to(ROOT).as_posix(),
        "derivative_path": DERIVATIVE.relative_to(ROOT).as_posix(),
        "file_manifest_csv": MANIFEST_CSV.relative_to(ROOT).as_posix(),
        "source_files_found": len(paths),
        "source_files_included": int(file_manifest["included_in_derivative"].sum()),
        "source_files_excluded_confirmed_quarantine": len(excluded),
        "whole_file_source_rows_excluded": sum(x["source_rows"] for x in excluded),
        "row_level_confirmed_rows_removed_from_included_files": removed_row_count,
        "derivative_rows": int(len(combined)),
        "source_bytes_read": sum(x.stat().st_size for x in paths),
        "derivative_bytes": DERIVATIVE.stat().st_size,
        "source_status_counts": file_manifest["source_audit_status"].value_counts().to_dict(),
        "isolated_exact_signature_candidates": len(exact_isolated),
        "candidate_rows_flagged_after_quarantine": int(combined["row_exact_full_boxscore_candidate"].sum()),
        "confirmed_quarantine_files": sorted(quarantine),
        "excluded_source_scopes": excluded,
        "row_level_register": ROW_REGISTER.relative_to(ROOT).as_posix(),
        "rules": [
            "No raw source file was changed.",
            "The two confirmed season-5/week-43/round-2 source files are omitted in full.",
            "Exact row-level register keys (season/week/round/player ID) are removed from other avg/tot source files.",
            "Isolated exact signatures with conflicting/invalid official PDK evidence remain flagged for review, not removed.",
            "Every retained row is marked audit_only_not_certified=True and eligible_for_training_from_this_derivative=False.",
            "Absence from current candidate scans is not evidence of clean season scope.",
        ],
        "not_for": ["training", "official target construction", "backtest labels", "production use"],
        "source_manifest": "reports/audit/dunkest_week_round_quarantine_manifest_v2.json",
    }
    MANIFEST_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    lines = [
        "# Weekly-round audit derivative — V2", "",
        f"Generated UTC: {summary['generated_utc']}", "",
        "## Purpose", "",
        "This is an audit-only derivative with provenance and review flags. It is not a certified clean dataset, official per-game target table, or training input.", "",
        "## Build summary", "",
        f"- Source files discovered: **{len(paths)}**",
        f"- Files retained: **{summary['source_files_included']}**",
        f"- Confirmed contaminated files excluded: **{len(excluded)}**",
        f"- Rows excluded with those files: **{summary['whole_file_source_rows_excluded']}**",
        f"- Additional exact high-confidence rows removed from retained files: **{removed_row_count}**",
        f"- Rows in derivative: **{len(combined)}**",
        f"- Remaining isolated candidate rows flagged: **{summary['candidate_rows_flagged_after_quarantine']}**", "",
        "## Safety rules", "",
        *[f"- {x}" for x in summary["rules"]], "",
        "## Important limitations", "",
        "The remaining rows are not certified as correctly season-scoped. Do not use this derivative for training, target construction, backtests, or production. The raw archive is unchanged.", "",
        f"Parquet: {DERIVATIVE.relative_to(ROOT)}",
        f"JSON: {MANIFEST_JSON.relative_to(ROOT)}",
        f"File manifest CSV: {MANIFEST_CSV.relative_to(ROOT)}", "",
        "Reproduce with: PYTHONPATH=src ./.venv/bin/python scripts/build_dunkest_week_round_audit_derivative_v2.py", "",
    ]
    MANIFEST_MD.write_text("\n".join(lines), encoding="utf-8")
    check = pd.read_parquet(DERIVATIVE, columns=["audit_only_not_certified", "eligible_for_training_from_this_derivative", "row_exact_full_boxscore_candidate"])
    assert len(check) == len(combined)
    assert check["audit_only_not_certified"].all() and (~check["eligible_for_training_from_this_derivative"]).all()
    assert int(check["row_exact_full_boxscore_candidate"].sum()) == summary["candidate_rows_flagged_after_quarantine"]
    print(json.dumps({
        "derivative": str(DERIVATIVE.relative_to(ROOT)),
        "files_found": len(paths), "files_retained": summary["source_files_included"],
        "whole_files_excluded": len(excluded), "whole_file_rows_excluded": summary["whole_file_source_rows_excluded"],
        "row_level_rows_removed": removed_row_count, "derivative_rows": len(combined),
        "remaining_candidate_rows_flagged": summary["candidate_rows_flagged_after_quarantine"],
        "safety_assertions": "PASS",
    }, indent=2))

if __name__ == "__main__":
    main()
