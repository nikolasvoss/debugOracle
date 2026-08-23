# Agent-First Discovery and README Plan

## Task Link

[`AGENT_FIRST_DISCOVERY_AND_README_TASK_SPEC.md`](AGENT_FIRST_DISCOVERY_AND_README_TASK_SPEC.md)

## Files / Modules To Change

- `debugoracle/readiness.py` and `debugoracle/workspace_init_plan.py` for
  bounded, prioritized discovery and agent-facing actions.
- `debugoracle/cli/commands/init_workspace.py` and workspace writers for input
  folder and owned `.gitignore` initialization.
- `debugoracle/docs_sidecar.py` and `debugoracle/cli/commands/docs_cli.py` for
  managed document-search storage and legacy reading.
- Focused tests for initialization, automatic planning, document ingestion,
  search/status compatibility, and README contract assertions.
- `README.md` plus linked user guides.

## Implementation Steps

1. Define the discovery roots, exclusions, artifact-type checks, traversal
   bounds, precedence, and normalized provenance schema in the affected specs.
2. Implement pure, deterministic inventory collection for the input folder and
   fallback locations; add tests before connecting it to the CLI.
3. Add idempotent managed creation of `debugoracle-input/` and `.gitignore`
   entries without touching unrelated user content.
4. Extend the automatic planner to render recognized, ignored, ambiguous, and
   missing inputs with agent-ready authorization actions for PDFs.
5. Introduce `.dbgoracle/documentation-search/` as the new generated-data store,
   preserve atomic writes and source provenance, and retain legacy sibling
   sidecar discovery for read compatibility.
6. Rewrite README onboarding around install → optional input folder → one agent
   prompt → evidence-backed investigation; move detailed content to guides.
7. Run focused tests, security review, full verification, and a manual
   agent-first walkthrough in a fixture workspace.

## Acceptance Criteria -> Validation Map

| AC ID | Validation Type | Location / Command |
|---|---|---|
| AC-AFD-001 | Unit/integration | New `init-workspace` workspace fixture tests |
| AC-AFD-002 | Unit/integration | `.gitignore` preservation/idempotence tests |
| AC-AFD-003 | Unit | `tests/test_auto_init_planner.py` discovery cases |
| AC-AFD-004 | Unit | Bounded traversal and excluded-directory tests |
| AC-AFD-005 | Unit/integration | Planner and automatic-init CLI ambiguity tests |
| AC-AFD-006 | Integration | Auto-init without/with authorization tests |
| AC-AFD-007 | Unit/integration | Docs ingest/search/status new-store and legacy-store tests |
| AC-AFD-008 | Manual/contract | README review and focused README contract tests |
| AC-AFD-009 | Manual | Link check and GitHub-rendered README review |

## Test Plan

- **Unit:** traversal ordering, root precedence, exclusions, candidate typing,
  normalization, `.gitignore` insertion, document store path resolution.
- **Integration:** fresh and existing workspaces; documents-only setup; mixed
  `debugoracle-input/` fixtures; ambiguous inputs; no PDF authorization;
  authorized ingest; legacy sidecar search.
- **Regression:** all existing automatic-init, docs-sidecar, fetch/SVD, and
  public-release contract tests.
- **Manual:** use the hardware-free peripheral-misconfiguration workspace with
  the README agent prompt and verify that each user-facing claim is accurate.

## Validation Commands

- Focused relevant test modules before broader checks.
- `./scripts/verify.sh fast`
- `/security-review`
- `./scripts/verify.sh full`

## Release / Compatibility Notes

- `debugoracle-input/` is optional and additive; established locations remain
  supported.
- New generated documentation data is centralized under `.dbgoracle`, but
  existing sibling sidecars remain readable.
- Owned `.gitignore` entries are an intentional user-visible workspace change
  and must be stated in setup output and documentation.
