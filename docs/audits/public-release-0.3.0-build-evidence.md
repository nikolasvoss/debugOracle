# Public Release 0.3.0 Build Evidence

**Recorded:** 2026-08-24
**Environment:** Ubuntu 24.04 x86-64, Python 3.12.3, pipx, isolated PEP 517
builds

## Candidate identity

- Canonical version: `0.3.0`
- Intended tag: `v0.3.0` (confirmed absent from `origin` before metadata freeze)
- Fixed `SOURCE_DATE_EPOCH`: `1787529600` (`2026-08-24T00:00:00Z`)
- Isolated build backend: `setuptools==84.0.0`
- Wheel: `debugoracle-0.3.0-py3-none-any.whl`
- Size: `147822` bytes
- SHA-256:
  `caf3d4896d688b4b4f85d6f8451e6e21b8e52b2127e18b81e264a52b6a17f9b0`

Two independent isolated builds produced the same wheel filename, size, and
SHA-256. After recording the hash and size in `release/install-manifest.json`,
a third isolated build produced the same wheel hash and size, confirming that
the manifest is outside the wheel payload.

The GitHub artifact gate uses the same exact Python 3.12.3 interpreter as this
canonical build. The separately maintained compatibility matrix continues to
exercise the current Python 3.10 through 3.14 releases.

The two generated source distributions both passed metadata validation but
were not byte-identical (`c711be3a...` versus `de0db7e...`). The sdist is not a
0.3.0 publication/install asset (GitHub Release wheel only; no PyPI release),
so the immutable installer identity is unaffected. This is retained as a
non-blocking reproducibility limitation rather than overstating equivalence.

## Automated artifact checks

- `twine check` passed for the final wheel and sdist.
- Wheel inventory contains the package, entry point, metadata, and project
  license and excludes tests, private notes, Git/cache data, and local evidence.
- A fresh venv installed the wheel plus exact runtime dependencies
  `packaging==26.0` and `pypdf==6.16.1`.
- The installed `dbgoracle --version` returned `0.3.0`; top-level help rendered
  successfully without exposing internal installer subcommands.

## Real disposable pipx lifecycle

Using isolated temporary `PIPX_HOME` and `PIPX_BIN_DIR` directories:

1. Fresh wheel install succeeded and reported `0.3.0`.
2. Force-upgrade/reinstall of the same immutable wheel succeeded and reported
   `0.3.0`.
3. `pipx uninstall debugoracle` succeeded; the temporary command and venv were
   absent afterward.

## Publication-dependent gates

- The public GitHub Release asset cannot be downloaded and compared until the
  release is uploaded. The published asset must match the filename, size, and
  SHA-256 above before the release is announced.
- Hardware-in-the-loop evidence was not fabricated. RTT, OpenOCD discovery,
  SVD register capture, and memory-read checks on a physical reference target
  remain a manual pre-announcement gate when that hardware is available.
