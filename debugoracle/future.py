from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Capability:
    name: str
    description: str
    read_only: bool = True


class CapabilityRegistry:
    """Placeholder registry for future AI action-model integrations."""

    def __init__(self) -> None:
        self._capabilities = [
            Capability("read_source_at_pc", "Read source around the current PC"),
            Capability("read_function", "Read the source for a function"),
            Capability("find_callers", "Find callers of the current function"),
            Capability("find_callees", "Find callees of the current function"),
            Capability("read_related_type", "Read a related type definition"),
            Capability("read_related_module", "Read a related module"),
        ]

    def list_capabilities(self) -> list[Capability]:
        return list(self._capabilities)


class SourceContextProvider:
    """No-op placeholder for future passive source enrichment."""

    def enrich_placeholder(self) -> dict[str, object]:
        return {
            "status": "not_collected",
            "notes": "Passive source enrichment is planned for a future version.",
        }

