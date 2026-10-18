# Frozen GW1 strategy variants — 2026/27

- Source run: 20261018T124836Z_e475d5d9
- Frozen at UTC: 2026-10-18T12:48:36.769554+00:00
- Mapped fixtures: 16
- Player forecasts: 528; coach forecasts: 30
- Snapshot hashes verified: 12
- Safe post-game retrieval cutoff: 2026-10-23 12:00 UTC

## Design

Six matched variants use the same frozen forecasts: expected-value vs risk-adjusted (lambda=0.10), with corrected plusvalenza, reconstructed uncorrected plusvalenza, or plusvalenza excluded. Forecast files and pregame snapshot bytes are retained unchanged; each variant has its own lineups and manifest.
Strict freshness gate: the forecast and all required player/coach/injury/Lineups snapshots must be timestamped and no more than 36 hours before the earliest mapped kickoff.
The no-gain variants set expected_plusvalenza to zero only in the in-memory optimizer input. The uncorrected variants subtract plusvalenza_bias_correction_cr from expected_plusvalenza; due to 0.1-CR quantization this is an approximate ablation. Actual outcomes are not read during generation.

## Frozen lineup comparison

                        variant  rank  expected_team_pdk   p10_team   p50_team   p90_team      coach     captain                                                                                                                                                  players
   risk_adjusted_corrected_gain     1         214.808953 161.579883 213.687782 261.436823 Micah Nori Evan Mobley Egor Demin; Evan Mobley; Immanuel Quickley; Jarrett Allen; Lauri Markkanen; Mohamed Diawara; Terance Mann; Ty Jerome; Walker Kessler; Zaccharie Risacher
   risk_adjusted_corrected_gain     2         214.477622 160.944245 212.934453 260.582181 Micah Nori Evan Mobley Ben Sheppard; Egor Demin; Evan Mobley; Immanuel Quickley; Jarrett Allen; Lauri Markkanen; Mohamed Diawara; Ty Jerome; Walker Kessler; Zaccharie Risacher
   risk_adjusted_corrected_gain     3         213.942249 160.607174 212.494557 259.951211 Micah Nori Jalen Duren   Evan Mobley; Immanuel Quickley; Jalen Duren; Lauri Markkanen; Mohamed Diawara; Seth Curry; Terance Mann; Ty Jerome; Walker Kessler; Zaccharie Risacher
  expected_value_corrected_gain     1         214.808953 161.579883 213.687782 261.436823 Micah Nori Evan Mobley Egor Demin; Evan Mobley; Immanuel Quickley; Jarrett Allen; Lauri Markkanen; Mohamed Diawara; Terance Mann; Ty Jerome; Walker Kessler; Zaccharie Risacher
  expected_value_corrected_gain     2         214.477622 160.944245 212.934453 260.582181 Micah Nori Evan Mobley Ben Sheppard; Egor Demin; Evan Mobley; Immanuel Quickley; Jarrett Allen; Lauri Markkanen; Mohamed Diawara; Ty Jerome; Walker Kessler; Zaccharie Risacher
  expected_value_corrected_gain     3         214.052760 160.582380 212.509591 260.069367 Micah Nori Jalen Duren Evan Mobley; Immanuel Quickley; Jalen Duren; Jevon Carter; Lauri Markkanen; Mohamed Diawara; Terance Mann; Ty Jerome; Walker Kessler; Zaccharie Risacher
 risk_adjusted_uncorrected_gain     1         214.808953 161.579883 213.687782 261.436823 Micah Nori Evan Mobley Egor Demin; Evan Mobley; Immanuel Quickley; Jarrett Allen; Lauri Markkanen; Mohamed Diawara; Terance Mann; Ty Jerome; Walker Kessler; Zaccharie Risacher
 risk_adjusted_uncorrected_gain     2         214.477622 160.944245 212.934453 260.582181 Micah Nori Evan Mobley Ben Sheppard; Egor Demin; Evan Mobley; Immanuel Quickley; Jarrett Allen; Lauri Markkanen; Mohamed Diawara; Ty Jerome; Walker Kessler; Zaccharie Risacher
 risk_adjusted_uncorrected_gain     3         213.942249 160.607174 212.494557 259.951211 Micah Nori Jalen Duren   Evan Mobley; Immanuel Quickley; Jalen Duren; Lauri Markkanen; Mohamed Diawara; Seth Curry; Terance Mann; Ty Jerome; Walker Kessler; Zaccharie Risacher
expected_value_uncorrected_gain     1         214.808953 161.579883 213.687782 261.436823 Micah Nori Evan Mobley Egor Demin; Evan Mobley; Immanuel Quickley; Jarrett Allen; Lauri Markkanen; Mohamed Diawara; Terance Mann; Ty Jerome; Walker Kessler; Zaccharie Risacher
expected_value_uncorrected_gain     2         214.477622 160.944245 212.934453 260.582181 Micah Nori Evan Mobley Ben Sheppard; Egor Demin; Evan Mobley; Immanuel Quickley; Jarrett Allen; Lauri Markkanen; Mohamed Diawara; Ty Jerome; Walker Kessler; Zaccharie Risacher
expected_value_uncorrected_gain     3         214.052760 160.582380 212.509591 260.069367 Micah Nori Jalen Duren Evan Mobley; Immanuel Quickley; Jalen Duren; Jevon Carter; Lauri Markkanen; Mohamed Diawara; Terance Mann; Ty Jerome; Walker Kessler; Zaccharie Risacher
          risk_adjusted_no_gain     1         214.808953 161.579883 213.687782 261.436823 Micah Nori Evan Mobley Egor Demin; Evan Mobley; Immanuel Quickley; Jarrett Allen; Lauri Markkanen; Mohamed Diawara; Terance Mann; Ty Jerome; Walker Kessler; Zaccharie Risacher
          risk_adjusted_no_gain     2         214.477622 160.944245 212.934453 260.582181 Micah Nori Evan Mobley Ben Sheppard; Egor Demin; Evan Mobley; Immanuel Quickley; Jarrett Allen; Lauri Markkanen; Mohamed Diawara; Ty Jerome; Walker Kessler; Zaccharie Risacher
          risk_adjusted_no_gain     3         213.942249 160.607174 212.494557 259.951211 Micah Nori Jalen Duren   Evan Mobley; Immanuel Quickley; Jalen Duren; Lauri Markkanen; Mohamed Diawara; Seth Curry; Terance Mann; Ty Jerome; Walker Kessler; Zaccharie Risacher
         expected_value_no_gain     1         214.808953 161.579883 213.687782 261.436823 Micah Nori Evan Mobley Egor Demin; Evan Mobley; Immanuel Quickley; Jarrett Allen; Lauri Markkanen; Mohamed Diawara; Terance Mann; Ty Jerome; Walker Kessler; Zaccharie Risacher
         expected_value_no_gain     2         214.477622 160.944245 212.934453 260.582181 Micah Nori Evan Mobley Ben Sheppard; Egor Demin; Evan Mobley; Immanuel Quickley; Jarrett Allen; Lauri Markkanen; Mohamed Diawara; Ty Jerome; Walker Kessler; Zaccharie Risacher
         expected_value_no_gain     3         214.052760 160.582380 212.509591 260.069367 Micah Nori Jalen Duren Evan Mobley; Immanuel Quickley; Jalen Duren; Jevon Carter; Lauri Markkanen; Mohamed Diawara; Terance Mann; Ty Jerome; Walker Kessler; Zaccharie Risacher

## Interpretation

Uncorrected plusvalenza is reconstructed by subtracting the stored CR bias correction from the archived corrected expectation; because the output was quantized to 0.1 CR, this is an ablation approximation, not an exact refit of the legacy model.
Score only after the safe cutoff with official player and coach outcomes linked to frozen fixture IDs. Missing outcomes must never be replaced with zero.

Artifacts: reports/audit/dunkest_gw1_strategy_variants_20261018T124836Z_e475d5d9_v1.json and reports/audit/dunkest_gw1_strategy_variants_20261018T124836Z_e475d5d9_v1_lineups.csv
