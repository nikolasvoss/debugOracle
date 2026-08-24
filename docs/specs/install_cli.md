# install_cli

- Module: `install_cli`
- Code Path: `debugoracle/cli/commands/install_cli.py`
- Public Entrypoints: `cmd_install_cli`
- Last Updated: `2026-08-24`

# SPEC: Internal Installer CLI Hook

## Purpose

Provide a narrow CLI surface that a Linux launcher can call to reuse the package-owned installer core.

## Responsibilities

- Translate parser arguments into installer-core options.
- Render installer outcomes in `text` or `json` form.
- Keep install policy out of shell wrappers while accepting launcher-provided source overrides.
- Accept checkout-local package source overrides from the Linux launcher.

## Constraints

- Hidden from normal user-facing help.
- Must not broaden the ordinary debug-evidence workflow surface.
- Must preserve structured outcome mapping from the installer core instead of flattening failures into generic text.

## Version Consistency Contract

- The package build version and `dbgoracle --version` derive from the canonical
  `debugoracle.version.__version__` value.
- The checkout manifest's `version`, release tag, and wheel filename must match
  that canonical version.
- The checkout launcher must continue to pass its local repository path as the
  package source override. That override takes precedence over the manifest
  source so an audited checkout installs its own contents.
- Release installation uses a project-owned GitHub Release wheel. PyPI is not
  an installation source for this release channel.
- Version ordering and Python requirement evaluation use PEP 440 through one
  package-owned implementation. Invalid versions and specifiers are controlled
  manifest/backend failures, never best-effort numeric normalization.
- A regression test must reject drift among these release metadata surfaces.

## Manifest Schema 2

Remote manifests fail closed unless all of the following are true:

- `schema_version` is exactly `"2"`;
- `package_name` identifies `debugoracle`;
- `artifact_kind` is `"wheel"`;
- `artifact_url` is the versioned wheel under this project's GitHub Release;
- `artifact_sha256` is a full SHA-256 hex digest;
- optional `artifact_size`, when present, is a positive byte count;
- `version`, `installer_min_version`, and `python_requires` are valid PEP 440
  values/specifiers.

The release candidate replaces any planning placeholder hash and size with the
exact values of the wheel that passed the release gate. Unknown schema versions
are rejected rather than interpreted as an older schema.

Schema 2 requires installer protocol `0.2.0` or newer. The minimum is part of
the release manifest so a schema-1 installer fails before it can fall back to
an unbound package requirement.

## Remote Trust Boundary

- A remote manifest must use HTTPS at the project-owned
  `raw.githubusercontent.com` path. Plain HTTP and other hosts are rejected
  before a request is made.
- Every redirect is checked. Manifest redirects must remain on the approved raw
  project path. Wheel redirects may terminate only at GitHub's HTTPS release
  asset hosts.
- Manifest reads are capped at 64 KiB. Wheel reads are capped at 100 MiB and by
  `artifact_size` when supplied. Declared and observed sizes must agree.
- The wheel is downloaded into a private temporary directory, hashed while it
  is read, and checked for project name and PEP 440 version identity before
  mutation. Only that verified local file path is passed to pipx.
- Download, redirect, size, checksum, or identity failure happens before pipx
  mutation and removes staging files.
- `--package-source` is a checkout-local override. URL-shaped overrides are
  rejected; a remote manifest cannot select a local path or an arbitrary pip
  requirement.

## Recovery Outcomes

Installer backend, integrity, and inspection failures are returned as stable
`InstallerOutcomeCode` values. In particular:

- `failed_artifact`: source identity, size, or checksum validation failed;
- `failed_network_transient`: bounded manifest/artifact retrieval failed;
- `failed_install`: pipx mutation failed and the prior state was preserved;
- `failed_post_install_inspection`: pipx returned success but its resulting
  state could not be inspected;
- `failed_cleanup`: recovery could not confirm the previous clean/working
  state;
- `failed_verify`: the installed CLI did not report the expected version.

No backend or post-install inspection error should escape this surface as a
traceback. A post-install inspection failure includes commands the operator can
use to inspect the pipx and CLI state before retrying. A failed fresh-install
inspection removes the new installation. After an upgrade, the state is
reported as unknown and the installer performs no unbound rollback download or
additional mutation: an automatic rollback would require a separately
manifest-bound hash for the previous wheel.

## Verified Alpha Environment

- Release evidence is produced on Ubuntu 24.04 LTS x86-64 with Python 3.12 and
  `pipx`.
- Other distributions, architectures, and Python versions remain unverified
  until the release compatibility matrix records them.
