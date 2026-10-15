# Dunkest stats endpoint scope audit (v1)

Generated UTC: 2026-10-12T15:00:41.691684+00:00

## Scope requests

| Scope | HTTP | Rows | Payload hash (16) |
|---|---:|---:|---|
| `s5_w43_r2_avg_minimal` | 200 | 118 | `dc4c525d96782a78` |
| `s5_w43_r2_avg_full` | 200 | 118 | `dc4c525d96782a78` |
| `s7_w43_r2_avg_minimal` | 200 | 143 | `e878ba987c1a3fa9` |
| `s5_w43_r2_tot_minimal` | 200 | 118 | `7ad203fdaa7f66c1` |
| `s5_w43_r2_tot_full` | 200 | 118 | `7ad203fdaa7f66c1` |
| `s7_w43_r2_tot_minimal` | 200 | 143 | `2b46847bfc6d133b` |
| `s5_w40_r3_tot` | 200 | 31 | `d334c4e9ce9e7cc2` |
| `s7_w40_r3_tot` | 200 | 49 | `96e9d363ac9bf41f` |
| `s5_w53_r2_tot` | 200 | 116 | `fce95ceab4ffaee0` |
| `s7_w53_r2_tot` | 200 | 205 | `71d20daea4f7b915` |
| `s9_w20_r2_tot` | 200 | 214 | `21ee6a96b7a4770d` |
| `s13_w20_r1_tot` | 200 | 127 | `fdc05e8a5059486d` |
| `s19_w20_r1_tot` | 200 | 41 | `3cb89d33b9a04822` |
| `s9_w40_r2_tot` | 200 | 62 | `577a56a1abd8eac7` |

## Request-variant parity

| Minimal vs explicit filters | Same row count | Same exact payload |
|---|---|---|
| `s5_w43_r2_avg_minimal` vs `s5_w43_r2_avg_full` | True | True |
| `s5_w43_r2_tot_minimal` vs `s5_w43_r2_tot_full` | True | True |

## Interpretation

The `season_id` parameter is explicitly sent in every request. The audit compares minimal requests with the collector-style request including team/position/sort filters and queries the same week/round under related season IDs. Reproducing the PHI–MIN rows from the live endpoint means the issue is not caused solely by a local Parquet write. If minimal/full hashes match, the omitted optional filters are not responsible for that response. This does not reveal whether the backend has a stale cache, a faulty join, or another server-side season-scope issue.

The endpoint does not expose a public diagnostic explaining row provenance, so the exact root cause remains unverified. Keep the confirmed scope quarantined from clean derivatives and isolated rows review-only. No raw or production data changed.

JSON: `reports/audit/dunkest_stats_endpoint_scope_v1.json`
Scope CSV: `reports/audit/dunkest_stats_endpoint_scope_v1_scopes.csv`
Focus-row CSV: `reports/audit/dunkest_stats_endpoint_scope_v1_focus_rows.csv`
