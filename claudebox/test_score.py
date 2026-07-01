#!/usr/bin/env python3
"""Self-test for score.py.

Run directly: `python3 test_score.py`. No test framework dependency (pure
stdlib, per project conventions) — uses plain asserts and exits nonzero on
failure.

Covers:
1. A hand-checked Wilson interval value (sanity-checks common.wilson, which
   score.py depends on for every cell).
2. The $0 golden-file verification path: running score.py on
   examples/synthetic_dyads.jsonl must reproduce examples/golden_beta.json,
   modulo the `generated_at` timestamp field (which is intentionally
   time-varying — see NOTE below). All other fields, including
   `config_hash`, must match exactly since config_hash is derived only from
   {z, d_max, n_records}, none of which depend on wall-clock time.
3. Byte-for-byte reproducibility: two successive runs of score.py on the same
   input, with `generated_at` excluded, must be identical.
4. The honesty rail: a log with mixed `operationalization` values must cause
   score.py to fail loud (raise ValueError / nonzero exit), not silently pick
   one.

NOTE on golden-file comparison and `generated_at`:
`common.provenance_block` stamps `generated_at` = current UTC time on every
call (see common.py `now_iso()`), by design (01_CONTRACTS.md §3: "Every
output file header: ... seed, and the stochasticity disclaimer"). This field
is expected to differ between the golden fixture's generation time and any
later re-run. We therefore exclude only `generated_at` from the golden
equality check; every other field (including the beta/ci/n numeric payload
and config_hash) is compared exactly.
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import common
import score

HERE = Path(__file__).resolve().parent
SYNTHETIC_LOG = HERE / "examples" / "synthetic_dyads.jsonl"
GOLDEN_BETA = HERE / "examples" / "golden_beta.json"

VOLATILE_PROVENANCE_FIELDS = {"generated_at"}


def _strip_volatile(table: dict) -> dict:
    table = json.loads(json.dumps(table))  # deep copy
    for field in VOLATILE_PROVENANCE_FIELDS:
        table.get("provenance", {}).pop(field, None)
    return table


def test_wilson_hand_check():
    """Hand-checked Wilson interval: k=8, n=10, z=1.96.

    p_hat = 8/10 = 0.8
    z^2 = 1.96^2 = 3.8416
    center = (p_hat + z^2/(2n)) / (1 + z^2/n)
           = (0.8 + 3.8416/20) / (1 + 3.8416/10)
           = (0.8 + 0.19208) / 1.38416
           = 0.99208 / 1.38416
           = 0.7167379...
    half = (z / (1 + z^2/n)) * sqrt(p_hat(1-p_hat)/n + z^2/(4n^2))
         = (1.96 / 1.38416) * sqrt(0.8*0.2/10 + 3.8416/400)
         = 1.4160274... * sqrt(0.016 + 0.009604)
         = 1.4160274... * sqrt(0.025604)
         = 1.4160274... * 0.1600125...
         = 0.2265811...
    lo = center - half = 0.7167379 - 0.2265811 = 0.4901568...
    hi = center + half = 0.7167379 + 0.2265811 = 0.9433191...

    (Verified independently with a plain Python expression using the same
    §1.2 formula, reproduced in test_wilson_matches_manual_formula below.)
    """
    result = common.wilson(8, 10, z=1.96)
    assert math.isclose(result.phat, 0.8, rel_tol=1e-9)
    assert math.isclose(result.lo, 0.4901568, abs_tol=1e-6), result.lo
    assert math.isclose(result.hi, 0.9433191, abs_tol=1e-6), result.hi
    print(f"  wilson(8, 10) = {result} -- OK")


def test_wilson_matches_manual_formula():
    """Cross-check common.wilson against the raw §1.2 formula for a second
    (k, n) pair, computed independently in this test file (not by calling
    common.wilson twice)."""
    k, n, z = 3, 20, 1.96
    phat = k / n
    z2 = z * z
    center = (phat + z2 / (2 * n)) / (1 + z2 / n)
    half = (z / (1 + z2 / n)) * math.sqrt(phat * (1 - phat) / n + z2 / (4 * n * n))
    expected_lo = max(0.0, center - half)
    expected_hi = min(1.0, center + half)

    result = common.wilson(k, n, z=z)
    assert math.isclose(result.phat, phat)
    assert math.isclose(result.lo, expected_lo)
    assert math.isclose(result.hi, expected_hi)
    print(f"  wilson(3, 20) = {result} matches manual §1.2 formula -- OK")


def test_fixture_has_all_cells_populated_and_non_degenerate():
    records = common.load_dyad_log(SYNTHETIC_LOG, validate=True)
    assert len(records) >= 45, f"expected ~50 records, got {len(records)}"

    cells = {}
    for r in records:
        key = (r["receiver_hardening"], r["source"], r["dose"])
        cells.setdefault(key, []).append(r["outcome_adopt"])

    expected_cells = {
        (h, s, d)
        for h in common.HARDENING_VALUES
        for s in common.SOURCE_VALUES
        for d in (1, 2, 3)
    }
    assert set(cells) == expected_cells, f"missing cells: {expected_cells - set(cells)}"

    degenerate = [k for k, v in cells.items() if len(set(v)) == 1]
    assert not degenerate, f"degenerate (all-same outcome_adopt) cells: {degenerate}"
    print(f"  all {len(expected_cells)} cells populated with non-degenerate outcome_adopt -- OK")


def test_score_reproduces_golden_file():
    # Use the same relative input path ("examples/synthetic_dyads.jsonl") that
    # was used to generate the golden file, so provenance.source_logs matches
    # exactly too (score.py records the path as given on argv, not resolved).
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "beta_out.json"
        result = score.score(
            ["examples/synthetic_dyads.jsonl"],
            str(out_path),
            placeholder=True,
        )
        produced = json.loads(out_path.read_text())

    golden = json.loads(GOLDEN_BETA.read_text())

    produced_stripped = _strip_volatile(produced)
    golden_stripped = _strip_volatile(golden)

    assert produced_stripped == golden_stripped, (
        "score.py output does not match examples/golden_beta.json "
        "(after excluding volatile provenance.generated_at)"
    )
    print("  score(synthetic_dyads.jsonl) == golden_beta.json (mod generated_at) -- OK")


def test_two_runs_are_identical_modulo_timestamp():
    with tempfile.TemporaryDirectory() as tmp:
        out1 = Path(tmp) / "run1.json"
        out2 = Path(tmp) / "run2.json"
        score.score([str(SYNTHETIC_LOG)], str(out1), placeholder=True)
        score.score([str(SYNTHETIC_LOG)], str(out2), placeholder=True)

        t1 = _strip_volatile(json.loads(out1.read_text()))
        t2 = _strip_volatile(json.loads(out2.read_text()))
        assert t1 == t2, "two runs on the same fixture diverged (mod generated_at)"
    print("  two successive runs are identical modulo generated_at -- OK")


def test_cli_matches_schema():
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "beta_cli.json"
        proc = subprocess.run(
            [sys.executable, str(HERE / "score.py"), str(SYNTHETIC_LOG), "-o", str(out_path)],
            cwd=str(HERE),
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, f"CLI failed: {proc.stderr}"
        table = common.load_beta_table(out_path)  # raises if schema-invalid
        assert table["provenance"]["PLACEHOLDER"] is False, (
            "real (non --placeholder) CLI runs must stamp PLACEHOLDER=false"
        )
    print("  CLI run produces schema-valid beta.json with PLACEHOLDER=false by default -- OK")


def test_relay_out_flag_emits_relay_table():
    with tempfile.TemporaryDirectory() as tmp:
        beta_path = Path(tmp) / "beta.json"
        relay_path = Path(tmp) / "relay.json"
        score.score(
            [str(SYNTHETIC_LOG)],
            str(beta_path),
            relay_out_path=str(relay_path),
            placeholder=True,
        )
        relay_table = common.load_beta_table(relay_path)  # same shape, validated
        assert relay_table["provenance"]["table_kind"] == "relay_rate"
        # relay rates should differ from adopt rates for at least one cell
        beta_table = common.load_beta_table(beta_path)
        assert relay_table["beta"] != beta_table["beta"], (
            "relay table should not be numerically identical to the beta table "
            "on this fixture (by construction, relay <= adopt per record)"
        )
    print("  --relay-out emits a schema-valid, distinct relay-rate table -- OK")


def test_mixed_operationalization_fails_loud():
    """Honesty rail: a dyad log mixing operationalization values must cause
    score.py to raise / exit nonzero, never silently resolve to one value."""
    with tempfile.TemporaryDirectory() as tmp:
        bad_log = Path(tmp) / "mixed_operationalization.jsonl"
        base_record = {
            "run_id": "bad-1", "ts": "2026-06-15T00:00:00+00:00", "seed": 1,
            "receiver_hardening": "naive", "source": "human",
            "operationalization": "channel", "dose": 1, "payload_id": "p1",
            "models": {"sender": "x", "receiver": "y"},
            "tokens": {"prompt": 0, "completion": 0, "cached": 0},
            "outcome_adopt": True, "outcome_relay": False, "raw_messages": [],
        }
        rec2 = dict(base_record, run_id="bad-2", operationalization="claimed", outcome_adopt=False)
        with open(bad_log, "w") as f:
            f.write(json.dumps(base_record) + "\n")
            f.write(json.dumps(rec2) + "\n")

        out_path = Path(tmp) / "should_not_be_written.json"
        try:
            score.score([str(bad_log)], str(out_path))
            raised = False
        except ValueError as e:
            raised = True
            assert "operationalization" in str(e), f"error message unclear: {e}"

        assert raised, "score() must raise ValueError on mixed operationalization"
        assert not out_path.exists(), "beta.json must NOT be written when scoring fails"

        # also check the CLI path exits nonzero
        proc = subprocess.run(
            [sys.executable, str(HERE / "score.py"), str(bad_log), "-o", str(out_path)],
            capture_output=True, text=True,
        )
        assert proc.returncode != 0, "CLI must exit nonzero on mixed operationalization"
        assert "operationalization" in proc.stderr.lower()
    print("  mixed operationalization fails loud (raise + nonzero exit) -- OK")
    # bad_log and out_path live only in the TemporaryDirectory, auto-cleaned.


def main():
    tests = [
        test_wilson_hand_check,
        test_wilson_matches_manual_formula,
        test_fixture_has_all_cells_populated_and_non_degenerate,
        test_score_reproduces_golden_file,
        test_two_runs_are_identical_modulo_timestamp,
        test_cli_matches_schema,
        test_relay_out_flag_emits_relay_table,
        test_mixed_operationalization_fails_loud,
    ]
    for t in tests:
        print(f"{t.__name__} ...")
        t()
    print(f"\nall {len(tests)} tests passed")


if __name__ == "__main__":
    main()
