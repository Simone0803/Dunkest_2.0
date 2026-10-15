# Confirmed row-level weekly-round contamination register — V1

Generated UTC: 2026-10-12T20:59:35.154584+00:00

- Total exact rows registered: **17**
- Rows in confirmed multi-player cluster: **15**
- Isolated exact boxscore + official PDK matches: **2**

## Registered rows by season ID

| Season ID | Rows |
|---:|---:|
| 13 | 1 |
| 5 | 16 |

## Policy

- Require an exact 15-field boxscore signature from a different NBA season and either membership in the confirmed multi-player cluster or a valid official-history PDK match at one-decimal precision.
- Do not quarantine isolated exact signatures when official PDK evidence disagrees or is invalid.
- Use exact season/week/round/player ID keys; do not remove all rows for a player.
- Raw source files and processed Parquet files are not edited by this register.

## Files

- CSV: reports/audit/dunkest_week_round_confirmed_contamination_rows_v1.csv
- JSON: reports/audit/dunkest_week_round_confirmed_contamination_rows_v1.json

## Reproducibility

    PYTHONPATH=src ./.venv/bin/python scripts/build_dunkest_week_round_confirmed_row_quarantine_v1.py
