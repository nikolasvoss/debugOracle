# Installation

The supported public-alpha installer is Linux with Python 3.10–3.14 and `pipx`;
the authoritative release environment is Ubuntu 24.04 x86-64 with Python 3.12.
The Docling, semantic, and combined profiles remain disabled until their
dependency and model license audits are complete.

From a checkout, run `./scripts/install/linux.sh --docs-tools none`. It installs `dbgoracle`, not OpenOCD, VS Code, Cortex-Debug, drivers, or board tooling. Remove it with `./scripts/install/uninstall.sh`; workspace files remain untouched.
