# Installation

The supported public-alpha installer requires Python 3.12.x and `pipx`.
Linux, current macOS on Apple Silicon and Intel, and current Windows with
PowerShell are supported. The Docling, semantic, and combined profiles remain
disabled until their dependency and model license audits are complete.

From a checkout, use the command for your platform:

| Platform | Install | Uninstall |
| --- | --- | --- |
| Linux | `./scripts/install/linux.sh --docs-tools none` | `./scripts/install/uninstall.sh` |
| macOS | `./scripts/install/macos.sh --docs-tools none` | `./scripts/install/uninstall-macos.sh` |
| Windows PowerShell | `.\scripts\install\windows.ps1 --docs-tools none` | `.\scripts\install\uninstall-windows.ps1` |

The launchers install `dbgoracle`, not OpenOCD, VS Code, Cortex-Debug, drivers,
or board tooling. They never request elevation or bypass PowerShell execution
policy. Workspace files remain untouched.
