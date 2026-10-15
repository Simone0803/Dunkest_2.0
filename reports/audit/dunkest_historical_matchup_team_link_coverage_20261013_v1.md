# Historical matchup linkage coverage audit — v1

Generated UTC: 2026-10-13T11:40:47.318118+00:00

## Question

Does separating the source Dunkest team from the historical NBA game team improve the date and opponent linkage used by the existing matchup/rest feature experiment? This audit measures coverage only; it does not retrain or change production.

## Overall results

- Source rows inspected: **93,785**.
- Legacy unique player/date links (source team + PDK): **64,996**.
- Corrected unique valid game/date links (full-stat linked dataset): **93,316**.
- Rounds meeting the existing date-confidence rule: legacy **768**, corrected **778**.
- Rounds ready under both methods with same target date: **768**.
- Rows with a schedule-derived opponent: legacy **90,219**, corrected **93,284**.
- Opponent coverage gain distribution (corrected minus legacy): {"-1": 451, "0": 89818, "1": 3516}.

## By season

| Season ID | Rows | Legacy ready rounds | Corrected ready rounds | Legacy opponent rows | Corrected opponent rows | Team-mismatch links |
|---:|---:|---:|---:|---:|---:|---:|
| 13 | 18,927 | 150 | 153 | 18,279 | 18,774 | 1,439 |
| 19 | 19,590 | 155 | 158 | 18,882 | 19,486 | 1,548 |
| 5 | 17,681 | 140 | 140 | 17,035 | 17,589 | 1,396 |
| 7 | 18,422 | 161 | 165 | 17,619 | 18,353 | 1,691 |
| 9 | 19,165 | 162 | 162 | 18,404 | 19,082 | 1,754 |

## Interpretation

The corrected mapping only changes how an outcome row is associated with its historical NBA game. It does not change the source row’s PDK, credit, role, or Dunkest team field. A coverage increase would support testing an isolated walk-forward ablation that uses the linked NBA team for target-game matchup features, while retaining only past-only opponent form and rest inputs. It would not justify using the weekly archive as a pre-lock roster or participation dataset.

## Artifacts
- Row-level comparison: reports/audit/dunkest_historical_matchup_team_link_coverage_20261013_v1_rows.csv
- Round readiness comparison: reports/audit/dunkest_historical_matchup_team_link_coverage_20261013_v1_rounds.csv
- JSON: reports/audit/dunkest_historical_matchup_team_link_coverage_20261013_v1.json
