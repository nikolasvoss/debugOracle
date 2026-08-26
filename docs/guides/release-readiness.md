# Release Readiness

Run the read-only preflight before creating a release tag or publishing assets:

```bash
python3 scripts/release-readiness.py --tag v<version>
```

It checks GitHub CLI authentication, a clean synchronized branch, canonical
version/manifest/changelog alignment, and local and remote tag availability.
It never creates tags, publishes assets, or changes credentials.

## Required native CI protection

GitHub branch protection for `main` must require these existing pull-request
checks before merge:

- `installer-platform-gate (macos-latest)`
- `installer-platform-gate (windows-latest)`

Apply or verify that protection with a maintainer-authenticated GitHub session.
The release preflight reports an invalid session before release work begins.
