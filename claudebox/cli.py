#!/usr/bin/env python3
"""cli.py -- single entry point for claudebox.

Dispatches `python -m claudebox <cmd> ...` (or `python3 cli.py <cmd> ...`
run directly from this directory) to the module that owns each subcommand:

    assay      -> assay.py     (spends tokens unless --dry-run)
    score      -> score.py     (token-free)
    simulate   -> simulate.py  (token-free)
    validate   -> validate.py  (spends tokens unless using injected fixtures)
    replay     -> render a dyad/game log as a readable transcript (token-free,
                  no network; implemented directly in this file)

This file does not re-implement any of assay/score/simulate/validate's logic:
it imports each module's `main(argv)` and forwards the remaining argv to it,
per 01_CONTRACTS.md §3 ("Integrate through these schemas / interfaces only").

Package layout note (see README.md "CLI wiring / package layout" section for
the full rationale): assay.py, score.py, simulate.py, validate.py, common.py
are flat sibling files in this directory and do `from common import ...` /
`import common` — i.e. they assume this directory is on sys.path, which is
how they already run standalone (`python3 assay.py ...`) and how their own
test files import `common`. To make `python -m claudebox <cmd>` work without
touching any of those already-built/committed files, this same directory
doubles as a package: it has an `__init__.py` (package marker) and a
`__main__.py` (the package entry point for `-m` execution). `__main__.py`
inserts this directory onto sys.path (it is not there by default under `-m`
execution of a package one level up) and then delegates to this file's
`main()`. Nothing in assay.py/score.py/simulate.py/validate.py/common.py was
modified to make this work.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

COMMANDS = ("assay", "score", "simulate", "validate", "replay")


def _dispatch_assay(rest: list[str]) -> int:
    import assay
    return assay.main(rest)


def _dispatch_score(rest: list[str]) -> int:
    import score
    return score.main(rest)


def _dispatch_simulate(rest: list[str]) -> int:
    import simulate
    return simulate.main(rest)


def _dispatch_validate(rest: list[str]) -> int:
    import validate
    return validate.main(rest)


# --------------------------------------------------------------------------
# replay -- render any dyad log as a readable transcript, token-free.
# --------------------------------------------------------------------------

def _render_message(msg: dict, indent: str = "    ") -> str:
    role = msg.get("role", "?")
    content = msg.get("content", "")
    if isinstance(content, str):
        text = content
    else:
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, dict):
                parts.append(json.dumps(block))
            else:
                parts.append(str(block))
        text = "\n".join(parts)
    wrapped_lines = []
    for line in text.splitlines() or [""]:
        wrapped_lines.append(indent + line)
    return f"{indent}[{role}]\n" + "\n".join(wrapped_lines)


def render_transcript(record: dict, index: int) -> str:
    """Render a single dyad-log record (01_CONTRACTS.md §2.1) as a readable,
    role-revealed transcript. Reads only fields already present on disk --
    no network, no model calls, no token spend.
    """
    lines: list[str] = []
    run_id = record.get("run_id", "?")
    ts = record.get("ts", "?")
    hardening = record.get("receiver_hardening", "?")
    source = record.get("source", "?")
    operationalization = record.get("operationalization", "?")
    dose = record.get("dose", "?")
    payload_id = record.get("payload_id", "?")
    models = record.get("models", {})
    tokens = record.get("tokens", {})
    outcome_adopt = record.get("outcome_adopt")
    outcome_relay = record.get("outcome_relay")

    lines.append("=" * 72)
    lines.append(f"[{index}] run_id={run_id}  ts={ts}")
    lines.append(
        f"    receiver_hardening={hardening}  source={source}  "
        f"operationalization={operationalization}  dose={dose}"
    )
    lines.append(
        f"    payload_id={payload_id}  sender_model={models.get('sender', '?')}  "
        f"receiver_model={models.get('receiver', '?')}"
    )
    lines.append(
        f"    tokens: prompt={tokens.get('prompt', '?')} "
        f"completion={tokens.get('completion', '?')} cached={tokens.get('cached', '?')}"
    )
    lines.append("-" * 72)

    raw_messages = record.get("raw_messages") or []
    if not raw_messages:
        lines.append("    (no raw_messages recorded for this record)")
    else:
        for msg in raw_messages:
            lines.append(_render_message(msg))
            lines.append("")

    lines.append("-" * 72)
    lines.append(f"    OUTCOME: adopted={outcome_adopt}   relayed={outcome_relay}")
    lines.append("=" * 72)
    return "\n".join(lines)


def replay(path: str, out=None) -> int:
    """Load a dyad-log JSONL file and print a readable transcript per record.

    Zero network, zero token spend: this only reads bytes already on disk.
    Works standalone on ANY shipped dyad log (real or synthetic/dry-run).
    """
    out = out or sys.stdout
    p = Path(path)
    if not p.exists():
        print(f"replay: no such file: {path}", file=sys.stderr)
        return 1

    n = 0
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            n += 1
            print(render_transcript(record, n), file=out)
            print(file=out)

    print(f"[replay] rendered {n} record(s) from {path}", file=out)
    return 0


def _dispatch_replay(rest: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="claudebox replay",
        description="Render a dyad/game log (JSONL) as a readable, role-revealed "
                    "transcript. Token-free: reads only fields already on disk.",
    )
    parser.add_argument("log", help="path to a dyad log JSONL file "
                                     "(e.g. examples/synthetic_dyads.jsonl)")
    args = parser.parse_args(rest)
    return replay(args.log)


_DISPATCH = {
    "assay": _dispatch_assay,
    "score": _dispatch_score,
    "simulate": _dispatch_simulate,
    "validate": _dispatch_validate,
    "replay": _dispatch_replay,
}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(
        prog="python -m claudebox",
        description="claudebox: agent-to-agent influence propagation study. "
                    "Dispatches to assay/score/simulate/validate/replay.",
    )
    parser.add_argument("command", choices=COMMANDS, help="subcommand to run")
    parser.add_argument("rest", nargs=argparse.REMAINDER,
                         help="remaining arguments, forwarded verbatim to the subcommand")
    args = parser.parse_args(argv)

    handler = _DISPATCH[args.command]
    return handler(args.rest)


if __name__ == "__main__":
    raise SystemExit(main())
