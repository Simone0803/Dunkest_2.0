# Historical lineup infeasibility audit — v1

Generated (UTC): 2026-10-13T11:07:46.396579+00:00

## Findings

- Failed records in sequential proxy: 147 (three transfer-penalty scenarios can repeat the same date slice).
- Unique failed date slices: 49.
- Failed slices whose maximum player capacity under the unchanged three-per-team rule is below 10: 49/49.
- Mean candidate teams in failed daily slices: 2.49.
- Mean pregame coach teams available per failed date slice: 13.14.
- Maximum player capacity under the unchanged team cap: 3–9 (shortfall 1–7).

## Diagnosis

The proxy filters the candidate pool to teams with a non-null matchup in the historical feature join for the target date. Across all 49 failed slices, this leaves only 1–3 candidate teams even though the pregame coach source contains 4–26 teams for the date. With the coach allowed to come from a different team, the unchanged max-three-per-team rule still permits only 3–9 player slots from those restricted pools, fewer than the required 10. CBC infeasibility is therefore expected for the supplied inputs; do not relax the production team cap to compensate.

## Consequence for the experiment

The current sequential transfer experiment is useful only as a restricted proxy for rounds that happen to be feasible. Its target-date matchup join does not expose a complete candidate universe: for example, on 2022-12-13 it has 43 player candidates but only GSW, LAL and UTA, while the coach source lists ten teams for that date. Thus the 49 infeasible slices are input-universe failures, not evidence of a production optimizer defect. The next valid lineup experiment must recover a complete pre-lock player/team/role universe and explicit scoring outcomes at the same date/turn granularity, preserve pregame information, and model lineup locks only when reliable Dunkest turn assignments are available. The production team cap remains 3; no production constraints were changed.

## Artifacts

- Details: `reports/audit/dunkest_historical_lineup_infeasibility_20261013_v1_rounds.csv`
- Summary JSON: `reports/audit/dunkest_historical_lineup_infeasibility_20261013_v1.json`
