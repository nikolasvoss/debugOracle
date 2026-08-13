# Claude Code Compatibility Plan

Status: Complete

## Purpose

Make the existing agent-neutral DebugOracle CLI equally discoverable and safely
guided in Codex and Claude Code without adding a runtime integration.

## Task Link

[Claude Code Compatibility Task Spec](CLAUDE_CODE_COMPATIBILITY_TASK_SPEC.md)

## Files / Modules To Change

- `CLAUDE.md`: Claude Code instruction entry point that imports canonical rules.
- `README.md`: named-agent onboarding guidance.
- `tests/test_agent_instruction_compatibility.py`: documentation compatibility
  regression coverage.

## Implementation Steps

1. Add a root `CLAUDE.md` containing an import of `AGENTS.md`.
2. Update the README setup headings and prose to name Codex and Claude Code.
3. Add focused regression coverage for the instruction import and onboarding
   wording.
4. Run focused and full validation.

## Acceptance Criteria -> Validation Map

| AC ID | Validation Type | Location / Command |
|---|---|---|
| AC-001 | Regression test | `tests/test_agent_instruction_compatibility.py` |
| AC-002 | Regression test | `tests/test_agent_instruction_compatibility.py` |
| AC-003 | Regression test | `python3 -m unittest tests.test_agent_instruction_compatibility` |

## Test Plan

- Regression: read repository instruction and README files through real file I/O.
- Integration: manually open the repository with Claude Code and confirm its
  project-memory view includes the imported instructions when Claude Code is
  available.

## Validation Commands

- `python3 -m unittest tests.test_agent_instruction_compatibility`
- `./scripts/verify.sh fast`
- `./scripts/verify.sh full`

## Release / Compatibility Notes

This is documentation and repository-instruction compatibility only. The
existing Linux CLI installation contract and all runtime interfaces remain
unchanged.
