# Frozen GW1 strategy variants — 2026/27

- Source run: 20261013T184846Z_21d331f5
- Frozen at UTC: 2026-10-13T18:48:46.412658+00:00
- Mapped fixtures: 16
- Player forecasts: 546; coach forecasts: 30
- Snapshot hashes verified: 11
- Safe post-game retrieval cutoff: 2026-10-23 12:00 UTC

## Design

Four matched variants use the same frozen forecasts: expected-value vs risk-adjusted (lambda=0.10), each with corrected plusvalenza included or excluded from optimization. Forecast files and pregame snapshot bytes are retained unchanged; each variant has its own lineups and manifest.
The no-gain variants set expected_plusvalenza to zero only in the in-memory optimizer input. Actual outcomes are not read during generation.

## Frozen lineup comparison

                      variant  rank  expected_team_pdk   p10_team   p50_team   p90_team         coach      captain                                                                                                                                                players
 risk_adjusted_corrected_gain     1         199.707256 134.420855 198.504868 268.734610    Micah Nori Jayson Tatum            Andrew Nembhard; Jayson Tatum; Kevin Love; Kyrie Irving; Nicolas Claxton; Riley Minix; Ty Jerome; Yaxel Lendeborg; Yuki Kawamura; Zach Edey
 risk_adjusted_corrected_gain     2         194.608346 133.130998 197.016365 269.030084 Doug Christie Kyrie Irving                Aday Mara; Andrew Nembhard; Jayson Tatum; Kyrie Irving; Mikel Brown Jr.; Riley Minix; Tolu Smith; Ty Jerome; Yaxel Lendeborg; Zach Edey
 risk_adjusted_corrected_gain     3         188.628262 126.494172 190.186058 258.804952     Ime Udoka Jaylen Brown          Aday Mara; Andrew Nembhard; Darius Acuff Jr; Jaylen Brown; Kyrie Irving; Nicolas Claxton; Riley Minix; Tolu Smith; Ty Jerome; Yaxel Lendeborg
expected_value_corrected_gain     1         201.747501 127.393635 199.429982 281.687156    Micah Nori Jayson Tatum            Aday Mara; Buddy Hield; Darius Acuff Jr; Jayson Tatum; Joan Beringer; Kyrie Irving; Mikel Brown Jr.; Nate Ament; Yaxel Lendeborg; Zach Edey
expected_value_corrected_gain     2         194.997781 128.889223 196.828292 274.914836 Doug Christie Kyrie Irving             Aday Mara; Andrew Nembhard; David Roddy; Jayson Tatum; Joan Beringer; Kyrie Irving; Mikel Brown Jr.; Ty Jerome; Yaxel Lendeborg; Zach Edey
expected_value_corrected_gain     3         190.530066 111.434096 173.349727 270.977114 Jamahl Mosley  Evan Mobley             Aaron Gordon; Aday Mara; Darius Acuff Jr; Evan Mobley; Joan Beringer; Kyrie Irving; Mikel Brown Jr.; Ty Jerome; Yaxel Lendeborg; Zach Edey
        risk_adjusted_no_gain     1         199.901188 134.708073 198.683772 268.694351    Micah Nori Jayson Tatum Aday Mara; Darius Acuff Jr; Jayson Tatum; Kyrie Irving; Nicolas Claxton; Riley Minix; Sandro Mamukelashvili; Ty Jerome; Yaxel Lendeborg; Yuki Kawamura
        risk_adjusted_no_gain     2         194.608346 133.130998 197.016365 269.030084 Doug Christie Kyrie Irving                Aday Mara; Andrew Nembhard; Jayson Tatum; Kyrie Irving; Mikel Brown Jr.; Riley Minix; Tolu Smith; Ty Jerome; Yaxel Lendeborg; Zach Edey
        risk_adjusted_no_gain     3         188.628262 126.494172 190.186058 258.804952     Ime Udoka Jaylen Brown          Aday Mara; Andrew Nembhard; Darius Acuff Jr; Jaylen Brown; Kyrie Irving; Nicolas Claxton; Riley Minix; Tolu Smith; Ty Jerome; Yaxel Lendeborg
       expected_value_no_gain     1         201.885414 128.712725 199.713146 280.418573    Micah Nori Jayson Tatum           Aday Mara; Braden Smith; Darius Acuff Jr; Jayson Tatum; Joan Beringer; Kyrie Irving; Mikel Brown Jr.; Nate Ament; Yaxel Lendeborg; Zach Edey
       expected_value_no_gain     2         195.367486 125.531443 196.781165 279.858087 Doug Christie Kyrie Irving         Aaron Gordon; Aday Mara; Darius Acuff Jr; Kyrie Irving; Marvin Bagley III; Mikel Brown Jr.; Paul George; Ty Jerome; Yaxel Lendeborg; Zach Edey
       expected_value_no_gain     3         190.530066 111.434096 173.349727 270.977114 Jamahl Mosley  Evan Mobley             Aaron Gordon; Aday Mara; Darius Acuff Jr; Evan Mobley; Joan Beringer; Kyrie Irving; Mikel Brown Jr.; Ty Jerome; Yaxel Lendeborg; Zach Edey

## Interpretation

Tests the lineup-score impact of including corrected plusvalenza in the optimizer, not the standalone accuracy gain of the correction versus the old uncorrected model.
Score only after the safe cutoff with official player and coach outcomes linked to frozen fixture IDs. Missing outcomes must never be replaced with zero.

Artifacts: reports/audit/dunkest_gw1_strategy_variants_20261013_v1.json and reports/audit/dunkest_gw1_strategy_variants_20261013_v1_lineups.csv
