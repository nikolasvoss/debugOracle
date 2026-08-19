# Automatic Workspace Initialization Security Review

Date: 2026-08-19

Gate: mandatory `/security-review`

Reviewed baseline: `799bfa7`

Task spec:
[`AUTOMATIC_WORKSPACE_INIT_TASK_SPEC.md`](../plans/AUTOMATIC_WORKSPACE_INIT_TASK_SPEC.md)

Risk register:
[`AUTOMATIC_WORKSPACE_INIT_RISK_REGISTER.md`](../plans/AUTOMATIC_WORKSPACE_INIT_RISK_REGISTER.md)

Code-review input:
[`automatic-workspace-init-code-review.md`](automatic-workspace-init-code-review.md)

## Result

- `risk_tier`: high
- `status`: issues_found
- `gate`: pass with fixes and tracked non-critical residual risks
- `blockers`: none for this security gate

No critical or high-severity finding remains open. The review found and fixed
two high-severity issues: unsafe document-sidecar storage aliases and a pinned
PDF parser version affected by published resource-consumption advisories.

The repository now declares `pypdf==6.16.1`. The local development environment
still contained 6.9.2 after an environment update was not authorized, so the
functional PDF suite below validates compatibility against 6.9.2, not the new
runtime pin. A clean-environment install must prove that 6.16.1 is selected and
run the same PDF tests before `/ship`; this is a release-validation condition,
not an unresolved source-code vulnerability.

## Findings

### Critical

None.

### High — fixed

#### SR-AWI-001: Sidecar work paths could follow attacker-controlled symlinks

- **Evidence:** Authorized automatic ingestion crosses into the shared sidecar
  writer at `debugoracle/cli/commands/init_workspace.py:189-211`. Before this
  review, `ingest_document` derived adjacent sidecar, staging, publish, and
  backup paths and then read or wrote them without rejecting a pre-existing
  symlink. The hardened boundary is now at
  `debugoracle/docs_sidecar.py:431-442` and
  `debugoracle/docs_sidecar.py:961-1000`; failed-result persistence rechecks the
  same boundary at `debugoracle/docs_sidecar.py:1803-1833`.
- **Impact:** A malicious workspace could redirect an authorized `--auto --yes`
  run to read sidecar state from, or write envelope/index/checkpoint data into,
  a same-user path outside the workspace.
- **Remediation:** Reject symlinked or non-directory sidecar storage roots and
  symlinked/non-regular known sidecar files before freshness checks or writes.
  Failed ingestion now returns structured evidence without persisting through
  an unsafe path. The regressions at `tests/test_auto_init_cli.py:391-485`
  cover sidecar, staging, publish, and backup directory aliases plus known-file
  aliases and prove external data remains unchanged.

#### SR-AWI-002: The base parser pin was affected by known PDF resource attacks

- **Evidence:** The parser calls `PdfReader` and page `extract_text()` at
  `debugoracle/docs_sidecar.py:1278-1312`. The former pin, pypdf 6.9.2, is in
  the affected ranges of official advisories for excessive runtime or memory
  use, including an XForm issue specifically reached during text extraction.
  The patched pin is `pypdf==6.16.1` at `pyproject.toml:21-23`, with license and
  provenance evidence in
  `docs/audits/public-alpha-p0-python-dependency-licenses.json` and
  `THIRD_PARTY_NOTICES.md:88-99`.
- **Impact:** A crafted local PDF, parsed after consent, could stall the agent
  process or consume excessive memory.
- **Remediation:** Pin the current security release 6.16.1. It is a pure-Python,
  BSD-3-Clause package with no required transitive dependency, so the update
  does not expand the runtime dependency footprint. Official evidence:
  [GHSA-23w6-3w8w-8484](https://github.com/py-pdf/pypdf/security/advisories/GHSA-23w6-3w8w-8484),
  [GHSA-763m-79hh-57f2](https://github.com/py-pdf/pypdf/security/advisories/GHSA-763m-79hh-57f2),
  [GHSA-fc8x-2rww-xw9m](https://github.com/py-pdf/pypdf/security/advisories/GHSA-fc8x-2rww-xw9m),
  [GHSA-fwg2-594c-jp42](https://github.com/py-pdf/pypdf/security/advisories/GHSA-fwg2-594c-jp42),
  and the [attested PyPI 6.16.1 release](https://pypi.org/project/pypdf/6.16.1/).

### Medium — residual, non-blocking

#### SR-AWI-003: Validation and filesystem use are not descriptor-atomic

- **Evidence:** Input and output components are checked before later opens or
  writes at `debugoracle/cli/commands/init_workspace.py:284-310`,
  `debugoracle/cli/commands/init_workspace.py:473-497`, and
  `debugoracle/docs_sidecar.py:961-1000`.
- **Impact:** A concurrent same-user process with workspace write access could
  replace a checked component between validation and use. The non-concurrent
  symlink cases are closed by the current checks.
- **Remediation:** If hostile concurrent workspace mutation enters the release
  threat model, introduce a cross-platform descriptor-relative writer using
  no-follow opens and identity revalidation immediately before atomic rename.

#### SR-AWI-004: PDF parsing remains in-process without an OS resource envelope

- **Evidence:** `PyPDFParser.parse` invokes pypdf directly in the CLI process at
  `debugoracle/docs_sidecar.py:1278-1312`.
- **Impact:** Version 6.16.1 fixes the known reviewed advisories above, but a
  future parser defect or extreme valid document can still consume CLI CPU or
  memory until the process is interrupted.
- **Remediation:** Track pypdf security releases continuously. If stronger
  isolation is required, define a separate behavior/spec slice for a bounded
  worker process with CPU, memory, output-size, and wall-clock limits while
  retaining deterministic failure evidence.

#### SR-AWI-005: Scaffold application is recoverable but not transactional

- **Evidence:** Capability failures are normalized and application continues at
  `debugoracle/cli/commands/init_workspace.py:103-140` and
  `debugoracle/cli/commands/init_workspace.py:313-366`; the existing writer
  persists three VS Code files separately.
- **Impact:** An I/O failure can leave a subset of managed scaffold files.
  Automatic mode reports `partial`, preserves current paths, and an unchanged
  rerun is idempotent, so the state is visible and recoverable rather than
  silently corrupt.
- **Remediation:** A future transactional-scaffold design should stage all
  managed files, fsync as required, and publish them as one documented recovery
  protocol. This is an architecture change, not a safe patch for this gate.

### Low

None.

## Trust-boundary verification

- **Consent:** `--yes` is the sole authorization that lets automatic discovery
  cross the PDF parse boundary
  (`debugoracle/cli/commands/init_workspace.py:96-105` and
  `debugoracle/cli/commands/init_workspace.py:189-211`). Without it, the command
  inventories candidates only; the parser/write tripwire test is
  `tests/test_auto_init_cli.py:24-74`.
- **Untrusted paths and JSONC:** inventory bounds config input at 128 KiB and
  candidate traversal at fixed limits (`debugoracle/readiness.py:18-20`). It
  rejects file/directory symlinks, outside-root paths, non-regular files, and
  ambiguous selections before application. JSONC strings are normalized only
  as workspace-contained file paths.
- **No discovered execution:** discovered ELF, SVD, and OpenOCD strings remain
  data used in deterministic JSON/scaffold output. Automatic init imports or
  invokes no subprocess, shell, socket, debugger transport, OpenOCD client,
  network client, build, probe, flash, or target operation. The live-I/O
  tripwire remains at `tests/test_auto_init_cli.py:745-771`.
- **User-owned configuration:** automatic output checks reject symlinked and
  non-regular destinations. Existing VS Code files retain the managed-marker,
  attach, and explicit `--force` ownership rules; blocked files are reported
  rather than overwritten.
- **Partial-state integrity:** documentation, scaffold, and register
  capabilities are applied independently and aggregated after every safe
  attempt. Per-document failures and re-inventory errors remain in structured
  output, so successful independent evidence is not hidden.
- **Secrets and logging:** the new path emits candidate paths, provenance,
  fixed remediation text, and normalized parser errors. It does not read
  environment credentials or log source document contents. JSON rendering
  escapes control characters; text rendering does not print application error
  objects.

## Dependency review

- Problem: the previous exact parser pin was inside multiple published affected
  ranges used by automatic text extraction.
- Update: exact `pypdf==6.16.1`; no new package and no transitive runtime
  dependency added.
- License/maintenance/provenance: BSD-3-Clause; official PyPI Trusted Publishing
  attestation and signed upstream tag recorded in the dependency audit.
- Determinism/reproducibility: the exact pin retains reproducible dependency
  selection. Existing page-order, normalization, warning, encrypted/malformed,
  and idempotence contracts remain the required regression suite.
- Alternative rejected: keeping 6.9.2 with application-level size checks would
  not address small crafted PDFs that trigger the published parser loops or
  amplification paths.

## Validation evidence

- `python3 -m unittest tests.test_auto_init_planner tests.test_auto_init_cli tests.test_docs_sidecar tests.test_public_release_contract`
  - 89 tests passed.
  - Includes missing-consent parser/write tripwires, authorized real PDF
    ingestion, malformed/encrypted PDF behavior, symlink containment,
    independent capability failures, idempotence, no-subprocess/no-socket
    tripwires, and dependency/license contract checks.
- Focused `ruff-check`: passed.
- Focused `ruff-format`: passed after applying its one deterministic reformat.
- `pyright`: passed.
- `bandit`: passed.
- `git diff --check`: passed before final staging.
- Local environment constraint: `python3 -m pip show pypdf` reported 6.9.2.
  The attempted environment update was not authorized and was not retried.

The mandatory clean-environment release gate must install the declared base
dependency, assert `pypdf.__version__ == "6.16.1"`, and run the same PDF suite
before `/ship`.
