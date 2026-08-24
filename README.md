# DebugOracle

DebugOracle helps your coding agent investigate embedded bugs using real evidence from your project, debugger, runtime logs, and manufacturer documentation.

It turns scattered debug information into a reusable report that separates observed facts from conclusions.

![DebugOracle evidence report for a UART failure](docs/assets/readme/evidence-reviewed-uart-demo.png)

DebugOracle grounds agent investigations in captured debugger data, runtime logs, peripheral registers, firmware source, and vendor documentation.

## What it can do

- Read captured debugger state: stop reason, call stack, registers, and local variables.
- Compare optional RTT logs with firmware source and captured hardware state.
- Decode peripheral registers safely and read-only with a matching SVD file.
- Search local reference manuals and datasheets with page-level references.
- Report the evidence used, what remains unknown, and the next useful action.

DebugOracle is operated by a coding agent such as Codex or Claude Code. You do not need to learn its commands to get started.

## What you need

| For | You need | It enables |
| --- | --- | --- |
| Install DebugOracle | Linux, Python 3.10–3.14, `pipx`, and Codex or Claude Code | Installation and agent-guided workspace setup |
| Capture debug evidence | Your firmware project, a built ELF, and your existing debugger setup—normally Cortex-Debug and OpenOCD | Debugger state, runtime logs, and captured target evidence |
| **Full hardware debugging** | A matching SVD plus the device reference manual and/or datasheet as PDFs | Registers interpreted in hardware context and checked against the manufacturer specification |

## Get started

1. Clone this repository with its pinned demo and SDK dependencies, then open it
   in Codex or Claude Code:

```bash
git clone --recurse-submodules https://github.com/nikolasvoss/ai-debugger-v2.git
cd ai-debugger-v2
```

   If you already cloned the repository without submodules, recover them before
   running the tests or opening the demo:

```bash
git submodule update --init --recursive
```

2. Ask the agent:

```text
Install DebugOracle for this user with the supported installer. Read the project instructions and README first. Explain optional components before installing them, make only routine per-user changes, and confirm that `dbgoracle --version` works.
```

3. **In your firmware project**, open an agent session and ask:

```text
Set up DebugOracle for this project. Discover the available inputs, configure everything that is safe and unambiguous, and explain clearly what is missing. Ask me before preparing manuals or datasheets for search. Do not overwrite my existing project configuration without showing me the required change.
```

> The supported installer is Linux-only. It installs DebugOracle, not OpenOCD, VS Code, Cortex-Debug, drivers, or board-specific tooling.

## Add files to supercharge your debugging

Use the optional `debugoracle-input/` folder for any helpful project files:

- Reference manuals or datasheets (`.pdf`)
- A matching peripheral description (`.svd`)
- A built firmware image (`.elf`)
- Existing debugger configuration
- Captured logs

```text
debugoracle-input/
├── documentation/
├── device.svd
├── firmware.elf
├── debugger-config/
└── captured-logs/
```

The folder is not required. Everything in it is optional, and filenames and subfolders do not matter. DebugOracle also checks common project locations such as `docs/`, `.dbgoracle/`, existing VS Code configuration, and known build-output locations.

<details>
<summary>How document search works</summary>

If PDFs are found, the agent asks permission before preparing them for local search. It may take seconds to several minutes. The tool searches only local PDFs; it does not download vendor documentation. Original files stay unchanged; generated search data is stored under `.dbgoracle/documentation-search/`.

Parser choice affects result quality. The supported 0.3.0 install uses the
default `pypdf` parser, which extracts text page by page. Scanned or image-only
pages are incomplete, encrypted or malformed PDFs cannot be ingested, and
complex tables or layouts may extract less accurately. The optional Docling
and semantic profiles remain disabled until their dependency and model license
audits are complete.
</details>

## See it work without hardware

Open [`examples/debugoracle-reference-workspaces/stm32/peripheral-miscfg`](examples/debugoracle-reference-workspaces/stm32/peripheral-miscfg) in a new agent session and ask:

```text
Set up the DebugOracle demo. Show the available evidence, investigate the serial failure, and clearly separate observations, documentation, and the conclusion.
```

The demo combines runtime output, firmware source, captured registers, and a local register reference to identify a serial clock/divider mismatch with evidence rather than a guess.

## What DebugOracle changes

| DebugOracle may create | DebugOracle does not |
| --- | --- |
| `.dbgoracle/` and `debugoracle-input/` | Modify firmware or supplied files |
| DebugOracle-owned VS Code setup files | Flash or control the target |
| Narrow `.gitignore` rules for local inputs and generated evidence | Download vendor documents or overwrite user-owned VS Code configuration |

## Platform support

The automated non-HIL compatibility suite covers Python 3.10 through 3.14 on Ubuntu. The authoritative public-release environment is Ubuntu 24.04 LTS x86-64 with Python 3.12 and `pipx`. Other Linux distributions and architectures are currently unverified.

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
