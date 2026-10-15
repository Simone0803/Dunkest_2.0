# Minutes allocator replay — 20261012T171217Z_2f98f42b

- Rows / unique players: 552 / 552
- Zero predictions before: 128
- Zero predictions after proportional allocation: 2
- Zero predictions among playable players before: 126
- Zero predictions among playable players after: 0
- Playable players with zero minutes before: 126
- Playable players with zero minutes after: 0
- Median expected PDK before / after: 2.876 / 3.683
- Mean absolute per-player score change: 1.036
- Role-budget violations: 0

## Scope

Deterministic replay of the frozen run's saved pre-allocation minute requests and saved model components; not a new end-to-end forecast or an out-of-sample accuracy result.

The proportional allocator spreads over-budget requested minutes across all players in the same team/role group in proportion to their capped requests. It preserves zero availability for players with p_play=0 and respects each role's total minute capacity. This audit is a mechanical replay only; it does not establish predictive accuracy.
