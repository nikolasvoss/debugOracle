# Delivery Contract and Release Preflight Risk Register

| ID | Risk | Tier | Control | Evidence |
| --- | --- | --- | --- | --- |
| R-001 | Preflight mutates GitHub or release state. | Medium | Fixed read-only subprocess calls only. | Subprocess contract tests. |
| R-002 | CI and local audit inputs drift. | Medium | One checked-in renderer used by CI. | Renderer and workflow regression tests. |
| R-003 | Branch protection remains unenforced. | Medium | Document exact required checks; apply with maintainer auth. | GitHub settings verification after authentication. |
