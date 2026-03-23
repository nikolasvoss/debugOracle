from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_MI_LOG_PATH = "${workspaceFolder}/.dbgoracle/cortex-debug-shared-mi.log"
DEFAULT_RTT_LOG_PATH = "${workspaceFolder}/.dbgoracle/session.rtt"
DEFAULT_RTT_STATE_PATH = "${workspaceFolder}/.dbgoracle/session.rtt.state.json"
DEFAULT_RTT_LAUNCH_LOG_PATH = "${workspaceFolder}/.dbgoracle/session.rtt.launch.log"
DEFAULT_RTT_PORT = "60001"
MIN_CORTEX_DEBUG_VERSION = "1.12.1"
MANAGED_BY_VALUE = "dbgoracle init-workspace"


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
    created_files: list[str]
    blocked_files: list[str]
    required_actions: list[RequiredAction]
    dependency_checks: list[DependencyCheck]


def cmd_init_workspace(args: argparse.Namespace) -> int:
    if not args.openocd_config:
        _emit_missing_openocd_config(args, fmt=args.format)
        return 1

    workspace_root = Path(args.workspace_root).resolve()
    try:
        result = initialize_workspace(args, workspace_root)
    except OSError as error:
        print(f"dbgoracle init-workspace: failed\nError: {error}")
        return 1

    _emit_result(result, fmt=args.format)
    return {"complete": 0, "partial": 2, "failed": 1}[result.status]


def _emit_missing_openocd_config(args: argparse.Namespace, *, fmt: str) -> None:
    workspace_root = str(Path(args.workspace_root).resolve())
    guidance = _missing_openocd_config_guidance(args)
    if fmt == "json":
        payload = {
            "status": "failed",
            "workspace_root": workspace_root,
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
        "`--openocd-config` is required because DebugOracle is generating a runnable Cortex-Debug/OpenOCD launch scaffold and cannot guess your OpenOCD setup.",
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


def initialize_workspace(args: argparse.Namespace, workspace_root: Path) -> InitWorkspaceResult:
    session_dir = workspace_root / ".dbgoracle"
    vscode_dir = workspace_root / ".vscode"
    session_dir.mkdir(parents=True, exist_ok=True)
    vscode_dir.mkdir(parents=True, exist_ok=True)

    desired_settings = _settings_payload(args)
    desired_files = [
        (vscode_dir / "settings.json", json.dumps(desired_settings, indent=2) + "\n"),
        (
            vscode_dir / "launch.json",
            _render_launch(openocd_config_files=list(args.openocd_config), with_rtt=bool(args.with_rtt)),
        ),
        (vscode_dir / "tasks.json", _render_tasks(with_rtt=bool(args.with_rtt))),
    ]

    created_files: list[str] = []
    blocked_files: list[str] = []
    required_actions: list[RequiredAction] = []

    for path, content in desired_files:
        if path.exists() and not _can_overwrite(path, force=args.force):
            blocked_files.append(str(path))
            required_actions.append(
                _required_action(
                    path,
                    desired_settings,
                    openocd_config_files=list(args.openocd_config),
                    with_rtt=bool(args.with_rtt),
                )
            )
            continue
        path.write_text(content, encoding="utf-8")
        created_files.append(str(path))

    dependency_checks = _dependency_checks(_resolve_workspace_dependency_path(args.executable, workspace_root))
    status = _overall_status(blocked_files, dependency_checks)
    return InitWorkspaceResult(
        status=status,
        workspace_root=str(workspace_root),
        created_files=created_files,
        blocked_files=blocked_files,
        required_actions=required_actions,
        dependency_checks=dependency_checks,
    )


def _settings_payload(args: argparse.Namespace) -> dict[str, object]:
    payload: dict[str, object] = {
        "debugoracle.managedBy": MANAGED_BY_VALUE,
        "debugoracle.executable": args.executable,
        "debugoracle.miLogPath": args.mi_log_path,
        "debugoracle.rttLogPath": args.rtt_log_path,
        "debugoracle.rttStatePath": args.rtt_state_path,
        "debugoracle.rttLaunchLogPath": args.rtt_launch_log_path,
        "debugoracle.rttPort": str(args.rtt_port),
        "debugoracle.openocdConfigFiles": list(args.openocd_config),
    }
    if args.svd_file:
        payload["debugoracle.svdFile"] = args.svd_file
    return payload


def _render_launch(*, openocd_config_files: list[str], with_rtt: bool) -> str:
    prelaunch_label = "DebugOracle: Prelaunch" if with_rtt else "Prepare debug logs"
    post_debug_line = '      "postDebugTask": "DebugOracle: Stop RTT run",\n' if with_rtt else ""
    rtt_block = ""
    if with_rtt:
        rtt_block = (
            "        // Optional RTT block enabled by init-workspace.\n"
            "        // Update the address window for your target before use.\n"
            "        // \"monitor rtt setup 0x20000000 0x1000 \\\"SEGGER RTT\\\"\",\n"
            "        // \"monitor rtt start\",\n"
            "        // \"monitor rtt server start 60001 0\"\n"
        )
    config_files_block = "\n".join(
        f'        "{value}",' if index < len(openocd_config_files) - 1 else f'        "{value}"'
        for index, value in enumerate(openocd_config_files)
    )
    return (
        "{\n"
        "  // Created by dbgoracle init-workspace.\n"
        "  \"version\": \"0.2.0\",\n"
        "  \"configurations\": [\n"
        "    {\n"
        "      \"name\": \"Debug STM32\",\n"
        "      \"type\": \"cortex-debug\",\n"
        "      \"request\": \"launch\",\n"
        "      \"showDevDebugOutput\": \"raw\",\n"
        "      \"servertype\": \"openocd\",\n"
        "      \"configFiles\": [\n"
        + config_files_block
        + "\n      ],\n"
        "      \"cwd\": \"${workspaceFolder}\",\n"
        "      \"executable\": \"${config:debugoracle.executable}\",\n"
        f"      \"preLaunchTask\": \"{prelaunch_label}\",\n"
        f"{post_debug_line}"
        "      \"preLaunchCommands\": [\n"
        "        \"set pagination off\",\n"
        "        \"set logging overwrite on\",\n"
        "        \"set logging file ${config:debugoracle.miLogPath}\",\n"
        "        \"set logging on\"\n"
        "      ],\n"
        "      \"postLaunchCommands\": [\n"
        "        \"set remotetimeout 20\",\n"
        "        \"monitor reset halt\",\n"
        "        \"set pagination off\""
        + ("\n" + rtt_block.rstrip("\n") if rtt_block else "")
        + "\n      ]\n"
        "    }\n"
        "  ]\n"
        "}\n"
    )


def _render_tasks(*, with_rtt: bool) -> str:
    tasks = [
        {
            "label": "Prepare debug logs",
            "type": "shell",
            "command": "mkdir -p \"${workspaceFolder}/.dbgoracle\" && : > \"${config:debugoracle.miLogPath}\"",
            "windows": {
                "command": "New-Item -ItemType Directory -Force -Path \"${workspaceFolder}\\.dbgoracle\" | Out-Null; New-Item -ItemType File -Force -Path \"${config:debugoracle.miLogPath}\" | Out-Null"
            },
            "problemMatcher": [],
        }
    ]
    if with_rtt:
        tasks = [
            {
                "label": "DebugOracle: Prelaunch",
                "dependsOn": ["Prepare debug logs", "DebugOracle: Start RTT run"],
                "dependsOrder": "sequence",
                "problemMatcher": [],
            },
            {
                "label": "Prepare debug logs",
                "type": "shell",
                "command": "mkdir -p \"${workspaceFolder}/.dbgoracle\" && : > \"${config:debugoracle.miLogPath}\" && : > \"${config:debugoracle.rttLogPath}\" && : > \"${config:debugoracle.rttLaunchLogPath}\" && rm -f \"${config:debugoracle.rttStatePath}\"",
                "windows": {
                    "command": "New-Item -ItemType Directory -Force -Path \"${workspaceFolder}\\.dbgoracle\" | Out-Null; New-Item -ItemType File -Force -Path \"${config:debugoracle.miLogPath}\" | Out-Null; New-Item -ItemType File -Force -Path \"${config:debugoracle.rttLogPath}\" | Out-Null; New-Item -ItemType File -Force -Path \"${config:debugoracle.rttLaunchLogPath}\" | Out-Null; Remove-Item -ErrorAction SilentlyContinue \"${config:debugoracle.rttStatePath}\""
                },
                "problemMatcher": [],
            },
            {
                "label": "DebugOracle: Start RTT run",
                "type": "shell",
                "command": "dbgoracle run --detach --workspace-root \"${workspaceFolder}\" --port ${config:debugoracle.rttPort} --connect-timeout 30 --output \"${config:debugoracle.rttLogPath}\" --state-out \"${config:debugoracle.rttStatePath}\"",
                "windows": {
                    "command": "dbgoracle run --detach --workspace-root \"${workspaceFolder}\" --port ${config:debugoracle.rttPort} --connect-timeout 30 --output \"${config:debugoracle.rttLogPath}\" --state-out \"${config:debugoracle.rttStatePath}\""
                },
                "problemMatcher": [],
            },
            {
                "label": "DebugOracle: Stop RTT run",
                "type": "shell",
                "command": "dbgoracle stop --workspace-root \"${workspaceFolder}\"",
                "windows": {
                    "command": "dbgoracle stop --workspace-root \"${workspaceFolder}\""
                },
                "problemMatcher": [],
            },
        ]
    payload = {
        "version": "2.0.0",
        "debugoracleManagedBy": MANAGED_BY_VALUE,
        "tasks": tasks,
    }
    return json.dumps(payload, indent=2) + "\n"


def _required_action(
    path: Path,
    settings_payload: dict[str, object],
    *,
    openocd_config_files: list[str],
    with_rtt: bool,
) -> RequiredAction:
    if path.name == "settings.json":
        fragment = json.dumps(settings_payload, indent=2)
        return RequiredAction(
            path=str(path),
            reason="existing file blocked automatic settings update",
            fragment=fragment,
        )
    if path.name == "launch.json":
        return RequiredAction(
            path=str(path),
            reason="existing file blocked automatic launch configuration update",
            fragment=_render_launch(openocd_config_files=openocd_config_files, with_rtt=with_rtt),
        )
    return RequiredAction(
        path=str(path),
        reason="existing file blocked automatic task configuration update",
        fragment=_render_tasks(with_rtt=with_rtt),
    )


def _can_overwrite(path: Path, *, force: bool) -> bool:
    if not force:
        return False
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return MANAGED_BY_VALUE in content


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


def _overall_status(blocked_files: list[str], dependency_checks: list[DependencyCheck]) -> str:
    if blocked_files:
        return "partial"
    if any(check.status == "missing" for check in dependency_checks):
        return "partial"
    return "complete"


def _emit_result(result: InitWorkspaceResult, *, fmt: str) -> None:
    if fmt == "json":
        payload = {
            "status": result.status,
            "workspace_root": result.workspace_root,
            "created_files": result.created_files,
            "blocked_files": result.blocked_files,
            "required_actions": [asdict(action) for action in result.required_actions],
            "dependency_checks": [asdict(check) for check in result.dependency_checks],
        }
        print(json.dumps(payload, indent=2))
        return

    print(f"dbgoracle init-workspace: {result.status}")
    print(f"Workspace: {result.workspace_root}")
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
    print("Next: start one debug session, then run `dbgoracle fetch` and `dbgoracle report`.")
