from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from ...artifacts.models import InvestigationArtifact, InvestigationRequest
from ...artifacts.repository import ArtifactLoadError, load_artifact, save_artifact
from ...builder import DEFAULT_RTT_WINDOW, FULL_RTT_WINDOW, build_bundle_from_files
from ...renderers.prompt import render_prompt
from ...renderers.report import ReportRenderOptions, render_report
from ...session import (
    DEFAULT_GDB_MI_FILENAME,
    DEFAULT_RTT_FILENAME,
    DEFAULT_SESSION_DIR,
    DEFAULT_SNAPSHOT_FILENAME,
    SessionConfig,
)


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
    bundle = resolve_bundle(
        args,
        gdb_mi=gdb_mi,
        rtt=rtt,
        allow_snapshot_fallback=False,
        command_name="fetch",
        explicit_gdb=discovery["gdb_mi_explicit"],
        explicit_rtt=discovery["rtt_explicit"],
        export_dir=Path(state_out).parent,
    )
    save_artifact(bundle, state_out)
    emit_fetch_summary(bundle, state_out)
    return 0


def cmd_prompt(args: argparse.Namespace) -> int:
    bundle = resolve_required_snapshot(args, command_name="prompt")
    intent = read_intent(args.intent, args.intent_file)
    request = InvestigationRequest(
        goal_text=args.goal,
        intent_text=intent,
        snapshot_ref=bundle.snapshot_id,
        format=args.format,
        detail_level="full" if args.full else "compact",
        var_scope=args.var_scope,
        var_names=list(args.var_name or []),
        var_detail=args.var_detail,
    )
    output = render_prompt(bundle, request)
    return emit(output, args.output)


def cmd_report(args: argparse.Namespace) -> int:
    bundle = resolve_required_snapshot(args, command_name="report")
    options = ReportRenderOptions(
        variable_names=list(args.vars or []) if args.vars is not None else None,
        include_gdb=bool(getattr(args, "gdb", False)),
        include_rtt=bool(getattr(args, "rtt", False)),
        verbose=bool(getattr(args, "verbose", False)),
        tail=getattr(args, "tail", None),
    )
    try:
        output = render_report(bundle, options=options)
    except RuntimeError as error:
        raise SystemExit(str(error)) from error
    return emit(output, args.output)


def emit_fetch_summary(bundle: InvestigationArtifact, output_path: str) -> None:
    gdb_source = bundle.sources.gdb
    rtt_source = bundle.sources.rtt
    embedded_sources: list[str] = []
    if gdb_source.raw_text:
        embedded_sources.append("gdb")
    if rtt_source.raw_text:
        embedded_sources.append("rtt")

    print(f"Snapshot ID: {bundle.snapshot_id}")
    print(f"Output Path: {output_path}")
    print("Embedded Sources: " + (", ".join(embedded_sources) if embedded_sources else "none"))
    print("Source Sizes/Counts:")
    print(
        "- gdb: "
        f"{len((gdb_source.raw_text or '').encode('utf-8'))} bytes, "
        f"{gdb_source.event_count} events"
    )
    print(
        "- rtt: "
        f"{len((rtt_source.raw_text or '').encode('utf-8'))} bytes, "
        f"{rtt_source.line_count} lines"
    )


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
) -> InvestigationArtifact:
    workspace_root = Path(args.workspace_root).resolve()
    config = resolve_session_config(args, workspace_root)
    requested_snapshot_file = getattr(args, "snapshot_file", None)
    requested_gdb = gdb_mi if gdb_mi is not None else getattr(args, "gdb_mi", None)
    requested_rtt = rtt if rtt is not None else getattr(args, "rtt", None)
    explicit_gdb = explicit_gdb or (getattr(args, "gdb_mi", None) is not None)
    explicit_rtt = explicit_rtt or (getattr(args, "rtt", None) is not None)

    if requested_snapshot_file:
        resolved_snapshot = resolve_workspace_path(requested_snapshot_file, workspace_root)
        emit_discovery_summary(
            command_name,
            {
                "snapshot-file": resolved_snapshot,
            },
            {
                "snapshot-file": False,
            },
        )
        return load_snapshot(
            command_name=command_name,
            path=resolved_snapshot,
            strict=strict_snapshot,
        )

    if allow_snapshot_fallback and not explicit_gdb and not explicit_rtt:
        if config.snapshot_file.exists():
            emit_discovery_summary(
                command_name,
                {
                    "snapshot-file": str(config.snapshot_file),
                },
                {
                    "snapshot-file": True,
                },
            )
            return load_snapshot(
                command_name=command_name,
                path=str(config.snapshot_file),
                strict=strict_snapshot,
            )

    resolved_gdb = None
    resolved_rtt = None
    gdb_discovered = False
    rtt_discovered = False

    if explicit_gdb:
        resolved_gdb = resolve_workspace_path(requested_gdb, workspace_root)
    elif config.gdb_mi_file.is_file():
        resolved_gdb = str(config.gdb_mi_file)
        gdb_discovered = True
    if explicit_rtt:
        resolved_rtt = resolve_workspace_path(requested_rtt, workspace_root)
    elif config.rtt_file.is_file():
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

    gdb_mi = resolved_gdb
    rtt = resolved_rtt

    rtt_window = FULL_RTT_WINDOW if full else getattr(args, "rtt_window", DEFAULT_RTT_WINDOW)
    discovered_inputs = {
        "snapshot-file": False,
        "gdb-mi": gdb_discovered,
        "rtt": rtt_discovered,
    }

    if gdb_mi is not None:
        require_readable_file(gdb_mi, "GDB/MI")

    emit_discovery_summary(
        command_name,
        {
            "gdb-mi": gdb_mi,
            "rtt": rtt,
        },
        discovered_inputs,
    )
    if rtt:
        require_readable_file(rtt, "RTT")
    try:
        return build_bundle_from_files(
            gdb_mi,
            rtt,
            rtt_window=rtt_window,
            export_raw=getattr(args, "export_raw", False),
            export_dir=export_dir or config.snapshot_file.parent,
        )
    except OSError as error:
        raise SystemExit(f"Unable to read one of the required input files: {error}") from error


def resolve_required_snapshot(
    args: argparse.Namespace,
    *,
    command_name: str,
) -> InvestigationArtifact:
    workspace_root = Path(args.workspace_root).resolve()
    config = resolve_session_config(args, workspace_root)
    requested_snapshot_file = getattr(args, "snapshot_file", None)

    if requested_snapshot_file:
        resolved_snapshot = resolve_workspace_path(requested_snapshot_file, workspace_root)
        return load_snapshot(command_name=command_name, path=resolved_snapshot, strict=True)

    if config.snapshot_file.exists():
        emit_discovery_summary(
            command_name,
            {"snapshot-file": str(config.snapshot_file)},
            {"snapshot-file": True},
        )
        return load_snapshot(command_name=command_name, path=str(config.snapshot_file), strict=True)

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
    rtt_state_file = getattr(args, "rtt_state", None) if hasattr(args, "rtt_state") else None
    return SessionConfig.from_workspace(
        workspace_root=workspace_root,
        snapshot_file=snapshot_file if isinstance(snapshot_file, str) else None,
        gdb_mi_file=gdb_mi_file if isinstance(gdb_mi_file, str) else None,
        rtt_file=rtt_file if isinstance(rtt_file, str) else None,
        rtt_state_file=rtt_state_file if isinstance(rtt_state_file, str) else None,
    )


def resolve_fetch_inputs(
    args: argparse.Namespace,
    workspace_root: Path,
) -> dict[str, str | None | bool]:
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
        lines.extend([
            "Either provide --snapshot-file, --gdb-mi, or --rtt, or run from a workspace with:",
            "  - Snapshot:",
            f"    - {snapshot_candidates[0]}",
            f"    - {snapshot_candidates[1]}",
        ])
    else:
        lines.append("Either provide --gdb-mi, --rtt, or both, or run from a workspace with:")
    lines.extend([
        "  - GDB/MI:",
        f"    - {gdb_candidates[0]}",
        f"    - {gdb_candidates[1]}",
        "  - RTT:",
        f"    - {rtt_candidates[0]}",
        f"    - {rtt_candidates[1]}",
        "  - At least one of GDB/MI or RTT must be available.",
        f"Workspace root: {workspace_root}",
    ])
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


def resolve_workspace_path(value: str | None, workspace_root: Path) -> str | None:
    if not value:
        return None
    path = Path(value).expanduser()
    if path.is_absolute():
        return str(path)
    return str(workspace_root / path)


def resolve_state_out_path(
    workspace_root: Path,
    requested_state_out: str | None,
    gdb_mi: str | None,
    rtt: str | None,
) -> str:
    if requested_state_out:
        return resolve_workspace_path(requested_state_out, workspace_root)

    if gdb_mi:
        return str(Path(gdb_mi).parent / DEFAULT_SNAPSHOT_FILENAME)

    if rtt:
        return str(Path(rtt).parent / DEFAULT_SNAPSHOT_FILENAME)

    return str(workspace_root / DEFAULT_SESSION_DIR / DEFAULT_SNAPSHOT_FILENAME)


def read_intent(intent: str | None, intent_file: str | None) -> str | None:
    if intent is not None:
        return intent
    if intent_file:
        if intent_file == "-":
            return sys.stdin.read().strip()
        return Path(intent_file).read_text(encoding="utf-8").strip()
    return None


def emit(output: str, path: str | None) -> int:
    if path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0
