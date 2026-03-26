# Repository Guidance

Local Codex note:

For DebugOracle module work, look for specifications in [`docs/specs/README.md`](docs/specs/README.md) before reading module code.

Spec conventions:

- Module specs live under `docs/specs/`.
- The spec filename matches the module filename exactly.
- Each spec includes a `Code Path` entry pointing to the canonical module file.

When changing a Python module in `debugoracle/*.py`, update the matching spec in `docs/specs/<module>.md` in the same change.
