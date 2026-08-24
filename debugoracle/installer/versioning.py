from __future__ import annotations

from packaging.specifiers import (  # pyright: ignore[reportMissingImports]
    InvalidSpecifier,
    SpecifierSet,
)
from packaging.version import (  # pyright: ignore[reportMissingImports]
    InvalidVersion,
    Version,
)


class VersioningError(ValueError):
    """Raised when installer version policy receives invalid PEP 440 input."""


def compare_versions(left: str, right: str) -> int:
    try:
        left_version = Version(left)
        right_version = Version(right)
    except InvalidVersion as error:
        raise VersioningError(str(error)) from error
    return (left_version > right_version) - (left_version < right_version)


def satisfies(version: str, specifier: str) -> bool:
    try:
        return Version(version) in SpecifierSet(specifier)
    except (InvalidSpecifier, InvalidVersion) as error:
        raise VersioningError(str(error)) from error
