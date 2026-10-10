# Implementation inventory

Work followed the requested priority order. LOW items were not added because
they would increase scope without a measured benefit.

| ID | Problem | Priority | File | Change | Risk | Verification |
| --- | --- | --- | --- | --- | --- | --- |
| C1 | Duplicate normalized player identities or inconsistent role/team codes could corrupt roster constraints. | CRITICAL | `src/dunkest/optimize/milp.py` | Reject blank/duplicate normalized names; normalize roles and team codes before solving; validate coach identity/team uniqueness. | Name normalization may conflate aliases; collisions now fail visibly for review. | Duplicate-name and lowercase role/team optimizer tests. |
| C2 | Solver status `Optimal` alone did not establish that the returned lineup was valid, and feasible CBC incumbents could be discarded. | CRITICAL | `src/dunkest/optimize/milp.py` | Accept CBC integer-feasible incumbents; independently check roster, slots, formation, budget, team cap, captain, score, transfer accounting, and objective. Stop claiming ranked alternatives after a non-optimal incumbent. | A time-limited incumbent is valid but not guaranteed globally optimal; status is reported. | Optimizer smoke tests and score-corruption validator test. |
| C3 | Solver objective and reported objective could diverge without detection. | CRITICAL | `src/dunkest/optimize/milp.py` | Recompute MILP objective from selected players, slots, coach, risk settings, and transfers; reject discrepancies. | The check must track future objective changes. | Objective consistency across optimizer tests, including risk-adjusted mode. |
| H1 | Top-k no-good constraints forced overly disjoint teams, reducing expected score. | HIGH | `src/dunkest/config.py`, `config/*.yaml`, `src/dunkest/optimize/milp.py` | Default to exact roster uniqueness; score and rank alternatives by the configured solver objective. | Alternatives may be very similar by design; optional minimum-difference setting remains available. | Top-k distinct-roster and objective-order tests. |
| H2 | Live market and coach caches could be reused after becoming stale. | HIGH | `src/dunkest/data/access.py`, `src/dunkest/data/dunkest/lineups_browser.py`, `src/dunkest/config.py` | Write atomic fetch metadata, enforce configurable market TTL, reject stale/invalid metadata, and warn for legacy files without timestamps. | Legacy CSVs cannot be proven fresh and remain warning-only for compatibility. | Freshness tests for stale metadata and legacy warning; full suite. |
| H3 | Availability-adjusted prediction was not clearly separated from conditional performance. | MEDIUM | `src/dunkest/models/predictor.py` | Preserve conditional forecast and expose `p_play` plus `expected_pdk_before_play_probability`; set optimizer `expected_pdk` to probability-adjusted value. | Probability calibration remains data-dependent and is not validated against live future outcomes in this run. | Projection contract test and full suite. |
| H4 | NBA log collection could report complete API retrieval while requested market names failed to match returned players. | HIGH | `src/dunkest/data/nba/collector.py` | Match names with normalized identity, report unmatched requests, and warn instead of silently implying full coverage. | Ambiguous aliases still require explicit data resolution. | Normalized match/unmatched coverage test. |
| H5 | `--giornata` may mean a Dunkest round composed of multiple NBA turns, while scraping selects a `TURNO`. | HIGH, mitigated | `src/dunkest/data/dunkest/fixtures.py`, `src/dunkest/data/dunkest/lineups_browser.py` | The scraper persists exact Lineups fixture labels for the selected turn; the mapper resolves team pair plus displayed date to one NBA game ID. First-appearance proxies are excluded. | Only the selected turn is mapped for G1; users must select the intended `--turno`. If fixture/date cannot be uniquely resolved, coach matchup advice remains unavailable. | Tests cover exact date/team resolution and rejection of unverified mappings. |
| M1 | Risk-adjusted top-k could be returned in raw expected-score order; a tiny coach-cost epsilon also changed the stated objective. | HIGH | `src/dunkest/optimize/milp.py` | Rank by solver objective and remove the artificial coefficient from the expected-score objective. | Equal-score coach selection may be solver-dependent; score correctness is preserved. | Risk-adjusted top-k ordering test; full suite. |

## Not implemented in this pass

- Official calendar integration for Dunkest `Giornata` versus `Turno`; until then,
  unverified fixture proxies are excluded from prediction paths.
- Automatic regular-season/playoffs rule switching; budget and transfer penalty
  remain configurable inputs rather than inferred from a round number.
- New prediction features or a new minutes model: existing walk-forward and
  leakage tests already cover the reviewed pipeline, and no demonstrated gain
  justified additional predictive complexity.
- Live API/scraper integration checks: these require current external service
  access and are not reproducible as part of the local automated suite.
