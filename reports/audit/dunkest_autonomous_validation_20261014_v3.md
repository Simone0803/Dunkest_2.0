# Dunkest autonomous validation — 2026-10-14 v3

## Scope

This pass verifies the live Lineups parser fix, a complete three-turn capture, regenerated opening projections, and the current historical-backtest blocker. No historical pre-lock snapshots were reconstructed. No strategy is declared a winner from uncertified backtests.

## Live Lineups capture — verified after parser changes

- Merged capture timestamp: `2026-10-14T17:48:48.780847+00:00` (UTC).
- Market coverage: 563 player rows and 30 coach rows; 593 rows total.
- All 16 fixtures scanned, no failed fixtures; all target turns complete:
  - Turn 1: 3/3 fixtures.
  - Turn 2: 11/11 fixtures.
  - Turn 3: 2/2 fixtures.
- Merged annotation groups: 380 bench labels, 150 starters, 4 unavailable labels, 14 coach labels.
- The merged market contains none of the known English/Dutch UI/ad-copy strings checked by the regression audit.
- The capture script writes the merged market only after each per-turn capture passes coverage gates. A failed turn therefore leaves the previous merged market intact.

### Unavailable-label handling

- Explicit parser filters cover known UI strings, including `learn more`, `path to success`, and observed Dutch/English promotional fragments.
- A market-aware filter now excludes unscoped unavailable-panel text whose final surname token is absent from the player market. This suppresses rotating ad copy without suppressing ambiguous real surnames that exist in the market.
- The live capture no longer reports advertising fragments as unresolved player identities. The remaining recurring ambiguous label is `Sharpe` with unknown team context; it is not used to exclude a player without a unique identity.
- `Miller`, `Ingram`, and `Johnson` are only retained as ambiguous when actually observed and are not excluded without a reliable identity.
- LAC eligibility produced conflicting observations during individual captures. The existing verified positive flag was preserved, and the raw observations were retained; the merged manifest has no unresolved eligibility conflict. Do not overwrite this status without corroborating fixture evidence.
- Current merged unavailable rows: Max Strus (LAC), Yanic Konan Niederhauser (LAC), Richie Saunders (MEM), and Ariel Hukporti (PHI). Official injury inputs and manual overrides remain separate evidence sources.

## Latest opening run

Artifact directory: `data/predictions/20261014T175113Z_7c1f0803`.

| Lineup | Expected team PDK | P10–P90 | Coach | Budget | Solver |
|---|---:|---:|---|---:|---|
| 1 | 243.30 | 167.8–317.9 | Micah Nori | 95.0 CR | Optimal |
| 2 | 237.90 | 165.2–314.4 | Sean Sweeney | 95.0 CR | Optimal |
| 3 | 235.40 | 166.1–313.8 | Tuomas Iisalo | 95.0 CR | Optimal |

All three rosters contain 10 distinct players and use the full 95 CR budget. The coach projection table includes matchup projections for all 30 coaches. These are model projections, not certified realized scores.

The run reports 14 players excluded by availability/eligibility rules. The live market includes 4 explicit unavailable rows; other exclusions can come from the separate injury snapshot and configured overrides. Do not treat the market-panel count as the full injury-exclusion count.

## Plusvalenza training coverage

The completeness gate requires at least 28 distinct NBA teams per season. It excludes incomplete cached seasons 2016, 2022, and 2025 from the production fit.

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

These metrics describe only the filtered cached sample and current validation design; they do not certify the full historical Dunkest market or a lineup strategy.

## Automated checks

- Full test suite: **378 passed**.
- `git diff --check`: passed.
- Regression coverage includes market-response deduplication, shared-surname resolution, hard-out identity matching, plusvalenza season completeness, market-aware UI-noise filtering, and artifact provenance.

## Historical backtest blocker

The read-only archive inventory was refreshed at `reports/audit/dunkest_prelock_archive_inventory_20261013_v1.md`. Across the seven historical season IDs scanned (1, 3, 5, 7, 9, 13, 19), it found **zero season-specific files** for each required family: fixture mapping, player market, injury snapshot, coach market, player-week outcomes, and coach outcomes. Existing legacy files have ambiguous season/round identity or lack cutoff evidence and cannot be promoted to certified pre-lock snapshots.

Therefore, the strict historical lineup backtest remains **not ready**. Current prospective data must not be substituted for historical pre-lock evidence, and no post-hoc roster/CR/injury/coach reconstruction should be used to claim historical performance.

## Constraints and next work

1. The live scraper/UI-copy issue is resolved for the observed rotating ad labels and verified against a fresh full three-turn capture. Keep the market-aware filter and its regression test.
2. Keep ambiguous `Sharpe` unresolved unless a unique identity can be established. Preserve LAC's verified positive eligibility flag unless independent evidence resolves the conflict.
3. Continue the historical evidence pipeline: source genuine season/round-specific pre-lock market, injury, coach, fixture, and outcome artifacts, or clearly report that the historical lineup strategy cannot be certified with available evidence.
4. Do not tune against the frozen 2026-27 GW1 holdout before `2026-10-23 12:00 UTC`.
5. No commit or push was performed.
