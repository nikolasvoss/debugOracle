# Verify Workflow Speed Test Plan

**Status:** Active

| Area | Expected behavior | Validation |
|---|---|---|
| Fast verification | Runs tests and skips coverage only. | Fake `pre-commit` integration test. |
| Full verification | Skips the fast hook and runs the coverage hook once. | Script/configuration regression tests and full gate. |
| CI verification | Uses the authoritative full command. | Workflow regression test. |
| CI timeout | Fails after three minutes of verification execution. | Workflow regression test. |
| Documentation | Describes the new fast behavior. | Workflow documentation regression test. |
