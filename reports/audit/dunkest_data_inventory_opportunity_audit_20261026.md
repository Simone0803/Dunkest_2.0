# Dunkest 2.0 — Data Inventory & Analysis Opportunity Audit

**Data inspection date:** 2026-10-26 (Europe/Amsterdam)
**Scope:** local artifacts under `data/`, existing audit reports, source/client code and read-only checks of official public pages/endpoints. No production code, model, configuration, historical data, forecast or lineup was changed. No training or scraping was run.

## Executive summary

There is enough local data to run meaningful player-level, game-level PDK diagnostics now. The strongest reproducible sample is an official Dunkest PDK game-level target joined to the 2025-26 NBA logs: **18,412 matched valid player-games**. A saved fixed-season holdout compares an experimental Random Forest with a last-10 baseline on exactly those rows. The model has a small overall gain, but it regresses on the highest-scoring cohort and underpredicts both high PDK and high-minute players. These findings justify targeted analysis, not a production change: the artifact itself says this game-level model is not wired into the live lineup pipeline.

Historical weekly/turn PDK and credit records are extensive and useful for lagged player-form studies. They do **not** certify point-in-time prices, availability, coach quotations or rosters for past lock dates. Historical lineup results therefore remain a proxy with very low strict complete-sample coverage. DvP is available as complete, timestamped snapshots for the current opening days only; values moved materially between captures, so there is no historical DvP series for a leakage-safe backtest. Exact coach PDK outcomes with historical coach-price multipliers are not present.

## 1. Local inventory

A read-only filesystem inventory found **4,677 files (about 904 MB)** under `data/`: 3,509 Parquet, 778 JSON, 361 CSV, 10 Joblib models, 2 JSONL, plus small documentation/config/image files. The primary locations contain approximately:

| Location | Observed contents | Use and limitation |
|---|---:|---|
| `data/raw/` | 2,370 files, 173 MB | Dunkest API captures/history, NBA historical logs, current Lineups captures, inspection payloads. Raw source material; timestamps vary by collector. |
| `data/processed/` | 234 top-level files; about 344 MB including files directly in the directory | Normalized official labels, NBA logs, training tables, price/plusvalenza histories, matchup and schedule snapshots. Includes old/empty/stale artifacts; file existence alone is not readiness. |
| `data/archive/` | 17 GW1–GW3 pre-match run bundles, 136 files, about 11 MB | Has input snapshots/manifests and hashes; not all bundles meet reviewer/cutoff requirements. No official outcome files were found in the archive tree. |
| `data/archives/` | 94 files, about 2 MB | Legacy pre-lock registries/snapshots. Useful for compatibility/history, but not sufficient by themselves to certify outcomes. |
| `data/predictions/` | 1,313 files, about 34 MB, across 115 run directories | Predictions, lineups, coach forecasts and some newer component snapshots. Many older runs have pre-match market inputs but no full versioned player/coach forecast contract. No outcome/actual files were found by filename search. |
| `reports/audit/` | Numerous saved audits and prediction tables | Reuse these before new modeling. Some are exploratory/proxy studies, not prospectively certified lineup evaluations. |

### 1.1 Dataset-level findings

| Dataset and path | Shape / coverage | Keys, quality, provenance and point-in-time assessment |
|---|---|---|
| Official Dunkest player-game source, [`official_dunkest_player_games_2025-26.parquet`](../../data/processed/official_dunkest_player_games_2025-26.parquet) | 27,706 rows; 527 Dunkest player IDs; 1,305 Dunkest game IDs; 210 dates, 2025-10-21–2026-06-13. 21,889 rows flagged `gameValidForDunkest=True`, 5,817 false. PDK/minutes are non-null in this capture. | Per-player/game rows from the Dunkest `/api/player/games` collector; `meta.json` records all 527 responses received and zero collection errors. Unique requested-player/game pairs in this file. Official target, but the validity flag must be honored and does not establish that every row is a played/eligible NBA game. Response acquisition time is recorded for the collected file, not as historical pre-lock information. |
| Official PDK ↔ NBA comparison, [`official_dunkest_vs_nba_player_games_2025-26.parquet`](../../data/processed/official_dunkest_vs_nba_player_games_2025-26.parquet) | 27,706 candidate rows. Join statuses: 23,781 matched by player name/date/opponent; 2,047 outside NBA log date range; 1,878 player/name not found in NBA logs. | Of the 21,889 official-valid rows, 18,412 are in the matched subset; the remaining 3,477 valid rows are not linked to an NBA log row. Exact-key paired modeling should use the 18,412 verified matches. This is an identity bridge based on name/date/opponent, not a common NBA game ID supplied by both sources. |
| Fixed-season PDK holdout, [`dunkest_pdk_holdout_2025-26_predictions_v1.csv`](../../data/processed/dunkest_pdk_holdout_2025-26_predictions_v1.csv) and audit JSON | 18,412 unique player–Dunkest-game pairs, 468 players, 1,043 game IDs, 160 calendar dates, 2025-10-21–2026-04-10. No missing target or model predictions. | Targets are official Dunkest PDK; train seasons are 2020/21–2024/25 (93,766 rows), test is 2025/26. The audit records no train/test season overlap and zero same/future-date prior NBA history rows. Features are past-only lags. This is an experimental game-level RF/last-10 comparison, not the production runtime model or an entire-season forecast made before opening night. |
| Historical Dunkest player-game source, [`official_dunkest_player_games_2018-25_v1.parquet`](../../data/processed/official_dunkest_player_games_2018-25_v1.parquet) | 172,098 rows over 7 Dunkest seasons (season IDs 1, 3, 5, 7, 9, 13, 19), 2018-10-16–2025-04-13; 1,077 Dunkest IDs. 93,766 valid-target rows in the supervised 2020/21–2024/25 seasons. | Enriched link audit reports 172,084 player/date/opponent matches and 14 unmatched; there are two duplicate candidate player–NBA-game links to inspect before any exact-game join. `gameValidForDunkest` is mixed; do not label every row as a target. Older season IDs 1 and 3 are not used as official supervised targets because their validity flags are unresolved/all false in the audit. |
| Training feature table, [`dunkest_pdk_game_training_2020-26_v3.parquet`](../../data/processed/dunkest_pdk_game_training_2020-26_v3.parquet) | 112,178 rows, 95 columns, seasons 2020/21–2025/26, dates 2020-12-22–2026-04-10. 112,165 joined NBA player-game IDs; 13 unmatched. | Game-level official PDK target plus past PDK/NBA history and opponent/position features. Reusable for diagnostics and past-only walk-forward experiments after confirming each feature's as-of construction. Some columns are mapping status/metadata rather than predictors. |
| Historical Dunkest week/turn, [`dunkest_historical_player_week_round_2020-25_v2.parquet`](../../data/processed/dunkest_historical_player_week_round_2020-25_v2.parquet) | 93,785 player-week-turn rows over five seasons (2020/21–2024/25); one row-grain value is `player_week_round`. PDK, CR, minutes and plusvalenza fields are populated in the stored table. | The source is the Dunkest weekly stats table (`avg`/`tot`) with actual Dunkest week and turn IDs, not NBA `GAME_ID`. Existing reconciliation audit reproduces 93,728 of 93,734 comparable turn totals within 0.02 PDK (99.994%). It supports turn/player outcome analysis after the verified calendar bridge; it cannot itself prove what CR/availability was known before that turn. |
| NBA player/team history | `player_game_logs_2018-25_v1/` raw historical season files plus processed 2024/25 and 2025/26 files; `team_game_logs_2018-26_v1.parquet` has 19,038 team-game rows across 2018/19–2025/26. | NBA `PLAYER_ID`, `TEAM_ID`, `GAME_ID`, dates, minutes and box-score fields allow role/minute and team-strength diagnostics. Dunkest scoring remains the official target; box-score PDK is only a proxy. Current-season 2026/27 files contain 717 player rows and 72 team rows across five game dates through Oct. 24, too little to assess season-wide role stability. |
| Rookie outcomes, [`rookie_official_pdk.csv`](../../data/rookie_official_pdk.csv) | 264 player labels, draft years 2020–2025; fields include official PDK/minute, games/minutes totals, source. | Allows a historical cohort audit/prior study for those cohorts, but not a full 2026 rookie forecast evaluation or rookie-by-role comparison until linked to current eligible player records. No inference should be made for absent labels. |
| Historical CR/plusvalenza | [`plusvalenza_history_multiseason_26_pre_gw0_5y_nba_v4.parquet`](../../data/processed/plusvalenza_history_multiseason_26_pre_gw0_5y_nba_v4.parquet): 93,744 rows, five seasons (IDs 5, 7, 9, 13, 19); historical week/turn tables also have CR/PDK/PLUS. Current `player_credits_26_gw1/2/3.parquet` hold 513/536/531 rows. | Historical tables have authentic Dunkest historical values at weekly/turn grain, but no validated per-season point-in-time lock timestamp. Existing market inventory explicitly treats same-round CR as unsafe as a pre-game price. Current-season credits can support current-run checks only when paired with a verified pre-lock snapshot; do not join them backward to historical outcomes. |
| Fixtures and calendar | `dunkest_fixture_mapping_26_lineups_browser_season_multigw_v1.parquet`: 49 NBA-game mappings, GW1–GW3, 8 distinct dates, with NBA IDs, teams, Dunkest GW/turn, verified flag, provenance, retrieval timestamp and payload hash. Additional 2026 run snapshots are under `data/archive/26/`. | Useful verified joins where flags are true. It does not provide a complete historical multi-season NBA↔Dunkest bridge or a certified explicit Team-at-Rest state for every market team. Missing fixture is not evidence of rest. Dunkest week, turn and NBA date/game are distinct keys. |
| Injuries/availability | `injuries_26_gw1/2/3.parquet`, corresponding metadata and pre-match snapshots; older manual/current Lineups files also exist. | Captures are limited to 2026/27 and their timestamp/cutoff quality differs by run. No multi-season point-in-time injury/availability panel exists. Historical injury effect or DNP calibration cannot be certified from these alone. |
| Coach outputs/outcomes | 2026/27 `coach_market` and coach forecast snapshots in some run bundles; saved historical coach walk-forward reports use team-level historical outcomes. | No multi-season coach-market CR snapshots or reconciled official coach PDK result archive found. Team box scores permit NBA margin/win analyses; official coach PDK can only be approximated from team outcomes if opponent coach CR coefficient is unavailable. Do not label that proxy official PDK. |
| DvP snapshots | `data/processed/dunkest_dvp/29/`: 6 complete capture directories and 1 failed capture. Each complete `records.parquet` has 2,880 rows, 30 teams × 3 positions × 8 statistics × 4 windows, no duplicate compound keys, and no missing numeric values. | Schema includes source and content hashes, exact acquisition timestamps, raw values/ranks, semantics and season ID 29. Captures exist only on 2026-10-25/26; they are not a historical DvP series. One capture failed explicitly, leaving prior complete snapshots intact. |
| Prediction archives and outcomes | 17 run bundles in `data/archive/26/gw*/pre_match_*`; `data/predictions/` contains player/coach forecasts, lineups and some versioned snapshot components. | Bundles contain input snapshot hashes and capture metadata, but readiness varies and pre-existing reviews show missing/non-certifiable evidence for at least some runs. No post-match official player/coach outcome tables were found in archive/prediction trees by filename. A forecast–outcome OOS evaluation must first use the reviewer and stable game/player identity gate; no current bundle count is asserted as eligible here. |

### 1.2 Identity and temporal constraints

- Safest player-game join in 2025/26 is the unique pair `(Dunkest player ID, Dunkest game ID)` in the official game dataset/holdout, with an audited bridge to NBA player/date/opponent. It covers 18,412 valid rows, not every official row.
- The historical 2018–25 enrichment has 14 unmatched rows and two duplicate candidate NBA-game links; those exceptions must remain explicit.
- Weekly `mode=dunkest, stats_type=avg` is an average over requested Dunkest week/turn scope, not an NBA-game PDK label. The official client in `src/dunkest/data/dunkest/client.py` deliberately preserves week/turn scope and does not invent round IDs.
- NBA week, Dunkest Giornata, Dunkest Turno, Dunkest game ID and NBA `GAME_ID` are not interchangeable.
- A missing row is never set to zero. Official `gameValidForDunkest=False` is not a missing outcome and must not be treated as a valid target.
- Existing market inventory report `reports/audit/historical_dunkest_market_snapshot_inventory_v1.json` found historical weekly CR/PDK together but no verified capture/as-of marker. Same-round prices therefore cannot be used as true pre-lock prices. The 2026/27 pre-match market snapshots do not supply past-season market state.

## 2. Official public source checks

Read-only source inspection was limited to official pages and locally captured API responses. The official NBA stats page currently renders regular-season leader tables and per-turn Dunkest points. The official DvP page describes average stats/fantasy points conceded by team and position after a 28-minute threshold; it identifies Guards/Forwards/Centers, L3/L5/L10/ALL windows, and says the table ranks worst-to-best defense. Local DvP manifests independently record the selectors (30 teams, 3 positions, 8 statistics, 4 windows) and captured values.

The project's `docs/data_sources.md` and `src/dunkest/data/dunkest/client.py` document and implement the public routes:

- `/api/stats/table`: current/historical Dunkest table; `mode`, `stats_type`, `season_id`, `weeks[]`, `rounds[]`, team/position filters and prices are passed explicitly.
- `/api/stats/dunkest/week/rounds`: returns the official Turn IDs for a Dunkest gameweek; the client refuses to guess missing turn IDs.
- `/api/player/games`: individual player-game outcome collector; `data/processed/official_dunkest_player_games_2025-26.meta.json` records the source, season, 527 queried IDs, 27,706 rows and zero collection errors.
- Official Flutter `https://fantasy.dunkest.com/1/injuries` is rendered through Playwright and captures `/api/v1/leagues/1/injuries`; that route requires the site's app/browser flow, not an assumed public JSON URL.
- Official Dunkest calendar acquisition is implemented in `src/dunkest/data/dunkest/fixtures.py`; the returned Dunkest matchday includes turn, teams, eligibility/status and `started_at`, but does not itself expose an NBA `GAME_ID`. The project needs a separate verified identity bridge.

**Live API access result:** a single bounded `requests.get(..., timeout=8)` was attempted for each of `/api/stats/table`, `/api/stats/dunkest/week/rounds`, and `/1/injuries`; all three failed before HTTP with local DNS `NameResolutionError`. The web reader also refused direct API/injury URLs. Therefore no live response schema/status is claimed from this session. Existing raw captures in `data/raw/dunkest_stats_inspection/`, `data/raw/dunkest_stats_season29_week1_round{1,2,3}_20261023.json`, the local client and saved official data provide offline evidence of previous successful acquisition. The failed current network check is not evidence that the public source is unavailable generally.

| Source | Verified today | Coverage/grain available locally | OOS status |
|---|---|---|---|
| [Dunkest NBA Stats](https://www.dunkest.com/en/nba/stats) | Official page opens and renders 2026/27 leader/category tables; local API captures expose per-round/week fields. | Public page is interactive; local API history includes player-game endpoint 2025/26 and week/turn endpoints. | Current web view cannot reconstruct old pre-lock state. Keep API rows at their documented game/week/turn grain. |
| [Dunkest DvP](https://www.dunkest.com/en/nba/stats/teams/defense-vs-position/regular-season/2026-2027) | Page semantics, positions, windows and 28-minute threshold verified. | Six complete 2,880-row local snapshots on Oct. 25–26; 30 teams, 3 positions, 8 stats, 4 windows. | No multi-season pre-lock snapshots; not suitable for a retrospective DvP benefit claim. |
| `/api/stats/table` | Route and request construction verified in project code and captured raw API payloads; direct live request blocked by local DNS. | Historical week/turn aggregates, and turn-specific records where requested; no universal NBA game key. | Valid for saved official values at returned grain; as-of timing depends on each capture. |
| `/api/stats/dunkest/week/rounds` | Route and parameter use verified in code/raw payload capture; direct live request blocked by local DNS. | Official turn IDs in captured response. | Can map Dunkest scope; does not alone identify NBA game ID or prove team rest. |
| [Official injuries app](https://fantasy.dunkest.com/1/injuries) | Site route and Playwright/API capture logic verified locally; direct live request blocked by local DNS. | 2026/27 dated snapshots only; no historical panel. | Current dated snapshot can inform a forecast if captured pre-lock; cannot be backfilled. |
| Official Team-at-Rest and fantasy rules | Rule pages explain rest vs off-schedule and treatment; no complete historical rest-state data found locally. | Current calendar bridge has only limited multi-GW mapping; explicit reliable rest state is not available for every team. | Rule is documented; data state needed to apply it is blocked where status is unknown. |
| Credits/plusvalenza | Official market rules and historical Dunkest weekly values exist; local market snapshots exist for 2026/27. | Historical week/turn PDK, CR, PLUS; current 2026/27 market snapshots. | Historical point-in-time lock CR/coach CR and roster are not established, so do not certify old lineup value studies. |
| Coach scoring | Official rule defines margin/score thresholds and an opponent-price coefficient. Local team logs and coach forecast snapshots exist. | Historical NBA team-game outcomes; current coach market/forecast. | Historical opponent-coach CR snapshots and official coach PDK outcomes are missing; exact coach fantasy score cannot be certified across old seasons. |

Official rule references: [player scoring](https://docs.dunkest.com/fantasy-rules/player-scoring), [coach scoring](https://docs.dunkest.com/fantasy-rules/coach-scoring), [managing team and rest teams](https://docs.dunkest.com/fantasy-rules/managing-team), [postponed games/rest/off-schedule](https://docs.dunkest.com/fantasy-rules/postponed-or-suspended-games), and [player value/capital gains](https://docs.dunkest.com/fantasy-rules/player-value-and-capital-gains). These rules support checking scoring/roster constraints; they do not fill missing historical prices, availability or results.

## 3. Quantitative analyses executed now

### 3.1 Fixed-season game-level PDK holdout

Recomputed from the saved prediction CSV, with both models on the same **18,412** official valid player-game targets:

| Predictor (saved artifact) | MAE | RMSE | Bias `prediction − actual` |
|---|---:|---:|---:|
| Experimental RF | 7.577 | 9.856 | -0.172 |
| Previous-10 PDK mean | 7.789 | 10.154 | -0.048 |

Paired daily-cluster bootstrap of RF-minus-baseline absolute error (160 dates, 3,000 resamples, fixed seed 20261026) gave average daily MAE difference **-0.208 PDK**, 95% interval **[-0.250, -0.167]**. It is a descriptive interval for this fixed historical holdout, not evidence that this artifact is the active production predictor.

The gain is not uniform by target score:

| Official actual PDK cohort | n | RF MAE / bias | Prev-10 MAE / bias |
|---|---:|---:|---:|
| `<0` | 834 | 10.530 / +10.530 | 10.003 / +10.002 |
| `0–<10` | 6,126 | 6.482 / +6.024 | 6.615 / +5.757 |
| `10–<20` | 5,325 | 5.176 / +0.992 | 5.878 / +1.080 |
| `20–<25` | 1,959 | 6.534 / -3.526 | 6.958 / -3.172 |
| `25–<30` | 1,456 | 8.227 / -6.623 | 8.419 / -6.131 |
| `≥30` | 2,712 | 14.265 / -13.861 | 13.771 / -12.944 |

Using a verified one-to-one join to official Dunkest minutes for the same 18,412 rows:

| Actual minutes | n | RF MAE / RMSE / bias | Prev-10 MAE / RMSE / bias |
|---|---:|---:|---:|
| `<10` | 2,467 | 5.332 / 6.663 / +4.681 | 5.350 / 7.000 / +4.327 |
| `10–<20` | 4,265 | 6.201 / 7.826 / +2.416 | 6.439 / 8.195 / +2.263 |
| `20–<30` | 6,537 | 7.717 / 9.847 / -0.549 | 8.037 / 10.229 / -0.404 |
| `≥30` | 5,143 | 9.620 / 12.348 / -4.168 | 9.762 / 12.526 / -3.610 |

**Interpretation:** the saved RF is better overall in this sample, but both methods are materially low on high PDK/high-minute games, and RF is worse on actual PDK ≥30 than prev-10. This is a concrete next diagnostic target (high-score tail and conditional minutes/production), not an automatic recalibration: the RF holdout artifact is experimental and not live production. The outcome cohorts are retrospective; they cannot be used to tune on the frozen GW1 2026/27 prospective test.

### 3.2 Official PDK/NBA joins and DvP drift

- 2025/26 official valid Dunkest PDK: 21,889 rows; verified player/date/opponent linkage to NBA logs: 18,412. The 3,477-row unmatched balance is excluded from paired error calculations rather than imputed.
- Current-season player logs have 717 unique player-game rows, no duplicate `(PLAYER_ID, GAME_ID)` keys, five NBA dates and no missing PDK/minute columns in the local file. Team logs have 72 rows. This permits early descriptive checks but is not enough for stable role-change/season-current estimates.
- DvP snapshot checks: each of the six complete snapshots contained all 2,880 unique combinations, numeric values with no nulls, 30 teams, 3 positions, 8 statistics and all four windows. Comparing the last valid 2026-10-25 capture to 2026-10-26: **896/2,880 values changed**, median absolute change 0, maximum absolute change 21.5. This demonstrates the live table is mutable. It is not a performance comparison and the newer snapshot must not be substituted into an earlier forecast.
- DvP's page and local manifest explicitly describe conceded averages and table rank semantics. The page’s 28-minute threshold limits the population; those values are not an all-player or direct coach-win measure.

### 3.3 Existing roster and coach analyses

Existing reports already answer some questions and should be reused rather than repeated:

- `reports/audit/dunkest_minutes_hgb_recency_walk_forward_20261024_v1.json` and its metrics/predictions compare minute approaches on historic observations. The separate paired archive report has only 289 observed positive-minute pairs, one forecast origin, incomplete pre-lock eligibility and no verified zero-minute labels; it supports keeping HGB shadow, not promoting it.
- Historical lineups: `reports/audit/dunkest_historical_lineups_strict_actual_coverage_20261014_v1.json` has only **3 paired rounds** with complete outcomes for all 10 players. Expanded game-level proxy report v8 has 13 rounds over 2022/23–2024/25, but lagged market/universe and no exact coach CR/malus; results are too sparse/proxy-heavy to select an optimizer policy.
- Coach reports contain historical team-score and win-probability evaluation. They can support the NBA margin/win component, but not exact historical credit-adjusted coach PDK without same-date coach prices and officially reconciled coach outcomes.
- Historical market inventory (`reports/audit/historical_dunkest_market_snapshot_inventory_v1.json`) documents that historical weekly CR and PDK have no verified point-in-time capture marker. Do not reinterpret that table as a lock-time roster snapshot.

## 4. Opportunities and priority

| # | Proposed analysis | Question answered | Available data / coverage | Result obtainable now | Limits / assumptions | Potential value | Cost | Decision |
|---:|---|---|---|---|---|---|---|---|
| 1 | PDK residual decomposition by minutes, actual-score tail, history count, player and role cohorts | Where does the game-level predictor miss, especially for high scores and role/minute shifts? | Official target + matched NBA minutes, 18,412 paired rows; 2020–26 training table; role/team IDs on source rows. | Reproducible overall and minute/score cohort metrics already computed; extend to time-varying history length/role cohorts with strict match filters. | Not the live ensemble; static held-out season; role/starter coverage must be verified before segment use. | **High**: directly identifies whether future work belongs in minutes, production rate or tail. | Low–medium; offline, no training needed for first decomposition. | **Eseguire subito** |
| 2 | Rookie/low-history official PDK cohort profile and past-only prior audit | Are rookie priors/low-history estimates centered and stable, and which cohorts are weakly supported? | 264 official rookie labels (draft 2020–25), 172,098 official game rows through 2024/25 and 93,766 valid targets in 2020–25. | Coverage, sample sizes, bias/MAE by rookie class and history count; compare existing saved prior audit. | Player ID/draft mapping must be checked; no adequate 2026 rookie target yet; separate training selection from final holdout. | **High** for early-season reliability. | Low–medium. | **Eseguire subito** |
| 3 | Historical weekly-turn PDK and credit descriptive analysis / plusvalenza replication | How do realized PDK, CR and PLUS vary by price and prior form? | 93,785 player-week-turn rows across five seasons; 93,728/93,734 reconciled totals within 0.02 PDK; plusvalenza datasets. | Descriptive price-band returns, volatility, PDK/CR and lagged PLUS rates; reproduce existing CR forecast report. | Same-turn CR lacks as-of stamp; not a pre-lock salary backtest and not game-level NBA output. | **Medium**: can guide hypotheses and sanity checks, not validate optimizer decisions. | Low. | **Eseguire subito**, label explicitly descriptive |
| 4 | Pre-lock roster/optimizer outcome comparison | Do current PDKs improve three full rosters under exact rules and cost? | Archived pre-match player/coach/fixture/injury inputs for 2026/27; historical week-turn outcomes and saved lineup proxy reports. | Verify solver feasibility and compare existing heuristic variants on only eligible runs; current archive review status must gate inclusion. | Historical exact market, transfer history, coach prices/outcomes and complete selected-player labels are sparse/absent; strict lineup sample only 3 rounds. | **Very high** if reliable; currently insufficient for model selection. | Medium–high, mostly data review. | **Eseguire dopo raccolta minima** of complete prospective bundles + reconciled outcomes |
| 5 | Coach and DvP incremental value | Does roster-adjustment shrinkage or DvP add value to coach/game or player forecasts? | Team logs and existing coach reports; six DvP snapshots only for opening 2026/27 days. | Existing team-score/win diagnostics can be reused; DvP schema/drift and fallback coverage can be audited. | No historical pre-lock DvP series; no historical coach CR/multiplier/outcome archive; do not use GW3 diagnostics or post-capture values as evidence. | **Medium–high**, but model relevance is uncertain until paired data is collected. | Medium. | **Eseguire dopo raccolta minima** of timestamped prospective DvP, coach forecasts, prices and official outcomes |

### Analyses excluded for now

- A backtest of DvP correction: no historical pre-lock DvP snapshots exist in the local data. Current snapshot values are season-to-date and changed between acquisitions.
- Historical exact roster optimality, transfer malus or capital-gain impact: no verified same-cutoff market/owned-roster/transfer history for prior seasons. The current CR cannot be projected backward.
- Historical official coach PDK comparison across model variants: no same-match coach prices and reconciled coach PDK outcomes. Team points/margins can test the NBA model, not the full fantasy coefficient.
- Historical injury, DNP, availability and player-minute prediction validation: no point-in-time multiseason injury panel, and the shadow minute archive lacks verified zero-minute outcomes.
- Team-at-Rest scoring: the rule is documented, but no complete reliable team-rest state plus per-player T1 average source is available across dates; no inference from absent fixtures.
- Player-by-player current salary efficiency with 2025/26 outcomes: current CR is not a valid historical price. Historical same-turn prices are not proven pre-lock.

## 5. Recommended operating plan

1. **Use existing official-label holdout artifacts first.** Preserve `dunkest_pdk_holdout_2025-26_predictions_v1.csv` as an already inspected holdout, not a tuning set. Extend diagnostics only with fixed cohabits (history length, official minutes, role/position, rookie flag) on the same rows and paired date bootstrap. Keep the ≥30 cohort regression visible.
2. **Run a rookie/low-history coverage audit, not a new broad training sweep.** Join the rookie label table to official Dunkest IDs, report unmatched/ambiguous IDs, then calculate cohort counts and past-only errors from saved walk-forward predictions. Do not infer zero for missing target rows.
3. **Use historical CR/PLUS only for descriptive and forecast-model replication.** Keep same-round price values out of claims about pre-lock efficiency until an as-of capture is proved. Avoid combining a current market snapshot with old outcomes.
4. **Make prospective data useful before expanding optimizer experiments.** For each future run, archive exact market/coach/fixture/injury state, player and coach forecast components, lineups, cutoff and hashes. Reconcile official player-game and coach outcomes later under stable player/game keys. Reviewer failures and excluded rows must remain visible.
5. **After sufficient prospective sample accumulates, test one factor at a time.** First minutes/role, then DvP player contribution, then coach roster adjustment, then lineup strategy. Use shared eligible matches and reserve a final period; do not tune on frozen GW1 outcomes.

### Minimum additional collection for the highest-value currently blocked work

- A complete immutable pre-lock bundle per gameweek: current player and coach CR, eligible player/role/lineups, exact fixture and Team-at-Rest status, injuries/status, forecast components, time/cutoff, code/config/model versions and hashes.
- Official player PDK outcomes mapped to NBA game IDs and stable Dunkest player IDs; retain invalid/missing/unmatched outcomes as distinct states.
- Official coach PDK outcomes plus both coach CR values from the same pregame fixture to apply/verify the matchup coefficient.
- For DvP experiments, immutable snapshot timestamp and reference scope available before each player’s actual matchup lock; no retrospective reconstruction.

## 6. Reproducibility and commands actually run

Read-only repository and data checks run in this session:

```text
git status --short
git diff --stat
find data -type f ...
find data/raw -maxdepth 3 -type f
find data/processed -maxdepth 1 -type f
rg -n "api/stats/table|api/stats/dunkest/week/rounds|injuries|defense-vs-position|Team at Rest" src docs data/README.md
PYTHONPATH=src .venv/bin/python - <<'PY'  # pandas inventory: shapes, schemas, IDs, dates, duplicates, nulls
PY
PYTHONPATH=src .venv/bin/python - <<'PY'  # official-label holdout metrics and same-row cohorts
PY
python3 - <<'PY'  # read saved market-inventory metadata
PY
```

A single bounded read-only HTTP request (`requests.get`, timeout 8 seconds) was attempted to each official endpoint noted above. All failed before HTTP with local DNS resolution errors; no retry loop or bulk request was made. Public pages were checked through the web reader on 2026-10-26. No training, scraping, forecast, source-data write, or test suite was run.

## 7. Git and file changes

The initial worktree was already dirty. Its pre-existing modifications were preserved; no model, code, configuration, data, model artifact, forecast or existing report was changed. The only file added by this audit is this report. No commit or push was performed.
