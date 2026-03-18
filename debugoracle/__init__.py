"""DebugOracle package."""


def main(argv: list[str] | None = None) -> int:
    from .cli import main as _main

    return _main(argv)

__all__ = ["main"]
