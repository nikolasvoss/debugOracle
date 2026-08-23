from __future__ import annotations

import shlex
from dataclasses import dataclass
from enum import Enum


class CapabilityStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class InputProvenance(str, Enum):
    EXPLICIT = "explicit"
    WORKSPACE_SETTING = "workspace_setting"
    CORTEX_DEBUG_LAUNCH = "cortex_debug_launch"
    WORKSPACE_DISCOVERY = "workspace_discovery"


@dataclass(frozen=True)
class AutomaticInitInventory:
    """Normalized, local-only inputs available to automatic initialization."""

    workspace_root: str
    executable_candidates: tuple[str, ...] = ()
    svd_candidates: tuple[str, ...] = ()
    raw_openocd_configs: tuple[str, ...] = ()
    configured_executable: str | None = None
    configured_svd: str | None = None
    configured_openocd_configs: tuple[str, ...] = ()
    cortex_debug_openocd_configs: tuple[tuple[str, ...], ...] = ()
    documents: tuple[str, ...] = ()
    truncated_candidate_classes: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlannedInput:
    key: str
    values: tuple[str, ...]
    provenance: InputProvenance

    def as_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "values": list(self.values),
            "provenance": self.provenance.value,
        }


@dataclass(frozen=True)
class CandidateEvidence:
    key: str
    values: tuple[str, ...]
    provenance: InputProvenance

    def as_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "values": list(self.values),
            "provenance": self.provenance.value,
        }


@dataclass(frozen=True)
class InputAmbiguity:
    key: str
    alternatives: tuple[tuple[str, ...], ...]
    provenance: InputProvenance

    def as_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "alternatives": [list(values) for values in self.alternatives],
            "provenance": self.provenance.value,
        }


@dataclass(frozen=True)
class PlanAction:
    action_id: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"action_id": self.action_id, "detail": self.detail}


@dataclass(frozen=True)
class CapabilityPlan:
    name: str
    status: CapabilityStatus
    inputs: tuple[PlannedInput, ...] = ()
    ambiguities: tuple[InputAmbiguity, ...] = ()
    evidence: tuple[CandidateEvidence, ...] = ()
    actions: tuple[PlanAction, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status.value,
            "inputs": [item.as_dict() for item in self.inputs],
            "ambiguities": [item.as_dict() for item in self.ambiguities],
            "evidence": [item.as_dict() for item in self.evidence],
            "actions": [item.as_dict() for item in self.actions],
        }


@dataclass(frozen=True)
class AutomaticWorkspaceInitPlan:
    workspace_root: str
    status: str
    capabilities: tuple[CapabilityPlan, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "1",
            "scope": "automatic_workspace_init",
            "workspace_root": self.workspace_root,
            "status": self.status,
            "capabilities": [item.as_dict() for item in self.capabilities],
        }


def plan_automatic_workspace_init(
    inventory: AutomaticInitInventory,
    *,
    docs_authorized: bool = False,
    explicit_executable: str | None = None,
    explicit_svd: str | None = None,
    explicit_openocd_configs: tuple[str, ...] = (),
) -> AutomaticWorkspaceInitPlan:
    """Reduce normalized inventory to a deterministic, side-effect-free plan."""

    truncated = frozenset(inventory.truncated_candidate_classes)
    documents_truncated = "documents" in truncated
    documents = () if documents_truncated else _canonical_values(inventory.documents)
    documentation = CapabilityPlan(
        name="documentation",
        status=(
            CapabilityStatus.PARTIAL
            if documents_truncated
            else CapabilityStatus.COMPLETE
            if documents and docs_authorized
            else CapabilityStatus.PARTIAL
            if documents
            else CapabilityStatus.UNAVAILABLE
        ),
        inputs=(
            PlannedInput(
                key="documents",
                values=documents,
                provenance=InputProvenance.WORKSPACE_DISCOVERY,
            ),
        )
        if documents
        else (),
        actions=(
            PlanAction(
                action_id="resolve_truncated_documents",
                detail=(
                    "Document discovery reached its bound; reduce PDFs under "
                    "`doc/` and `docs/` before automatic ingestion."
                ),
            ),
        )
        if documents_truncated
        else (
            PlanAction(
                action_id="authorize_document_ingest",
                detail=(
                    "Local document search lets your agent cite manuals and "
                    "datasheets while debugging. Parsing may take seconds to "
                    "several minutes depending on document size. Re-run "
                    "`dbgoracle init-workspace --workspace-root "
                    f"{shlex.quote(inventory.workspace_root)} --auto --yes "
                    "--format json` to authorize local PDF parsing."
                ),
            ),
        )
        if documents and not docs_authorized
        else (
            PlanAction(
                action_id="add_documents",
                detail=(
                    "Place manuals or datasheets in the optional "
                    "`debugoracle-input/` folder, or leave them in a common "
                    "workspace documentation location."
                ),
            ),
        )
        if not documents
        else (),
    )

    executable_truncated = (
        "executables" in truncated
        and explicit_executable is None
        and inventory.configured_executable is None
    )
    executable, executable_ambiguity = _select_path(
        key="executable",
        explicit=explicit_executable,
        configured=inventory.configured_executable,
        candidates=() if executable_truncated else inventory.executable_candidates,
    )
    openocd_truncated = (
        "cortex_debug_openocd_configs" in truncated
        and not explicit_openocd_configs
        and not inventory.configured_openocd_configs
    )
    openocd, openocd_ambiguity = _select_openocd(
        explicit=explicit_openocd_configs,
        configured=inventory.configured_openocd_configs,
        launch_configurations=(
            () if openocd_truncated else inventory.cortex_debug_openocd_configs
        ),
    )
    scaffold_inputs = tuple(item for item in (executable, openocd) if item is not None)
    scaffold_ambiguities = tuple(
        item for item in (executable_ambiguity, openocd_ambiguity) if item is not None
    )
    scaffold_actions = (
        PlanAction(
            action_id="resolve_truncated_executables",
            detail=(
                "Executable discovery reached its bound; reduce candidates or pass "
                "`--executable`."
            ),
        )
        if executable_truncated
        else _input_action(
            selected=executable,
            ambiguity=executable_ambiguity,
            missing_id="provide_executable",
            ambiguous_id="choose_executable",
            missing_detail="Provide `--executable <workspace-relative ELF>`.",
            ambiguous_detail="Choose one executable and pass it with `--executable`.",
        ),
        PlanAction(
            action_id="resolve_truncated_cortex_debug_configs",
            detail=(
                "Cortex-Debug configuration discovery was truncated; pass ordered "
                "`--openocd-config` values."
            ),
        )
        if openocd_truncated
        else _input_action(
            selected=openocd,
            ambiguity=openocd_ambiguity,
            missing_id="provide_openocd_configs",
            ambiguous_id="choose_openocd_configuration",
            missing_detail=(
                "Provide ordered `--openocd-config` values or configure one "
                "Cortex-Debug launch."
            ),
            ambiguous_detail=(
                "Choose one Cortex-Debug `configFiles` list and pass its ordered "
                "values with `--openocd-config`."
            ),
        ),
    )
    debug_scaffold = CapabilityPlan(
        name="debug_scaffold",
        status=(
            CapabilityStatus.COMPLETE
            if executable is not None and openocd is not None
            else CapabilityStatus.PARTIAL
            if (
                scaffold_inputs
                or scaffold_ambiguities
                or executable_truncated
                or openocd_truncated
            )
            else CapabilityStatus.UNAVAILABLE
        ),
        inputs=scaffold_inputs,
        ambiguities=scaffold_ambiguities,
        evidence=(
            CandidateEvidence(
                key="raw_openocd_configs",
                values=_canonical_values(inventory.raw_openocd_configs),
                provenance=InputProvenance.WORKSPACE_DISCOVERY,
            ),
        )
        if inventory.raw_openocd_configs
        else (),
        actions=tuple(action for action in scaffold_actions if action is not None),
    )

    svd_truncated = (
        "svd_files" in truncated
        and explicit_svd is None
        and inventory.configured_svd is None
    )
    svd, svd_ambiguity = _select_path(
        key="svd_file",
        explicit=explicit_svd,
        configured=inventory.configured_svd,
        candidates=() if svd_truncated else inventory.svd_candidates,
    )
    register_catalog = CapabilityPlan(
        name="register_catalog",
        status=(
            CapabilityStatus.COMPLETE
            if svd is not None
            else CapabilityStatus.PARTIAL
            if svd_truncated
            else CapabilityStatus.UNAVAILABLE
        ),
        inputs=(svd,) if svd is not None else (),
        ambiguities=(svd_ambiguity,) if svd_ambiguity is not None else (),
        actions=(
            PlanAction(
                action_id="resolve_truncated_svd_files",
                detail=(
                    "SVD discovery reached its bound; leave one default in "
                    "`.dbgoracle/` or pass `--svd-file`."
                ),
            )
            if svd_truncated
            else PlanAction(
                action_id="choose_svd" if svd_ambiguity is not None else "add_svd",
                detail=(
                    "Choose one SVD and pass it with `--svd-file`."
                    if svd_ambiguity is not None
                    else "Place one default SVD at `.dbgoracle/<device>.svd`."
                ),
            ),
        )
        if svd is None
        else (),
    )
    if svd_ambiguity is not None:
        register_catalog = CapabilityPlan(
            name=register_catalog.name,
            status=CapabilityStatus.PARTIAL,
            inputs=register_catalog.inputs,
            ambiguities=register_catalog.ambiguities,
            evidence=register_catalog.evidence,
            actions=register_catalog.actions,
        )
    capabilities = (documentation, debug_scaffold, register_catalog)
    status = (
        "complete"
        if all(item.status is CapabilityStatus.COMPLETE for item in capabilities)
        else "partial"
        if any(item.status is not CapabilityStatus.UNAVAILABLE for item in capabilities)
        else "failed"
    )
    return AutomaticWorkspaceInitPlan(
        workspace_root=inventory.workspace_root,
        status=status,
        capabilities=capabilities,
    )


def _select_path(
    *,
    key: str,
    explicit: str | None,
    configured: str | None,
    candidates: tuple[str, ...],
) -> tuple[PlannedInput | None, InputAmbiguity | None]:
    if explicit is not None:
        return (
            PlannedInput(
                key=key,
                values=(explicit,),
                provenance=InputProvenance.EXPLICIT,
            ),
            None,
        )
    if configured is not None:
        return (
            PlannedInput(
                key=key,
                values=(configured,),
                provenance=InputProvenance.WORKSPACE_SETTING,
            ),
            None,
        )
    canonical = _canonical_values(candidates)
    if len(canonical) == 1:
        return (
            PlannedInput(
                key=key,
                values=canonical,
                provenance=InputProvenance.WORKSPACE_DISCOVERY,
            ),
            None,
        )
    if len(canonical) > 1:
        return (
            None,
            InputAmbiguity(
                key=key,
                alternatives=tuple((value,) for value in canonical),
                provenance=InputProvenance.WORKSPACE_DISCOVERY,
            ),
        )
    return None, None


def _select_openocd(
    *,
    explicit: tuple[str, ...],
    configured: tuple[str, ...],
    launch_configurations: tuple[tuple[str, ...], ...],
) -> tuple[PlannedInput | None, InputAmbiguity | None]:
    if explicit:
        return (
            PlannedInput(
                key="openocd_configs",
                values=explicit,
                provenance=InputProvenance.EXPLICIT,
            ),
            None,
        )
    if configured:
        return (
            PlannedInput(
                key="openocd_configs",
                values=configured,
                provenance=InputProvenance.WORKSPACE_SETTING,
            ),
            None,
        )
    configurations = tuple(
        sorted(launch_configurations, key=lambda values: tuple(values))
    )
    if len(configurations) == 1:
        return (
            PlannedInput(
                key="openocd_configs",
                values=configurations[0],
                provenance=InputProvenance.CORTEX_DEBUG_LAUNCH,
            ),
            None,
        )
    if len(configurations) > 1:
        return (
            None,
            InputAmbiguity(
                key="openocd_configs",
                alternatives=configurations,
                provenance=InputProvenance.CORTEX_DEBUG_LAUNCH,
            ),
        )
    return None, None


def _canonical_values(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(set(values)))


def _input_action(
    *,
    selected: PlannedInput | None,
    ambiguity: InputAmbiguity | None,
    missing_id: str,
    ambiguous_id: str,
    missing_detail: str,
    ambiguous_detail: str,
) -> PlanAction | None:
    if selected is not None:
        return None
    if ambiguity is not None:
        return PlanAction(action_id=ambiguous_id, detail=ambiguous_detail)
    return PlanAction(action_id=missing_id, detail=missing_detail)
