# Review Checklist

## Required Links
- [ ] Spec is linked
- [ ] Plan is linked

## Acceptance Criteria Coverage
- [ ] Every AC is mapped to test or explicit manual validation

## Invariants
- [ ] Invariants touched are listed and reviewed

## Validation Evidence
- [ ] `./scripts/verify.sh fast` preflight was run (optional)
- [ ] `./scripts/verify.sh full` was run
- [ ] `pre-commit run --all-files` output/result is attached in PR description

## Scope Declaration
- [ ] PR declares `Behavior Change: yes` or `Behavior Change: no`
- [ ] If `Behavior Change: yes`, traceability fields are complete

## Exceptions
- [ ] Any exception includes explicit justification and expiry for this PR only
