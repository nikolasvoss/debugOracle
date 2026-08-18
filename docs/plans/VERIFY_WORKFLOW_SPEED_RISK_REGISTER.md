# Verify Workflow Speed Risk Register

**Status:** Active

| Risk | Tier | Mitigation |
|---|---:|---|
| Fast gate omits tests | Medium | Test the `SKIP` contract through the public script interface. |
| Full gate omits coverage | Medium | Keep the coverage hook and assert it is the only test hook. |
| Contributors skip final validation | Low | Preserve the required full-gate instruction in script output and docs. |
