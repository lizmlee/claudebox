"""Acceptance test for common.py (Phase 0). Run: python3 test_common.py"""
import math
import tempfile
from pathlib import Path

import common


def test_wilson_hand_checked():
    # k=8, n=10, z=1.96 -> hand-derivable Wilson interval, widely cited as ~(0.49, 0.94).
    r = common.wilson(8, 10, z=1.96)
    assert math.isclose(r.phat, 0.8, rel_tol=1e-9)
    assert math.isclose(r.lo, 0.4903, abs_tol=1e-3), r.lo
    assert math.isclose(r.hi, 0.9435, abs_tol=1e-3), r.hi


def test_wilson_edges():
    # k=0: lower bound must be 0, not negative.
    r0 = common.wilson(0, 10)
    assert r0.lo == 0.0
    # k=n: upper bound must be 1, not >1.
    rn = common.wilson(10, 10)
    assert rn.hi == 1.0


def test_config_hash_stable_under_key_order():
    h1 = common.config_hash({"a": 1, "b": 2})
    h2 = common.config_hash({"b": 2, "a": 1})
    assert h1 == h2


def test_dyad_log_roundtrip():
    rec = {
        "run_id": "r0", "ts": common.now_iso(), "seed": 0,
        "receiver_hardening": "naive", "source": "human",
        "operationalization": "channel", "dose": 1, "payload_id": "p0",
        "models": {"sender": "m", "receiver": "m"},
        "tokens": {"prompt": 1, "completion": 1, "cached": 0},
        "outcome_adopt": True, "outcome_relay": False, "raw_messages": [],
    }
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "dyads.jsonl"
        common.write_dyad_log(path, [rec])
        loaded = common.load_dyad_log(path)
        assert loaded == [rec]


def test_config_yaml_lite_loader():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "config.yaml"
        path.write_text(
            "topology: er  # comment\n"
            "N: 1000\n"
            "rewire_p: 0.1\n"
            "rho_sweep: [0.01,0.02,0.05]\n"
            "source_mode: all_orchestrator\n"
        )
        cfg = common.load_config(path)
        assert cfg["topology"] == "er"
        assert cfg["N"] == 1000
        assert cfg["rewire_p"] == 0.1
        assert cfg["rho_sweep"] == [0.01, 0.02, 0.05]


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} tests passed.")
