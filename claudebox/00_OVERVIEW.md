# claudebox — Build Coordinator (entry point)

**Read order for the orchestrating agent:** this file, then `01_CONTRACTS.md`. Do not load task files yourself; hand each to a subagent.

## What this is
A clean-room, independently-owned study of agent-to-agent influence propagation in a population of naive personal assistants. Measures per-contact transmission empirically, then simulates population cascade. Demonstrates whether instruction **provenance** (human vs orchestrator agent) changes propagation.

Built to run on the owner's own tokens / own machine / public API. **Zero dependency on any employer's tokens, infra, or proprietary material.** Provenance is the point: every artifact must stand without external context.

## The three layers
| Layer | Spends tokens? | Produces |
|---|---|---|
| `assay` | yes | per-contact transmission β table (indexed by receiver_hardening × source × dose) |
| `simulate` | no | population cascade stats: adopted-fraction, time-to-saturation, percolation threshold, **human-vs-orchestrator gap** |
| `validate` | a few paid runs | live small networks checked against simulator prediction |

## Verification tiers (design requirement — must hold)
1. **Read it** — single-purpose pure-stdlib files, no numpy, no Docker, no DB, no cloud.
2. **Re-score for $0** — ship raw dyad logs; anyone re-derives β from `score.py` without spending a token.
3. **Regenerate (paid)** — `assay` re-measures β; `validate` re-runs live networks.

## OPEN DECISION — must be resolved before `assay` (04) is built
**Source operationalization:** how "instruction source" is encoded in the dyad.
- `channel` (DEFAULT) — human instruction occupies the true principal/user role; orchestrator instruction arrives as another agent's message. Tests whether the model keys off real role structure.
- `claimed` — identical placement, only textual attribution differs. Tests whether it keys off asserted authority.
Owner must confirm `channel` or switch. Conflating the two is the primary validity attack — keep it a single declared factor, optionally run `claimed` as a second factor later.

## Delegation map & build order
1. **Freeze `01_CONTRACTS.md`** (interfaces + math). Nothing else starts until schemas are fixed.
2. **Parallel:** `02_TASK_simulate.md` and `03_TASK_score.md`. Both pure-stdlib, token-free, depend only on contracts. These are auditable tonight without spending anything.
3. **`04_TASK_assay.md`** — needs contracts + the resolved OPEN DECISION.
4. **`05_TASK_cli_validate.md`** — wires CLI (`assay|score|simulate|validate|replay`), README, provenance stamping. Depends on the others' *interfaces*, not internals.

## Token-efficiency protocol for the build
- Each subagent context = `00_OVERVIEW` (this, short) + `01_CONTRACTS` + its single task file. **Never** load sibling task files or sibling implementations.
- Interfaces live only in `01_CONTRACTS`; subagents integrate through schemas, not by reading each other's code.
- Each task ships fixtures; subagents test against fixtures, never the live API.
- Coordinator accepts/rejects a module by running its **Acceptance criteria**, not by reading full transcripts.

## Audit hooks (for owner review, later)
Load-bearing assumptions are tagged `AUDIT:` in `01_CONTRACTS.md`. The decomposition itself (single-edge β composes into independent-cascade) is the chief assumption; `validate` exists to test it.
