# Module Specs

Module specs live in this directory so agents have one predictable place to look before opening code.

Read [`../architecture.md`](../architecture.md) first for the whole-system view, package boundaries, and architecture diagrams. Then use the module specs below for code-near detail.

Conventions:

- The spec filename matches the module filename exactly.
- Every spec begins with module metadata, including `Code Path`.
- For DebugOracle Python modules, start here before reading module code.

## Registry

The registry below tracks the spec-backed module surfaces we expect agents and maintainers to use
during this refactor. It is intentionally curated rather than a flat dump of every helper module.

| Module | Code Path | Spec |
| --- | --- | --- |
| `builder` | `debugoracle/builder.py` | [`builder.md`](builder.md) |
| `cli` | `debugoracle/cli/__init__.py` | [`cli.md`](cli.md) |
| `main` | `debugoracle/cli/main.py` | [`main.md`](main.md) |
| `storage` | `debugoracle/pipeline/storage.py` | [`storage.md`](storage.md) |
| `status_capture` | `debugoracle/cli/commands/status_capture.py` | [`status_capture.md`](status_capture.md) |
| `run_stop` | `debugoracle/cli/commands/run_stop.py` | [`run_stop.md`](run_stop.md) |
| `evidence` | `debugoracle/cli/commands/evidence.py` | [`evidence.md`](evidence.md) |
| `halt_snapshot` | `debugoracle/sources/debuggers/gdb/halt_snapshot.py` | [`halt_snapshot.md`](halt_snapshot.md) |
| `live` | `debugoracle/live.py` | [`live.md`](live.md) |
| `memory` | `debugoracle/sources/debuggers/gdb/memory.py` | [`memory.md`](memory.md) |
| `peripheral_registers` | `debugoracle/sources/debuggers/gdb/peripheral_registers.py` | [`peripheral_registers.md`](peripheral_registers.md) |
| `mi` | `debugoracle/mi.py` | [`mi.md`](mi.md) |
| `registers` | `debugoracle/sources/debuggers/gdb/registers.py` | [`registers.md`](registers.md) |
| `rtt` | `debugoracle/rtt.py` | [`rtt.md`](rtt.md) |
| `session` | `debugoracle/session.py` | [`session.md`](session.md) |
| `trust` | `debugoracle/policy/trust.py` | [`trust.md`](trust.md) |
| `transcript` | `debugoracle/sources/debuggers/gdb/transcript.py` | [`transcript.md`](transcript.md) |
