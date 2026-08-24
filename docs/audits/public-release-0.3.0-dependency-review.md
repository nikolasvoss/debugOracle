# Public Release 0.3.0 Runtime Dependency Review

**Recorded:** 2026-08-24
**Configuration:** `pyproject.toml`

## Decision

The supported runtime is pinned to `packaging==26.0` and `pypdf==6.16.1`.
Optional Docling and semantic profiles remain disabled and outside the
supported installer profile.

The isolated build backend is pinned separately to `setuptools==84.0.0`.
Official PyPI metadata records Python 3.10 or newer, wheel SHA-256
`51a52592b3b99e102b609654876bd65f19f999935166d1352678931132b0c670`,
and no known vulnerabilities at review time. The exact pin, together with the
fixed `SOURCE_DATE_EPOCH`, prevents later backend-resolution drift when the
same tag is rebuilt. It is a build requirement, not a shipped runtime package.

## `packaging==26.0`

- Problem: the installer previously duplicated version ordering and did not
  implement the complete PEP 440 contract required by the release manifest.
- Why the standard library/current code is insufficient: Python exposes no
  standard-library PEP 440 parser or specifier evaluator; retaining local
  parsers produced divergent behavior at installer trust boundaries.
- Expected gain: one canonical implementation for final, pre-release, dev,
  post, local, and epoch versions, with adversarial regression coverage.
- Security/maintenance: PyPA's `packaging` is the shared implementation used by
  Python packaging tools. Version 26.0 declares no runtime dependencies and is
  pinned exactly.
- License: official PyPI metadata declares
  `Apache-2.0 OR BSD-2-Clause`; the wheel SHA-256 is
  `b36f1fef9334a5588b4166f8bcd26a14e521f2b55e6b9de3aaa80d3ff7a37529`.
- Footprint: one universal wheel of 74,366 bytes and no transitive runtime
  packages.
- Determinism/reproducibility: the exact pin removes resolver drift; installer
  comparisons are pure and do not depend on locale, clock, or network state.
- Alternatives rejected: expanding the two ad-hoc parsers was rejected because
  it would duplicate a compatibility standard and retain two sources of truth.

## Vulnerability audit

`pip-audit 2.10.1` was run against an explicit requirements input containing
only `packaging==26.0` and `pypdf==6.16.1`. It completed successfully with
`No known vulnerabilities found` on 2026-08-24.

The outcome is point-in-time evidence, not a guarantee that future advisories
will not affect these versions. Release automation should rerun the audit for
every candidate.
