from __future__ import annotations

import argparse
import json
import os
import platform
import select
import shlex
import signal
import subprocess  # nosec B404
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ...safe_io import (
    SafeIOError,
    atomic_write_text,
    open_stream_output,
    read_text_no_follow,
    unlink_file_no_follow,
)
from ...session import DEFAULT_SESSION_DIR
from ...sources.streams.rtt import (
    DEFAULT_RTT_HOST,
    RttCaptureTimeoutError,
    capture_rtt,
    default_state_path,
)
from ._shared import resolve_workspace_path

DEFAULT_RUN_PORT = 60001
DEFAULT_RUN_OUTPUT = "session.rtt"
DEFAULT_RUN_METADATA = "session.rtt.run.json"
DEFAULT_RUN_LAUNCH_LOG = "session.rtt.launch.log"
PACKAGE_ROOT = Path(__file__).resolve().parents[3]
RUN_METADATA_SCHEMA_VERSION = 1


class RuntimeMetadataError(RuntimeError):
    """Raised when detached-run metadata exists but is unsafe or malformed."""


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    start_time_ticks: int
    executable: str
    argv: tuple[str, ...]


def capture_process_identity(
    pid: int,
    *,
    proc_root: Path = Path("/proc"),
) -> ProcessIdentity | None:
    process_root = proc_root / str(pid)
    try:
        stat_text = (process_root / "stat").read_text(encoding="utf-8")
        closing_parenthesis = stat_text.rfind(")")
        if closing_parenthesis < 0:
            return None
        remaining_fields = stat_text[closing_parenthesis + 1 :].split()
        if len(remaining_fields) <= 19:
            return None
        start_time_ticks = int(remaining_fields[19], 10)
        executable = str((process_root / "exe").resolve(strict=True))
        raw_argv = (process_root / "cmdline").read_bytes()
        argv = tuple(
            part.decode("utf-8", errors="surrogateescape")
            for part in raw_argv.split(b"\x00")
            if part
        )
    except (OSError, ValueError):
        return None
    if not argv or start_time_ticks < 0:
        return None
    return ProcessIdentity(
        pid=pid,
        start_time_ticks=start_time_ticks,
        executable=executable,
        argv=argv,
    )


def cmd_run(args: argparse.Namespace) -> int:
    workspace_root = Path(args.workspace_root).resolve()
    output_path = resolve_run_output_path(workspace_root, args.output)
    state_path = (
        Path(resolve_workspace_path(args.state_out, workspace_root) or "")
        if args.state_out
        else default_state_path(output_path)
    )
    launch_log = workspace_root / DEFAULT_SESSION_DIR / DEFAULT_RUN_LAUNCH_LOG
    runtime_path = workspace_root / DEFAULT_SESSION_DIR / DEFAULT_RUN_METADATA

    if args.detach:
        return _cmd_run_detach(
            args=args,
            workspace_root=workspace_root,
            output_path=output_path,
            state_path=state_path,
            runtime_path=runtime_path,
            launch_log=launch_log,
        )
    return _run_capture_foreground(args, output_path, state_path, workspace_root)


def cmd_stop(args: argparse.Namespace) -> int:
    workspace_root = Path(args.workspace_root).resolve()
    runtime_path = (
        Path(resolve_workspace_path(args.runtime_file, workspace_root) or "")
        if args.runtime_file
        else workspace_root / DEFAULT_SESSION_DIR / DEFAULT_RUN_METADATA
    )
    try:
        runtime = load_runtime_metadata(runtime_path, workspace_root=workspace_root)
    except RuntimeMetadataError as error:
        print(f"Unsafe runtime metadata at {runtime_path}: {error}", file=sys.stderr)
        return 1
    if runtime is None:
        print(f"No detached RTT run is active for workspace {workspace_root}.")
        return 0
    pid = parse_pid(runtime)
    if pid <= 0:
        print(
            f"Warning: Invalid runtime metadata in {runtime_path}. Cleaning up stale file."
        )
        safe_unlink(runtime_path, workspace_root=workspace_root)
        return 0
    try:
        process_handle = open_process_handle(pid)
    except ProcessLookupError:
        safe_unlink(runtime_path, workspace_root=workspace_root)
        print(f"Cleaned stale detached RTT metadata for exited pid {pid}.")
        return 0
    except OSError as error:
        print(
            f"Refusing to stop pid {pid}: a stable Linux pidfd could not be opened: "
            f"{error}. No signal was sent; inspect or remove "
            f"{runtime_path} manually.",
            file=sys.stderr,
        )
        return 1
    try:
        current_identity = capture_process_identity(pid)
        identity_error = runtime_identity_error(
            runtime,
            workspace_root,
            current=current_identity,
        )
        if identity_error is not None:
            print(
                f"Refusing to stop pid {pid}: process identity mismatch: "
                f"{identity_error}. No signal was sent; inspect or remove "
                f"{runtime_path} manually.",
                file=sys.stderr,
            )
            return 1
        try:
            signal_process_handle(process_handle, signal.SIGTERM)
        except OSError as error:
            print(
                f"Failed to signal detached RTT run pid {pid}: {error}",
                file=sys.stderr,
            )
            return 1
        if wait_for_process_exit(process_handle, max(0.0, args.grace_timeout)):
            safe_unlink(runtime_path, workspace_root=workspace_root)
            print(f"Stopped detached RTT run (pid {pid}).")
            return 0

        current_identity = capture_process_identity(pid)
        identity_error = runtime_identity_error(
            runtime,
            workspace_root,
            current=current_identity,
        )
        if identity_error is not None:
            print(
                f"Refusing to force-stop pid {pid}: process identity mismatch: "
                f"{identity_error}. SIGKILL was not sent.",
                file=sys.stderr,
            )
            return 1
        try:
            kill_signal = (
                signal.SIGKILL if hasattr(signal, "SIGKILL") else signal.SIGTERM
            )
            signal_process_handle(process_handle, kill_signal)
        except OSError as error:
            print(
                f"Failed to force-stop detached RTT run pid {pid}: {error}",
                file=sys.stderr,
            )
            return 1
        if not wait_for_process_exit(process_handle, 1.0):
            print(f"Failed to stop detached RTT run (pid {pid}).", file=sys.stderr)
            return 1
        safe_unlink(runtime_path, workspace_root=workspace_root)
        print(f"Stopped detached RTT run (pid {pid}) after force-kill.")
        return 0
    finally:
        os.close(process_handle)


def _cmd_run_detach(
    *,
    args: argparse.Namespace,
    workspace_root: Path,
    output_path: Path,
    state_path: Path,
    runtime_path: Path,
    launch_log: Path,
) -> int:
    try:
        existing_runtime = load_runtime_metadata(
            runtime_path,
            workspace_root=workspace_root,
        )
    except RuntimeMetadataError as error:
        print(f"Unsafe runtime metadata at {runtime_path}: {error}", file=sys.stderr)
        return 1
    if existing_runtime is not None:
        pid = parse_pid(existing_runtime)
        if pid > 0:
            current = capture_process_identity(pid)
            if (
                current is not None
                and runtime_identity_error(
                    existing_runtime,
                    workspace_root,
                    current=current,
                )
                is None
            ):
                print(
                    "Detached RTT run already active "
                    f"(pid {pid}). Use `dbgoracle stop --workspace-root {workspace_root}` first."
                )
                return 0
            if current is not None:
                print(
                    "Refusing to replace runtime metadata for live pid "
                    f"{pid} because its strong identity does not match. "
                    f"Inspect {runtime_path} manually.",
                    file=sys.stderr,
                )
                return 1
        else:
            print(
                f"Warning: Found stale detached runtime metadata at {runtime_path}. "
                "Replacing it."
            )
        safe_unlink(runtime_path, workspace_root=workspace_root)

    command = build_detached_run_command(
        args=args,
        workspace_root=workspace_root,
        output_path=output_path,
        state_path=state_path,
    )
    with open_stream_output(
        launch_log,
        append=True,
        workspace_root=workspace_root,
    ) as log_handle:
        child = subprocess.Popen(  # nosec B603
            command,
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

    identity = capture_process_identity(child.pid)
    if identity is None or identity.argv != tuple(command):
        child_stopped = stop_detached_child(child)
        state_message = (
            "the child was stopped"
            if child_stopped
            else f"the child could not be confirmed stopped (pid {child.pid})"
        )
        print(
            "Detached RTT run identity could not be verified from /proc; "
            f"{state_message} and no runtime metadata was written.",
            file=sys.stderr,
        )
        return 1

    try:
        atomic_write_text(
            runtime_path,
            json.dumps(
                {
                    "schema_version": RUN_METADATA_SCHEMA_VERSION,
                    "pid": child.pid,
                    "start_time_ticks": identity.start_time_ticks,
                    "executable": identity.executable,
                    "argv": list(identity.argv),
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
            workspace_root=workspace_root,
        )
    except OSError as error:
        child_stopped = stop_detached_child(child)
        state_message = (
            "the child was stopped"
            if child_stopped
            else f"the child could not be confirmed stopped (pid {child.pid})"
        )
        print(
            "Detached RTT run could not publish safe runtime metadata; "
            f"{state_message}: {error}",
            file=sys.stderr,
        )
        return 1
    print(
        "Started detached RTT run "
        f"(pid {child.pid}) -> {output_path}. "
        f"Use `dbgoracle stop --workspace-root {workspace_root}` to stop."
    )
    return 0


def open_process_handle(pid: int) -> int:
    if not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
        raise OSError("this Linux/Python runtime does not support pidfd signaling")
    return os.pidfd_open(pid)


def signal_process_handle(
    process_handle: int, requested_signal: signal.Signals
) -> None:
    signal.pidfd_send_signal(process_handle, requested_signal)


def wait_for_process_exit(process_handle: int, timeout_seconds: float) -> bool:
    poller = select.poll()
    poller.register(process_handle, select.POLLIN | select.POLLHUP | select.POLLERR)
    timeout_milliseconds = max(0, round(timeout_seconds * 1000))
    return bool(poller.poll(timeout_milliseconds))


def stop_detached_child(child: subprocess.Popen[bytes]) -> bool:
    if child.poll() is not None:
        return True
    try:
        child.terminate()
        child.wait(timeout=1.0)
        return True
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        child.kill()
        child.wait(timeout=1.0)
        return True
    except (OSError, subprocess.SubprocessError):
        return child.poll() is not None


def _run_capture_foreground(
    args: argparse.Namespace,
    output_path: Path,
    state_path: Path,
    workspace_root: Path,
) -> int:
    safe_workspace_root = (
        workspace_root
        if output_path.is_relative_to(workspace_root)
        and state_path.is_relative_to(workspace_root)
        else None
    )
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
            workspace_root=safe_workspace_root,
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


def load_runtime_metadata(
    path: Path,
    *,
    workspace_root: Path | None = None,
) -> dict[str, object] | None:
    try:
        raw_text = read_text_no_follow(path, workspace_root=workspace_root)
    except SafeIOError as error:
        if isinstance(error.__cause__, FileNotFoundError):
            return None
        raise RuntimeMetadataError(str(error)) from error
    try:
        payload = json.loads(raw_text)
    except (ValueError, TypeError) as error:
        raise RuntimeMetadataError(f"invalid JSON: {error}") from error
    if not isinstance(payload, dict):
        raise RuntimeMetadataError("payload must be a JSON object")
    return payload


def parse_pid(metadata: dict[str, object]) -> int:
    raw_pid = metadata.get("pid", 0)
    if isinstance(raw_pid, int):
        return raw_pid
    if isinstance(raw_pid, str):
        try:
            return int(raw_pid, 10)
        except ValueError:
            return 0
    return 0


def runtime_identity_error(
    metadata: dict[str, object],
    workspace_root: Path,
    *,
    current: ProcessIdentity | None = None,
) -> str | None:
    if metadata.get("schema_version") != RUN_METADATA_SCHEMA_VERSION:
        return (
            "legacy or unsupported runtime metadata lacks the strong identity "
            f"schema {RUN_METADATA_SCHEMA_VERSION}"
        )
    pid = parse_pid(metadata)
    start_time_ticks = metadata.get("start_time_ticks")
    executable = metadata.get("executable")
    raw_argv = metadata.get("argv")
    recorded_workspace = metadata.get("workspace_root")
    if (
        pid <= 0
        or not isinstance(start_time_ticks, int)
        or not isinstance(executable, str)
        or not executable
        or not isinstance(raw_argv, list)
        or not raw_argv
        or not all(isinstance(value, str) for value in raw_argv)
        or not isinstance(recorded_workspace, str)
    ):
        return "runtime metadata is malformed"
    if recorded_workspace != str(workspace_root.resolve()):
        return "recorded workspace does not match the requested canonical workspace"
    argv = tuple(raw_argv)
    if not _is_expected_run_argv(argv, recorded_workspace):
        return "recorded argv is not the exact managed dbgoracle run shape"
    try:
        argv_executable = str(Path(argv[0]).resolve(strict=True))
    except OSError:
        return "recorded argv executable cannot be resolved"
    if argv_executable != executable:
        return "recorded argv executable does not match canonical executable"
    observed = current if current is not None else capture_process_identity(pid)
    if observed is None:
        return "Linux /proc identity evidence is missing or inaccessible"
    if observed.pid != pid:
        return "PID changed"
    if observed.start_time_ticks != start_time_ticks:
        return "process start time changed (possible PID reuse)"
    if observed.executable != executable:
        return "canonical executable changed"
    if observed.argv != argv:
        return "exact argv changed"
    return None


def _is_expected_run_argv(argv: tuple[str, ...], workspace_root: str) -> bool:
    if len(argv) < 6 or argv[1:4] != ("-m", "debugoracle", "run"):
        return False
    if "--detach" in argv or argv.count("--workspace-root") != 1:
        return False
    workspace_index = argv.index("--workspace-root")
    return (
        workspace_index + 1 < len(argv) and argv[workspace_index + 1] == workspace_root
    )


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
        result = subprocess.run(  # nosec
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
                f'$p = Get-CimInstance Win32_Process -Filter "ProcessId = {pid}"; '
                "if ($p -ne $null) { $p.CommandLine }"
            )
            result = subprocess.run(  # nosec
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


def safe_unlink(path: Path, *, workspace_root: Path | None = None) -> None:
    try:
        unlink_file_no_follow(path, workspace_root=workspace_root)
    except OSError:
        return


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
