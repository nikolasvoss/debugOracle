from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import sys
from contextlib import redirect_stderr
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

from ...docs_sidecar import ingest_documents
from ...readiness import collect_workspace_plan
from ...workspace_init_plan import (
    CapabilityPlan,
    CapabilityStatus,
    plan_automatic_workspace_init,
)
from ._shared import parse_jsonc

DEFAULT_MI_LOG_PATH = "${workspaceFolder}/.dbgoracle/cortex-debug-shared-mi.log"
DEFAULT_RTT_LOG_PATH = "${workspaceFolder}/.dbgoracle/session.rtt"
DEFAULT_RTT_STATE_PATH = "${workspaceFolder}/.dbgoracle/session.rtt.state.json"
DEFAULT_RTT_LAUNCH_LOG_PATH = "${workspaceFolder}/.dbgoracle/session.rtt.launch.log"
DEFAULT_RTT_PORT = "60001"
MIN_CORTEX_DEBUG_VERSION = "1.12.1"
MANAGED_BY_VALUE = "dbgoracle init-workspace"
DEFAULT_LAUNCH_NAME = "DebugOracle: Debug STM32"
ATTACH_LAUNCH_NAME = "DebugOracle: Attach STM32"
DEFAULT_LAUNCH_ROLE = "workspace-scaffold"
ATTACH_LAUNCH_ROLE = "golden-path-attach"


@dataclass(frozen=True)
class DependencyCheck:
    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class RequiredAction:
    path: str
    reason: str
    fragment: str


@dataclass(frozen=True)
class InitWorkspaceResult:
    status: str
    workspace_root: str
    mode: str
    launch_config_name: str
    launch_config_role: str
    merge_strategy: str
    next_human_action: str
    created_files: list[str]
    blocked_files: list[str]
    required_actions: list[RequiredAction]
    dependency_checks: list[DependencyCheck]


def cmd_init_workspace(args: argparse.Namespace) -> int:
    if getattr(args, "auto", False):
        return _cmd_init_workspace_auto(args)
    if not args.openocd_config:
        _emit_missing_openocd_config(args, fmt=args.format)
        return 1

    workspace_root = Path(args.workspace_root).resolve()
    try:
        result = initialize_workspace(args, workspace_root)
    except (OSError, ValueError) as error:
        print(f"dbgoracle init-workspace: failed\nError: {error}")
        return 1

    _emit_result(result, fmt=args.format)
    return {"complete": 0, "partial": 2, "failed": 1}[result.status]


def _cmd_init_workspace_auto(args: argparse.Namespace) -> int:
    try:
        workspace_root = Path(args.workspace_root).expanduser().resolve(strict=True)
        inventory = collect_workspace_plan(workspace_root).automatic_init_inventory
        explicit_executable = _validated_auto_file(args.executable, workspace_root)
        explicit_svd = _validated_auto_file(args.svd_file, workspace_root)
        explicit_openocd_configs = tuple(
            cast(str, _validated_auto_file(value, workspace_root))
            for value in (args.openocd_config or ())
        )
    except (OSError, ValueError) as error:
        return _emit_auto_failure(args, error)

    plan = plan_automatic_workspace_init(
        inventory,
        docs_authorized=bool(args.yes),
        explicit_executable=explicit_executable,
        explicit_svd=explicit_svd,
        explicit_openocd_configs=explicit_openocd_configs,
    )
    documentation_status, documentation_application = _apply_auto_documentation(
        plan.capabilities[0], workspace_root=workspace_root, authorized=bool(args.yes)
    )
    scaffold_status, scaffold_application = _apply_auto_scaffold(
        plan.capabilities[1],
        register_capability=plan.capabilities[2],
        args=args,
        workspace_root=workspace_root,
    )
    register_status, register_application = _apply_auto_register_catalog(
        plan.capabilities[2],
        args=args,
        workspace_root=workspace_root,
    )
    final_inventory_error: str | None = None
    try:
        final_inventory = collect_workspace_plan(
            workspace_root
        ).automatic_init_inventory
        final_plan = plan_automatic_workspace_init(
            final_inventory,
            docs_authorized=bool(args.yes),
            explicit_executable=explicit_executable,
            explicit_svd=explicit_svd,
            explicit_openocd_configs=explicit_openocd_configs,
        )
    except OSError as error:
        final_plan = plan
        final_inventory_error = str(error)
    payload = final_plan.as_dict()
    capabilities = cast(list[dict[str, object]], payload["capabilities"])
    for capability, status, application in zip(
        capabilities,
        (documentation_status, scaffold_status, register_status),
        (documentation_application, scaffold_application, register_application),
    ):
        capability["status"] = status
        capability["application"] = application
    if documentation_status == CapabilityStatus.PARTIAL.value and bool(
        documentation_application.get("attempted")
    ):
        _append_auto_action(
            capabilities[0],
            action_id="inspect_document_ingest_results",
            detail=(
                "Inspect the per-document ingest results and run "
                "`dbgoracle docs doctor` before retrying failed or partial PDFs."
            ),
        )
    if scaffold_status == CapabilityStatus.PARTIAL.value and bool(
        scaffold_application.get("attempted")
    ):
        _append_auto_action(
            capabilities[1],
            action_id="complete_debug_scaffold_setup",
            detail=(
                "Resolve the blocked workspace files and missing dependency checks "
                "reported by this capability, then re-run automatic initialization."
            ),
        )
    if register_status == CapabilityStatus.PARTIAL.value:
        _append_auto_action(
            capabilities[2],
            action_id="persist_svd_setting",
            detail=(
                "Merge the selected `debugoracle.svdFile` value into the user-owned "
                "`.vscode/settings.json`, or re-run with `--force` only when that "
                "file is DebugOracle-managed."
            ),
        )
    statuses = tuple(str(item["status"]) for item in capabilities)
    payload["status"] = _auto_overall_status(statuses)
    if final_inventory_error is not None:
        payload["status"] = (
            "partial"
            if any(status != CapabilityStatus.UNAVAILABLE.value for status in statuses)
            else "failed"
        )
        payload["error"] = (
            "Workspace re-inventory failed after capability application: "
            f"{final_inventory_error}"
        )
    _emit_auto_payload(payload, fmt=args.format)
    return {"complete": 0, "partial": 2, "failed": 1}[str(payload["status"])]


def _apply_auto_documentation(
    capability: CapabilityPlan,
    *,
    workspace_root: Path,
    authorized: bool,
) -> tuple[str, dict[str, object]]:
    documents = _capability_input_values(capability, "documents")
    if not authorized or not documents:
        return capability.status.value, {
            "attempted": False,
            "results": [],
            "warnings": [],
        }
    parser_stderr = io.StringIO()
    try:
        with redirect_stderr(parser_stderr):
            batch = ingest_documents(
                workspace_root=workspace_root,
                files=list(documents),
                parser_name="pypdf",
                semantic=False,
                force=False,
            )
    except Exception as error:
        parser_diagnostics = tuple(
            line for line in parser_stderr.getvalue().splitlines() if line
        )
        return CapabilityStatus.PARTIAL.value, {
            "attempted": True,
            "results": [],
            "warnings": list(parser_diagnostics),
            "invalid_inputs": [],
            "error": str(error),
        }
    parser_diagnostics = tuple(
        line for line in parser_stderr.getvalue().splitlines() if line
    )
    normalized_results = [
        {
            "source_pdf": result.source_pdf,
            "sidecar_dir": result.sidecar_dir,
            "parser_used": result.parser_used,
            "page_count": result.page_count,
            "chunk_count": result.chunk_count,
            "ingest_state": result.ingest_state,
            "warning_summary": result.warning_summary,
            "warnings": list(result.warnings),
        }
        for result in sorted(batch.results, key=lambda item: item.source_pdf)
    ]
    states = {result.ingest_state for result in batch.results}
    status = (
        CapabilityStatus.COMPLETE.value
        if batch.results and states <= {"clean", "warning"}
        else CapabilityStatus.PARTIAL.value
    )
    return status, {
        "attempted": True,
        "results": normalized_results,
        "warnings": [*batch.warnings, *parser_diagnostics],
        "invalid_inputs": list(batch.invalid_inputs),
    }


def _capability_input_values(capability: CapabilityPlan, key: str) -> tuple[str, ...]:
    for item in capability.inputs:
        if item.key == key:
            return item.values
    return ()


def _auto_overall_status(statuses: tuple[str, ...]) -> str:
    if statuses and all(
        status == CapabilityStatus.COMPLETE.value for status in statuses
    ):
        return "complete"
    if any(status != CapabilityStatus.UNAVAILABLE.value for status in statuses):
        return "partial"
    return "failed"


def _emit_auto_failure(args: argparse.Namespace, error: Exception) -> int:
    workspace_root = str(Path(args.workspace_root).expanduser().resolve())
    payload: dict[str, object] = {
        "schema_version": "1",
        "scope": "automatic_workspace_init",
        "workspace_root": workspace_root,
        "status": "failed",
        "capabilities": [],
        "error": str(error),
    }
    _emit_auto_payload(payload, fmt=args.format)
    return 1


def _validated_auto_file(value: str | None, workspace_root: Path) -> str | None:
    if value is None:
        return None
    expanded = value.replace("${workspaceFolder}", str(workspace_root))
    candidate = Path(expanded).expanduser()
    if not candidate.is_absolute():
        candidate = workspace_root / candidate
    try:
        relative = candidate.relative_to(workspace_root)
    except ValueError as error:
        raise ValueError(
            f"automatic input is outside the workspace: {value}"
        ) from error
    current = workspace_root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"automatic input must not use symlinks: {value}")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise ValueError(f"automatic input does not exist: {value}") from error
    if not resolved.is_file() or not os.access(resolved, os.R_OK):
        raise ValueError(f"automatic input is not a readable regular file: {value}")
    if not resolved.is_relative_to(workspace_root):
        raise ValueError(f"automatic input is outside the workspace: {value}")
    return str(resolved)


def _apply_auto_scaffold(
    capability: CapabilityPlan,
    *,
    register_capability: CapabilityPlan,
    args: argparse.Namespace,
    workspace_root: Path,
) -> tuple[str, dict[str, object]]:
    executable = _capability_input_values(capability, "executable")
    openocd_configs = _capability_input_values(capability, "openocd_configs")
    if not executable or not openocd_configs:
        return capability.status.value, {"attempted": False}
    try:
        _validate_auto_output_directory(
            workspace_root,
            workspace_root / ".dbgoracle",
            filenames=(),
        )
        _validate_auto_output_directory(
            workspace_root,
            workspace_root / ".vscode",
            filenames=("settings.json", "launch.json", "tasks.json"),
        )
    except ValueError as error:
        return CapabilityStatus.PARTIAL.value, {
            "attempted": True,
            "workspace_files": [],
            "blocked_files": [],
            "required_actions": [],
            "dependency_checks": [],
            "error": str(error),
        }
    selected_svd = _capability_input_values(register_capability, "svd_file")
    apply_args = argparse.Namespace(**vars(args))
    apply_args.executable = executable[0]
    apply_args.openocd_config = list(openocd_configs)
    apply_args.svd_file = selected_svd[0] if selected_svd else None
    try:
        result = initialize_workspace(apply_args, workspace_root)
    except (OSError, ValueError) as error:
        return CapabilityStatus.PARTIAL.value, {
            "attempted": True,
            "workspace_files": _current_auto_workspace_files(workspace_root),
            "blocked_files": [],
            "required_actions": [],
            "dependency_checks": [],
            "error": str(error),
        }
    return result.status, {
        "attempted": True,
        "workspace_files": _current_auto_workspace_files(workspace_root),
        "blocked_files": sorted(result.blocked_files),
        "required_actions": [asdict(action) for action in result.required_actions],
        "dependency_checks": [asdict(check) for check in result.dependency_checks],
    }


def _current_auto_workspace_files(workspace_root: Path) -> list[str]:
    return [
        str(path)
        for path in (
            workspace_root / ".vscode" / "settings.json",
            workspace_root / ".vscode" / "launch.json",
            workspace_root / ".vscode" / "tasks.json",
        )
        if path.is_file()
    ]


def _apply_auto_register_catalog(
    capability: CapabilityPlan,
    *,
    args: argparse.Namespace,
    workspace_root: Path,
) -> tuple[str, dict[str, object]]:
    selected = _capability_input_values(capability, "svd_file")
    if not selected:
        return capability.status.value, {"attempted": False}
    selected_path = Path(selected[0])
    setting_path = workspace_root / ".vscode" / "settings.json"
    if selected_path.parent == workspace_root / ".dbgoracle":
        return CapabilityStatus.COMPLETE.value, {
            "attempted": False,
            "selected_file": str(selected_path),
            "state": "current",
            "source": "dbgoracle_default_directory",
        }
    try:
        _validate_auto_output_directory(
            workspace_root,
            workspace_root / ".vscode",
            filenames=("settings.json",),
        )
    except ValueError as error:
        return CapabilityStatus.PARTIAL.value, {
            "attempted": True,
            "selected_file": str(selected_path),
            "setting_path": str(workspace_root / ".vscode" / "settings.json"),
            "state": "blocked",
            "error": str(error),
        }
    try:
        state = _persist_auto_svd_setting(
            setting_path,
            selected_path=selected_path,
            force=bool(args.force),
            allow_write=not bool(args.attach),
        )
    except OSError as error:
        return CapabilityStatus.PARTIAL.value, {
            "attempted": True,
            "selected_file": str(selected_path),
            "setting_path": str(setting_path),
            "state": "failed",
            "error": str(error),
        }
    return (
        CapabilityStatus.COMPLETE.value
        if state == "current"
        else CapabilityStatus.PARTIAL.value,
        {
            "attempted": True,
            "selected_file": str(selected_path),
            "setting_path": str(setting_path),
            "state": state,
        },
    )


def _persist_auto_svd_setting(
    setting_path: Path, *, selected_path: Path, force: bool, allow_write: bool
) -> str:
    if setting_path.exists():
        try:
            payload = parse_jsonc(setting_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return "blocked"
        if not isinstance(payload, dict):
            return "blocked"
        current = payload.get("debugoracle.svdFile")
        if isinstance(current, str) and _setting_path_matches(
            current, selected_path=selected_path, workspace_root=setting_path.parents[1]
        ):
            return "current"
        if not allow_write:
            return "blocked"
        if payload.get("debugoracle.managedBy") != MANAGED_BY_VALUE or not force:
            return "blocked"
        payload["debugoracle.svdFile"] = str(selected_path)
    else:
        if not allow_write:
            return "blocked"
        payload = {
            "debugoracle.managedBy": MANAGED_BY_VALUE,
            "debugoracle.svdFile": str(selected_path),
        }
        setting_path.parent.mkdir(parents=True, exist_ok=True)
    setting_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return "current"


def _validate_auto_output_directory(
    workspace_root: Path,
    directory: Path,
    *,
    filenames: tuple[str, ...],
) -> None:
    try:
        relative = directory.relative_to(workspace_root)
    except ValueError as error:
        raise ValueError(
            f"automatic output is outside the workspace: {directory}"
        ) from error
    current = workspace_root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"automatic output must not use symlinks: {current}")
    if directory.exists() and not directory.is_dir():
        raise ValueError(f"automatic output directory is not a directory: {directory}")
    for filename in filenames:
        output_path = directory / filename
        if output_path.is_symlink():
            raise ValueError(f"automatic output must not use symlinks: {output_path}")
        if output_path.exists() and not output_path.is_file():
            raise ValueError(f"automatic output is not a regular file: {output_path}")


def _setting_path_matches(
    current: str, *, selected_path: Path, workspace_root: Path
) -> bool:
    expanded = current.replace("${workspaceFolder}", str(workspace_root))
    path = Path(expanded).expanduser()
    if not path.is_absolute():
        path = workspace_root / path
    return path.resolve() == selected_path


def _append_auto_action(
    capability_payload: dict[str, object], *, action_id: str, detail: str
) -> None:
    actions = cast(list[dict[str, str]], capability_payload["actions"])
    if any(action["action_id"] == action_id for action in actions):
        return
    actions.append({"action_id": action_id, "detail": detail})


def _emit_auto_payload(payload: dict[str, object], *, fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(payload, indent=2))
        return
    print(f"dbgoracle init-workspace --auto: {payload['status']}")
    print(f"Workspace: {payload['workspace_root']}")
    for raw in cast(list[dict[str, object]], payload.get("capabilities", [])):
        print(f"- {raw['name']}: {raw['status']}")
        for selected in cast(list[dict[str, object]], raw["inputs"]):
            values = ", ".join(cast(list[str], selected["values"]))
            print(f"  {selected['key']} ({selected['provenance']}): {values}")
        for ambiguity in cast(list[dict[str, object]], raw["ambiguities"]):
            alternatives = ", ".join(
                "/".join(values)
                for values in cast(list[list[str]], ambiguity["alternatives"])
            )
            print(
                f"  ambiguous {ambiguity['key']} ({ambiguity['provenance']}): "
                f"{alternatives}"
            )
        for action in cast(list[dict[str, str]], raw["actions"]):
            print(f"  action: {action['detail']}")
    if error := payload.get("error"):
        print(f"Error: {error}", file=sys.stderr)


def _emit_missing_openocd_config(args: argparse.Namespace, *, fmt: str) -> None:
    workspace_root = str(Path(args.workspace_root).resolve())
    guidance = _missing_openocd_config_guidance(args)
    if fmt == "json":
        payload = {
            "status": "failed",
            "workspace_root": workspace_root,
            "mode": "attach" if getattr(args, "attach", False) else "fresh",
            "created_files": [],
            "blocked_files": [],
            "required_actions": [
                {
                    "path": "--openocd-config",
                    "reason": "missing required OpenOCD launch config",
                    "fragment": guidance,
                }
            ],
            "dependency_checks": [],
        }
        print(json.dumps(payload, indent=2))
        return
    print(guidance, file=sys.stderr)


def _missing_openocd_config_guidance(args: argparse.Namespace) -> str:
    command_parts = [
        "dbgoracle init-workspace",
        f"--workspace-root {args.workspace_root}",
        f"--executable {args.executable or 'path/to/firmware.elf'}",
    ]
    if getattr(args, "attach", False):
        command_parts.append("--attach")
    if args.svd_file:
        command_parts.append(f"--svd-file {args.svd_file}")
    if args.with_rtt:
        command_parts.append("--with-rtt")
    command_parts.extend(
        [
            "--openocd-config interface/stlink.cfg",
            "--openocd-config target/stm32l4x.cfg",
        ]
    )
    example_command = " ".join(command_parts)
    parts = [
        "dbgoracle init-workspace: missing required OpenOCD launch config",
        "",
        "`--openocd-config` is required because DebugOracle is generating Cortex-Debug attach fragments and cannot guess your OpenOCD setup.",
        "",
        "What to provide:",
        "- `interface/*.cfg` = the debug probe, for example `interface/stlink.cfg`.",
        "- `target/*.cfg` = the MCU family, for example `target/stm32l4x.cfg`.",
        "",
        "Try this:",
        example_command,
        "",
        "If Cortex-Debug already works in this workspace, copy the same `configFiles` entries from `.vscode/launch.json`.",
        "More help: `dbgoracle init-workspace --help` and `examples/cortex-debug/README.md`.",
    ]
    return "\n".join(parts)


def initialize_workspace(
    args: argparse.Namespace, workspace_root: Path
) -> InitWorkspaceResult:
    attach_mode = bool(getattr(args, "attach", False))
    mode = "attach" if attach_mode else "fresh"
    launch_config_name = ATTACH_LAUNCH_NAME if attach_mode else DEFAULT_LAUNCH_NAME
    launch_config_role = ATTACH_LAUNCH_ROLE if attach_mode else DEFAULT_LAUNCH_ROLE

    session_dir = workspace_root / ".dbgoracle"
    vscode_dir = workspace_root / ".vscode"
    session_dir.mkdir(parents=True, exist_ok=True)
    if not attach_mode:
        vscode_dir.mkdir(parents=True, exist_ok=True)

    desired_settings = _settings_payload(
        args,
        workspace_root=workspace_root,
        attach_mode=attach_mode,
        launch_config_name=launch_config_name,
        launch_config_role=launch_config_role,
    )
    desired_launch_config = _launch_configuration(
        openocd_config_files=list(args.openocd_config),
        with_rtt=bool(args.with_rtt),
        attach_mode=attach_mode,
        launch_name=launch_config_name,
        launch_role=launch_config_role,
        include_managed_marker=not attach_mode,
    )
    desired_tasks = _tasks_payload(
        with_rtt=bool(args.with_rtt),
        attach_mode=attach_mode,
        include_managed_marker=not attach_mode,
    )

    created_files: list[str] = []
    blocked_files: list[str] = []
    required_actions: list[RequiredAction] = []

    if attach_mode:
        for path in (
            vscode_dir / "settings.json",
            vscode_dir / "launch.json",
            vscode_dir / "tasks.json",
        ):
            blocked_files.append(str(path))
            required_actions.append(
                _required_action(
                    path,
                    desired_settings,
                    desired_launch_config,
                    desired_tasks,
                    attach_mode=True,
                )
            )
    else:
        desired_files = [
            (
                vscode_dir / "settings.json",
                json.dumps(desired_settings, indent=2) + "\n",
            ),
            (vscode_dir / "launch.json", _render_launch_file(desired_launch_config)),
            (vscode_dir / "tasks.json", json.dumps(desired_tasks, indent=2) + "\n"),
        ]
        for path, content in desired_files:
            if (
                getattr(args, "auto", False)
                and path.is_file()
                and path.read_text(encoding="utf-8") == content
            ):
                continue
            if path.exists() and not _can_overwrite(path, force=args.force):
                blocked_files.append(str(path))
                required_actions.append(
                    _required_action(
                        path,
                        desired_settings,
                        desired_launch_config,
                        desired_tasks,
                        attach_mode=False,
                    )
                )
                continue
            path.write_text(content, encoding="utf-8")
            created_files.append(str(path))

    dependency_checks = _dependency_checks(
        _resolve_workspace_dependency_path(args.executable, workspace_root)
    )
    status = _overall_status(blocked_files, dependency_checks)
    return InitWorkspaceResult(
        status=status,
        workspace_root=str(workspace_root),
        mode=mode,
        launch_config_name=launch_config_name,
        launch_config_role=launch_config_role,
        merge_strategy="agent" if attach_mode else "direct",
        next_human_action=_next_human_action(
            attach_mode=attach_mode,
            blocked_files=blocked_files,
            launch_config_name=launch_config_name,
        ),
        created_files=created_files,
        blocked_files=blocked_files,
        required_actions=required_actions,
        dependency_checks=dependency_checks,
    )


def _settings_payload(
    args: argparse.Namespace,
    *,
    workspace_root: Path,
    attach_mode: bool,
    launch_config_name: str,
    launch_config_role: str,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "debugoracle.executable": args.executable,
        "debugoracle.miLogPath": args.mi_log_path,
        "debugoracle.rttLogPath": args.rtt_log_path,
        "debugoracle.rttStatePath": args.rtt_state_path,
        "debugoracle.rttLaunchLogPath": args.rtt_launch_log_path,
        "debugoracle.rttPort": str(args.rtt_port),
        "debugoracle.openocdConfigFiles": list(args.openocd_config),
        "debugoracle.workspaceSetupMode": "attach" if attach_mode else "fresh",
        "debugoracle.launchConfigName": launch_config_name,
        "debugoracle.launchConfigRole": launch_config_role,
    }
    if not attach_mode:
        payload["debugoracle.managedBy"] = MANAGED_BY_VALUE
    if args.svd_file:
        svd_file = args.svd_file.replace("${workspaceFolder}", str(workspace_root))
        payload["debugoracle.svdFile"] = str(
            _resolve_workspace_dependency_path(svd_file, workspace_root)
        )
    return payload


def _launch_configuration(
    *,
    openocd_config_files: list[str],
    with_rtt: bool,
    attach_mode: bool,
    launch_name: str,
    launch_role: str,
    include_managed_marker: bool,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": launch_name,
        "type": "cortex-debug",
        "request": "launch",
        "showDevDebugOutput": "raw",
        "servertype": "openocd",
        "configFiles": openocd_config_files,
        "cwd": "${workspaceFolder}",
        "executable": "${config:debugoracle.executable}",
        "preLaunchTask": "DebugOracle: Prelaunch"
        if (with_rtt or attach_mode)
        else "Prepare debug logs",
        "preLaunchCommands": [
            "set pagination off",
            "set logging overwrite on",
            "set logging file ${config:debugoracle.miLogPath}",
            "set logging on",
        ],
        "postLaunchCommands": [
            "set remotetimeout 20",
            "monitor reset halt",
            "set pagination off",
        ],
        "debugoracleRole": launch_role,
    }
    if include_managed_marker:
        payload["debugoracleManagedBy"] = MANAGED_BY_VALUE
    if with_rtt:
        payload["postDebugTask"] = "DebugOracle: Stop RTT run"
        cast(list[str], payload["postLaunchCommands"]).extend(
            [
                'monitor rtt setup 0x20000000 0x1000 "SEGGER RTT"',
                "monitor rtt start",
                "monitor rtt server start ${config:debugoracle.rttPort} 0",
            ]
        )
    return payload


def _render_launch_file(configuration: dict[str, object]) -> str:
    payload = {
        "version": "0.2.0",
        "debugoracleManagedBy": MANAGED_BY_VALUE,
        "configurations": [configuration],
    }
    return json.dumps(payload, indent=2) + "\n"


def _tasks_payload(
    *, with_rtt: bool, attach_mode: bool, include_managed_marker: bool
) -> dict[str, object]:
    prepare_debug_logs = {
        "label": "Prepare debug logs",
        "type": "shell",
        "command": 'mkdir -p "${workspaceFolder}/.dbgoracle" && : > "${config:debugoracle.miLogPath}"',
        "windows": {
            "command": 'New-Item -ItemType Directory -Force -Path "${workspaceFolder}\\.dbgoracle" | Out-Null; New-Item -ItemType File -Force -Path "${config:debugoracle.miLogPath}" | Out-Null'
        },
        "problemMatcher": [],
    }
    if with_rtt:
        prepare_debug_logs = {
            "label": "Prepare debug logs",
            "type": "shell",
            "command": 'mkdir -p "${workspaceFolder}/.dbgoracle" && : > "${config:debugoracle.miLogPath}" && : > "${config:debugoracle.rttLogPath}" && : > "${config:debugoracle.rttLaunchLogPath}" && rm -f "${config:debugoracle.rttStatePath}"',
            "windows": {
                "command": 'New-Item -ItemType Directory -Force -Path "${workspaceFolder}\\.dbgoracle" | Out-Null; New-Item -ItemType File -Force -Path "${config:debugoracle.miLogPath}" | Out-Null; New-Item -ItemType File -Force -Path "${config:debugoracle.rttLogPath}" | Out-Null; New-Item -ItemType File -Force -Path "${config:debugoracle.rttLaunchLogPath}" | Out-Null; Remove-Item -ErrorAction SilentlyContinue "${config:debugoracle.rttStatePath}"'
            },
            "problemMatcher": [],
        }

    tasks = [prepare_debug_logs]
    if with_rtt or attach_mode:
        prelaunch_dependencies = ["Prepare debug logs"]
        if attach_mode:
            prelaunch_dependencies.append("DebugOracle: Guard Attach Launch")
            tasks.append(
                {
                    "label": "DebugOracle: Guard Attach Launch",
                    "type": "shell",
                    "command": 'dbgoracle guard-openocd-launch --workspace-root "${workspaceFolder}"',
                    "windows": {
                        "command": 'dbgoracle guard-openocd-launch --workspace-root "${workspaceFolder}"'
                    },
                    "problemMatcher": [],
                }
            )
        if with_rtt:
            prelaunch_dependencies.append("DebugOracle: Start RTT run")
            tasks.append(
                {
                    "label": "DebugOracle: Start RTT run",
                    "type": "shell",
                    "command": 'dbgoracle run --detach --workspace-root "${workspaceFolder}" --port ${config:debugoracle.rttPort} --connect-timeout 30 --output "${config:debugoracle.rttLogPath}" --state-out "${config:debugoracle.rttStatePath}"',
                    "windows": {
                        "command": 'dbgoracle run --detach --workspace-root "${workspaceFolder}" --port ${config:debugoracle.rttPort} --connect-timeout 30 --output "${config:debugoracle.rttLogPath}" --state-out "${config:debugoracle.rttStatePath}"'
                    },
                    "problemMatcher": [],
                }
            )
            tasks.append(
                {
                    "label": "DebugOracle: Stop RTT run",
                    "type": "shell",
                    "command": 'dbgoracle stop --workspace-root "${workspaceFolder}"',
                    "windows": {
                        "command": 'dbgoracle stop --workspace-root "${workspaceFolder}"'
                    },
                    "problemMatcher": [],
                }
            )
        tasks.insert(
            0,
            {
                "label": "DebugOracle: Prelaunch",
                "dependsOn": prelaunch_dependencies,
                "dependsOrder": "sequence",
                "problemMatcher": [],
            },
        )
    payload = {
        "version": "2.0.0",
        "tasks": tasks,
    }
    if include_managed_marker:
        payload["debugoracleManagedBy"] = MANAGED_BY_VALUE
    return payload


def _required_action(
    path: Path,
    settings_payload: dict[str, object],
    launch_payload: dict[str, object],
    tasks_payload: dict[str, object],
    *,
    attach_mode: bool,
) -> RequiredAction:
    if path.name == "settings.json":
        fragment = json.dumps(settings_payload, indent=2)
        reason = (
            "merge the DebugOracle attach settings into the existing workspace settings"
            if attach_mode
            else "existing file blocked automatic settings update"
        )
        return RequiredAction(path=str(path), reason=reason, fragment=fragment)
    if path.name == "launch.json":
        fragment = json.dumps(launch_payload, indent=2)
        reason = (
            "merge the DebugOracle attach launch into the existing launch configurations"
            if attach_mode
            else "existing file blocked automatic launch configuration update"
        )
        return RequiredAction(path=str(path), reason=reason, fragment=fragment)
    fragment = json.dumps({"tasks": tasks_payload["tasks"]}, indent=2)
    reason = (
        "merge the DebugOracle attach tasks into the existing task list"
        if attach_mode
        else "existing file blocked automatic task configuration update"
    )
    return RequiredAction(path=str(path), reason=reason, fragment=fragment)


def _can_overwrite(path: Path, *, force: bool) -> bool:
    if not force:
        return False
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return False
    payload = parse_jsonc(content)
    if not isinstance(payload, dict):
        return False
    if path.name == "settings.json":
        return payload.get("debugoracle.managedBy") == MANAGED_BY_VALUE
    if path.name == "tasks.json":
        return payload.get("debugoracleManagedBy") == MANAGED_BY_VALUE
    if path.name == "launch.json":
        if payload.get("debugoracleManagedBy") == MANAGED_BY_VALUE:
            return True
        configurations = payload.get("configurations")
        if not isinstance(configurations, list) or len(configurations) != 1:
            return False
        configuration = configurations[0]
        return (
            isinstance(configuration, dict)
            and configuration.get("debugoracleManagedBy") == MANAGED_BY_VALUE
        )
    return False


def _resolve_workspace_dependency_path(value: str, workspace_root: Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return workspace_root / path


def _dependency_checks(executable_path: Path) -> list[DependencyCheck]:
    return [
        DependencyCheck(
            name="openocd",
            status="available" if shutil.which("openocd") else "missing",
            detail="required for the Cortex-Debug/OpenOCD setup path",
        ),
        DependencyCheck(
            name="executable",
            status="available" if executable_path.exists() else "deferred",
            detail=str(executable_path),
        ),
        DependencyCheck(
            name="cortex-debug",
            status="unknown",
            detail=(
                "required VS Code extension for the generated launch configuration; "
                f"minimum supported version {MIN_CORTEX_DEBUG_VERSION}"
            ),
        ),
    ]


def _overall_status(
    blocked_files: list[str], dependency_checks: list[DependencyCheck]
) -> str:
    if blocked_files:
        return "partial"
    if any(check.status == "missing" for check in dependency_checks):
        return "partial"
    return "complete"


def _next_human_action(
    *, attach_mode: bool, blocked_files: list[str], launch_config_name: str
) -> str:
    if attach_mode:
        return f"Merge the DebugOracle attach fragments into the workspace, then start `{launch_config_name}` in VS Code and rerun `dbgoracle status --workspace-root .`."
    if blocked_files:
        return f"Update the blocked workspace files, then start `{launch_config_name}` in VS Code and rerun `dbgoracle status --workspace-root .`."
    return f"Start `{launch_config_name}` in VS Code, keep the debug session running, then rerun `dbgoracle status --workspace-root .`."


def _emit_result(result: InitWorkspaceResult, *, fmt: str) -> None:
    if fmt == "json":
        payload = {
            "status": result.status,
            "workspace_root": result.workspace_root,
            "mode": result.mode,
            "launch_config_name": result.launch_config_name,
            "launch_config_role": result.launch_config_role,
            "merge_strategy": result.merge_strategy,
            "next_human_action": result.next_human_action,
            "created_files": result.created_files,
            "blocked_files": result.blocked_files,
            "required_actions": [asdict(action) for action in result.required_actions],
            "dependency_checks": [asdict(check) for check in result.dependency_checks],
        }
        print(json.dumps(payload, indent=2))
        return

    print(f"dbgoracle init-workspace: {result.status}")
    print(f"Workspace: {result.workspace_root}")
    print(f"Mode: {result.mode}")
    print(
        f"Launch Configuration: {result.launch_config_name} ({result.launch_config_role})"
    )
    if result.created_files:
        print("Created:")
        for path in result.created_files:
            print(f"- {path}")
    if result.blocked_files:
        print("Blocked:")
        for action in result.required_actions:
            print(f"- {action.path}: {action.reason}")
    print("Dependency checks:")
    for check in result.dependency_checks:
        print(f"- {check.name}: {check.status} ({check.detail})")
    if result.required_actions:
        print("Required actions:")
        for action in result.required_actions:
            print(f"- Update {action.path}: {action.reason}")
            print(action.fragment)
    print(f"Next human action: {result.next_human_action}")
