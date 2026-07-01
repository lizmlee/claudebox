#!/usr/bin/env python3
"""score.py — turn dyad logs into a beta table with Wilson confidence intervals.

Pure stdlib, token-free (01_CONTRACTS.md §3). Streams one or more `logs/*.jsonl`
dyad logs (§2.1 schema) and produces `beta.json` (§2.2 schema): per-cell
adoption rate beta_hat = adoptions/contacts, its Wilson score confidence
interval (via `common.wilson`, z=1.96 default per §1.2), and the trial count n,
all indexed by (receiver_hardening, source, dose).

This module never contacts a network and never spends a model token — it only
reads already-collected dyad logs (produced by `assay.py`) and aggregates them.

Usage
-----
    python3 score.py logs/*.jsonl -o beta.json
    python3 score.py examples/synthetic_dyads.jsonl -o beta_out.json --relay-out relay.json

CLI flags
---------
    positional  paths           one or more dyad log JSONL files (globs already
                                 expanded by the shell)
    -o/--out    PATH            output path for the beta table (default: beta.json)
    --relay-out PATH             optional: also emit a relay-rate table (same
                                 cell shape as beta.json, built from
                                 `outcome_relay` instead of `outcome_adopt`).
                                 Needed later for cascade calibration
                                 (03_TASK_score.md point 5). Not part of the
                                 core beta.json schema (§2.2), so it is only
                                 written when this flag is given.
    --placeholder                 stamp provenance.PLACEHOLDER = true instead of
                                 false (real logs should NOT pass this flag;
                                 only synthetic/placeholder fixtures should).
    -z FLOAT                     Wilson z-score (default 1.96, per §1.2)

Dose indexing
-------------
Arrays are indexed by dose d = 0..D, where D = max dose seen across the input
records (§2.2: "Arrays index dose d=0..D"). A cell/dose combination with zero
observed contacts is represented as beta=0.0, ci=[0.0, 0.0], n=0 (n=0 makes the
"no data" state visible per the honesty rail "report n per cell so
under-powered cells are visible" — do not confuse a real 0.0 rate, which has
n>0, with an absent cell, which has n=0).

Honesty rails (03_TASK_score.md, 01_CONTRACTS.md §1.6)
-------------------------------------------------------
- `operationalization` is read from the records themselves (never hardcoded to
  "channel", even though that is the resolved OPEN DECISION per §2.5 — real
  logs are expected to carry "channel", but score.py must still detect and
  fail loud if a set of input records mixes "channel" and "claimed", since
  conflating the two is "the primary validity attack" (00_OVERVIEW.md).
- Every output stamps n per cell, so under-powered cells are visible.
- PLACEHOLDER defaults to false (this is real/derived data unless --placeholder
  is explicitly passed).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import common


def _bucket_key(record: dict) -> tuple[str, str, int]:
    return (record["receiver_hardening"], record["source"], record["dose"])


def read_all_records(paths: list[str]) -> list[dict]:
    """Load and validate every dyad record from the given log files.

    Raises ValueError (via common.load_dyad_log/validate_dyad_record) on any
    malformed record, naming the file/line/field at fault.
    """
    records: list[dict] = []
    for path in paths:
        records.extend(common.load_dyad_log(path, validate=True))
    if not records:
        raise ValueError("no dyad records found in input logs")
    return records


def check_operationalization(records: list[dict]) -> str:
    """Return the single operationalization value used across all records.

    Fails loud (ValueError) if records disagree — conflating `channel` and
    `claimed` dyads in one score run is the primary validity attack this
    project guards against (00_OVERVIEW.md OPEN DECISION note).
    """
    values = {r["operationalization"] for r in records}
    if len(values) > 1:
        raise ValueError(
            "mixed `operationalization` across input records: "
            f"{sorted(values)!r} — refuse to score a run that conflates "
            "channel and claimed dyads (see 00_OVERVIEW.md OPEN DECISION)"
        )
    return next(iter(values))


def max_dose(records: list[dict]) -> int:
    return max(r["dose"] for r in records)


def bucket_counts(records: list[dict], outcome_field: str) -> dict[tuple[str, str, int], tuple[int, int]]:
    """Bucket records by (hardening, source, dose) -> (successes, trials).

    `outcome_field` is either "outcome_adopt" (for the beta table) or
    "outcome_relay" (for the relay-rate table).
    """
    counts: dict[tuple[str, str, int], list[int]] = {}
    for r in records:
        key = _bucket_key(r)
        bucket = counts.setdefault(key, [0, 0])
        bucket[1] += 1  # trials
        if r[outcome_field]:
            bucket[0] += 1  # successes
    return {k: (v[0], v[1]) for k, v in counts.items()}


def build_table(
    records: list[dict],
    outcome_field: str,
    d_max: int,
    z: float = 1.96,
) -> tuple[dict, dict, dict]:
    """Build nested beta/ci/n dicts (§2.2 shape) for the given outcome field.

    Arrays are indexed by dose d=0..d_max (inclusive), so length d_max+1.
    A dose bucket with zero observed trials gets beta=0.0, ci=[0.0,0.0], n=0.
    """
    counts = bucket_counts(records, outcome_field)

    beta: dict[str, dict[str, list[float]]] = {}
    ci: dict[str, dict[str, list[list[float]]]] = {}
    n: dict[str, dict[str, list[int]]] = {}

    for hardening in common.HARDENING_VALUES:
        beta[hardening] = {}
        ci[hardening] = {}
        n[hardening] = {}
        for source in common.SOURCE_VALUES:
            beta_row: list[float] = []
            ci_row: list[list[float]] = []
            n_row: list[int] = []
            for d in range(0, d_max + 1):
                k_successes, n_trials = counts.get((hardening, source, d), (0, 0))
                if n_trials == 0:
                    beta_row.append(0.0)
                    ci_row.append([0.0, 0.0])
                    n_row.append(0)
                else:
                    result = common.wilson(k_successes, n_trials, z=z)
                    beta_row.append(result.phat)
                    ci_row.append([result.lo, result.hi])
                    n_row.append(n_trials)
            beta[hardening][source] = beta_row
            ci[hardening][source] = ci_row
            n[hardening][source] = n_row

    return beta, ci, n


def score(
    paths: list[str],
    out_path: str,
    relay_out_path: str | None = None,
    z: float = 1.96,
    placeholder: bool = False,
    generated_by: str = "score.py v1",
) -> dict:
    """End-to-end: load logs, validate, aggregate, write beta.json (+ optional
    relay.json). Returns the beta table dict that was written."""
    records = read_all_records(paths)
    operationalization = check_operationalization(records)
    d_max = max_dose(records)

    beta, ci, n = build_table(records, "outcome_adopt", d_max, z=z)

    provenance = common.provenance_block(
        config={"z": z, "d_max": d_max, "n_records": len(records)},
        seed=0,
        generated_by=generated_by,
        extra={
            "source_logs": sorted(str(Path(p)) for p in paths),
            "operationalization": operationalization,
            "PLACEHOLDER": placeholder,
        },
    )
    # provenance_block always stamps generated_at (a timestamp) — this is
    # expected to vary run-to-run; see examples/golden_beta.json comparison
    # notes in the module docstring / task report for how reviewers should
    # diff around it.

    common.write_beta_table(out_path, beta, ci, n, provenance)

    if relay_out_path is not None:
        relay_beta, relay_ci, relay_n = build_table(records, "outcome_relay", d_max, z=z)
        relay_provenance = common.provenance_block(
            config={"z": z, "d_max": d_max, "n_records": len(records)},
            seed=0,
            generated_by=generated_by,
            extra={
                "source_logs": sorted(str(Path(p)) for p in paths),
                "operationalization": operationalization,
                "PLACEHOLDER": placeholder,
                "table_kind": "relay_rate",
            },
        )
        common.write_beta_table(relay_out_path, relay_beta, relay_ci, relay_n, relay_provenance)

    return {"beta": beta, "ci": ci, "n": n, "provenance": provenance}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Score dyad logs into a beta.json table with Wilson CIs (token-free).",
    )
    parser.add_argument("paths", nargs="+", help="dyad log JSONL file(s)")
    parser.add_argument("-o", "--out", default="beta.json", help="output beta.json path")
    parser.add_argument(
        "--relay-out", default=None,
        help="optional output path for the relay-rate table (same shape, from outcome_relay)",
    )
    parser.add_argument("-z", type=float, default=1.96, help="Wilson z-score (default 1.96)")
    parser.add_argument(
        "--placeholder", action="store_true",
        help="stamp provenance.PLACEHOLDER=true (use only for synthetic/placeholder fixtures)",
    )
    args = parser.parse_args(argv)

    try:
        score(
            args.paths,
            args.out,
            relay_out_path=args.relay_out,
            z=args.z,
            placeholder=args.placeholder,
        )
    except ValueError as e:
        print(f"score.py: error: {e}", file=sys.stderr)
        return 1

    print(f"wrote {args.out}")
    if args.relay_out:
        print(f"wrote {args.relay_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
