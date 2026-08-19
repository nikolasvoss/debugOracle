# Automatic Workspace Initialization Task Spec

Status: Approved for TDD implementation

Affected specifications:

- [`init_workspace`](../specs/init_workspace.md)
- [`readiness`](../specs/readiness.md)
- [`docs_cli`](../specs/docs_cli.md)
- [`cli`](../specs/cli.md)

## Problem Statement

The explicit `dbgoracle init-workspace` flow requires users or coding agents to
provide an executable and OpenOCD configuration before any workspace setup can
start. That prevents an otherwise useful documentation index or unambiguous SVD
default from being initialized when hardware-debug inputs are absent.

Add an opt-in automatic mode that inventories trusted workspace locations,
initializes each capability whose inputs are unambiguous, and reports precise
next actions for the rest. A user should be able to put vendor PDFs in
`docs/vendor/`, put one SVD in `.dbgoracle/`, ask an agent to initialize the
workspace, and receive useful local documentation access even without a board,
probe, OpenOCD setup, compiler, or installed embedded toolchain.

## Public Interface

- Add `dbgoracle init-workspace --workspace-root <path> --auto`.
- In automatic mode, `--executable`, `--svd-file`, and repeatable
  `--openocd-config` are optional. An explicit value always takes precedence
  over a discovered value for the same input.
- Add `--yes` as explicit authorization to parse and persist sidecars for PDFs
  discovered under `doc/` or `docs/`. Automatic mode without `--yes` still
  initializes independent capabilities and reports the docs candidates and the
  exact rerun action.
- Existing non-automatic invocations retain their current required inputs,
  overwrite/attach rules, outputs, and exit-code semantics.
- Automatic JSON output uses a versioned deterministic payload and adds a
  `capabilities` list. Each capability reports `complete`, `partial`, or
  `unavailable`, its selected inputs with provenance, and ordered next actions.
- Overall status remains `complete`, `partial`, or `failed`, mapped to exit codes
  `0`, `2`, and `1` respectively. A docs-only successful initialization is
  `partial`, never `failed`, because hardware setup remains actionable.

The coding-agent golden path is:

```bash
dbgoracle init-workspace --workspace-root . --auto --yes --format json
```

The command is non-interactive. `--yes` conveys authorization; automatic mode
must not add a TTY prompt whose answer would make output non-reproducible.

## Scope

In scope:

- Extend the existing bounded `collect_workspace_plan` path as the single
  automatic-initialization inventory.
- Reuse the existing docs candidate discovery and docs ingestion APIs; do not
  implement a second PDF scanner or parser.
- Resolve executable, SVD, existing Cortex-Debug `configFiles`, and PDF inputs
  using the deterministic rules below.
- Ingest docs independently of Cortex-Debug/OpenOCD scaffold readiness.
- Preserve the current fresh/attach ownership boundary for `.vscode` files.
- Produce deterministic text and JSON summaries suitable for a coding agent.

Out of scope:

- Installing a compiler, GDB, OpenOCD, VS Code, Cortex-Debug, drivers, or udev
  rules.
- Downloading reference manuals, SVD files, firmware, board profiles, or any
  other vendor resource.
- Probing, flashing, resetting, halting, or otherwise contacting a target.
- Building firmware or choosing a board/probe based on a filename heuristic.
- Selecting arbitrary `.cfg` files and inferring an interface/target pairing.
- Moving, rewriting, or deleting user-owned source documents or VS Code files.
- Semantic embeddings by default; automatic docs ingestion uses `pypdf` and
  lexical indexing unless an explicit future behavior change is specified.

## Architecture and Data Flow

The existing Acquire → Normalize → Reduce → Persist → Render model remains
unchanged.

1. **Acquire:** `collect_workspace_plan` performs local-only, bounded discovery.
   It reuses the docs-sidecar candidate-discovery primitive and bounded JSONC
   reading; no CLI command launches or probes hardware.
2. **Normalize:** a pure automatic-init planner combines discovered candidates,
   existing DebugOracle/Cortex-Debug configuration, and explicit CLI inputs.
   Each normalized input records its source: `explicit`, `workspace_setting`,
   `cortex_debug_launch`, or `workspace_discovery`.
3. **Reduce:** deterministic selection rules produce a per-capability plan. An
   ambiguity is a result, not permission to choose.
4. **Persist:** the existing init-workspace writer applies only the planned
   DebugOracle-owned scaffold/fragments; the existing docs API writes sidecars
   only when `--yes` is present. Capability application is isolated so a docs
   failure cannot suppress safe scaffold work and missing hardware inputs cannot
   suppress docs ingestion.
5. **Render:** the CLI aggregates ordered capability results, required actions,
   and overall status. stdout contains the result; stderr is reserved for a
   command-level failure that cannot produce a structured result.

The planner must be callable without writes. CLI orchestration must not duplicate
candidate traversal, input precedence, or ambiguity decisions.

## Deterministic Discovery and Selection Rules

General rules:

1. Resolve the workspace root once. Reject a missing root.
2. Do not follow file or directory symlinks. Every selected path must resolve
   within the workspace root and be a regular readable file.
3. Bound entry count, file count, config size, and reported candidate count.
   Truncation blocks automatic selection only for the affected candidate class;
   it does not suppress explicit inputs or an independent capability.
4. Normalize to resolved absolute paths, deduplicate, and sort lexicographically
   before selection and rendering.
5. Never resolve a tie by traversal order, modification time, filename length,
   or a board-family guess.

Input rules:

- **Executable:** explicit `--executable` wins. Otherwise select only when the
  existing workspace-plan roots contain exactly one `.elf`. Zero is unavailable;
  more than one is ambiguous/partial.
- **SVD:** explicit `--svd-file` wins, then a valid existing
  `debugoracle.svdFile`, then exactly one direct `.dbgoracle/*.svd` candidate.
  Multiple candidates are ambiguous. No SVD is copied or generated.
- **OpenOCD:** explicit flags win. Otherwise reuse `configFiles` only when
  exactly one readable Cortex-Debug launch configuration supplies one non-empty,
  ordered list of workspace-contained strings. Raw `.cfg` candidates are
  reported as evidence but are never paired or selected automatically.
- **VS Code ownership:** an absent `.vscode` scaffold may use current fresh-mode
  writes. Existing user-owned files use current attach/merge-fragment behavior;
  automatic mode never silently edits them. DebugOracle-managed files retain the
  existing `--force` contract.
- **Documents:** include sorted PDFs under `doc/` and `docs/`, including
  `docs/vendor/`, through the existing docs discovery primitive. Ignore existing
  sidecar directories, symlink escapes, unreadable files, and candidates beyond
  the bound. `--yes` authorizes the existing idempotent `pypdf` ingest path.

## Capability and Overall Status Rules

Capabilities are rendered in this fixed order: `documentation`, `debug_scaffold`,
`register_catalog`.

- `complete`: planned work succeeded or an identical owned/indexed result was
  already current.
- `partial`: some useful work succeeded but ambiguity, a blocked user-owned
  file, a per-document failure, or missing consent requires follow-up.
- `unavailable`: no safe input exists and no work was attempted; the result must
  include an exact expected path or option.

Overall status is:

- `complete` when every reported capability is complete;
- `partial` when at least one capability is complete or partial and the command
  can return structured, actionable state;
- `failed` only when no capability produced usable state or a command-level
  error prevents trustworthy planning/application.

Per-document ingest failures are preserved in documentation capability details
and do not roll back successful sidecars or other capabilities. Re-running the
same command over unchanged inputs must produce no content changes and the same
normalized JSON apart from fields already defined by an existing artifact
contract as content-derived.

## Trust Boundaries and Safety Invariants

- Workspace paths, JSONC, Cortex-Debug fields, ELF/SVD files, and PDFs are
  untrusted local input.
- PDF parsing is a high-risk parsing boundary. It occurs only after explicit
  `--auto --yes`, through the existing parser abstraction and atomic sidecar
  publication path.
- Discovered strings are data, never shell commands. Generated task commands
  remain fixed project templates; automatic initialization starts no task.
- No socket, OpenOCD transport, debugger transport, subprocess build, or target
  access is allowed in discovery, planning, or initialization.
- Source documents and user-owned VS Code configuration remain authoritative and
  are never mutated.
- Every selected value and every ambiguity must retain explicit provenance.

Risk tier: **high**, because a user-facing convenience path automatically parses
untrusted local PDFs and reads untrusted workspace configuration. The
implementation therefore requires `/security-review`.

## Acceptance Criteria

- **AC-AWI-001:** `init-workspace --auto` accepts omitted executable, SVD, and
  OpenOCD flags, while non-auto mode preserves the existing explicit-input
  contract and behavior.
- **AC-AWI-002:** automatic mode reuses the bounded workspace plan and existing
  docs discovery primitive; it does not introduce an independent filesystem
  scanner, follow symlinks, select outside-root paths, or select from a truncated
  candidate class.
- **AC-AWI-003:** explicit inputs take precedence, one eligible candidate is
  selected, and zero/multiple candidates produce deterministic unavailable or
  partial results without guessing.
- **AC-AWI-004:** OpenOCD `configFiles` are reused only from one unambiguous,
  readable Cortex-Debug configuration; raw `.cfg` candidates are never paired
  automatically.
- **AC-AWI-005:** exactly one eligible SVD is stored as the workspace default;
  missing or multiple SVDs leave register setup actionable and do not block docs.
- **AC-AWI-006:** `--auto --yes` ingests all eligible discovered PDFs through the
  existing default docs pipeline; without `--yes`, candidates and an exact rerun
  action are reported and no PDF is parsed.
- **AC-AWI-007:** docs-only initialization succeeds without a toolchain,
  executable, OpenOCD configuration, probe, or board and returns overall
  `partial`/exit `2` with documentation `complete`.
- **AC-AWI-008:** each capability is applied independently: a missing/ambiguous
  hardware input or a per-document ingest failure cannot suppress safe progress
  in another capability.
- **AC-AWI-009:** existing user-owned VS Code files remain byte-for-byte
  unchanged; current attach fragments, ownership markers, and `--force` rules are
  preserved.
- **AC-AWI-010:** automatic initialization performs no network access, download,
  dependency installation, build, socket/OpenOCD/debugger transport, or target
  interaction.
- **AC-AWI-011:** text and versioned JSON output use stable capability/action
  ordering, explicit input provenance, status/exit mappings, and actionable
  destination paths; two equivalent runs normalize to identical JSON.
- **AC-AWI-012:** an unchanged rerun is idempotent: owned scaffold and docs
  sidecars are not rewritten, source inputs are never changed, and output states
  remain truthful.
- **AC-AWI-013:** README/agent instructions tell users to put PDFs in
  `docs/vendor/`, one default SVD in `.dbgoracle/<device>.svd`, and use the
  automatic initialization prompt without implying that DebugOracle downloads
  restricted vendor material.

## Implementation Plan

1. Update the affected specifications and write failing contract tests.
2. Extend/harden the existing workspace-plan candidate inventory and introduce a
   pure per-capability planner; do not add another scanner.
3. Add conditional parser validation for explicit versus `--auto` mode and the
   deterministic result schema/rendering.
4. Apply existing scaffold/attach logic and docs ingestion independently, then
   aggregate statuses and exit codes.
5. Add idempotence, containment, ambiguity, zero-live-I/O, and legacy regression
   tests.
6. Run `/review`, `/cli-qa`, `/security-review`, `/document-release`, and full
   repository validation.

## Rollback Plan

Remove the `--auto`/`--yes` parser surface and automatic planner/orchestration
while retaining the existing explicit `init-workspace`, workspace plan, and docs
commands. Existing docs sidecars and DebugOracle-owned scaffold files remain
valid artifacts and need no migration. Prior versions safely ignore the new
result fields.
