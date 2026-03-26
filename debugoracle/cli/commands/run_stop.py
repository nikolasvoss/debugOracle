from __future__ import annotations

import argparse
import json
import os
import platform
import shlex
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from ...session import DEFAULT_SESSION_DIR
from ...sources.streams.rtt import (
    DEFAULT_RTT_HOST,
    RttCaptureTimeoutError,
    capture_rtt,
    default_state_path,
)

DEFAULT_RUN_PORT = 60001
DEFAULT_RUN_OUTPUT = "session.rtt"
DEFAULT_RUN_METADATA = "session.rtt.run.json"
DEFAULT_RUN_LAUNCH_LOG = "session.rtt.launch.log"
PACKAGE_ROOT = Path(__file__).resolve().parents[3]


def cmd_run(args: argparse.Namespace) -> int:
    workspace_root = Path(args.workspace_root).resolve()
    output_path = resolve_run_output_path(workspace_root, args.output)
    state_path = (
        Path(resolve_workspace_path(args.state_out, workspace_root) or "")
        if args.state_out
        else default_state_path(output_path)
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    launch_log = output_path.parent / DEFAULT_RUN_LAUNCH_LOG
    runtime_path = output_path.parent / DEFAULT_RUN_METADATA

    if args.detach:
        return _cmd_run_detach(
            args=args,
            workspace_root=workspace_root,
            output_path=output_path,
            state_path=state_path,
            runtime_path=runtime_path,
            launch_log=launch_log,
        )
    return _run_capture_foreground(args, output_path, state_path)


def cmd_stop(args: argparse.Namespace) -> int:
    workspace_root = Path(args.workspace_root).resolve()
    runtime_path = (
        Path(resolve_workspace_path(args.runtime_file, workspace_root) or "")
        if args.runtime_file
        else workspace_root / DEFAULT_SESSION_DIR / DEFAULT_RUN_METADATA
    )
    runtime = load_runtime_metadata(runtime_path)
    if runtime is None:
        print(f"No detached RTT run is active for workspace {workspace_root}.")
        return 0
    pid = int(runtime.get("pid", 0))  # type: ignore[arg-type]
    if pid <= 0:
        print(f"Warning: Invalid runtime metadata in {runtime_path}. Cleaning up stale file.")
        safe_unlink(runtime_path)
        return 0
    if not is_pid_running(pid):
        print(f"Warning: Detached RTT run pid {pid} is not running. Cleaning up stale metadata.")
        safe_unlink(runtime_path)
        return 0
    if not is_owned_run_process(pid):
        print(
            "Warning: Refusing to stop pid "
            f"{pid} because it is not a managed dbgoracle run process. "
            "Cleaning up stale metadata."
        )
        safe_unlink(runtime_path)
        return 0

    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as error:
        print(f"Failed to signal detached RTT run pid {pid}: {error}", file=sys.stderr)
        return 1
    deadline = time.monotonic() + max(0.0, args.grace_timeout)
    while time.monotonic() < deadline:
        if not is_pid_running(pid):
            safe_unlink(runtime_path)
            print(f"Stopped detached RTT run (pid {pid}).")
            return 0
        time.sleep(0.1)

    if is_pid_running(pid):
        try:
            kill_signal = signal.SIGKILL if hasattr(signal, "SIGKILL") else signal.SIGTERM
            os.kill(pid, kill_signal)
        except OSError as error:
            print(f"Failed to force-stop detached RTT run pid {pid}: {error}", file=sys.stderr)
            return 1
        time.sleep(0.1)
    if is_pid_running(pid):
        print(f"Failed to stop detached RTT run (pid {pid}).", file=sys.stderr)
        return 1
    safe_unlink(runtime_path)
    print(f"Stopped detached RTT run (pid {pid}) after force-kill.")
    return 0


def _cmd_run_detach(
    *,
    args: argparse.Namespace,
    workspace_root: Path,
    output_path: Path,
    state_path: Path,
    runtime_path: Path,
    launch_log: Path,
) -> int:
    existing_runtime = load_runtime_metadata(runtime_path)
    if existing_runtime is not None:
        pid = int(existing_runtime.get("pid", 0))  # type: ignore[arg-type]
        if pid > 0 and is_pid_running(pid):
            if is_owned_run_process(pid):
                print(
                    "Detached RTT run already active "
                    f"(pid {pid}). Use `dbgoracle stop --workspace-root {workspace_root}` first."
                )
                return 0
            print(
                "Warning: Runtime metadata points to an unrelated live process "
                f"(pid {pid}). Cleaning stale metadata and starting a new detached run."
            )
        else:
            print(
                f"Warning: Found stale detached runtime metadata at {runtime_path}. "
                "Replacing it."
            )
        safe_unlink(runtime_path)

    launch_log.parent.mkdir(parents=True, exist_ok=True)
    with launch_log.open("a", encoding="utf-8") as log_handle:
        child = subprocess.Popen(
            build_detached_run_command(
                args=args,
                workspace_root=workspace_root,
                output_path=output_path,
                state_path=state_path,
            ),
            env=build_detached_run_env(),
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    time.sleep(0.2)
    early_exit_code = child.poll()
    if early_exit_code is not None:
        print(
            "Detached RTT run exited during startup "
            f"(exit code {early_exit_code}). Check {launch_log}.",
            file=sys.stderr,
        )
        return 1

    runtime_path.write_text(
        json.dumps(
            {
                "pid": child.pid,
                "host": args.host,
                "port": args.port,
                "workspace_root": str(workspace_root),
                "output": str(output_path),
                "state_out": str(state_path),
                "launch_log": str(launch_log),
                "started_at": utc_now(),
                "mode": "detached",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        "Started detached RTT run "
        f"(pid {child.pid}) -> {output_path}. "
        f"Use `dbgoracle stop --workspace-root {workspace_root}` to stop."
    )
    return 0


def _run_capture_foreground(
    args: argparse.Namespace,
    output_path: Path,
    state_path: Path,
) -> int:
    try:
        state = capture_rtt(
            host=args.host,
            port=args.port,
            output_path=output_path,
            state_path=state_path,
            connect_timeout=max(0.0, args.connect_timeout),
            poll_interval=max(0.05, args.poll_interval),
            idle_timeout=args.idle_timeout,
            append=args.append,
            on_connect=lambda _: print(
                f"RTT run connected {args.host}:{args.port} -> {output_path}"
            ),
        )
    except RttCaptureTimeoutError as error:
        print(str(error), file=sys.stderr)
        return 2
    except OSError as error:
        print(f"RTT run failed: {error}", file=sys.stderr)
        return 1

    if state.status == "idle":
        print("RTT run stopped after reaching the configured idle timeout.")
    elif state.status == "eof":
        print("RTT run stopped because the RTT server closed the connection.")
    elif state.status == "interrupted":
        print("RTT run interrupted by user.")
        return 130
    return 0


def resolve_run_output_path(workspace_root: Path, output: str | None) -> Path:
    if output:
        resolved = resolve_workspace_path(output, workspace_root)
        return Path(resolved or "")
    return workspace_root / DEFAULT_SESSION_DIR / DEFAULT_RUN_OUTPUT


def build_detached_run_command(
    *,
    args: argparse.Namespace,
    workspace_root: Path,
    output_path: Path,
    state_path: Path,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "debugoracle",
        "run",
        "--workspace-root",
        str(workspace_root),
        "--host",
        args.host or DEFAULT_RTT_HOST,
        "--port",
        str(args.port),
        "--output",
        str(output_path),
        "--state-out",
        str(state_path),
        "--connect-timeout",
        str(args.connect_timeout),
        "--poll-interval",
        str(args.poll_interval),
    ]
    if args.idle_timeout is not None:
        command.extend(["--idle-timeout", str(args.idle_timeout)])
    if args.append:
        command.append("--append")
    return command


def build_detached_run_env() -> dict[str, str]:
    env = os.environ.copy()
    package_root = str(PACKAGE_ROOT)
    existing = env.get("PYTHONPATH")
    if existing:
        env["PYTHONPATH"] = os.pathsep.join([package_root, existing])
    else:
        env["PYTHONPATH"] = package_root
    return env


def load_runtime_metadata(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def is_owned_run_process(pid: int) -> bool:
    cmdline = read_process_cmdline(pid)
    if not cmdline:
        return False
    try:
        tokens = set(shlex.split(cmdline))
    except ValueError:
        return False
    has_run = "run" in tokens
    looks_like_dbgoracle = "dbgoracle" in cmdline or "debugoracle" in cmdline
    return has_run and looks_like_dbgoracle


def read_process_cmdline(pid: int) -> str:
    try:
        data = Path(f"/proc/{pid}/cmdline").read_bytes()
        text = data.replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()
        if text:
            return text
    except OSError:
        pass

    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "args="],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            text = result.stdout.strip()
            if text:
                return text
    except OSError:
        pass

    if platform.system().lower().startswith("win"):
        try:
            command = (
                f"$p = Get-CimInstance Win32_Process -Filter \"ProcessId = {pid}\"; "
                "if ($p -ne $null) { $p.CommandLine }"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", command],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                text = result.stdout.strip()
                if text:
                    return text
        except OSError:
            pass
    return ""


def is_pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def safe_unlink(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError:
        return


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def resolve_workspace_path(value: str | None, workspace_root: Path) -> str | None:
    if not value:
        return None
    path = Path(value).expanduser()
    if path.is_absolute():
        return str(path)
    return str(workspace_root / path)
