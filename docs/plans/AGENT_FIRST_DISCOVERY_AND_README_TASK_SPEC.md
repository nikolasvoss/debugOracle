# Agent-First Discovery and README Task Spec

Status: Implemented and verified

Affected specifications:

- [`init_workspace`](../specs/init_workspace.md)
- [`docs_sidecar`](../specs/docs_sidecar.md)
- [`docs_cli`](../specs/docs_cli.md)
- [`readiness`](../specs/readiness.md)

## Problem Statement

DebugOracle currently asks an engineer to understand several technical input
locations before an agent can prepare a workspace: vendor PDFs belong in
`docs/vendor/`, while a default SVD belongs in `.dbgoracle/`. Generated search
sidecars are also written beside source PDFs. This creates friction for the
engineer, hides the product's agent-first workflow, and makes the README read
like a command manual rather than a clear GitHub landing page.

An engineer should be able to add any project-related input to an optional
`debugoracle-input/` folder, or leave existing files where they already are,
then ask their coding agent to initialize DebugOracle. The agent must discover
safe, recognized inputs quickly; report ambiguity rather than guess; request
permission before parsing PDFs; and explain the benefit and expected duration
of document ingestion.

## Scope

In scope:

- Create `debugoracle-input/` during workspace initialization and add
  `debugoracle-input/` plus `.dbgoracle/` to `.gitignore` with an owned,
  idempotent marker.
- Discover recognized local inputs from `debugoracle-input/` recursively first,
  then use bounded fallback discovery in the workspace root and established
  project locations.
- Recognize PDFs, SVDs, ELF files, OpenOCD configuration, and supported
  captured debug artifacts. Preserve the current deterministic precedence,
  ambiguity, and provenance rules.
- Exclude version-control, dependency-cache, virtual-environment, and other
  known irrelevant directories. Inspect known build-output locations only for
  recognized artifact types rather than traversing arbitrary build trees.
- Keep document-ingestion authorization with the coding agent: automatic init
  without authorization reports the documents, why local search is useful, an
  estimated duration category, and the exact rerun action; it does not parse a
  PDF or write search data.
- Store new generated document-search data beneath
  `.dbgoracle/documentation-search/`; preserve read access to legacy sibling
  sidecars so existing workspaces remain usable.
- Rewrite the root README for the engineer-facing, agent-operated journey and
  link detailed setup, reference, platform, and troubleshooting material out
  of the onboarding path.

Out of scope:

- Downloading, moving, modifying, or redistributing vendor files.
- Parsing unrecognized files merely because they are inside `debugoracle-input/`.
- Full-workspace unrestricted recursive scanning.
- Building firmware, installing external debug tooling, connecting to hardware,
  or changing target state during discovery or initialization.
- Replacing existing user-owned VS Code files or unmarked `.gitignore` content.
- A new interactive CLI prompt; the agent owns the human conversation and the
  CLI remains deterministic and machine-readable.

## Invariants Touched

- Deterministic discovery and stable rendered results.
- Evidence-first provenance: every selected or rejected candidate identifies
  its source and selection reason.
- Read-only target behavior and no network access during setup.
- Reproducible, bounded local filesystem work.
- User-owned project files are not silently overwritten.

## Acceptance Criteria

- **AC-AFD-001:** Workspace initialization creates `debugoracle-input/` when
  missing and preserves an existing directory and its contents.
- **AC-AFD-002:** Initialization adds one owned, idempotent `.gitignore` entry
  for `debugoracle-input/` and `.dbgoracle/`, preserving unrelated content.
- **AC-AFD-003:** Automatic discovery searches `debugoracle-input/` recursively
  before bounded fallback locations and reports the source location for every
  candidate.
- **AC-AFD-004:** Discovery avoids configured excluded directories and broad
  arbitrary build traversal while retaining recognized artifacts in supported
  locations; bounded traversal remains deterministic.
- **AC-AFD-005:** A unique eligible candidate can be selected; zero or multiple
  candidates remain unavailable or partial with actionable, deterministic
  choices rather than a guessed selection.
- **AC-AFD-006:** PDF discovery without authorization performs no parser work
  or derived-data write and reports why ingestion helps, a duration category,
  and the exact authorization action. Authorized ingestion uses the existing
  trusted parser path.
- **AC-AFD-007:** New document-search artifacts are stored under
  `.dbgoracle/documentation-search/`, while search and status continue to find
  legacy sibling sidecars.
- **AC-AFD-008:** The README explains the product in plain language, has clear
  abilities and requirements lists, uses the hardware-free demo as proof, and
  makes the agent—not manual commands—the primary operator.
- **AC-AFD-009:** README detail that does not support first-run onboarding is
  moved to linked guides, including advanced setup, command reference,
  troubleshooting, platform support, and contribution/developer material.

## Risks

- **Technical:** Altering sidecar storage affects ingest, search, status,
  atomic publication, and legacy artifact discovery. A source-to-derived-data
  manifest or deterministic namespaced paths may be needed to avoid filename
  collisions.
- **Operational:** Automatic `.gitignore` edits could surprise users or conflict
  with an existing policy. They must be narrow, clearly marked, idempotent, and
  surface their action in setup output.
- **Security:** PDF parsing and workspace configuration are untrusted local
  inputs. The existing explicit authorization and no-symlink/no-network rules
  must remain intact.

## Rollback Plan

Revert the new discovery locations and generated-store writer while retaining
legacy sidecar readers. The input folder and owned `.gitignore` entries can be
left harmlessly in existing workspaces; a documented cleanup action can remove
only DebugOracle-owned entries if rollback requires it.
