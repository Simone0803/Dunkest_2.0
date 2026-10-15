# Supersession note — game-level lineup actuals V2

Date: 2026-10-14

V2's realized player scores use the corrected date-consensus official PDK reconstruction, but its lineup-performance comparison is superseded due to training-feature leakage. The training matrix used rows where fields named lag1_pdk/lag1_min_avg and several box-score features still contained the same-round target outcome. Those columns were valid for inference when reading the previous observed row, but not when fitting directly on the target row.

Do not use V2's model-vs-baseline lineup performance or bootstrap estimate as evidence of strategy superiority. The game-level PDK reconstruction validation itself remains useful: 93,734 comparable player-round rows, 93,728 within 0.02 PDK, MAE 0.00149. V3 rebuilds each training example from the latest player observation strictly before its target round and joins target-round schedule context separately.
