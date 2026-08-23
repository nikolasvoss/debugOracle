# Installation

The supported public-alpha installer is Linux with Python 3.10+ and `pipx`; the verified environment is Ubuntu 24.04 x86-64 with Python 3.12.

From a checkout, run `./scripts/install/linux.sh --docs-tools none`. It installs `dbgoracle`, not OpenOCD, VS Code, Cortex-Debug, drivers, or board tooling. Remove it with `./scripts/install/uninstall.sh`; workspace files remain untouched.
