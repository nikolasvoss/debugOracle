# Plan Retention

Plans record delivery decisions; they are not the source of truth for current
behavior. Use the [roadmap](../../ROADMAP.md) for priorities, the
[workflow rules](../workflows/AGENT_WORKFLOW_RULES.md) for delivery process, and
the relevant module [specification](../specs/README.md) for behavior.

## Future Proposals

- [Testing Plan Phase 4](TESTING_PLAN_PHASE_4.md) and
  [Testing Plan Phase 5](TESTING_PLAN_PHASE_5.md) are future, non-binding
  proposals. They become implementation scope only when scheduled through the
  roadmap and a task spec.

## Retired Records

| Retired material | Status | Durable replacement |
| --- | --- | --- |
| Fast-pass verification plan | Complete | README verification loop and workflow templates |
| Memory-read parity plan | Complete | `memory`, `models`, `storage`, `evidence`, and `cli` specs |
| Spec-driven workflow evaluation | Superseded | Workflow rules and PR traceability template |
| Testing Plans Phases 1–3 | Complete | Testing specs and the 0.1.2 changelog entry |
| Docs-sidecar manual-ingestion design | Superseded | Docs-ingestion guide and docs-sidecar specs |
| Developer scratch notes | Retired | Actionable items moved to the roadmap |

## Plan Convention

Every new plan or design starts with a purpose and one status: `Active`,
`Proposal`, `Complete`, or `Superseded`. A retired document must name the
current replacement. Keep scratch notes out of versioned docs; promote
actionable items to the roadmap or a task spec.
