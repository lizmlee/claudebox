"""claudebox shared helpers: schema IO, Wilson CI, config hashing, provenance headers.

Pure Python stdlib only. See 01_CONTRACTS.md for schemas and math this implements.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, NamedTuple

STOCHASTICITY_DISCLAIMER = (
    "Seeds fix graph generation, seed-set choice, and IC RNG only. "
    "They do NOT fix model stochasticity, which lives solely in `assay` "
    "(live API sampling) and is not reproducible run-to-run."
)

REQUIRED_DYAD_FIELDS = (
    "run_id", "ts", "seed", "receiver_hardening", "source",
    "operationalization", "dose", "payload_id", "models", "tokens",
    "outcome_adopt", "outcome_relay", "raw_messages",
)

HARDENING_VALUES = ("naive", "hardened")
SOURCE_VALUES = ("human", "orchestrator")
OPERATIONALIZATION_VALUES = ("channel", "claimed")

SIM_CSV_FIELDS = (
    "topology", "N", "k", "rewire_p", "rho", "h", "source_mode", "phi",
    "rep", "seed", "R", "tau", "cascade", "R0",
)


# --------------------------------------------------------------------------
# Wilson score interval (01_CONTRACTS.md §1.2)
# --------------------------------------------------------------------------

class WilsonResult(NamedTuple):
    phat: float
    lo: float
    hi: float


def wilson(k: int, n: int, z: float = 1.96) -> WilsonResult:
    """Wilson score interval for k successes out of n trials.

    Correct at small n / extreme p, unlike the normal (Wald) approximation.
    """
    if n <= 0:
        raise ValueError("n must be > 0")
    if k < 0 or k > n:
        raise ValueError("k must be in [0, n]")
    phat = k / n
    z2 = z * z
    center = (phat + z2 / (2 * n)) / (1 + z2 / n)
    half = (z / (1 + z2 / n)) * math.sqrt(phat * (1 - phat) / n + z2 / (4 * n * n))
    lo = max(0.0, center - half)
    hi = min(1.0, center + half)
    return WilsonResult(phat, lo, hi)


# --------------------------------------------------------------------------
# Config hashing + provenance headers (§1.6)
# --------------------------------------------------------------------------

def config_hash(config: dict) -> str:
    """sha256 of the canonicalized (sorted-key) config, as a hex digest."""
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def provenance_block(config: dict, seed: int, generated_by: str, extra: dict | None = None) -> dict:
    """Standard provenance header embedded/attached to every claudebox artifact."""
    block = {
        "config_hash": config_hash(config),
        "seed": seed,
        "generated_by": generated_by,
        "generated_at": now_iso(),
        "stochasticity_disclaimer": STOCHASTICITY_DISCLAIMER,
    }
    if extra:
        block.update(extra)
    return block


def write_provenance_sidecar(output_path: str | Path, config: dict, seed: int,
                              generated_by: str, extra: dict | None = None) -> Path:
    """For artifacts with a fixed schema (e.g. sim_results.csv) that can't carry
    a provenance field inline, write a `<name>.provenance.json` sidecar next to it."""
    p = Path(output_path)
    sidecar = p.with_name(p.name + ".provenance.json")
    sidecar.write_text(json.dumps(provenance_block(config, seed, generated_by, extra), indent=2))
    return sidecar


# --------------------------------------------------------------------------
# Dyad log IO (§2.1) — logs/*.jsonl
# --------------------------------------------------------------------------

def validate_dyad_record(record: dict) -> None:
    missing = [f for f in REQUIRED_DYAD_FIELDS if f not in record]
    if missing:
        raise ValueError(f"dyad record missing fields: {missing}")
    if record["receiver_hardening"] not in HARDENING_VALUES:
        raise ValueError(f"bad receiver_hardening: {record['receiver_hardening']!r}")
    if record["source"] not in SOURCE_VALUES:
        raise ValueError(f"bad source: {record['source']!r}")
    if record["operationalization"] not in OPERATIONALIZATION_VALUES:
        raise ValueError(f"bad operationalization: {record['operationalization']!r}")


def load_dyad_log(path: str | Path, validate: bool = True) -> list[dict]:
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{line_no}: invalid JSON: {e}") from e
            if validate:
                validate_dyad_record(rec)
            records.append(rec)
    return records


def write_dyad_log(path: str | Path, records: Iterable[dict], validate: bool = True, append: bool = False) -> None:
    mode = "a" if append else "w"
    with open(path, mode, encoding="utf-8") as f:
        for rec in records:
            if validate:
                validate_dyad_record(rec)
            f.write(json.dumps(rec, sort_keys=True) + "\n")


# --------------------------------------------------------------------------
# beta.json IO (§2.2)
# --------------------------------------------------------------------------

def validate_beta_table(table: dict) -> None:
    for key in ("beta", "ci", "n", "provenance"):
        if key not in table:
            raise ValueError(f"beta table missing key: {key!r}")
    for hardening in HARDENING_VALUES:
        if hardening not in table["beta"]:
            raise ValueError(f"beta table missing hardening tier: {hardening!r}")
        for source in SOURCE_VALUES:
            if source not in table["beta"][hardening]:
                raise ValueError(f"beta table missing source {source!r} under {hardening!r}")


def load_beta_table(path: str | Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        table = json.load(f)
    validate_beta_table(table)
    return table


def write_beta_table(path: str | Path, beta: dict, ci: dict, n: dict, provenance: dict) -> None:
    table = {"beta": beta, "ci": ci, "n": n, "provenance": provenance}
    validate_beta_table(table)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(table, f, indent=2, sort_keys=True)


def is_placeholder(table: dict) -> bool:
    return bool(table.get("provenance", {}).get("PLACEHOLDER", False))


PLACEHOLDER_BANNER = (
    "=" * 70 + "\n"
    "  WARNING: PLACEHOLDER BETA VALUES IN USE.\n"
    "  These are NOT measured transmission rates. Any downstream numbers\n"
    "  (R, tau, thresholds, source gap) are illustrative only until real\n"
    "  beta from `assay` + `score` replaces this table.\n"
    + "=" * 70
)


# --------------------------------------------------------------------------
# sim_results.csv IO (§2.3)
# --------------------------------------------------------------------------

def write_sim_csv(path: str | Path, rows: Iterable[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SIM_CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row[k] for k in SIM_CSV_FIELDS})


def load_sim_csv(path: str | Path) -> list[dict]:
    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != list(SIM_CSV_FIELDS):
            raise ValueError(f"sim CSV header mismatch: {reader.fieldnames}")
        return list(reader)


# --------------------------------------------------------------------------
# config IO (§2.4) — minimal stdlib-only loader (JSON, or a flat YAML subset)
# --------------------------------------------------------------------------

_YAML_LINE_RE = re.compile(r"^(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*(?P<value>.*)$")


def _parse_yaml_scalar(raw: str) -> Any:
    raw = raw.split("#", 1)[0].strip()  # strip trailing comments
    if raw == "":
        return None
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [_parse_yaml_scalar(item.strip()) for item in inner.split(",")]
    if raw.lower() in ("true", "false"):
        return raw.lower() == "true"
    try:
        if any(c in raw for c in (".", "e", "E")):
            return float(raw)
        return int(raw)
    except ValueError:
        pass
    if raw[0] == raw[-1] == '"' or raw[0] == raw[-1] == "'":
        return raw[1:-1]
    return raw


def load_config(path: str | Path) -> dict:
    """Load config.json, or the flat `key: value` YAML subset used by 01_CONTRACTS §2.4.

    No third-party YAML parser: this is a deliberately minimal stdlib loader for
    the flat, non-nested config shape claudebox actually uses.
    """
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix == ".json":
        return json.loads(text)
    config: dict[str, Any] = {}
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = _YAML_LINE_RE.match(stripped)
        if not m:
            raise ValueError(f"{path}:{line_no}: cannot parse config line: {line!r}")
        config[m.group("key")] = _parse_yaml_scalar(m.group("value"))
    return config
