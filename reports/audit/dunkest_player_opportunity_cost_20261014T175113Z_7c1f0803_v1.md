# Player opportunity-cost counterfactual — 20261014T175113Z_7c1f0803

## Reference lineup

- Objective: risk_adjusted; risk lambda: 0.1
- Coach: Micah Nori
- Expected net team PDK: 243.30
- Budget used: 95.00 CR

## Method

Each selected player is excluded in turn; the same MILP is re-solved using the same eligible market, coach candidates, budget, roster rules, objective and fixed capital-gain shadow price. This is a counterfactual diagnostic, not a realized-outcome backtest.

## Results

- Completed optimal counterfactuals: 10 / 10
- Median objective opportunity cost: 0.107 PDK-equivalent
- Median net expected-PDK difference: 0.081

| Excluded player | Role | CR | Slot | Objective gap | Net expected PDK gap | Replacement players |
|---|---|---:|---|---:|---:|---|
| Dean Wade | F | 5.0 | Sixth Man | 0.376 | 0.130 | Jarrett Allen; Jevon Carter; Jonathan Kuminga; Jose Alvarado; Lebron James; Seth Curry |
| Egor Demin | G | 6.0 | Bench | 0.052 | 0.047 | Klay Thompson |
| Evan Mobley | F | 14.0 | Captain | 0.079 | -0.231 | Jarrett Allen; Jayson Tatum; Jevon Carter; Jose Alvarado; Seth Curry |
| Jalen Suggs | G | 9.0 | Sixth Man | 0.079 | -0.231 | Jarrett Allen; Jayson Tatum; Jevon Carter; Jose Alvarado; Seth Curry |
| Kyle Kuzma | F | 7.0 | Starter | 0.135 | 0.116 | Jevon Carter; Nicolas Claxton; Paul George; Seth Curry |
| Lauri Markkanen | F | 12.5 | Captain | 1.174 | 0.832 | Day'ron Sharpe; Jayson Tatum; Jevon Carter; Seth Curry |
| Neemias Queta | C | 11.0 | Captain | 0.079 | -0.231 | Jarrett Allen; Jayson Tatum; Jevon Carter; Jose Alvarado; Seth Curry |
| Terance Mann | G | 5.0 | Bench | 0.079 | -0.231 | Jarrett Allen; Jayson Tatum; Jevon Carter; Jose Alvarado; Seth Curry |
| Ty Jerome | G | 7.5 | Starter | 3.571 | 3.039 | Jarrett Allen; Jayson Tatum; Jevon Carter; Seth Curry |
| Walker Kessler | C | 10.5 | Starter | 0.616 | 0.504 | Jarrett Allen; Jevon Carter |

## Limitations

- Costs are model-based, conditional on this prediction run and candidate market.
- A zero or small gap means the optimizer can replace the player with little modeled loss; it does not prove the replacement is better in reality.
- Solver timeouts are marked inconclusive, not interpreted as an opportunity-cost estimate.
- No historical outcomes or frozen 2026/27 GW1 results were used.

## Artifacts

- CSV: reports/audit/dunkest_player_opportunity_cost_20261014T175113Z_7c1f0803_v1.csv
- JSON: reports/audit/dunkest_player_opportunity_cost_20261014T175113Z_7c1f0803_v1.json
