"""claudebox package marker.

This directory (`claudebox/`) serves double duty:
  1. It is where the flat, sibling-importing modules live: common.py,
     simulate.py, score.py, assay.py, validate.py, cli.py. Those files do
     `import common` / `from common import ...` (not package-relative
     imports), matching how they already run standalone and how their own
     test files (test_common.py, test_score.py) import them.
  2. It is ALSO the `claudebox` package, so `python -m claudebox <cmd>` works
     when invoked from the parent directory (`/home/user/claudebox/`).

See `__main__.py` for how these two roles are reconciled without modifying
any of the already-built flat modules, and see README.md's "CLI wiring /
package layout" section for the full rationale.
"""
