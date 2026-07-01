# CLAUDE.md — claudebox build instructions for Claude Code

You are building **claudebox**: an independently-owned study of agent-to-agent influence
propagation in a population of naive personal assistants. Measure per-contact transmission
empirically (`assay`), then simulate population cascade (`simulate`), and show whether
instruction provenance (human vs orchestrator) changes propagation.

## Source of truth
The full spec lives in this directory. **Read `00_OVERVIEW.md`, then `01_CONTRACTS.md` before doing anything.**
Task specs: `02_TASK_simulate.md`, `03_TASK_score.md`, `04_TASK_assay.md`, `05_TASK_cli_validate.md`.
`BUILD_PLAN.md` is the execution sequence — follow it.

## Golden rules (do not violate)
1. **Pure Python stdlib only.** The single exception is the `anthropic` SDK, used *only* inside `assay.py`.
2. **Token-free core.** `simulate.py` and `score.py` must run with zero network access, on shipped fixtures. Never call an API to test them.
3. **Provenance / clean-room.** No employer tokens, infra, or proprietary material. Public API only. Stamp every output with config hash + seed + the stochasticity disclaimer (see `01_CONTRACTS` §1.6).
4. **Honesty rails.** Placeholder β values carry `"PLACEHOLDER": true` and must trigger a loud banner in any results output. Seeds fix graph/sim RNG, NOT model stochasticity — say so in output headers.
5. **GATE — do not guess.** The OPEN DECISION (`channel` vs `claimed`, see `00`/`04`) must be answered by the human before `assay.py` is built. Stop and ask if unanswered.

## Subagent delegation protocol (token efficiency)
- Give each subagent ONLY: `00_OVERVIEW.md` + `01_CONTRACTS.md` + its single task file.
- Subagents integrate through the schemas in `01_CONTRACTS`, never by reading each other's implementations.
- Each subagent tests against its shipped fixtures and reports against its task's **Acceptance criteria**.
- Accept/reject a module by running its acceptance criteria, not by re-reading everything.

## Don't
- Don't spend tokens during build or test. Use dry-run modes and fixtures.
- Don't introduce dependencies. Don't add a database, Docker, or cloud.
- Don't present simulated cascades as measured results.
