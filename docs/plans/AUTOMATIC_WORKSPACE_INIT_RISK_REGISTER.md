# Automatic Workspace Initialization Risk Register

Status: Approved controls; implementation evidence pending

Task: [Automatic Workspace Initialization Task Spec](AUTOMATIC_WORKSPACE_INIT_TASK_SPEC.md)

Overall risk tier: **high**. `/security-review` is required before completion.

| ID | Risk | Tier | Required control | Exit evidence |
| --- | --- | --- | --- | --- |
| R-AWI-001 | Automatic mode parses a malicious or malformed local PDF. | High | Require explicit `--auto --yes`; reuse the existing parser abstraction, resource/error bounds, per-document failure reporting, and atomic sidecar publication; do not enable semantic models by default. | Adversarial/malformed/encrypted PDF fixtures fail locally without corrupting prior sidecars or blocking unrelated capabilities; `/security-review` passes. |
| R-AWI-002 | Discovery escapes the workspace or follows attacker-controlled symlinks. | High | Resolve root once; reject file and directory symlinks; enforce resolved-root containment, bounded candidate classes, and stable deduplication before selection. | Symlink/outside-root/unreadable/truncation tests select nothing unsafe and emit provenance-aware actions. |
| R-AWI-003 | Untrusted JSONC or discovered strings become host commands. | High | Bounded typed JSONC parsing; discovered values remain data; generated command bodies are fixed templates; auto init starts no task or subprocess. | Injection fixtures cannot change command templates or cause subprocess/socket calls; call-graph security review. |
| R-AWI-004 | Convenience initialization contacts or mutates a target. | High | Keep discovery/planning/application outside OpenOCD/debugger transports; prohibit sockets, probe detection, builds, launches, resets, and flashes. | Tripwire tests fail on live-client import/use, socket, OpenOCD launch, or target interaction. |
| R-AWI-005 | Automatic setup overwrites user-owned VS Code configuration. | High | Preserve current ownership markers, attach fragments, and managed-only `--force`; hash user-owned files before/after. | Fresh/partial/attach fixtures prove user files byte-identical and fragments deterministic. |
| R-AWI-006 | Ambiguous ELF/SVD/OpenOCD inputs cause a plausible but wrong configuration. | High | Explicit-over-discovered precedence; select exactly one eligible candidate; never pair raw `.cfg` files; ambiguity is a partial result with all candidates. | Reordered multi-candidate fixtures never select and produce identical output. |
| R-AWI-007 | A docs failure prevents all useful initialization, or a hardware gap prevents docs access. | Medium | Plan/apply/report capabilities independently; aggregate after every safe attempt; preserve per-document outcomes. | Mixed-failure integration tests prove unaffected capabilities complete. |
| R-AWI-008 | Scan size or recursive documents cause denial of service or unstable truncation. | Medium | Bound entries/files/candidates/config bytes; sort before selection; report truncation per candidate class and never select within it. | Boundary-size and reversed-order tests complete within the test budget with stable results. |
| R-AWI-009 | Reruns rewrite sidecars/scaffold, create drift, or damage source inputs. | Medium | Reuse source-hash skip and managed-file checks; never modify source documents; compare desired content before writes. | Second-run hashes/mtimes and source hashes remain unchanged; normalized output is equal. |
| R-AWI-010 | Missing `--yes` is treated as implicit consent to parse workspace PDFs. | Medium | Non-interactive fail-closed consent: inventory/report only, zero parser calls and zero sidecar writes. | Parser/write spies prove no docs mutation without `--yes`; CLI output gives exact rerun command. |
| R-AWI-011 | Output is too vague for an agent or changes with filesystem order. | Medium | Versioned schema, closed status values, fixed capability/action order, resolved paths, explicit provenance, deterministic rendering. | Golden text/JSON and creation-order reversal tests; `/cli-qa` passes. |
| R-AWI-012 | Automatic mode silently downloads or suggests redistribution of restricted vendor resources. | Medium | No network/download code; docs name exact local destinations and distinguish project-owned demo material from optional vendor originals. | Network tripwire and documentation contract tests; `/document-release` passes. |

## Gate Routing

- Engineering-plan status: `clean` for implementation; no product decision is
  intentionally left to the coding phase.
- Implementation: `/tdd` required.
- Pre-landing: `/review` required.
- User-facing CLI: `/cli-qa` required.
- Security: `/security-review` required because the overall tier is high.
- Documentation/release metadata: `/document-release` required.
- Final validation: `/ship`/repository full verification after all earlier gates.

Any expansion into downloading vendor material, installing host dependencies,
executing discovered commands, applying fragments to user-owned files, or
contacting a target invalidates this review and requires a new spec and risk
review.
