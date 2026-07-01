# TASK: build `simulate.py`

**Context:** read `00_OVERVIEW.md` and `01_CONTRACTS.md` only. Pure stdlib. Token-free — must run and be auditable with no API access.

## Input
- `config.yaml` (§2.4) and `beta.json` (§2.2).

## Output
- `sim_results.csv` (§2.3) + a console summary including the **source gap** (§1.5) and the **R0 analytic anchor** beside empirical R.

## Implement (per §1.3–§1.5)
1. Graph generators: `er(N, k, seed)`, `smallworld(N, k, rewire_p, seed)`. Hand-rolled, stdlib only.
2. `run_once(G, rho, h, source_mode, phi, beta, seed) -> (R, tau, cascade)` implementing independent cascade with the dose × one-shot-per-exposer rule exactly as specified in §1.3 `AUDIT` note. Track per-node dose; select β column by (hardening, edge source).
3. `sweep(config, beta) -> rows` over `rho_sweep` × reps; Monte Carlo mean R + percentile CI.
4. `threshold(rows) -> rho*` via max dR/dρ (and R-crossing-R_macro as secondary).
5. Report `R0 = k * mean(beta)` per cell next to empirical R; flag if sign of (R0>1) disagrees with (R≥R_macro).
6. Headline: compute Δρ\* between `all_human` and `all_orchestrator` when both available.

## Honesty rails (enforce)
- If `beta.provenance.PLACEHOLDER` is true, print a loud banner and tag every results row `PLACEHOLDER`.
- Output header carries config hash + seed + the §1.6 stochasticity disclaimer.

## Acceptance criteria
- `python simulate.py --config examples/config.yaml --beta examples/beta_placeholder.json` runs in seconds, writes CSV, prints summary with PLACEHOLDER banner.
- Determinism: same seed → identical CSV.
- Sanity: with β=0 → R≈ρ; with β=1 on connected ER → R≈1; R0 cross-check printed.
- Provide `examples/beta_placeholder.json` (clearly fake) and `examples/config.yaml`.

## Fixtures to ship
`examples/config.yaml`, `examples/beta_placeholder.json`.
