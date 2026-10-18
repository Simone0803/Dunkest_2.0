# Optimizer synthetic risk sensitivity — 2026-10-18 V1

Result: **PASS**

- Synthetic pool: 40 players and 2 coaches; seed `20261018`.
- Same player pool, coach pool, roster rules and budget used in all five runs.
- All plusvalenza values are zero; no transfer history or real score labels are used.
- Every solution is checked by the optimizer's independent validator.

| Objective | Risk lambda | Solver objective | Expected net PDK | P10 | P50 | P90 | Budget | Seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| expected_value | 0.00 | 256.555 | 256.555 | 225.913 | 256.555 | 287.196 | 111.61 | 0.0863 |
| risk_adjusted | 0.05 | 250.591 | 256.466 | 226.739 | 256.466 | 286.194 | 111.67 | 0.0390 |
| risk_adjusted | 0.10 | 244.715 | 256.466 | 226.739 | 256.466 | 286.194 | 111.67 | 0.0391 |
| risk_adjusted | 0.20 | 233.390 | 255.791 | 227.612 | 255.791 | 283.969 | 111.67 | 0.0380 |
| risk_adjusted | 0.50 | 201.371 | 253.710 | 227.248 | 253.710 | 280.171 | 110.16 | 0.0398 |

## Selected players

- `expected_value`, lambda `0.00`: Synthetic Player 04, Synthetic Player 09, Synthetic Player 10, Synthetic Player 15, Synthetic Player 16, Synthetic Player 19, Synthetic Player 25, Synthetic Player 27, Synthetic Player 37, Synthetic Player 39; coach Synthetic Coach A; module 3-1-1.
- `risk_adjusted`, lambda `0.05`: Synthetic Player 04, Synthetic Player 05, Synthetic Player 09, Synthetic Player 10, Synthetic Player 16, Synthetic Player 19, Synthetic Player 25, Synthetic Player 27, Synthetic Player 37, Synthetic Player 39; coach Synthetic Coach A; module 3-1-1.
- `risk_adjusted`, lambda `0.10`: Synthetic Player 04, Synthetic Player 05, Synthetic Player 09, Synthetic Player 10, Synthetic Player 16, Synthetic Player 19, Synthetic Player 25, Synthetic Player 27, Synthetic Player 37, Synthetic Player 39; coach Synthetic Coach A; module 3-1-1.
- `risk_adjusted`, lambda `0.20`: Synthetic Player 04, Synthetic Player 05, Synthetic Player 09, Synthetic Player 10, Synthetic Player 16, Synthetic Player 19, Synthetic Player 25, Synthetic Player 27, Synthetic Player 37, Synthetic Player 39; coach Synthetic Coach A; module 3-1-1.
- `risk_adjusted`, lambda `0.50`: Synthetic Player 04, Synthetic Player 05, Synthetic Player 09, Synthetic Player 10, Synthetic Player 16, Synthetic Player 19, Synthetic Player 27, Synthetic Player 30, Synthetic Player 37, Synthetic Player 39; coach Synthetic Coach A; module 3-1-1.

## Decision and limits

retain current policy; synthetic sensitivity verifies objective behavior only and cannot select a real-data strategy
Synthetic score distributions validate deterministic optimizer sensitivity and arithmetic only. They do not estimate real-game performance or justify a change to `risk_lambda`.

## Reproduction

```bash
PYTHONPATH=src .venv/bin/python scripts/audit_dunkest_optimizer_synthetic_risk_20261018_v1.py
```
