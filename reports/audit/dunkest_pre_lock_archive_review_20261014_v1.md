# Pre-lock archive review

Run: `20261014T103438Z_034cc8bc`

## Integrity and eligibility

- SHA-256 integrity: verified.
- Registry record: present.
- Archived files modified during review: no.
- Eligibility for certified pre-lock backtesting: **no**.

## Freshness audit

| Input | Age at forecast | Status |
|---|---:|---|
| Coach market | 0.001 h | Fresh |
| Player credits | 0.033 h | Fresh |
| Injury snapshot | 0.033 h | Fresh |
| Lineups market | 0.552 h | Fresh |
| Lineups availability | 0.552 h | Fresh |
| Fixture mapping | 49.688 h | Stale |

The archive's initial manifest marked fixture freshness unknown. A separate review read the per-fixture `source_retrieved_at_utc` embedded in the frozen mapping and found it was 49.7 hours old, beyond the 36-hour limit.

The archive remains immutable and ineligible. New prediction runs will preserve `lineups_fixtures_validation.json`; the validator now checks the mapping's actual source-retrieval timestamps, not its file modification time or validation-decision time.

## Decision

Retain this run for diagnostics only. Do not use it as certified evidence of strategy superiority. For future rounds, capture a fresh fixture mapping, archive the forecast before lock, and require every snapshot check to pass.
