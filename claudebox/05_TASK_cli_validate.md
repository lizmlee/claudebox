# TASK: `cli.py`, `validate.py`, `common.py`, `README.md`

**Context:** read `00_OVERVIEW.md` and `01_CONTRACTS.md` only. Integrate via schemas, not by reading sibling implementations.

## `common.py`
- Schema IO (load/validate dyad log, beta.json, config, sim CSV).
- `wilson(k, n, z=1.96)`.
- `config_hash(config)` (sha256 of canonicalized config).
- Output-header writer (config hash + seed + §1.6 stochasticity disclaimer).

## `cli.py`
Single entry: `python -m claudebox <cmd>`:
- `assay`   → `assay.py`
- `score`   → `score.py`
- `simulate`→ `simulate.py`
- `validate`→ `validate.py`
- `replay <log.jsonl>` → render any dyad/game log as a readable transcript with roles revealed (token-free).

## `validate.py`
Tests the decomposition assumption (`AUDIT`, §1.6): run a small number of **live** multi-node networks end-to-end via the assay machinery, record the real cascade, and compare to `simulate`'s prediction using the measured β. Output: predicted vs observed R/τ with intervals, and a pass/fail on whether observed falls in predicted CI. This is the rigor capstone; keep paid runs few.

## `README.md`
- One-screen quickstart: clone → `pip install anthropic` → set `ANTHROPIC_API_KEY` (only for `assay`/`validate`).
- The **three verification tiers** (§00) stated up front, with the exact $0 path: `simulate` + `score` on shipped fixtures spends nothing.
- The stochasticity disclaimer and the PLACEHOLDER convention.
- Provenance statement: clean-room, public API, owner-owned.

## Acceptance criteria
- `python -m claudebox simulate ...` and `... score ...` run end-to-end on fixtures with **zero** network access.
- `replay` renders a shipped log readably.
- README's $0 path works exactly as written on a clean checkout.

## Build last
Depends on the interfaces of 02–04 (not internals). Resolve the OPEN DECISION before wiring `assay`.
