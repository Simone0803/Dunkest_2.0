# Historical game-linked rows v3 — date-assisted exact-signature linkage

Generated UTC: 2026-10-13T12:10:08.690173+00:00

## Coverage

- Base rows: **93,785**.
- Independently date-ready rounds: **778/779**.
- Unresolved single-game rows considered: **475**.
- Uniquely resolved using exact PDK + 17-stat signature: **441**.
- Of those, official NBA team differs from source team: **36**.
- Remaining unresolved among considered rows: **34**.

### Remaining unresolved statuses

| Status | Rows |
|---|---:|
| no_unique_exact_candidate | 32 |
| date_candidates_but_signature_mismatch | 2 |

## Independent integrity check

The v3 dataset is rebuilt from the original player-week-round parquet as the source of truth; v2 linkage metadata is joined by `(season, week, round, player ID)`, not row position. All 441 date-assisted rows were rechecked against the raw source: **zero mismatches** across PDK and the 17 box-score fields. All 441 also resolve to an official-valid game matching the persisted date, NBA team, game ID, PDK, and all 17 statistics. The original observed `gameValidForDunkest` field is preserved; date-assisted validity is established by the verified candidate and the separate v3 status.

The persisted-dataset walk-forward V9 reproduces V8 predictions exactly within floating-point tolerance: 285,304/285,304 prediction rows match, with maximum absolute prediction difference `2.85e-14`. This verifies reproducibility, not a predictive improvement.

## Method and guardrails

For rows unresolved by v2, only gp=1 rows on an independently inferred round date (>=10 unique links and >=75% date agreement) are considered. A link is accepted only if one unique official-valid candidate matches rounded source PDK and all 17 box-score fields. Source team is not used to select the candidate.

This is a separate experimental dataset. Original source team/name/PDK fields and v2 linkage status are preserved. Date-assisted links are marked in separate fields and have an explicit `link_status_v3`; ambiguous or unmatched rows are not imputed. The round date is derived from other unique historical links, but the resulting mapping remains retrospective outcome linkage and does not provide a complete pre-lock market snapshot.

## Artifacts
- Parquet: `data/processed/dunkest_historical_game_linked_rows_20261013_v3_date_assisted.parquet`
- Date-assisted rows: `reports/audit/dunkest_historical_game_linked_rows_20261013_v3_date_assisted_resolved_rows.csv`
- Unresolved considered rows: `reports/audit/dunkest_historical_game_linked_rows_20261013_v3_date_assisted_unresolved_rows.csv`
- Round-date evidence: `reports/audit/dunkest_historical_game_linked_rows_20261013_v3_date_assisted_round_dates.csv`
- JSON: `reports/audit/dunkest_historical_game_linked_rows_20261013_v3_date_assisted.json`

## Guardrails

- Experimental dataset only; no production code/config or labels changed.
- Unresolved and ambiguous candidates remain unresolved.
- Missing game rows are not interpreted as DNP or OUT.
- Historical outcome linkage is not a pre-lock roster/availability snapshot.
- Frozen 2026/27 GW1 holdout remains untouched until 2026-10-23T12:00:00Z.
