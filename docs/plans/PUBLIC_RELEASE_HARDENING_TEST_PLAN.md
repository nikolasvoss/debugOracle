# Public Release Hardening Test Plan

**Status:** Ready for implementation

## Principles

- Add the failing regression before each fix.
- Use real filesystem and subprocess behavior where practical; fake only
  external services, pipx state, sockets, `/proc` races, and injected failures.
- Bound every parser, network, and process test with an explicit timeout.
- Assert exit code, stdout, stderr, artifacts, and recovery state separately.
- Use outside sentinel files for path-safety tests; never target real user data.
- Run deterministic cases at least twice and compare canonical bytes.
- HIL results supplement but never replace offline regression tests.

## Test Environments

| Environment | Purpose | Required result |
|---|---|---|
| Fresh recursive clone, Ubuntu 24.04 x86-64, Python 3.12 | Authoritative release candidate | All automated gates pass |
| Python 3.10 through 3.14 on Ubuntu | Declared compatibility | Pass or metadata explicitly excludes failing versions |
| Fresh temporary venv from built wheel | Packaging/entrypoint | Install and CLI smoke pass |
| Disposable pipx home | Installer lifecycle | Install, upgrade, verify, uninstall pass |
| Supported embedded HIL setup | Transport/target integration | Sanitized manual matrix passes |

## Automated Matrix

### Packaging and clean clone

| Case | Expected behavior | Evidence |
|---|---|---|
| Isolated sdist/wheel build | Both artifacts created without warnings promoted to errors | Build log and artifact list |
| Metadata validation | README and package metadata render correctly | `twine check` |
| Wheel contents | Required license/package/entrypoint present; private/dev files absent | Archive inventory assertion |
| Fresh wheel install | Real `dbgoracle` entrypoint reports candidate version | Temporary-venv smoke |
| Recursive clone | All gitlinks initialized at pinned commits | `git submodule status --recursive` |
| Non-recursive clone | Release script fails immediately with actionable recovery command | Script regression test |
| Repeat build | Candidate wheels have identical SHA-256 under fixed inputs | Hash comparison |

The fixed build epoch comes from the documented release date and remains
unchanged across the manifest-hash commit. It must not be recomputed from the
new commit timestamp.

### Safe filesystem writes

For each automatically derived output family—snapshot, persisted GDB/RTT input,
RTT state, runtime metadata, and managed logs—test:

| Case | Expected behavior |
|---|---|
| New regular target | Correct bytes and mode written |
| Existing regular target | Documented replace/append behavior |
| Final target symlink outside workspace | Controlled rejection; outside sentinel unchanged |
| Parent directory symlink outside workspace | Controlled rejection; outside sentinel unchanged |
| Nested `..` or canonical escape | Controlled rejection |
| Parent swapped during operation | Operation uses held directory identity or fails closed |
| Short write / ENOSPC / fsync failure | Prior canonical file remains valid |
| Replace failure | Temp file cleaned; prior canonical file remains valid |
| Concurrent reader | Sees old or new complete canonical JSON, never partial JSON |
| Explicit safe absolute output | Allowed only through explicit-output policy |
| Explicit symlink target | Rejected unless a separately specified contract explicitly permits it |

RTT streaming adds:

- safe create;
- safe truncate;
- safe append;
- connect timeout writes valid atomic state but does not create/truncate an
  unsafe log target;
- capture interruption reports partial byte count and recoverable state.

### GDB/MI parser

Retain every existing valid fixture and add bounded cases for:

- `^done,result=[}]`;
- mismatched list/tuple closing delimiter;
- empty value after `=`;
- trailing comma and repeated comma;
- unterminated string and escape;
- EOF inside nested list/tuple;
- unexpected closer at each nesting level;
- bounded deeply nested valid and invalid values;
- noise records already supported by transcript parsing.

Assertions:

- valid inputs preserve the exact parsed structure;
- malformed inputs raise/record `MIParseError` with a stable position;
- no case exceeds the test timeout;
- transcript ingestion salvages unrelated valid records and records parse
  warnings according to the existing evidence-first contract.

### Run/stop process identity

| Case | Expected behavior |
|---|---|
| Matching PID/start time/argv/workspace | SIGTERM sent and clean stop reported |
| PID reused with different start time | No signal; stale identity reported |
| Similar argv containing `run` and `debugoracle` | No signal |
| Same process, different workspace | No signal |
| Metadata symlink or malformed JSON | No signal; controlled unsafe-state result |
| `/proc` missing or permission denied | No signal; fail closed |
| Identity changes before escalation | SIGKILL is not sent |
| Already exited process | Idempotent stopped/stale result |
| Legacy runtime schema | No automatic kill; migration/recovery instruction |

Use a real harmless child process for the positive integration case. Use an
injected process-inspection seam for deterministic PID-reuse and timing cases.

### Installer and supply chain

| Case | Expected behavior |
|---|---|
| Valid bounded HTTPS manifest | Parsed into supported schema |
| HTTP manifest/source | Rejected before network/install action |
| Redirect to HTTP or unexpected host | Rejected |
| Oversized manifest or wheel | Bounded rejection and cleanup |
| Unknown schema/package/artifact kind | Rejected |
| Correct release wheel hash | Local verified file passed to pipx |
| Incorrect/missing hash | No pipx mutation; temp file removed |
| Interrupted download | No pipx mutation; temp file removed |
| pipx install/upgrade failure | Structured deterministic outcome |
| Post-install inspection failure | Structured deterministic outcome, no traceback |
| Installed old/final/rc/dev/post version | Correct PEP 440 action selected |
| Local checkout override | Explicit local source wins and is reported as local |

PEP 440 table must include equality and ordering for final, rc, dev, post,
local, and epoch forms plus invalid input. Test `SpecifierSet` behavior for the
supported Python and installer version constraints.

### CLI contracts

| Case | Exit | stdout | stderr/artifact |
|---|---:|---|---|
| `fetch` MI + RTT | 0 | primary result only | no false warning |
| `fetch` GDB only | 0 | primary result only | RTT warning plus structured warning |
| `fetch` RTT only | 0 | primary result only | GDB warning plus structured warning |
| `fetch` no valid source | 2 | no mixed error | actionable resolution error |
| malformed required input | 1 or specified controlled code | no traceback | precise error |
| port `0`, `65536`, negative, nonnumeric | 2 | argparse contract | no connection attempt |
| port `1`, `65535` | normal command path | normal | no validation rejection |
| repeated deterministic report | 0 | byte-identical | stable stderr |

Run top-level and command-specific help/reference checks for every documented
command and option, including `docs doctor`, readiness commands, `init-workspace
--auto`, and the absence of removed `docs search --semantic`.

### Documentation and metadata

Automated assertions cover:

- canonical version equals manifest version and expected release tag;
- manifest release URL and wheel filename contain the selected version;
- SECURITY supports the selected series and does not claim a withdrawn series;
- changelog contains one dated section for the selected release;
- README clone instructions initialize submodules;
- documented schema equals `CURRENT_BUNDLE_SCHEMA_VERSION`;
- every documented CLI flag appears in parser help or is explicitly marked
  internal;
- optional profiles are described as blocked while their license gate is closed;
- no private notes, caches, local snapshots, or unlicensed removed assets occur
  in tracked or built release inventories.

### Recovery and failure injection

Run a combined recovery suite for:

- interrupted atomic write;
- ENOSPC-like failure;
- malformed MI;
- RTT connection timeout;
- stale/reused PID;
- manifest timeout/oversize;
- checksum mismatch;
- pipx failure after download;
- post-install inspection failure.

Each test asserts the previous user installation or evidence state remains
recoverable and the CLI returns a controlled outcome. For an upgrade followed
by an inspection failure, recoverable means a deterministic `state unknown`
result with inspection/remediation commands and no additional mutation; it
does not claim byte-exact rollback without a trusted prior-version artifact.

## Manual / HIL Matrix

Record date, OS, architecture, Python, pipx, DebugOracle commit/version,
OpenOCD/GDB versions, board/device, probe, and sanitized artifact hashes.

| Workflow | Required evidence |
|---|---|
| Fresh install from public candidate asset | Installer outcome, version, wheel hash |
| Upgrade from latest supported prior version | Preserved config and new version |
| Attempted rc-to-final upgrade | Stable final correctly replaces older rc |
| Uninstall | Package removed; only managed PATH lines changed |
| Real RTT capture | Bytes, state transitions, timeout/stop behavior |
| `run --detach` then `stop` | Correct process identity and cleanup |
| OpenOCD TCL discovery | Correct bounded discovery and error handling |
| SVD register capture | Read-only register evidence with provenance |
| Bounded memory read | Requested address/size only; limit enforced |
| Hardware absent/unreachable | Controlled failure; no target or source mutation |

If HIL infrastructure is unavailable, the release remains blocked or the public
hardware claim must be narrowed through an explicit spec change. It is not a
valid exception merely because offline tests pass.

## Focused Commands

Expected focused suites after implementation:

```bash
.venv/bin/pytest tests/test_safe_io.py tests/test_artifact_schema.py tests/test_pipeline_renderers.py -q --tb=short
.venv/bin/pytest tests/test_mi_parse.py tests/test_cli_flow.py -q --tb=short
.venv/bin/pytest tests/test_rtt_capture.py tests/test_run_stop.py -q --tb=short
.venv/bin/pytest tests/test_installer.py tests/test_installer_backend_manifest.py tests/test_install_bootstrap.py tests/test_uninstall_bootstrap.py -q --tb=short
.venv/bin/pytest tests/test_release_version_metadata.py tests/test_public_release_contract.py tests/test_reference_workspace_samples.py tests/test_verify_workflow_docs.py -q --tb=short
```

Final gates:

```bash
./scripts/verify.sh fast
./scripts/verify.sh full
./scripts/verify-release.sh
pre-commit run --all-files
```

## Pass / Fail Rule

Temporary exception recorded 2026-08-24: pull-request and `main` CI may omit
the private reference-workspace checkout and deselect only its content-dependent
tests. The workflow must report the omission. This exception does not apply to
a tag: release-tag validation must initialize and verify the complete recursive
submodule graph, so AC-003 remains open until the reference repository is
publicly readable or equivalently distributed.

- Any critical/high security finding, failed AC, failed provenance item,
  distribution-build error, dirty/missing submodule, or failed HIL release case
  blocks publication.
- Medium findings require a fix or an explicit owner, rationale, and dated
  follow-up accepted before the ship gate.
- Low findings may ship only when tracked and unrelated to correctness,
  security, data integrity, or public contract accuracy.
