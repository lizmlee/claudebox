"""Package entry point for `python -m claudebox <cmd> ...`.

Run from the PARENT of this directory, e.g.:

    cd /home/user/claudebox
    python -m claudebox simulate --config claudebox/examples/config.yaml \\
        --beta claudebox/examples/beta_placeholder.json --out /tmp/out.csv

Why this file exists / what it does
------------------------------------
Under `python -m claudebox`, Python puts the PARENT directory
(`/home/user/claudebox`) on sys.path[0], not this package directory itself
(verified empirically; this is standard `-m` package-execution behavior).
But common.py/simulate.py/score.py/assay.py/validate.py/cli.py are flat
files that import each other as top-level modules (`import common`), which
only resolves if THIS directory is on sys.path. Rather than rewrite those
already-built-and-committed modules to use package-relative imports, this
thin shim inserts this directory onto sys.path before importing anything,
then delegates to cli.main(). This is the only place that path manipulation
happens.
"""
from __future__ import annotations

import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import cli  # noqa: E402  (must follow the sys.path fix above)

if __name__ == "__main__":
    raise SystemExit(cli.main(sys.argv[1:]))
