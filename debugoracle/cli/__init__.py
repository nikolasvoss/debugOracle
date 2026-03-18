from __future__ import annotations

import sys
from types import ModuleType


class _CliPackage(ModuleType):
    @property
    def main(self):
        from .main import main as _main

        return _main


sys.modules[__name__].__class__ = _CliPackage


__all__ = ["main"]
