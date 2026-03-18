from __future__ import annotations

from dataclasses import dataclass

SOURCE_FAMILIES = {"stream", "snapshot"}


@dataclass(frozen=True)
class SourceDescriptor:
    source_id: str
    family: str
    trigger: str
    requires_halt: bool
    persistence_default: str
    backend_dependency: str
    supports_parsing: bool
    supports_reduction: bool


def validate_source_descriptor(descriptor: SourceDescriptor) -> SourceDescriptor:
    if not descriptor.source_id.strip():
        raise ValueError("source_id must be non-empty.")
    if descriptor.family not in SOURCE_FAMILIES:
        raise ValueError(
            f"family must be one of {sorted(SOURCE_FAMILIES)}, got {descriptor.family!r}."
        )
    if not descriptor.trigger.strip():
        raise ValueError("trigger must be non-empty.")
    if not descriptor.persistence_default.strip():
        raise ValueError("persistence_default must be non-empty.")
    if not descriptor.backend_dependency.strip():
        raise ValueError("backend_dependency must be non-empty.")
    return descriptor
