# TASK: build `score.py`

**Context:** read `00_OVERVIEW.md` and `01_CONTRACTS.md` only. Pure stdlib. Token-free.

## Input
- One or more dyad logs `logs/*.jsonl` (§2.1).

## Output
- `beta.json` (§2.2): β̂ + Wilson CI + n per cell (hardening × source × dose), with `provenance`.

## Implement (per §1.2)
1. Stream JSONL; bucket by (receiver_hardening, source, dose).
2. Per cell: β̂ = adoptions/contacts; Wilson interval (§1.2). Put `common.wilson(k,n,z)` in `common.py`.
3. Assemble nested arrays indexed by dose d=0..D.
4. `provenance`: list source log files, operationalization (read from records; error if mixed/inconsistent), generator+version. Set `PLACEHOLDER=false` for real logs; the placeholder fixture sets true.
5. Also emit a relay-rate table (same shape, from `outcome_relay`) — needed later for cascade calibration.

## Honesty rails
- Refuse silently-mixed `operationalization` across records — fail loud.
- Report n per cell so under-powered cells are visible.

## Acceptance criteria
- `python score.py logs/*.jsonl -o beta.json` produces schema-valid `beta.json`.
- On `examples/synthetic_dyads.jsonl` (ship it) reproduces a known β table exactly → this is the **$0 verification path** reviewers use.
- Wilson CI matches a hand-checked value in the task's unit test.

## Fixtures to ship
`examples/synthetic_dyads.jsonl` (~50 records spanning all cells) + the β table it must produce, as a golden file.
