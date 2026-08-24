#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 0 ]; then
  echo "Usage: ./scripts/verify-release.sh" >&2
  exit 2
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd -- "$REPOSITORY_ROOT"

skip_private_reference="${DEBUGORACLE_SKIP_PRIVATE_REFERENCE:-0}"
if [ "$skip_private_reference" = "1" ]; then
  if [ -n "${DEBUGORACLE_RELEASE_TAG:-}" ]; then
    echo "A tagged release cannot skip the private reference-workspace gate." >&2
    exit 1
  fi
  echo "WARNING: private reference-workspace gate is deferred for this non-tag CI run." >&2
else
  submodule_status="$(git submodule status --recursive)"
  printf '%s\n' "$submodule_status"
  if printf '%s\n' "$submodule_status" | grep -Eq '^[+-U]'; then
    echo "Release verification requires every recursive submodule at its pinned commit." >&2
    echo "Run: git submodule update --init --recursive" >&2
    exit 1
  fi
fi

./scripts/verify.sh full

PYTHON_BIN="${PYTHON:-python3}"
SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-1787529600}"
export SOURCE_DATE_EPOCH
if ! [[ "$SOURCE_DATE_EPOCH" =~ ^[0-9]+$ ]]; then
  echo "SOURCE_DATE_EPOCH must be an integer Unix timestamp." >&2
  exit 2
fi
release_tmp=""
cleanup() {
  if [ -n "$release_tmp" ] && [ -d "$release_tmp" ]; then
    rm -rf -- "$release_tmp"
  fi
}
trap cleanup EXIT

release_tmp="$(mktemp -d "${TMPDIR:-/tmp}/debugoracle-release.XXXXXX")"
dist_dir_one="$release_tmp/dist-one"
dist_dir_two="$release_tmp/dist-two"
"$PYTHON_BIN" -m build --outdir "$dist_dir_one" .
"$PYTHON_BIN" -m build --outdir "$dist_dir_two" .

shopt -s nullglob
wheels_one=("$dist_dir_one"/*.whl)
sdists_one=("$dist_dir_one"/*.tar.gz)
wheels_two=("$dist_dir_two"/*.whl)
sdists_two=("$dist_dir_two"/*.tar.gz)
shopt -u nullglob
if [ "${#wheels_one[@]}" -ne 1 ] || [ "${#sdists_one[@]}" -ne 1 ] || \
   [ "${#wheels_two[@]}" -ne 1 ] || [ "${#sdists_two[@]}" -ne 1 ]; then
  echo "Expected exactly one wheel and one sdist from each isolated release build." >&2
  exit 1
fi

"$PYTHON_BIN" -m twine check "${wheels_one[@]}" "${sdists_one[@]}"

"$PYTHON_BIN" - \
  "$REPOSITORY_ROOT/release/install-manifest.json" \
  "${wheels_one[0]}" \
  "${wheels_two[0]}" <<'PY'
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
first_wheel = Path(sys.argv[2])
second_wheel = Path(sys.argv[3])
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


first_hash = sha256(first_wheel)
second_hash = sha256(second_wheel)
if first_hash != second_hash:
    raise SystemExit("Two fixed-epoch wheel builds produced different SHA-256 values.")
if first_wheel.name != second_wheel.name:
    raise SystemExit("Two fixed-epoch wheel builds produced different filenames.")
expected_name = f"debugoracle-{manifest['version']}-py3-none-any.whl"
if first_wheel.name != expected_name:
    raise SystemExit(
        f"Built wheel {first_wheel.name!r} does not match manifest version {expected_name!r}."
    )
if manifest["artifact_sha256"] == "0" * 64:
    raise SystemExit("Release manifest still contains the planning checksum placeholder.")
if manifest["artifact_sha256"] != first_hash:
    raise SystemExit("Release manifest SHA-256 does not match the reproducible wheel.")
if manifest["artifact_size"] != first_wheel.stat().st_size:
    raise SystemExit("Release manifest artifact_size does not match the wheel.")
if not str(manifest["artifact_url"]).endswith("/" + first_wheel.name):
    raise SystemExit("Release manifest artifact_url does not name the built wheel.")
PY

wheel_listing="$("$PYTHON_BIN" -m zipfile -l "${wheels_one[0]}")"
for required_path in \
  "debugoracle/__init__.py" \
  ".dist-info/licenses/LICENSE" \
  ".dist-info/entry_points.txt"; do
  if ! printf '%s\n' "$wheel_listing" | grep -Fq -- "$required_path"; then
    echo "Wheel is missing required release content: $required_path" >&2
    exit 1
  fi
done
if printf '%s\n' "$wheel_listing" | grep -Eq \
  '(tests/|docs/private_notes/|/\.git/|__pycache__/|\.pytest_cache/|\.ruff_cache/|\.dbgoracle/)'; then
  echo "Wheel contains private, test, cache, or repository-only content." >&2
  exit 1
fi

smoke_venv="$release_tmp/smoke-venv"
"$PYTHON_BIN" -m venv "$smoke_venv"
"$smoke_venv/bin/python" -m pip install --disable-pip-version-check "${wheels_one[0]}"
installed_version="$("$smoke_venv/bin/dbgoracle" --version)"
wheel_basename="$(basename -- "${wheels_one[0]}")"
expected_version="${wheel_basename#debugoracle-}"
expected_version="${expected_version%-py3-none-any.whl}"
if [ "$installed_version" != "$expected_version" ]; then
  echo "Installed dbgoracle version '$installed_version' does not match '$expected_version'." >&2
  exit 1
fi
"$smoke_venv/bin/dbgoracle" --help >/dev/null

echo "Release verification complete: wheel and sdist validated; dbgoracle $installed_version smoke-tested."
