# DebugOracle Agent Runbook

Goal:
- Help an agent use DebugOracle correctly inside an STM32 workspace.
- Keep the workflow aligned with the current proof of concept:
  real `NUCLEO-L432KC` session, GDB-first evidence, read-only analysis after
  logs have been captured.

## PoC assumptions

- The relevant evidence source is the GDB/MI log.
- RTT is optional and not required for success.
- Live reads are not part of this PoC.
- DebugOracle does not control the debugger.
- A useful report is expected to contain GDB stop information such as stop
  reason, stack, registers, or locals, or an explicit warning when some of that
  context is missing.

## Interpret these requests as DebugOracle tasks

- "fetch the prompt from dbgoracle"
- "get the debug report"
- "show me the detailed embedded evidence"
- "use dbgoracle on this workspace"

The agent should prefer the smallest successful path that produces the
requested artifact.

## Required self-discovery rule

Do not guess DebugOracle flags, output modes, or command behavior.

When the user asks for more detail, a different rendering mode, or an unfamiliar
command, inspect the CLI help first:

```bash
dbgoracle --help
dbgoracle <command> --help
```

Use the actual supported flags from help output. For example,
`dbgoracle report` supports detailed inspection with `--vars`, `--gdb`, `--rtt`,
and `--verbose` rather than a separate `snapshot` rendering command.

## Command decision path

1. If a usable snapshot already exists, prefer rendering from it.
2. If no snapshot exists but a GDB/MI log exists, run `dbgoracle fetch`.
3. After a snapshot exists:
   - use `dbgoracle report` for a human-readable GDB evidence summary
   - use `dbgoracle prompt --goal "Explain why the target stopped here"` for an
     agent handoff artifact
   - use `dbgoracle report --gdb` or `dbgoracle report --rtt` for detailed
     structured source inspection
   - use `dbgoracle report --verbose` for one compact JSON object with summary,
     variables, and embedded source sections
4. If neither a snapshot nor a usable GDB/MI log exists, report that required
   debug evidence is missing.

## Preferred verification flow

Use the current workspace root unless the user gives a different path.

1. Check the current DebugOracle state:

```bash
dbgoracle status --workspace-root .
```

2. If a reusable snapshot is already present, render from it:

```bash
dbgoracle report --workspace-root .
dbgoracle prompt --workspace-root . --goal "Explain why the target stopped here"
```

3. If no snapshot exists but the GDB/MI log exists, build a snapshot and then
   render:

```bash
dbgoracle fetch --workspace-root .
dbgoracle report --workspace-root .
dbgoracle prompt --workspace-root . --goal "Explain why the target stopped here"
```

## Minimal workflows

For "fetch the prompt from dbgoracle":

```bash
dbgoracle status --workspace-root .
dbgoracle fetch --workspace-root .   # only if no usable snapshot exists
dbgoracle prompt --workspace-root . --goal "Explain why the target stopped here"
```

For "get the debug report":

```bash
dbgoracle status --workspace-root .
dbgoracle fetch --workspace-root .   # only if no usable snapshot exists
dbgoracle report --workspace-root .
```

For "show me the detailed embedded evidence" or "give me verbose structured output":

```bash
dbgoracle status --workspace-root .
dbgoracle fetch --workspace-root .   # only if no usable snapshot exists
dbgoracle report --workspace-root . --verbose
```

If the user wants one specific embedded section, prefer:

```bash
dbgoracle report --workspace-root . --gdb
dbgoracle report --workspace-root . --rtt
dbgoracle report --workspace-root . --vars
```

## Failure handling

Stop and report the issue if any of the following are true:

- no GDB/MI log exists
- the available session evidence does not let `fetch` build a snapshot
- the report is too thin because the session did not capture meaningful halt
  context
- the user appears to expect live reads or debugger control

## Troubleshooting guidance

- If the report or prompt is thin, suggest refreshing Call Stack, Registers, and
  Variables/Locals before ending the debug session and recapturing.
- If the snapshot is missing, check whether the workspace contains a GDB/MI log
  before attempting `fetch`.
- If `fetch` fails, tell the user that the current workspace does not contain
  a usable GDB evidence input for DebugOracle.
- If the user asks for detailed structured evidence, do not invent flags. Check
  `dbgoracle report --help` and use the supported inspect options.