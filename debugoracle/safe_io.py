from __future__ import annotations

import io
import os
import secrets
import stat
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Iterator


class SafeIOError(OSError):
    """Raised when an output path cannot be used without following links."""


def atomic_write_text(
    path: str | Path,
    text: str,
    *,
    workspace_root: str | Path | None = None,
    encoding: str = "utf-8",
) -> None:
    atomic_write_bytes(
        path,
        text.encode(encoding),
        workspace_root=workspace_root,
    )


def atomic_write_bytes(
    path: str | Path,
    data: bytes,
    *,
    workspace_root: str | Path | None = None,
) -> None:
    target = Path(path)
    with _opened_parent(
        target,
        workspace_root=workspace_root,
        create_parents=True,
    ) as (parent_fd, name):
        original = _regular_target_state(parent_fd, name)
        mode = stat.S_IMODE(original.st_mode) if original is not None else 0o666
        temporary_name = f".{name}.tmp-{secrets.token_hex(8)}"
        temporary_fd = -1
        try:
            temporary_fd = os.open(
                temporary_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | _no_follow_flag(),
                mode,
                dir_fd=parent_fd,
            )
            _write_all(temporary_fd, data)
            if original is not None:
                os.fchmod(temporary_fd, mode)
            os.fsync(temporary_fd)
            os.close(temporary_fd)
            temporary_fd = -1
            _require_unchanged_target(parent_fd, name, original)
            os.replace(
                temporary_name,
                name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
            os.fsync(parent_fd)
        except OSError as error:
            raise SafeIOError(f"Could not safely write '{target}': {error}") from error
        finally:
            if temporary_fd >= 0:
                os.close(temporary_fd)
            try:
                os.unlink(temporary_name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
            except OSError:
                pass


def open_stream_output(
    path: str | Path,
    *,
    append: bool,
    workspace_root: str | Path | None = None,
) -> BinaryIO:
    target = Path(path)
    try:
        with _opened_parent(
            target,
            workspace_root=workspace_root,
            create_parents=True,
        ) as (parent_fd, name):
            original = _regular_target_state(parent_fd, name)
            if original is not None and original.st_nlink != 1:
                raise SafeIOError(
                    f"Unsafe output path '{target}': target has multiple hard links."
                )
            flags = os.O_WRONLY | _no_follow_flag() | os.O_NONBLOCK
            if append:
                flags |= os.O_APPEND
            if original is None:
                flags |= os.O_CREAT | os.O_EXCL
            fd = os.open(name, flags, 0o666, dir_fd=parent_fd)
            try:
                target_state = os.fstat(fd)
                if not stat.S_ISREG(target_state.st_mode) or target_state.st_nlink != 1:
                    raise SafeIOError(
                        f"Unsafe output path '{target}': target is not a unique regular file."
                    )
                if original is not None and (
                    target_state.st_dev,
                    target_state.st_ino,
                ) != (original.st_dev, original.st_ino):
                    raise SafeIOError(
                        f"Unsafe output path '{target}': target changed while opening."
                    )
                if not append:
                    os.ftruncate(fd, 0)
                return io.FileIO(fd, mode="ab" if append else "wb", closefd=True)
            except BaseException:
                os.close(fd)
                raise
    except SafeIOError:
        raise
    except OSError as error:
        raise SafeIOError(
            f"Could not safely open '{target}': {error.__class__.__name__}: {error}"
        ) from error


def read_text_no_follow(
    path: str | Path,
    *,
    workspace_root: str | Path | None = None,
    encoding: str = "utf-8",
) -> str:
    target = Path(path)
    try:
        with _opened_parent(
            target,
            workspace_root=workspace_root,
            create_parents=False,
        ) as (parent_fd, name):
            fd = os.open(
                name,
                os.O_RDONLY | os.O_NONBLOCK | _no_follow_flag(),
                dir_fd=parent_fd,
            )
            try:
                target_state = os.fstat(fd)
                if not stat.S_ISREG(target_state.st_mode):
                    raise SafeIOError(
                        f"Unsafe input path '{target}': target is not a regular file."
                    )
                with io.FileIO(fd, mode="rb", closefd=True) as handle:
                    fd = -1
                    return handle.read().decode(encoding)
            finally:
                if fd >= 0:
                    os.close(fd)
    except SafeIOError:
        raise
    except OSError as error:
        raise SafeIOError(
            f"Could not safely read '{target}': {error.__class__.__name__}: {error}"
        ) from error


def unlink_file_no_follow(
    path: str | Path,
    *,
    workspace_root: str | Path | None = None,
) -> None:
    target = Path(path)
    try:
        with _opened_parent(
            target,
            workspace_root=workspace_root,
            create_parents=False,
        ) as (parent_fd, name):
            target_state = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if not stat.S_ISREG(target_state.st_mode):
                raise SafeIOError(
                    f"Unsafe unlink path '{target}': target is not a regular file."
                )
            os.unlink(name, dir_fd=parent_fd)
            os.fsync(parent_fd)
    except FileNotFoundError:
        return
    except SafeIOError:
        raise
    except OSError as error:
        raise SafeIOError(
            f"Could not safely unlink '{target}': {error.__class__.__name__}: {error}"
        ) from error


@contextmanager
def _opened_parent(
    target: Path,
    *,
    workspace_root: str | Path | None,
    create_parents: bool,
) -> Iterator[tuple[int, str]]:
    if not target.name or target.name in {".", ".."}:
        raise SafeIOError(f"Unsafe output path '{target}': missing filename.")

    if workspace_root is None:
        absolute_target = Path(os.path.abspath(target))
        parent_fd = _open_absolute_directory(
            absolute_target.parent,
            create=create_parents,
        )
        try:
            yield parent_fd, absolute_target.name
        finally:
            os.close(parent_fd)
        return

    if ".." in target.parts:
        raise SafeIOError(
            f"Unsafe workspace output '{target}': '..' components are not allowed."
        )
    root = Path(workspace_root).resolve(strict=True)
    absolute_target = Path(os.path.abspath(target))
    try:
        relative = absolute_target.relative_to(root)
    except ValueError as error:
        raise SafeIOError(
            f"Unsafe workspace output '{target}': path escapes '{root}'."
        ) from error
    if any(part in {"", ".", ".."} for part in relative.parts):
        raise SafeIOError(f"Unsafe workspace output '{target}'.")

    directory_fd = _open_absolute_directory(root)
    try:
        for component in relative.parts[:-1]:
            next_fd = _open_child_directory(
                directory_fd,
                component,
                create=create_parents,
            )
            os.close(directory_fd)
            directory_fd = next_fd
        yield directory_fd, relative.name
    finally:
        os.close(directory_fd)


def _open_absolute_directory(path: Path, *, create: bool = False) -> int:
    if not path.is_absolute():
        raise SafeIOError(f"Safe directory path must be absolute: '{path}'.")
    try:
        directory_fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | _no_follow_flag())
    except OSError as error:
        raise SafeIOError(f"Unsafe directory '{path}': {error}") from error
    try:
        for component in path.parts[1:]:
            next_fd = _open_child_directory(directory_fd, component, create=create)
            os.close(directory_fd)
            directory_fd = next_fd
        return directory_fd
    except BaseException:
        os.close(directory_fd)
        raise


def _open_child_directory(parent_fd: int, name: str, *, create: bool) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | _no_follow_flag()
    try:
        return os.open(name, flags, dir_fd=parent_fd)
    except FileNotFoundError:
        if not create:
            raise
        try:
            os.mkdir(name, 0o777, dir_fd=parent_fd)
            return os.open(name, flags, dir_fd=parent_fd)
        except OSError as error:
            raise SafeIOError(
                f"Could not safely create output directory '{name}': {error}"
            ) from error
    except OSError as error:
        raise SafeIOError(f"Unsafe output directory '{name}': {error}") from error


def _regular_target_state(parent_fd: int, name: str) -> os.stat_result | None:
    try:
        target_state = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(target_state.st_mode):
        raise SafeIOError(f"Unsafe output target '{name}': not a regular file.")
    return target_state


def _require_unchanged_target(
    parent_fd: int,
    name: str,
    original: os.stat_result | None,
) -> None:
    current = _regular_target_state(parent_fd, name)
    if original is None:
        if current is not None:
            raise SafeIOError(f"Output target '{name}' appeared during the write.")
        return
    if current is None or (current.st_dev, current.st_ino) != (
        original.st_dev,
        original.st_ino,
    ):
        raise SafeIOError(f"Output target '{name}' changed during the write.")


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    written = 0
    while written < len(view):
        count = os.write(fd, view[written:])
        if count <= 0:
            raise OSError("write made no progress")
        written += count


def _no_follow_flag() -> int:
    flag = getattr(os, "O_NOFOLLOW", None)
    if flag is None:
        raise SafeIOError("Safe no-follow output is unavailable on this platform.")
    return int(flag)
