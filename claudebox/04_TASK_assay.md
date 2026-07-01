# TASK: build `assay.py`  (the only token-spending module)

**Context:** read `00_OVERVIEW.md` and `01_CONTRACTS.md` only. Uses the `anthropic` SDK. **BLOCKED until the OPEN DECISION in `00` is resolved** (`channel` vs `claimed`). Default `channel`.

## Goal
Run short dyadic contacts and log them (§2.1) so `score.py` can estimate β. Content held constant; only source/operationalization/hardening/dose vary.

## Protocol
1. **Payload registry:** fixed set of influence payloads X, each with a `payload_id`. Identical text reused across every source condition. An adoption/relay checker (objective string/semantic test defined per payload — prefer deterministic check; if a judge is unavoidable, isolate + log it).
2. **Receiver agent:** "naive personal assistant for its user" (naive) or same + vigilance overlay (hardened). Default model from config; per-role override allowed (e.g., Haiku receiver).
3. **Source operationalization (the OPEN DECISION):**
   - `channel`: human payload delivered in the true user/principal role; orchestrator payload delivered as a separate agent message. 
   - `claimed`: identical placement, attribution text differs only.
   Implement the confirmed one; leave the other behind a flag.
4. **Dose:** deliver 1..D exposures from distinct "neighbor" framings; log each as its own record with incrementing `dose`.
5. **Outcome:** `outcome_adopt` (receiver incorporates X) and `outcome_relay` (receiver would pass X onward — elicit a forwarded message and check).

## Token efficiency (required)
- **Prompt caching** on the stable prefix (assistant system prompt + fixed payload framing). 
- Cap receiver output (structured: a short decision + ≤2-sentence rationale + optional relay text).
- **Batch API** for the mass sweep; log `tokens.cached`.
- Cheapest viable receiver tier by default; sender can be cheapest too.

## Honesty rails
- Log full `raw_messages`, model versions, seed, operationalization on every record.
- No Meta/employer infra, tokens, or proprietary payloads. Public API only. Stamp provenance.

## Acceptance criteria
- Dry-run mode (no API) emits schema-valid records from canned responses → lets CI test logging without spend.
- One real cell (e.g., naive×orchestrator, d=1, n=20) writes valid JSONL that `score.py` consumes.
- Token report per cell printed so full-sweep cost is estimable before committing.

## Fixtures
`examples/payloads.json` (≥3 payloads + their deterministic adoption checks).
