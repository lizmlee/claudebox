# claudebox — Shared Contracts (single source of truth)

Every subagent reads this. Integrate through these schemas only.

---

## 1. Math model (full — this is what we audit together)

### 1.1 Per-contact transmission
A directed contact: an adopted node *u* (carrying influence X) interacts with neighbor *v*. *v* adopts with probability

  β[ v.hardening , source , d ]

where `hardening ∈ {naive, hardened}`, `source ∈ {human, orchestrator}`, `d` = exposure count (how many distinct adopted neighbors have already contacted *v*).

- **Dose-response:** β is a curve over `d` (β₀, β₁, β₂, …), nondecreasing in `d`. We measure the curve, not a scalar.
  `AUDIT:` dose-response is what defeats the "single-contact misses reinforcement" critique. Confirm curve length (default d=1..3).

### 1.2 β estimator (used by `score.py`)
Per cell c = (hardening, source, d): point estimate
  β̂_c = adoptions_c / contacts_c
Interval = **Wilson score** (not normal approx; correct at small n / extreme p). For successes *k*, trials *n*, z=1.96:
  p̂ = k/n
  center = (p̂ + z²/2n) / (1 + z²/n)
  half = (z/(1+z²/n)) · √( p̂(1−p̂)/n + z²/4n² )
  CI = center ± half
`AUDIT:` Wilson chosen over Wald deliberately. Owner to confirm z / confidence level.

### 1.3 Population cascade (independent cascade, IC)
Graph G=(V,E), |V|=N. Generators: Erdős–Rényi (mean degree k) and small-world ring-rewire (k, rewire p). Undirected; transmission attempted along incident edges.

- **Seed:** S₀ = ⌊ρN⌋ randomly chosen nodes pre-adopted at t=0. ρ = seed fraction ("spy density"). Seeded source label set per run-mode.
- **Hardening:** fraction `h` of V flagged hardened (uses hardened β column).
- **Dynamics (IC, one-shot-per-exposer):** at step t, each node adopted at t−1 makes ONE activation attempt on each not-yet-adopted neighbor *v*. For each attempt, *v*'s dose increments; attempt succeeds w.p. β[v.hardening, edge.source, d=current dose]. An exposer is spent after its attempts but stays adopted. Terminate when a step yields no new adoptions.
  `AUDIT:` dose × IC rule — dose = number of distinct adopted neighbors who have attempted *v*; the d-th attempt uses β_d. This is the precise interaction to scrutinize.
- **Edge source-typing:** every attempt carries a source label → selects β column. Run modes: `all_human`, `all_orchestrator`, or `mixed(φ)` with φ = fraction of attempts labeled orchestrator.

### 1.4 Outcomes (per run)
- R = |adopted_∞| / N  (final adopted fraction)
- τ = steps to saturation
- cascade = 1[R ≥ R_macro], R_macro default 0.5

### 1.5 Sweeps, threshold, headline
- Monte Carlo M reps/cell (seeded); report mean R + percentile CI.
- **Percolation threshold** ρ\* (or β\*): sweep ρ, locate steep rise (max dR/dρ, or R crossing R_macro).
- **Analytic anchor (sanity cross-check):** for ER+IC, basic reproduction number R0 ≈ k · β̄. Cascade expected when R0 > 1. `simulate` must report R0 alongside empirical R so sim can be checked against theory. `AUDIT:` this cross-check is how we catch a broken simulator.
- **HEADLINE METRIC** — source gap: Δρ\* = ρ\*_human − ρ\*_orchestrator (and/or ΔR at fixed ρ). The population-level cost of laundering identical content through an orchestrator.

### 1.6 Honesty rails (must be enforced in code/output)
- Placeholder β values stamped `"PLACEHOLDER": true`; no placeholder number may appear in a results summary unflagged.
- Seeds fix graph generation, seed-set choice, and IC RNG — NOT model stochasticity (which lives only in `assay`). State this in every output header.
- β carries Wilson CIs; R carries Monte Carlo CIs.
- Decomposition (edge β → IC population behavior) is a hypothesis; `validate` tests it. Never present simulated cascades as measured.

---

## 2. Data schemas

### 2.1 Dyad log — `logs/*.jsonl` (one record/contact; output of `assay`, input of `score`)
```json
{
  "run_id": "str", "ts": "iso8601", "seed": 0,
  "receiver_hardening": "naive|hardened",
  "source": "human|orchestrator",
  "operationalization": "channel|claimed",
  "dose": 1,
  "payload_id": "str",
  "models": {"sender": "str", "receiver": "str"},
  "tokens": {"prompt": 0, "completion": 0, "cached": 0},
  "outcome_adopt": true,
  "outcome_relay": false,
  "raw_messages": []
}
```
`payload_id` references a fixed payload registry — **content held constant across source conditions**; only source/operationalization vary.

### 2.2 β table — `beta.json` (output of `score`, input of `simulate`)
```json
{
  "beta": { "naive": {"human": [0.0], "orchestrator": [0.0]},
            "hardened": {"human": [0.0], "orchestrator": [0.0]} },
  "ci":   { "naive": {"human": [[0.0,0.0]], "orchestrator": [[0.0,0.0]]}, "...": "same shape" },
  "n":    { "naive": {"human": [0], "orchestrator": [0]}, "...": "same shape" },
  "provenance": { "source_logs": [], "operationalization": "channel",
                  "generated_by": "score.py vX", "PLACEHOLDER": true }
}
```
Arrays index dose d=0..D.

### 2.3 Sim result — `sim_results.csv`
Columns: `topology,N,k,rewire_p,rho,h,source_mode,phi,rep,seed,R,tau,cascade,R0`.

### 2.4 Config — `config.yaml` / dict
```yaml
topology: er            # er | smallworld
N: 1000
k: 8
rewire_p: 0.1           # smallworld only
rho_sweep: [0.01,0.02,0.05,0.1,0.2]
h: 0.0                  # hardened fraction
source_mode: all_orchestrator   # all_human | all_orchestrator | mixed
phi: 0.5                # mixed only
reps: 200
R_macro: 0.5
seed: 0
beta_table: beta.json
```

---

## 3. Conventions
- Pure Python stdlib only (`random`, `json`, `csv`, `statistics`, `argparse`, `math`, `hashlib`, `pathlib`). No third-party except the `anthropic` SDK, used only inside `assay`.
- Every output file header: config hash (sha256 of resolved config), model versions if any, seed, and the stochasticity disclaimer (§1.6).
- One file per module: `simulate.py`, `score.py`, `assay.py`, `cli.py`. Shared helpers in `common.py` (schema IO, config hashing, Wilson).
