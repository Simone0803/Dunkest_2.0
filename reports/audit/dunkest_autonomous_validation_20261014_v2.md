# Dunkest autonomous validation — 2026-10-14 v2

## Scope

Validation performed after the lineup scraper, hard-out identity resolution, opening-market prior, and plusvalenza-history completeness changes. No historical pre-lock inputs were reconstructed and no model winner was declared from uncertified backtests.

## Current Lineups capture

- Capture timestamp: `2026-10-14T17:09:20.994139+00:00`.
- Market: 563 players and 30 coaches (593 rows total).
- All 16 fixtures were scanned to the bottom of the fixture list.
- Target-fixture coverage by Dunkest turn: turn 1 = 3/3, turn 2 = 11/11, turn 3 = 2/2; all three turn captures report complete.
- Turn annotations: 30 starters and 71 bench labels for turn 1; 110 starters and 287 bench labels for turn 2; 10 starters and 22 bench labels for turn 3.
- The existing market was replaced only after the complete capture/merge succeeded.

### Scraper caveats retained for follow-up

- Five of eight labels in the unavailable panel were not matched with sufficient certainty: `learn more`, `path to success`, `sharpe`, `miller`, `ingram`. The ambiguous surnames are not used to exclude players without a unique identity. A follow-up parser change now rejects the two known UI-copy labels (`learn more`, `path to success`) before identity matching; that change is covered by a regression test but has not yet been exercised by another live browser capture.
- Lineups eligibility observations for LAC conflict across captures. The previously verified positive status is preserved and the conflicting raw observations are retained; do not overwrite the status without corroborating evidence.
- The latest scrape records 4 unavailable-panel labels in the merged `INDISPONIBILI` group and 3 explicit OUT matches in each turn's capture log. Manual injury overrides and official injury inputs remain separate evidence sources.

## Latest generated opening run

Artifact directory: `data/predictions/20261014T171122Z_11fa7d2a`.

| Lineup | Expected team PDK | P10–P90 | Coach | Budget | Solver |
|---|---:|---:|---|---:|---|
| 1 | 243.30 | 167.8–317.9 | Micah Nori | 95.0 CR | Optimal |
| 2 | 237.72 | 165.2–314.4 | Sean Sweeney | 95.0 CR | Optimal |
| 3 | 235.15 | 166.1–313.8 | Tuomas Iisalo | 95.0 CR | Optimal |

All three rosters contain 10 distinct players and use the full 95 CR budget. The coach projection table reports verified matchup projections for all 30 coaches. These are model projections, not certified realized scores.

## Plusvalenza training coverage

The completeness gate requires at least 28 distinct NBA teams per season. It excludes the incomplete cached seasons 2016, 2022, and 2025 from the production fit.

| Season ID | Rows in source archive | Distinct teams | Production fit |
|---|---:|---:|---|
| 13 | 18,927 | 30 | Included |
| 16 | 435 | 2 | Excluded |
| 19 | 19,590 | 30 | Included |
| 22 | 519 | 2 | Excluded |
| 25 | 1,858 | 2 | Excluded |

- Source rows: 41,329.
- Fit rows after completeness filtering: 36,582.
- Walk-forward validation rows: 7,294.
- Walk-forward MAE: 0.06861 CR.
- Training-window mean baseline MAE: 0.17778 CR.

These metrics are valid only for the filtered cached sample and its current validation design; they do not certify the full Dunkest historical market or a lineup strategy.

## Automated checks

- Full test suite: **377 passed** (`PYTHONPATH=src ./.venv/bin/python -W error::DeprecationWarning -m pytest -q`).
- `git diff --check`: passed.
- Regression coverage includes repeated market-response deduplication, shared-surname resolution, injury identity matching, the plusvalenza season-completeness gate, and manifest provenance.

## Remaining blockers

The strict historical lineup backtest remains **not ready**. The latest manifest fails the fixture-mapping freshness check, historical roster/CR/injury/coach pre-lock snapshot checks, the combined pre-match-data check, and hash-verified fixture-linked actual-results check. The current October 14 capture is a present-day prospective snapshot and must not be substituted for historical pre-lock evidence.

Next steps:

1. Re-run the live capture once after the UI-copy filter to confirm the two false labels disappear while preserving all 16 fixtures and the existing market-protection rule.
2. Resolve the LAC eligibility conflict only with corroborating fixture evidence; keep ambiguous `Sharpe`, `Miller`, and `Ingram` labels unresolved unless a unique identity can be established.
3. Continue the strict pre-lock archive and realized-score work; do not tune against the frozen 2026-27 GW1 holdout before `2026-10-23 12:00 UTC`.
