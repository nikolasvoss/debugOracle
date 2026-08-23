# DebugOracle

DebugOracle helps your coding agent investigate embedded bugs using real evidence from your project, debugger, runtime logs, and manufacturer documentation.

It turns scattered debug information into a reusable report that separates observed facts from conclusions.

## What it can do

- Read captured debugger information: stop reason, call stack, registers, and local variables.
- Use optional RTT runtime logs.
- Use a matching SVD file for safe, read-only peripheral-register evidence.
- Search local manuals and datasheets with page-level references.
- Tell your agent what evidence is available, what is missing, and what to do next.

DebugOracle is operated by a coding agent such as Codex or Claude Code. You do not need to learn its commands to get started.

## See it work without hardware

Open [`examples/debugoracle-reference-workspaces/stm32/peripheral-miscfg`](examples/debugoracle-reference-workspaces/stm32/peripheral-miscfg) in a new agent session and ask:

```text
Set up the DebugOracle demo. Show the available evidence, investigate the serial failure, and clearly separate observations, documentation, and the conclusion.
```

The demo combines runtime output, firmware source, captured registers, and a local register reference to identify a serial clock/divider mismatch with evidence rather than a guess.

## What you need

- To install: Linux, Python 3.10+, `pipx`, and Codex or Claude Code.
- To debug a device: your firmware project, a built firmware file (ELF), and your existing debugger setup—normally Cortex-Debug and OpenOCD.
- Recommended: manufacturer manuals or datasheets as PDFs, plus a matching SVD file for peripheral-register support.

## Get started

1. Clone this repository and open it in Codex or Claude Code.
2. Ask the agent:

```text
Install DebugOracle for this user with the supported installer. Read the project instructions and README first. Explain optional components before installing them, make only routine per-user changes, and confirm that `dbgoracle --version` works.
```

3. Open your firmware project in an agent session and ask:

```text
Set up DebugOracle for this project. Discover the available inputs, configure everything that is safe and unambiguous, and explain clearly what is missing. Ask me before preparing manuals or datasheets for search. Do not overwrite my existing project configuration without showing me the required change.
```

The supported installer is Linux-only. It installs DebugOracle, not OpenOCD, VS Code, Cortex-Debug, drivers, or board-specific tooling.

## Add files if you have them

Fresh workspace setup creates an optional `debugoracle-input/` folder. Put any project-related files there—manuals, datasheets, SVD files, ELF files, debugger configuration, or captured logs. Filenames and subfolders do not matter.

The folder is not required. DebugOracle also checks common workspace locations, including the project root, `docs/`, `.dbgoracle/`, existing VS Code configuration, and known build-output locations. It uses only supported file types, leaves other files alone, and asks rather than guessing when several choices are credible.

If PDFs are found, the agent asks permission before preparing them for local search. It explains why that helps and that it may take seconds to several minutes. Original files are unchanged; new agent-driven search data lives under `.dbgoracle/documentation-search/`.

## What DebugOracle changes

During fresh setup, DebugOracle can create `.dbgoracle/`, `debugoracle-input/`, DebugOracle-owned VS Code setup files, and narrow `.gitignore` rules so inputs and generated evidence stay local.

It does not modify firmware, flash or control the target, download vendor documents, change supplied files, or overwrite user-owned VS Code configuration.

## Platform support

The verified public-alpha environment is Ubuntu 24.04 LTS x86-64 with Python 3.12 and `pipx`. Other Linux distributions, architectures, and Python versions are currently unverified.

## Help and documentation

- [Installation](docs/guides/installation.md)
- [Workspace setup and file discovery](docs/guides/workspace-setup.md)
- [Manufacturer documentation](docs/guides/vendor-documentation.md)
- [Cortex-Debug setup](examples/cortex-debug/README.md)
- [Troubleshooting](docs/guides/troubleshooting.md)
- [Command reference](docs/specs/cli.md)
- [Architecture](docs/architecture.md)
- [Security reporting](SECURITY.md)

For ordinary bugs and setup questions, use [GitHub Issues](https://github.com/nikolasvoss/ai-debugger-v2/issues).
