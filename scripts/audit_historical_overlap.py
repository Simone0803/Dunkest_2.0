
from pathlib import Path
import pandas as pd

raw_root = Path("data/raw/dunkest_history")
processed_root = Path("data/processed")

for season in ["13", "16", "19", "22"]:
    old_path = (
        processed_root /
        f"plusvalenza_history_nba_{season}_through_gw91_v3.parquet"
    )

    if not old_path.exists():
        print(f"\nStagione {season}: dataset precedente non trovato")
        continue

    old = pd.read_parquet(old_path).copy()
    old["gameweek"] = pd.to_numeric(old["gameweek"], errors="coerce")

    print(f"\n{'=' * 65}\nSTAGIONE {season}")
    print("Righe storico esistente:", len(old))

    for stats_type in ["avg", "tot"]:
        parts = []

        for path in sorted(raw_root.glob(f"season_{season}_*.parquet")):
            if not path.exists():
                continue

            df = pd.read_parquet(path)
            if df.empty or "source_stats_type" not in df:
                continue

            df = df[df["source_stats_type"] == stats_type].copy()
            if not df.empty:
                parts.append(df)

        if not parts:
            print(stats_type, ": nessun dato")
            continue

        new = pd.concat(parts, ignore_index=True)
        new["source_week"] = pd.to_numeric(
            new["source_week"], errors="coerce"
        )

        keys = ["player_name", "team_code", "role"]
        left = old.copy()
        right = new.copy()

        # La settimana fa parte della chiave temporale.
        left = left.rename(columns={"gameweek": "week"})
        right = right.rename(columns={"source_week": "week"})

        merged = left.merge(
            right,
            on=keys + ["week"],
            how="inner",
            suffixes=("_old", "_new"),
        )

        print(f"\n{stats_type}:")
        print("Righe API:", len(new))
        print("Abbinamenti con storico:", len(merged))

        if not merged.empty:
            for col in ["pdk", "plus", "cr", "min", "starter"]:
                a, b = f"{col}_old", f"{col}_new"
                if a not in merged or b not in merged:
                    continue

                x = pd.to_numeric(merged[a], errors="coerce")
                y = pd.to_numeric(merged[b], errors="coerce")
                valid = x.notna() & y.notna()

                equal = (x[valid] - y[valid]).abs() < 1e-9
                print(
                    f"  {col}: confrontabili={int(valid.sum())}, "
                    f"uguali={int(equal.sum())}, "
                    f"diversi={int((~equal).sum())}"
                )

            if "pdk_old" in merged and "pdk_new" in merged:
                diff = merged[
                    pd.to_numeric(merged["pdk_old"], errors="coerce")
                    .ne(pd.to_numeric(merged["pdk_new"], errors="coerce"))
                ]
                if not diff.empty:
                    print("  Esempi di PDK differenti:")
                    cols = [
                        c for c in [
                            "week", "player_name", "team_code",
                            "pdk_old", "pdk_new", "min_old", "min_new"
                        ] if c in diff.columns
                    ]
                    print(diff[cols].head(5).to_string(index=False))
