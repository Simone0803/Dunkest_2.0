# Supersession note — game-level lineup actuals V1

Date: 2026-10-14

The V1 experiment and its paired-bootstrap companion are superseded by V2.

V1 reconstructed a round's fixture slate by taking the union of every linked NBA game ID in that source round. A small number of repeated player box-score signatures linked to a different date, causing unrelated games to enter a round's score sum. This was detected when inspecting the 47 player-round discrepancies greater than 0.02 PDK: they were concentrated in three rounds, with cross-date game IDs visible in the round slate.

V2 instead establishes one round date from the mode of linked player-game dates, requires at least 75% date agreement and at least 10 unique player links, then sums official Dunkest-valid per-game PDK for the full season/date slate. The strict V2 run compared 93,734 player-round rows, 93,728 matching within 0.02 PDK (99.994%), with MAE 0.00149 PDK and no high-error rounds in the three tested seasons.

Do not use V1's lineup score or bootstrap estimate for decisions. V1 artifacts are retained for audit history, not as authoritative results. V2's lineup score is also superseded due to training-feature leakage. Use the V3 leakage-safe report and bootstrap, while treating its +20.49 PDK gain over the raw previous-five-observation baseline as conditional evidence only because that baseline is strongly overoptimistic after selection.
