# Supersession note — sequential transfer proxy interpretation (2026-10-13)

The sequential transfer experiment V2 and its paired bootstrap remain reproducible, but their coefficient comparison must be interpreted more conservatively after `dunkest_historical_lineup_infeasibility_20261013_v1`.

The audit found 49 unique failed date slices. Every one contained candidates from only 1–3 NBA teams, yielding at most 3–9 player slots once the coach and the production max-three-per-team constraint were accounted for. The capacity shortfall is 1–7 roster slots. The 2022-12-13 slice had 43 candidate rows but only GSW/LAL/UTA in the matchup-eligible pool (capacity nine players), whereas the pregame coach source covered ten teams for that date. This confirms that the historical matchup join does not expose a complete candidate slate.

Consequently:

- The infeasibility is not evidence of a production MILP defect; the solver is correctly enforcing the supplied constraints.
- Do not relax or alter the Dunkest three-per-team rule to make the proxy run.
- The paired +0.323 points per source-round/date slice estimate for coefficient 2.5 vs 5.0 remains statistically inconclusive and is additionally subject to candidate-universe selection bias. It is **not** a basis for production tuning.
- Keep the production transfer coefficient at 5 and treat all lineup-level transfer results as restricted sensitivity analyses until complete pre-lock market/CR data and unambiguous scoring-granularity labels are available.

No production model, configuration or solver constraint was changed. The original experiment artifacts are retained for reproducibility.
