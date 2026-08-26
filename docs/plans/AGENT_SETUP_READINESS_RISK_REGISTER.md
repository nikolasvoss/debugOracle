# Agent Setup Readiness Risk Register

Status: Active

The completed readiness task spec was pruned. Any renewed implementation work
must begin with a replacement task spec under the current workflow rules.

| ID | Risk | Tier | Required control | Exit evidence |
| --- | --- | --- | --- | --- |
| R-001 | Workspace/profile content becomes a host command. | High | Typed allowlisted remediation actions; no executable command strings from discovered input; approval required. | Injection fixtures cannot alter action ID or argv. |
| R-002 | A “static” diagnostic contacts OpenOCD or target hardware. | High | Separate static module boundary; forbid socket/live-client imports and OpenOCD launch. | Tests fail on socket, transport import, or server subprocess call. |
| R-003 | Merge support corrupts user-owned VS Code JSON. | High | First slice is preview-only; preserve ownership rules. | Attach fixtures prove zero writes and stable diff/plan. |
| R-004 | Discovery leaks files outside workspace through symlinks. | Medium | Resolved-root containment; no directory-symlink traversal; bounded scan. | Escape/unreadable fixtures are excluded deterministically. |
| R-005 | Default reports disclose secrets in process arguments or paths. | Medium | Typed redacted provenance, output caps, opt-in verbose mode. | Redaction fixtures prove sensitive argument omission. |
| R-006 | Distro variability makes guidance unreliable. | Medium | Linux-first support map; unsupported facts block instead of guessing. | Unsupported-distro contract tests. |
| R-007 | Agent treats an advice string as authorization. | Medium | Prompts and schema distinguish advice from approval-required mutation. | Documentation and JSON contract review. |
