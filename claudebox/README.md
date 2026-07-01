# claudebox

A clean-room, independently-owned study of agent-to-agent influence
propagation in a population of naive personal assistants. It measures
per-contact transmission empirically (`assay`), then simulates population
cascade (`simulate`), and asks whether instruction **provenance** (human vs.
orchestrator agent) changes propagation.

Built to run on the owner's own tokens / own machine / public API only.
**Zero dependency on any employer's tokens, infra, or proprietary material.**
See "Provenance" at the bottom.

## Quickstart (one screen)

```bash
git clone <this-repo> claudebox && cd claudebox   # you are already here
pip install anthropic     # only needed for `assay`/`validate` real runs
export ANTHROPIC_API_KEY=sk-...   # only needed for `assay`/`validate` real runs
```

Everything else below — `score`, `simulate`, `replay`, and validate.py's own
self-test — runs with **zero network access** and **zero API key**, on the
fixtures shipped in `claudebox/examples/`.

Run all commands from the **parent** of the `claudebox/` package directory
(i.e. from `/home/user/claudebox`, one level above `claudebox/claudebox/`... 
if your checkout put the package directly at the repo root, run from that
repo root instead — the rule is: run from the directory that *contains*
`claudebox/`).

## The three verification tiers (00_OVERVIEW.md)

| Tier | Spends tokens? | What it proves |
|---|---|---|
| 1. **Read it** | no | Every module is a single-purpose, pure-stdlib file (no numpy, no Docker, no DB, no cloud) — auditable by eye. |
| 2. **Re-score for $0** | no | Raw dyad logs are shipped (`examples/synthetic_dyads.jsonl`); anyone re-derives `beta.json` via `score.py`, then a full population cascade via `simulate.py`, without spending a token. |
| 3. **Regenerate (paid)** | yes | `assay` re-measures real per-contact transmission `beta`; `validate` re-runs a few live small networks end-to-end and checks the result against `simulate`'s prediction. |

### The exact $0 path (copy-paste, run from the directory containing `claudebox/`)

```bash
# 1. Re-derive beta.json for $0 from the shipped raw dyad log (score.py).
#    --placeholder is passed here ONLY because synthetic_dyads.jsonl is a
#    hand-authored fixture, not a real assay run -- see PLACEHOLDER convention below.
python -m claudebox score claudebox/examples/synthetic_dyads.jsonl \
    -o /tmp/beta_from_fixture.json --placeholder

# 2. Simulate the population cascade from that re-derived beta + the shipped config.
#    Zero network access; deterministic given the seed in config.yaml.
python -m claudebox simulate --config claudebox/examples/config.yaml \
    --beta /tmp/beta_from_fixture.json --out /tmp/sim_results.csv

# 3. (Optional) Simulate directly against the hand-authored placeholder beta table too.
python -m claudebox simulate --config claudebox/examples/config.yaml \
    --beta claudebox/examples/beta_placeholder.json --out /tmp/sim_results_placeholder.csv

# 4. Render any shipped dyad log as a readable, role-revealed transcript (also $0).
python -m claudebox replay claudebox/examples/synthetic_dyads.jsonl
```

All four commands above were run on a clean shell as part of building this
module; see "Self-test log" below for the exact acceptance-criteria runs and
their (abbreviated) output.

`assay` (real run) and `validate` (real run) are the only two commands that
touch the network or spend tokens, and only when invoked **without**
`--dry-run`. Both refuse to run their live path in this repository's current
session/environment (see `assay.py`'s and `validate.py`'s `main()`) — that
refusal is intentional and is part of the honesty rails, not a bug. Run
`assay --dry-run` / `validate --dry-run` to exercise their full logic
network-free.

## CLI

```
python -m claudebox assay     ...   # delegates to assay.py    (spends tokens unless --dry-run)
python -m claudebox score     ...   # delegates to score.py    (token-free)
python -m claudebox simulate  ...   # delegates to simulate.py (token-free)
python -m claudebox validate  ...   # delegates to validate.py (spends tokens unless --dry-run)
python -m claudebox replay <log.jsonl>   # readable transcript of a dyad log (token-free)
```

Each subcommand forwards its remaining flags verbatim to the corresponding
module's own `argparse` parser — run `python -m claudebox <cmd> --help` (or
read that module's own docstring) for its full flag set; this README does not
duplicate them.

### CLI wiring / package layout (why there's a `claudebox/` inside `claudebox/`)

`common.py`, `simulate.py`, `score.py`, `assay.py`, `validate.py`, and
`cli.py` are flat sibling files that import each other the simple way
(`import common`, `from common import ...`) — the same way their own test
files (`test_common.py`, `test_score.py`) already import them, and the same
way you can run e.g. `python3 assay.py --dry-run ...` directly from inside
this directory. None of those already-built files were renamed, moved, or
had their internals changed to support `python -m claudebox`.

To get `python -m claudebox <cmd>` working on top of that flat layout without
touching those files, this same directory doubles as a Python **package**:

- `__init__.py` — package marker (docstring only, no logic).
- `__main__.py` — the package's `-m` entry point. Under `python -m claudebox`,
  Python puts the *parent* of this directory on `sys.path[0]`, not this
  directory itself (verified empirically) — so a naive `import cli` here
  would fail to see `common`, `assay`, etc. `__main__.py`'s only job is to
  insert this directory onto `sys.path` (so the flat `import common`-style
  imports keep working unmodified) and then delegate to `cli.main()`.
- `cli.py` — the actual dispatcher (`assay|score|simulate|validate|replay`)
  and the `replay` implementation itself. This is what you'd read to
  understand the CLI's logic; `__main__.py` is a two-line shim in front of it.

So: **run `python -m claudebox` from the directory that contains this
`claudebox/` package directory**, e.g.:

```bash
cd /home/user/claudebox            # contains ./claudebox/{__init__,__main__,cli,...}.py
python -m claudebox simulate --config claudebox/examples/config.yaml \
    --beta claudebox/examples/beta_placeholder.json --out /tmp/out.csv
```

You can still run any individual module directly the original way too
(`python3 claudebox/simulate.py --config ...` from outside, or
`python3 simulate.py --config ...` from inside) — `cli.py`/`__main__.py` are
additive, not a replacement for the modules' own standalone CLIs.

## `replay` — reading a dyad log without spending anything

```bash
python -m claudebox replay claudebox/examples/synthetic_dyads.jsonl
```

Prints one transcript block per record: run metadata (hardening / source /
operationalization / dose / payload / models / token counts), the full
`raw_messages` sequence with roles revealed (`[user]` / `[assistant]`), and
the outcome (`adopted` / `relayed`). This works on **any** shipped dyad log —
the hand-authored `synthetic_dyads.jsonl` fixture (which has empty
`raw_messages`, since it's synthetic outcome data, not a real transcript) or
a real/dry-run `assay.py` output (which has full message sequences). It never
imports `anthropic`, opens a socket, or reads `ANTHROPIC_API_KEY`.

## `validate` — testing the decomposition assumption

`01_CONTRACTS.md` §1.6 flags the chief audit item: does per-edge `beta`
(measured on isolated dyads) actually **compose** into the population-level
cascade `simulate.py` predicts? `validate.py` tests this directly: it runs a
*few* small live networks end-to-end (each edge-activation attempt is a real
dyadic contact, using `assay`'s own message-building and outcome-checking
logic), records the real `(R, tau)`, and compares it against `simulate`'s
Monte Carlo prediction — using the *same* measured `beta` — for the same
graph draws. Output is predicted-vs-observed `R`/`tau` with intervals and a
PASS/FAIL on whether the observed mean falls inside the predicted CI.

Like `assay.py`, `validate.py`'s real-network path imports `anthropic` lazily
(only inside the function that performs the actual API call — see
`make_real_edge_executor` → `assay.run_real_single_cell`) and refuses to run
that path in this build/session:

```bash
python -m claudebox validate --beta <beta.json> --payloads claudebox/examples/payloads.json \
    --payload-id p001_forward_promo_link
# -> "Real-run mode requested (no --dry-run). ... Refusing to proceed
#     in this environment/session." (exit code 2)
```

Pass `--dry-run` to exercise the full CLI/statistics pipeline for $0, using
assay's own canned receiver-response generator as a stand-in for the real
network calls:

```bash
python -m claudebox validate --dry-run --beta claudebox/examples/golden_beta.json \
    --payloads claudebox/examples/payloads.json --payload-id p001_forward_promo_link \
    --n-networks 3 --N 12 --k 3 --predict-reps 100
```

`validate.py` additionally ships a fixture/mocked-executor **self-test**
(dependency-injected `edge_executor`, see the module docstring) that
exercises 100% of the real comparison/statistics code — `run_live_networks`
→ `predict` → `compare` → `print_report` — with zero network access. This is
distinct from `--dry-run` above (which still goes through `assay`'s dry-run
machinery); the self-test injects a bespoke canned executor to prove the
comparison logic itself is correct in isolation. See "Self-test log" below.

## Honesty rails

**Stochasticity disclaimer** (from `common.STOCHASTICITY_DISCLAIMER`, printed
in every `simulate`/`validate` output header):

> "Seeds fix graph generation, seed-set choice, and IC RNG only. They do NOT
> fix model stochasticity, which lives solely in `assay` (live API sampling)
> and is not reproducible run-to-run."

**PLACEHOLDER convention:** any `beta.json` whose `provenance.PLACEHOLDER` is
`true` (stamped by `score.py --placeholder`, or hand-authored as in
`examples/beta_placeholder.json`) triggers a loud, repeated
`common.PLACEHOLDER_BANNER` in every `simulate`/`validate` output that
consumes it, plus an explicit "ALL ROWS ABOVE ARE PLACEHOLDER-DERIVED" line.
`examples/synthetic_dyads.jsonl` is hand-authored synthetic data (not a real
`assay` run), so re-scoring it must pass `--placeholder`; `score.py` defaults
`PLACEHOLDER` to `false` and only synthetic/placeholder fixtures should pass
that flag. Never present a simulated or placeholder-derived cascade as a
measured result.

## Provenance

Clean-room, independently owned study. Uses only the public Anthropic API
(`pip install anthropic`, `ANTHROPIC_API_KEY` from the owner's own account).
No employer tokens, infrastructure, credentials, or proprietary material are
used anywhere in this repository. Every artifact `simulate`/`score`/`assay`
produces is stamped with a config hash, seed, and the stochasticity
disclaimer above so it stands on its own without external context.

## Self-test log (acceptance criteria, run during the Phase 3 build)

All of the following were run on a clean shell from
`/home/user/claudebox` (the directory containing this `claudebox/` package):

1. **`simulate` end-to-end, zero network:**
   `python -m claudebox simulate --config claudebox/examples/config.yaml --beta claudebox/examples/beta_placeholder.json --out /tmp/sim_out.csv`
   → exit 0, printed stochasticity disclaimer + PLACEHOLDER banner (beta is
   the hand-authored placeholder fixture), R0 anchor, per-rho table,
   percolation thresholds, source-gap headline, wrote 150 rows.

2. **`score` end-to-end, zero network:**
   `python -m claudebox score claudebox/examples/synthetic_dyads.jsonl -o /tmp/beta_out.json`
   → exit 0, `wrote /tmp/beta_out.json`.

3. **`replay`, token-free, readable transcript:**
   `python -m claudebox replay claudebox/examples/synthetic_dyads.jsonl` → 48
   records rendered with hardening/source/dose/payload/outcome header lines
   (this fixture's `raw_messages` are empty, since it's a hand-authored
   outcome-only fixture). Also verified against a live-shaped log with real
   message content: `python -m claudebox assay --dry-run --payloads
   claudebox/examples/payloads.json --dose 2 -n 1 -o /tmp/dry_dyads.jsonl`
   followed by `python -m claudebox replay /tmp/dry_dyads.jsonl` — rendered
   full `[user]`/`[assistant]` turn sequences with roles revealed.

4. **`validate.py` self-test with a mocked/fixture edge executor, zero
   network:** a standalone script imported `validate`, asserted
   `'anthropic' not in sys.modules` immediately after import, called
   `validate.run_live_networks(..., edge_executor=<fixture function>)` (the
   fixture draws outcomes from `examples/golden_beta.json`'s measured rates
   rather than calling the real API), then `validate.predict(...)` and
   `validate.compare(...)`, and re-asserted `'anthropic' not in sys.modules`
   at the end. Output: a full predicted-vs-observed report (per-rep R/tau,
   predicted mean + 90% CI, PASS/FAIL per metric, overall verdict) — in the
   run recorded during build, `OVERALL: PASS`.

5. **`anthropic` isolation check:** `grep -n anthropic validate.py` shows
   only docstring/comment mentions — no top-level `import anthropic` and no
   `import anthropic` inside any function reachable from `main()`'s
   `--dry-run` path or from the self-test. `import assay` inside
   `make_real_edge_executor` mirrors `assay.py`'s own style (that function is
   never called by the self-test or by `--dry-run`). Confirmed via
   `python3 -c "import sys; import validate; assert 'anthropic' not in
   sys.modules"` (passes) both before and after running the self-test above.

6. **`validate --dry-run` CLI wiring, zero network:**
   `python -m claudebox validate --dry-run --beta claudebox/examples/golden_beta.json --payloads claudebox/examples/payloads.json --payload-id p001_forward_promo_link --n-networks 3 --N 12 --k 3 --predict-reps 100`
   → exit 0, correctly displayed the PLACEHOLDER banner (`golden_beta.json`
   is derived from the synthetic fixture, so its provenance is honestly
   stamped `PLACEHOLDER: true`), printed observed vs. predicted R/tau, PASS.

7. **README's $0 path, run literally as written:** all four commands in "The
   exact $0 path" above were executed verbatim on a clean shell and
   completed with exit code 0 and no network access.
