# BUILD_PLAN.md — claudebox phased execution (for Claude Code)

Follow phases in order. Each phase names which subagent to spawn, its context, and the human checkpoint. Do not spend tokens until Phase 4's explicit single-cell step.

---

## Phase 0 — Freeze contracts (human + you, no subagents)
- Human confirms schemas in `01_CONTRACTS.md` (§2) and the math model (§1).
- **GATE:** human answers the OPEN DECISION — `channel` (default) or `claimed`. Record it in `01_CONTRACTS` provenance notes. `assay` is blocked until this is set.
- Create repo skeleton: `common.py`, `simulate.py`, `score.py`, `assay.py`, `cli.py`, `validate.py`, `examples/`, `logs/`, `README.md`.
- Build `common.py` first (shared by all): schema IO, `wilson(k,n,z)`, `config_hash`, output-header writer. Acceptance: unit test for `wilson` matches a hand-checked value.

## Phase 1 — Token-free core (two subagents IN PARALLEL)
- **Subagent A** → context: `00`, `01`, `02_TASK_simulate.md`. Build `simulate.py` + fixtures. Acceptance: runs on `examples/` in seconds, deterministic by seed, PLACEHOLDER banner fires, R0 cross-check printed.
- **Subagent B** → context: `00`, `01`, `03_TASK_score.md`. Build `score.py` + fixtures. Acceptance: reproduces the golden β table from `examples/synthetic_dyads.jsonl` exactly; Wilson CI unit test passes.
- **Human checkpoint:** run both on fixtures ($0). Confirm the $0 verification path works end to end before proceeding. This is the auditable core — review the math here.

## Phase 2 — Assay (one subagent; GATED on Phase 0 decision)
- **Subagent C** → context: `00`, `01`, `04_TASK_assay.md`. Build `assay.py` with the confirmed operationalization; leave the other behind a flag.
- Acceptance: **dry-run mode (no API)** emits schema-valid records from canned responses; per-cell token report prints. Do NOT call the live API yet.
- Human checkpoint: review payloads (`examples/payloads.json`) and the adoption/relay checks for objectivity.

## Phase 3 — Integration (one subagent)
- **Subagent D** → context: `00`, `01`, `05_TASK_cli_validate.md`. Build `cli.py`, `validate.py`, finish `common.py`, write `README.md`.
- Acceptance: `python -m claudebox simulate ...` and `... score ...` run on fixtures with zero network; `replay` renders a log; README's $0 path works on a clean checkout.

## Phase 4 — Spend, deliberately
1. Smoke-test the whole pipeline on fixtures ($0).
2. Run **one real assay cell** (e.g. naive×orchestrator, d=1, n≈20) → read the printed token cost → extrapolate the full sweep before committing.
3. Human decides sweep scope (lean two-density contrast vs full grid) based on real per-cell cost.
4. Run sweep via Batch API; `score` → `beta.json`; `simulate` the headline source-gap; `validate` a few live networks against prediction.

## Standing reminders
- Each subagent: only its three files. Integrate via schemas. Test on fixtures.
- Keep placeholder β flagged until real β replaces it.
- Stamp provenance on every artifact. Clean-room, owner-owned, public API only.
