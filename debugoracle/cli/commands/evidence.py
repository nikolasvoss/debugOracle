from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import TypedDict

from ...artifacts.models import InvestigationArtifact
from ...artifacts.repository import ArtifactLoadError, load_artifact, save_artifact
from ...builder import DEFAULT_RTT_WINDOW, FULL_RTT_WINDOW, build_bundle_from_files
from ...openocd import (
    DISCOVERY_MATCHED,
    DISCOVERY_MULTIPLE,
    DISCOVERY_NO_SESSION,
    DISCOVERY_PID_NOT_FOUND,
    DISCOVERY_UNREACHABLE,
    OpenOcdCandidate,
    OpenOcdDiscoveryResult,
    OpenOcdReachabilityError,
    discover_workspace_openocd_session,
)
from ...policy.halted_analysis import evaluate_artifact_live_state
from ...policy.trust import evaluate_artifact_trust
from ...renderers.report import ReportRenderOptions, render_report
from ...session import (
    collect_session_status,
    DEFAULT_GDB_MI_FILENAME,
    DEFAULT_RTT_FILENAME,
    DEFAULT_SESSION_DIR,
    DEFAULT_SNAPSHOT_FILENAME,
    SessionConfig,
)
from ._shared import parse_jsonc, resolve_workspace_path


def cmd_fetch(args: argparse.Namespace) -> int:
    workspace_root = Path(args.workspace_root).resolve()
    discovery = resolve_fetch_inputs(args, workspace_root)
    gdb_mi = discovery["gdb_mi"]
    rtt = discovery["rtt"]
    state_out = resolve_state_out_path(
        workspace_root=workspace_root,
        requested_state_out=args.state_out,
        gdb_mi=gdb_mi,
        rtt=rtt,
    )
    resolved_svd_file, svd_discovered, svd_notice = resolve_fetch_svd_file(
        args, workspace_root
    )
    resolved_openocd_tcl_host, resolved_openocd_tcl_port, tcl_discovered, tcl_notice = (
        resolve_fetch_openocd_tcl_endpoint(
            args,
            gdb_mi=gdb_mi,
            resolved_svd_file=resolved_svd_file,
        )
    )
    _validate_fetch_live_capture_arguments(args, resolved_svd_file=resolved_svd_file)
    if svd_notice:
        print(svd_notice, file=sys.stderr)
    if tcl_notice:
        print(tcl_notice, file=sys.stderr)
    if resolved_svd_file:
        require_readable_file(resolved_svd_file, "SVD")
    try:
        bundle = _resolve_fetch_bundle(
            args,
            gdb_mi=gdb_mi,
            rtt=rtt,
            state_out=state_out,
            discovery=discovery,
            resolved_svd_file=resolved_svd_file,
            svd_discovered=svd_discovered,
            resolved_openocd_tcl_host=resolved_openocd_tcl_host,
            resolved_openocd_tcl_port=resolved_openocd_tcl_port,
        )
    except OpenOcdReachabilityError as initial_error:
        recovery_error = initial_error
        if resolved_svd_file and tcl_discovered:
            endpoint = f"{resolved_openocd_tcl_host or '127.0.0.1'}:{resolved_openocd_tcl_port}"
            try:
                bundle = _resolve_fetch_bundle(
                    args,
                    gdb_mi=gdb_mi,
                    rtt=rtt,
                    state_out=state_out,
                    discovery=discovery,
                    resolved_svd_file=resolved_svd_file,
                    svd_discovered=svd_discovered,
                    resolved_openocd_tcl_host=None,
                    resolved_openocd_tcl_port=None,
                )
            except OpenOcdReachabilityError as fallback_error:
                recovery_error = fallback_error
            except SystemExit as fallback_error:
                reason = str(fallback_error) or "register enrichment failed"
                print(
                    f"Auto-discovered OpenOCD Tcl endpoint '{endpoint}' could not be used ({reason}). Continuing without register capture.",
                    file=sys.stderr,
                )
                bundle = _resolve_fetch_bundle_without_register_capture(
                    args,
                    gdb_mi=gdb_mi,
                    rtt=rtt,
                    state_out=state_out,
                    discovery=discovery,
                )
            else:
                save_artifact(bundle, state_out)
                emit_fetch_summary(
                    bundle, state_out, workspace_root=str(workspace_root)
                )
                return 0
        try:
            bundle = attempt_fetch_openocd_recovery(
                args,
                workspace_root=workspace_root,
                gdb_mi=gdb_mi,
                rtt=rtt,
                state_out=state_out,
                discovery=discovery,
                resolved_svd_file=resolved_svd_file,
                svd_discovered=svd_discovered,
                initial_error=recovery_error,
            )
        except SystemExit as recovery_error:
            reason = str(recovery_error) or "register enrichment failed"
            if resolved_svd_file and tcl_discovered:
                endpoint = f"{resolved_openocd_tcl_host or '127.0.0.1'}:{resolved_openocd_tcl_port}"
                print(
                    f"Auto-discovered OpenOCD Tcl endpoint '{endpoint}' could not be used ({reason}). Continuing without register capture.",
                    file=sys.stderr,
                )
                bundle = _resolve_fetch_bundle_without_register_capture(
                    args,
                    gdb_mi=gdb_mi,
                    rtt=rtt,
                    state_out=state_out,
                    discovery=discovery,
                )
            elif resolved_svd_file and svd_discovered:
                print(
                    f"Auto-discovered SVD '{resolved_svd_file}' could not be used ({reason}). Continuing without register capture.",
                    file=sys.stderr,
                )
                bundle = _resolve_fetch_bundle_without_register_capture(
                    args,
                    gdb_mi=gdb_mi,
                    rtt=rtt,
                    state_out=state_out,
                    discovery=discovery,
                )
            else:
                raise
    except SystemExit as error:
        reason = str(error) or "register enrichment failed"
        if resolved_svd_file and svd_discovered:
            print(
                f"Auto-discovered SVD '{resolved_svd_file}' could not be used ({reason}). Continuing without register capture.",
                file=sys.stderr,
            )
            bundle = _resolve_fetch_bundle_without_register_capture(
                args,
                gdb_mi=gdb_mi,
                rtt=rtt,
                state_out=state_out,
                discovery=discovery,
            )
        elif resolved_svd_file and tcl_discovered:
            endpoint = f"{resolved_openocd_tcl_host or '127.0.0.1'}:{resolved_openocd_tcl_port}"
            try:
                bundle = _resolve_fetch_bundle(
                    args,
                    gdb_mi=gdb_mi,
                    rtt=rtt,
                    state_out=state_out,
                    discovery=discovery,
                    resolved_svd_file=resolved_svd_file,
                    svd_discovered=svd_discovered,
                    resolved_openocd_tcl_host=None,
                    resolved_openocd_tcl_port=None,
                )
            except SystemExit:
                print(
                    f"Auto-discovered OpenOCD Tcl endpoint '{endpoint}' could not be used ({reason}). Continuing without register capture.",
                    file=sys.stderr,
                )
                bundle = _resolve_fetch_bundle_without_register_capture(
                    args,
                    gdb_mi=gdb_mi,
                    rtt=rtt,
                    state_out=state_out,
                    discovery=discovery,
                )
        else:
            raise
    save_artifact(bundle, state_out)
    emit_fetch_summary(bundle, state_out, workspace_root=str(workspace_root))
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    bundle = resolve_required_snapshot(args, command_name="report")
    workspace_root = Path(args.workspace_root).resolve()
    if getattr(args, "snapshot_file", None):
        trust = derive_bundle_trust(bundle)
    else:
        trust = collect_session_status(
            resolve_session_config(args, workspace_root)
        ).trust
    options = ReportRenderOptions(
        variable_names=list(args.vars or []) if args.vars is not None else None,
        include_gdb=bool(getattr(args, "gdb", False)),
        include_rtt=bool(getattr(args, "rtt", False)),
        verbose=bool(getattr(args, "verbose", False)),
        tail=getattr(args, "tail", None),
        regs_list_selector=getattr(args, "regs_list", None),
        regs_selectors=list(args.regs or []) if args.regs is not None else None,
        allow_unsafe=bool(getattr(args, "allow_unsafe", False)),
    )
    try:
        output = render_report(bundle, options=options, trust=trust)
    except RuntimeError as error:
        raise SystemExit(str(error)) from error
    return emit(output, args.output)


def attempt_fetch_openocd_recovery(
    args: argparse.Namespace,
    *,
    workspace_root: Path,
    gdb_mi: str | None,
    rtt: str | None,
    state_out: str,
    discovery: _FetchInputs,
    resolved_svd_file: str | None,
    svd_discovered: bool,
    initial_error: OpenOcdReachabilityError,
) -> InvestigationArtifact:
    if resolved_svd_file is None:
        raise SystemExit(str(initial_error))
    discovery_result = discover_workspace_openocd_session(
        workspace_root,
        connect_timeout=0.35,
    )
    candidate = discovery_result.candidate
    if candidate is None:
        raise SystemExit(
            _format_fetch_recovery_unavailable(initial_error, discovery_result)
        )
    if _endpoint_matches_failure(candidate, initial_error):
        raise SystemExit(_format_fetch_same_endpoint(initial_error, candidate))
    if discovery_result.status != DISCOVERY_MATCHED:
        raise SystemExit(
            _format_fetch_recovery_unavailable(initial_error, discovery_result)
        )
    print(
        f"Automatic Tcl recovery: retrying fetch with the live debug session at {candidate.host}:{candidate.tcl_port}.",
        file=sys.stderr,
    )
    try:
        return resolve_bundle(
            args,
            gdb_mi=gdb_mi,
            rtt=rtt,
            allow_snapshot_fallback=False,
            command_name="fetch",
            explicit_gdb=bool(discovery["gdb_mi_explicit"]),
            explicit_rtt=bool(discovery["rtt_explicit"]),
            export_dir=Path(state_out).parent,
            resolved_svd_file=resolved_svd_file,
            svd_discovered=svd_discovered,
            resolved_openocd_tcl_host=candidate.host,
            resolved_openocd_tcl_port=candidate.tcl_port,
        )
    except OpenOcdReachabilityError as retry_error:
        raise SystemExit(
            _format_fetch_retry_failure(initial_error, candidate, str(retry_error))
        ) from retry_error
    except SystemExit as retry_error:
        reason = str(retry_error) or "register enrichment failed"
        raise SystemExit(
            _format_fetch_retry_failure(initial_error, candidate, reason)
        ) from retry_error


def _endpoint_matches_failure(
    candidate: OpenOcdCandidate, error: OpenOcdReachabilityError
) -> bool:
    return candidate.host == error.host and candidate.tcl_port == error.port


def _format_fetch_recovery_unavailable(
    initial_error: OpenOcdReachabilityError,
    discovery_result: OpenOcdDiscoveryResult,
) -> str:
    base = f"{initial_error}. "
    if discovery_result.status == DISCOVERY_NO_SESSION:
        return (
            base
            + "Automatic Tcl recovery could not find a running debug session. "
            + "A debug session must already be running before `dbgoracle fetch` or `dbgoracle find-tcl-port` can discover the live Tcl port. "
            + "Start the debug session first, then retry `dbgoracle fetch` or run `dbgoracle find-tcl-port --print-fetch`."
        )
    if discovery_result.status == DISCOVERY_MULTIPLE:
        pids = ", ".join(
            str(candidate.pid)
            for candidate in sorted(
                discovery_result.candidates, key=lambda item: item.pid
            )
        )
        return (
            base
            + "Automatic Tcl recovery found multiple running debug sessions that match this workspace. "
            + f"Re-run `dbgoracle find-tcl-port --pid <PID>` with one of: {pids}."
        )
    if (
        discovery_result.status == DISCOVERY_UNREACHABLE
        and discovery_result.candidate is not None
    ):
        candidate = discovery_result.candidate
        return (
            base
            + "Automatic Tcl recovery found the matching debug session, but its discovered Tcl endpoint "
            + f"{candidate.host}:{candidate.tcl_port} is not reachable yet. "
            + "Keep the debug session running, then retry `dbgoracle fetch` or use `dbgoracle find-tcl-port --print-fetch`."
        )
    if (
        discovery_result.status == DISCOVERY_PID_NOT_FOUND
        and discovery_result.requested_pid is not None
    ):
        return (
            base
            + f"Automatic Tcl recovery could not find the requested OpenOCD pid {discovery_result.requested_pid}."
        )
    return (
        base
        + "Automatic Tcl recovery could not determine a usable OpenOCD Tcl endpoint."
    )


def _format_fetch_same_endpoint(
    initial_error: OpenOcdReachabilityError, candidate: OpenOcdCandidate
) -> str:
    return (
        f"{initial_error}. "
        + "Automatic Tcl recovery found the same endpoint again "
        + f"({candidate.host}:{candidate.tcl_port}), so no retry was attempted. "
        + "A debug session must already be running for discovery to help. "
        + "Verify the session's live Tcl port with `dbgoracle find-tcl-port --print-fetch` and retry."
    )


def _format_fetch_retry_failure(
    initial_error: OpenOcdReachabilityError,
    candidate: OpenOcdCandidate,
    retry_reason: str,
) -> str:
    return (
        f"{initial_error}. "
        + f"Automatic Tcl recovery retried with {candidate.host}:{candidate.tcl_port}, but register capture still failed ({retry_reason}). "
        + "Keep the debug session running and confirm the live Tcl port with `dbgoracle find-tcl-port --print-fetch`."
    )


def _validate_fetch_live_capture_arguments(
    args: argparse.Namespace,
    *,
    resolved_svd_file: str | None = None,
) -> None:
    openocd_tcl_host = getattr(args, "openocd_tcl_host", None)
    openocd_tcl_port = getattr(args, "openocd_tcl_port", None)
    if openocd_tcl_host is not None and not openocd_tcl_host.strip():
        raise SystemExit("--openocd-tcl-host must not be empty.")
    if openocd_tcl_host is None and openocd_tcl_port is None:
        return
    if resolved_svd_file is None and not getattr(args, "svd_file", None):
        print(
            "OpenOCD Tcl overrides were provided, but no SVD file was resolved. Continuing without register capture.",
            file=sys.stderr,
        )


def emit_fetch_summary(
    bundle: InvestigationArtifact, output_path: str, *, workspace_root: str
) -> None:
    gdb_source = bundle.sources.gdb
    rtt_source = bundle.sources.rtt
    workspace_arg = f"--workspace-root {workspace_root}"

    print("DebugOracle Fetch Summary")
    print("")
    print("Outcome:")
    print(f"- Snapshot saved: {bundle.snapshot_id}")
    print(f"- Output path: {output_path}")
    print("Evidence:")
    print(
        "- GDB: "
        + (
            f"present, {gdb_source.event_count} events, {len((gdb_source.raw_text or '').encode('utf-8'))} bytes"
            if gdb_source.raw_text
            else "absent"
        )
    )
    print(
        "- RTT: "
        + (
            f"present, {rtt_source.line_count} lines, {len((rtt_source.raw_text or '').encode('utf-8'))} bytes"
            if rtt_source.raw_text
            else "absent"
        )
    )
    if bundle.has_embedded_register_source:
        register_source = bundle.sources.registers
        print(
            "- Registers: "
            f"present, {register_source.peripheral_count} peripherals, "
            f"{register_source.register_count} registers, "
            f"{register_source.success_count} success, "
            f"{register_source.failure_count} failure, "
            f"{register_source.skipped_count} skipped"
        )
    else:
        print("- Registers: absent")
    print("Next:")
    print(f"- dbgoracle report {workspace_arg}")
    print(f"- dbgoracle report {workspace_arg} --vars [NAME ...]")
    if gdb_source.raw_text:
        print(f"- dbgoracle report {workspace_arg} --gdb --tail 50")
    if rtt_source.raw_text:
        print(f"- dbgoracle report {workspace_arg} --rtt --tail 50")
    if bundle.has_embedded_register_source:
        print(f"- dbgoracle report {workspace_arg} --regs-list")


def resolve_bundle(
    args: argparse.Namespace,
    full: bool = False,
    gdb_mi: str | None = None,
    rtt: str | None = None,
    *,
    allow_snapshot_fallback: bool = True,
    command_name: str = "fetch",
    strict_snapshot: bool = False,
    explicit_gdb: bool = False,
    explicit_rtt: bool = False,
    export_dir: Path | None = None,
    resolved_svd_file: str | None = None,
    svd_discovered: bool = False,
    resolved_openocd_tcl_host: str | None = None,
    resolved_openocd_tcl_port: int | None = None,
) -> InvestigationArtifact:
    workspace_root = Path(args.workspace_root).resolve()
    config = resolve_session_config(args, workspace_root)
    requested_snapshot_file = getattr(args, "snapshot_file", None)
    requested_gdb = gdb_mi if gdb_mi is not None else getattr(args, "gdb_mi", None)
    requested_rtt = rtt if rtt is not None else getattr(args, "rtt", None)
    explicit_gdb = explicit_gdb or (getattr(args, "gdb_mi", None) is not None)
    explicit_rtt = explicit_rtt or (getattr(args, "rtt", None) is not None)

    snapshot = _resolve_snapshot_from_request_or_fallback(
        command_name=command_name,
        strict_snapshot=strict_snapshot,
        requested_snapshot_file=requested_snapshot_file,
        workspace_root=workspace_root,
        config=config,
        allow_snapshot_fallback=allow_snapshot_fallback,
        explicit_gdb=explicit_gdb,
        explicit_rtt=explicit_rtt,
    )
    if snapshot is not None:
        return snapshot

    gdb_mi, rtt, gdb_discovered, rtt_discovered = _resolve_bundle_inputs(
        command_name=command_name,
        workspace_root=workspace_root,
        config=config,
        requested_gdb=requested_gdb,
        requested_rtt=requested_rtt,
        explicit_gdb=explicit_gdb,
        explicit_rtt=explicit_rtt,
        allow_snapshot_fallback=allow_snapshot_fallback,
    )

    rtt_window = (
        FULL_RTT_WINDOW if full else getattr(args, "rtt_window", DEFAULT_RTT_WINDOW)
    )
    discovered_inputs = {
        "snapshot-file": False,
        "gdb-mi": gdb_discovered,
        "rtt": rtt_discovered,
        "svd-file": svd_discovered,
    }

    if gdb_mi is not None:
        require_readable_file(gdb_mi, "GDB/MI")

    emit_discovery_summary(
        command_name,
        {
            "gdb-mi": gdb_mi,
            "rtt": rtt,
            "svd-file": resolved_svd_file,
        },
        discovered_inputs,
    )
    if rtt:
        require_readable_file(rtt, "RTT")
    if resolved_svd_file is None:
        resolved_svd_file = resolve_workspace_path(
            getattr(args, "svd_file", None), workspace_root
        )

    return _build_bundle_from_resolved_inputs(
        args=args,
        config=config,
        gdb_mi=gdb_mi,
        rtt=rtt,
        rtt_window=rtt_window,
        export_dir=export_dir,
        resolved_svd_file=resolved_svd_file,
        command_name=command_name,
        resolved_openocd_tcl_host=resolved_openocd_tcl_host,
        resolved_openocd_tcl_port=resolved_openocd_tcl_port,
    )


def _resolve_snapshot_from_request_or_fallback(
    *,
    command_name: str,
    strict_snapshot: bool,
    requested_snapshot_file: str | None,
    workspace_root: Path,
    config: SessionConfig,
    allow_snapshot_fallback: bool,
    explicit_gdb: bool,
    explicit_rtt: bool,
) -> InvestigationArtifact | None:
    if requested_snapshot_file:
        resolved_snapshot = resolve_workspace_path(
            requested_snapshot_file, workspace_root
        )
        emit_discovery_summary(
            command_name,
            {"snapshot-file": resolved_snapshot},
            {"snapshot-file": False},
        )
        return load_snapshot(
            command_name=command_name,
            path=resolved_snapshot,
            strict=strict_snapshot,
        )
    if (
        allow_snapshot_fallback
        and not explicit_gdb
        and not explicit_rtt
        and config.snapshot_file.exists()
    ):
        emit_discovery_summary(
            command_name,
            {"snapshot-file": str(config.snapshot_file)},
            {"snapshot-file": True},
        )
        return load_snapshot(
            command_name=command_name,
            path=str(config.snapshot_file),
            strict=strict_snapshot,
        )
    return None


def _resolve_bundle_inputs(
    *,
    command_name: str,
    workspace_root: Path,
    config: SessionConfig,
    requested_gdb: str | None,
    requested_rtt: str | None,
    explicit_gdb: bool,
    explicit_rtt: bool,
    allow_snapshot_fallback: bool,
) -> tuple[str | None, str | None, bool, bool]:
    resolved_gdb = (
        resolve_workspace_path(requested_gdb, workspace_root) if explicit_gdb else None
    )
    resolved_rtt = (
        resolve_workspace_path(requested_rtt, workspace_root) if explicit_rtt else None
    )
    gdb_discovered = False
    rtt_discovered = False

    if resolved_gdb is None and config.gdb_mi_file.is_file():
        resolved_gdb = str(config.gdb_mi_file)
        gdb_discovered = True
    if resolved_rtt is None and config.rtt_file.is_file():
        resolved_rtt = str(config.rtt_file)
        rtt_discovered = True

    if resolved_gdb is None and resolved_rtt is None:
        raise SystemExit(
            missing_inputs_error(
                command_name,
                workspace_root,
                allow_snapshot_fallback,
            )
        )

    return resolved_gdb, resolved_rtt, gdb_discovered, rtt_discovered


def _build_bundle_from_resolved_inputs(
    *,
    args: argparse.Namespace,
    config: SessionConfig,
    gdb_mi: str | None,
    rtt: str | None,
    rtt_window: int,
    export_dir: Path | None,
    resolved_svd_file: str | None,
    command_name: str,
    resolved_openocd_tcl_host: str | None,
    resolved_openocd_tcl_port: int | None,
) -> InvestigationArtifact:
    try:
        return build_bundle_from_files(
            gdb_mi,
            rtt,
            rtt_window=rtt_window,
            export_raw=getattr(args, "export_raw", False),
            export_dir=export_dir or config.snapshot_file.parent,
            svd_file_path=resolved_svd_file,
            enable_live_peripheral_capture=bool(
                resolved_svd_file and command_name == "fetch"
            ),
            openocd_tcl_host=resolved_openocd_tcl_host,
            openocd_tcl_port=resolved_openocd_tcl_port,
        )
    except OpenOcdReachabilityError:
        raise
    except OSError as error:
        raise SystemExit(
            f"Unable to read one of the required input files: {error}"
        ) from error
    except ValueError as error:
        raise SystemExit(str(error)) from error


def resolve_required_snapshot(
    args: argparse.Namespace,
    *,
    command_name: str,
) -> InvestigationArtifact:
    workspace_root = Path(args.workspace_root).resolve()
    config = resolve_session_config(args, workspace_root)
    requested_snapshot_file = getattr(args, "snapshot_file", None)

    if requested_snapshot_file:
        resolved_snapshot = resolve_workspace_path(
            requested_snapshot_file, workspace_root
        )
        return load_snapshot(
            command_name=command_name, path=resolved_snapshot, strict=True
        )

    if config.snapshot_file.exists():
        emit_discovery_summary(
            command_name,
            {"snapshot-file": str(config.snapshot_file)},
            {"snapshot-file": True},
        )
        return load_snapshot(
            command_name=command_name, path=str(config.snapshot_file), strict=True
        )

    raise SystemExit(
        f"{command_name} requires a snapshot. run `fetch` first or pass --snapshot-file."
    )


def load_snapshot(
    *,
    command_name: str,
    path: str | None,
    strict: bool,
) -> InvestigationArtifact:
    if not path:
        raise SystemExit(f"{command_name} could not resolve a snapshot file path.")
    try:
        return load_artifact(path, strict=strict)
    except ArtifactLoadError as error:
        raise SystemExit(f"{command_name} failed to load snapshot: {error}") from error


def resolve_session_config(
    args: argparse.Namespace,
    workspace_root: Path,
) -> SessionConfig:
    snapshot_file = getattr(args, "snapshot_file", None)
    gdb_mi_file = getattr(args, "gdb_mi", None)
    rtt_file = getattr(args, "rtt", None)
    rtt_state_file = (
        getattr(args, "rtt_state", None) if hasattr(args, "rtt_state") else None
    )
    return SessionConfig.from_workspace(
        workspace_root=workspace_root,
        snapshot_file=snapshot_file if isinstance(snapshot_file, str) else None,
        gdb_mi_file=gdb_mi_file if isinstance(gdb_mi_file, str) else None,
        rtt_file=rtt_file if isinstance(rtt_file, str) else None,
        rtt_state_file=rtt_state_file if isinstance(rtt_state_file, str) else None,
    )


class _FetchInputs(TypedDict):
    gdb_mi: str | None
    rtt: str | None
    gdb_mi_discovered: bool
    rtt_discovered: bool
    gdb_mi_explicit: bool
    rtt_explicit: bool


def resolve_fetch_inputs(
    args: argparse.Namespace,
    workspace_root: Path,
) -> _FetchInputs:
    config = resolve_session_config(args, workspace_root)
    explicit_gdb = getattr(args, "gdb_mi", None) is not None
    explicit_rtt = getattr(args, "rtt", None) is not None
    gdb_mi = resolve_workspace_path(
        getattr(args, "gdb_mi", None),
        workspace_root,
    )
    rtt = resolve_workspace_path(
        getattr(args, "rtt", None),
        workspace_root,
    )
    gdb_mi_discovered = False
    rtt_discovered = False

    if gdb_mi is None and config.gdb_mi_file.is_file():
        gdb_mi = str(config.gdb_mi_file)
        gdb_mi_discovered = True
    if rtt is None and config.rtt_file.exists():
        rtt = str(config.rtt_file)
        rtt_discovered = True

    return {
        "gdb_mi": gdb_mi,
        "rtt": rtt,
        "gdb_mi_discovered": gdb_mi_discovered,
        "rtt_discovered": rtt_discovered,
        "gdb_mi_explicit": explicit_gdb,
        "rtt_explicit": explicit_rtt,
    }


def _resolve_fetch_bundle(
    args: argparse.Namespace,
    *,
    gdb_mi: str | None,
    rtt: str | None,
    state_out: str,
    discovery: _FetchInputs,
    resolved_svd_file: str | None,
    svd_discovered: bool,
    resolved_openocd_tcl_host: str | None = None,
    resolved_openocd_tcl_port: int | None = None,
) -> InvestigationArtifact:
    return resolve_bundle(
        args,
        gdb_mi=gdb_mi,
        rtt=rtt,
        allow_snapshot_fallback=False,
        command_name="fetch",
        explicit_gdb=discovery["gdb_mi_explicit"],
        explicit_rtt=discovery["rtt_explicit"],
        export_dir=Path(state_out).parent,
        resolved_svd_file=resolved_svd_file,
        svd_discovered=svd_discovered,
        resolved_openocd_tcl_host=resolved_openocd_tcl_host,
        resolved_openocd_tcl_port=resolved_openocd_tcl_port,
    )


def _resolve_fetch_bundle_without_register_capture(
    args: argparse.Namespace,
    *,
    gdb_mi: str | None,
    rtt: str | None,
    state_out: str,
    discovery: _FetchInputs,
) -> InvestigationArtifact:
    return _resolve_fetch_bundle(
        args,
        gdb_mi=gdb_mi,
        rtt=rtt,
        state_out=state_out,
        discovery=discovery,
        resolved_svd_file=None,
        svd_discovered=False,
    )


def resolve_fetch_svd_file(
    args: argparse.Namespace,
    workspace_root: Path,
) -> tuple[str | None, bool, str | None]:
    explicit_svd = getattr(args, "svd_file", None)
    if explicit_svd:
        return resolve_workspace_path(explicit_svd, workspace_root), False, None

    workspace_default_svd = resolve_workspace_default_svd_file(workspace_root)
    if workspace_default_svd:
        return (
            workspace_default_svd,
            False,
            f"Workspace default SVD for fetch: {workspace_default_svd}",
        )

    session_dir = workspace_root / DEFAULT_SESSION_DIR
    if not session_dir.is_dir():
        return None, False, None

    candidates = [session_dir / name for name in sorted(os.listdir(session_dir))]
    svd_candidates = [
        path for path in candidates if path.is_file() and path.suffix.lower() == ".svd"
    ]
    if len(svd_candidates) == 1:
        resolved = str(svd_candidates[0])
        return resolved, True, f"Auto-discovered SVD for fetch: {resolved}"
    if len(svd_candidates) > 1:
        joined = ", ".join(str(path.name) for path in svd_candidates)
        return (
            None,
            False,
            "Multiple SVD candidates were found in .dbgoracle "
            f"({joined}). Continuing without register capture.",
        )
    return (
        None,
        False,
        "No SVD candidate was found in .dbgoracle. Continuing without register capture.",
    )


def resolve_fetch_openocd_tcl_endpoint(
    args: argparse.Namespace,
    *,
    gdb_mi: str | None,
    resolved_svd_file: str | None,
) -> tuple[str | None, int | None, bool, str | None]:
    explicit_host = getattr(args, "openocd_tcl_host", None)
    explicit_port = getattr(args, "openocd_tcl_port", None)
    if explicit_host is not None or explicit_port is not None:
        return explicit_host, explicit_port, False, None
    if resolved_svd_file is None or gdb_mi is None:
        return None, None, False, None
    discovered_port = discover_openocd_tcl_port_from_mi_log(gdb_mi)
    if discovered_port is None:
        return None, None, False, None
    return (
        None,
        discovered_port,
        True,
        f"Discovered OpenOCD Tcl port for fetch from GDB/MI log: {discovered_port}",
    )


def discover_openocd_tcl_port_from_mi_log(gdb_mi_path: str) -> int | None:
    try:
        raw_text = Path(gdb_mi_path).read_text(encoding="utf-8")
    except OSError:
        return None
    lines = raw_text.splitlines()
    launch_indexes = [
        index for index, line in enumerate(lines) if "Launching gdb-server:" in line
    ]
    search_lines = lines[launch_indexes[-1] :] if launch_indexes else lines[-200:]
    matches = [
        match.group(1)
        for line in search_lines
        for match in re.finditer(r"tcl_port\s+(\d+)", line)
    ]
    if not matches:
        return None
    try:
        return int(matches[-1], 10)
    except ValueError:
        return None


def resolve_workspace_default_svd_file(workspace_root: Path) -> str | None:
    settings_path = workspace_root / ".vscode" / "settings.json"
    if not settings_path.is_file():
        return None
    try:
        raw_text = settings_path.read_text(encoding="utf-8")
    except OSError:
        return None
    payload = parse_jsonc(raw_text)
    if not isinstance(payload, dict):
        return None
    raw_value = payload.get("debugoracle.svdFile")
    if not isinstance(raw_value, str) or not raw_value.strip():
        return None
    return resolve_workspace_path(
        expand_workspace_tokens(raw_value, workspace_root), workspace_root
    )


def expand_workspace_tokens(value: str, workspace_root: Path) -> str:
    return value.replace("${workspaceFolder}", str(workspace_root))


def missing_inputs_error(
    command_name: str,
    workspace_root: Path,
    allow_snapshot_fallback: bool,
) -> str:
    gdb_candidates = [
        workspace_root / DEFAULT_GDB_MI_FILENAME,
        workspace_root / DEFAULT_SESSION_DIR / DEFAULT_GDB_MI_FILENAME,
    ]
    rtt_candidates = [
        workspace_root / DEFAULT_RTT_FILENAME,
        workspace_root / DEFAULT_SESSION_DIR / DEFAULT_RTT_FILENAME,
    ]
    lines = [
        f"{command_name} could not auto-resolve an input source.",
    ]
    if allow_snapshot_fallback:
        snapshot_candidates = [
            workspace_root / DEFAULT_SNAPSHOT_FILENAME,
            workspace_root / DEFAULT_SESSION_DIR / DEFAULT_SNAPSHOT_FILENAME,
        ]
        lines.extend(
            [
                "Either provide --snapshot-file, --gdb-mi, or --rtt, or run from a workspace with:",
                "  - Snapshot:",
                f"    - {snapshot_candidates[0]}",
                f"    - {snapshot_candidates[1]}",
            ]
        )
    else:
        lines.append(
            "Either provide --gdb-mi, --rtt, or both, or run from a workspace with:"
        )
    lines.extend(
        [
            "  - GDB/MI:",
            f"    - {gdb_candidates[0]}",
            f"    - {gdb_candidates[1]}",
            "  - RTT:",
            f"    - {rtt_candidates[0]}",
            f"    - {rtt_candidates[1]}",
            "  - At least one of GDB/MI or RTT must be available.",
            f"Workspace root: {workspace_root}",
        ]
    )
    if allow_snapshot_fallback:
        lines.append(
            "Tip: run from a folder with latest_snapshot.json (or .dbgoracle/latest_snapshot.json) "
            "or set --workspace-root."
        )
    else:
        lines.append(
            "Tip: set --gdb-mi, --rtt, or both and run from a workspace with "
            "cortex-debug-shared-mi.log or session.rtt (at workspace root or inside .dbgoracle)."
        )
    return "\n".join(lines)


def emit_discovery_summary(
    command_name: str,
    values: dict[str, str | None],
    discovered: dict[str, bool],
) -> None:
    discovered_items = [
        (label, value)
        for label, value in values.items()
        if value and discovered.get(label, False)
    ]
    if not discovered_items:
        return
    print(
        f"Auto-discovered input paths for {command_name}:",
        file=sys.stderr,
    )
    for label, value in discovered_items:
        print(f"- {label}: {value}", file=sys.stderr)


def require_readable_file(path: str, label: str) -> None:
    if not os.path.exists(path):
        raise SystemExit(f"{label} file does not exist: {path}")
    if not os.path.isfile(path):
        raise SystemExit(f"{label} path is not a file: {path}")
    if not os.access(path, os.R_OK):
        raise SystemExit(f"{label} file is not readable: {path}")


def resolve_state_out_path(
    workspace_root: Path,
    requested_state_out: str | None,
    gdb_mi: str | None,
    rtt: str | None,
) -> str:
    if requested_state_out:
        return resolve_workspace_path(requested_state_out, workspace_root) or ""

    if gdb_mi:
        return str(Path(gdb_mi).parent / DEFAULT_SNAPSHOT_FILENAME)

    if rtt:
        return str(Path(rtt).parent / DEFAULT_SNAPSHOT_FILENAME)

    return str(workspace_root / DEFAULT_SESSION_DIR / DEFAULT_SNAPSHOT_FILENAME)


def emit(output: str, path: str | None) -> int:
    if path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0


def derive_bundle_trust(bundle: InvestigationArtifact) -> dict[str, object]:
    halt_policy = evaluate_artifact_live_state(bundle.live_state)
    snapshot_usable = bundle.snapshot_id != "invalid-snapshot" and halt_policy.allowed
    critical_warning_count = _as_int(bundle.provenance.get("critical_warning_count"))
    critical_warnings = _critical_warnings(bundle, critical_warning_count)
    action_reason = (
        "A reusable snapshot is available for inspection."
        if snapshot_usable
        else "The requested snapshot is not usable for inspection."
    )
    return evaluate_artifact_trust(
        snapshot_exists=True,
        snapshot_usable=snapshot_usable,
        snapshot_stale=False,
        action_state="ready" if snapshot_usable else "capture_needed",
        action_reason=action_reason,
        recommended_next_command="dbgoracle report --workspace-root .",
        halt_policy=halt_policy,
        critical_warnings=critical_warnings,
        parse_warnings=list(bundle.parse_warnings),
        variable_count=bundle.variable_evidence.count(),
        has_embedded_gdb_source=bundle.has_embedded_gdb_source,
    ).to_dict()


def _critical_warnings(
    bundle: InvestigationArtifact, critical_warning_count: int | None
) -> list[str]:
    if critical_warning_count is not None and critical_warning_count <= 0:
        return []
    raw = bundle.provenance.get("critical_warnings")
    if isinstance(raw, list):
        warnings = [item for item in raw if isinstance(item, str)]
        if warnings:
            return warnings
    if critical_warning_count is None:
        return []
    return ["Parser reported unresolved critical events while processing the snapshot."]


def _as_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 10)
        except ValueError:
            return None
    return None
