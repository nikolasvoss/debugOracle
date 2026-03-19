# Implementation Plan: Self-Contained Snapshots and `fetch`/`report` CLI Redesign

## Goal

Replace `observe` with `fetch`, remove `snapshot`, make snapshots self-contained and lossless, and turn `report` into a snapshot-only inspection surface with one human summary mode and structured JSON inspect modes.

Chosen defaults:

- keep `latest_snapshot.json`
- keep `snapshot_id` terminology
- `fetch` overwrites the latest snapshot for now
- `report` and `prompt` never rebuild from raw
- expanded `report` modes are compact JSON outputs
- missing selected sources are explicit failures
- older snapshots load best-effort, but new inspect modes may fail if embedded source sections are missing

## Decisions Locked In

### Command model

- `fetch` replaces `observe`
- `snapshot` is removed
- `fetch` is the only command that reads raw sources and builds a snapshot
- `report` is snapshot-only and never rebuilds from raw
- `prompt` is snapshot-only, but prompt redesign is deferred for now

### Snapshot model

- `latest_snapshot.json` stays the filename
- `snapshot_id` and snapshot terminology stay in the schema
- the snapshot becomes the single canonical, self-contained evidence package
- no information should be lost
- full source payloads should be embedded in the snapshot
- for GDB, store both raw text and parsed ordered events
- for RTT, store raw text and a convenient line representation
- missing sources are allowed; `fetch` still succeeds with the user-chosen inputs

### `fetch` behavior

- supports both explicit source paths and auto-discovery
- explicit paths override discovery
- if discovery finds nothing usable, fail explicitly and name the candidate paths checked
- overwrites the default latest snapshot for now
- prints only:
  - snapshot id
  - output path
  - embedded sources
  - source sizes/counts

### `report` behavior

- default `report` stays human-readable plain text
- keep current summary-style sections like parsing summary and unknowns/gaps
- add contextual hints near relevant sections, like `report --vars`, `report --gdb`, `report --rtt`
- state explicitly, per source, that full embedded source data exists in the snapshot

### Expanded `report` modes

- remove `--format`
- remove `--var-detail`, `--var-scope`, and `--var-name`
- add machine-oriented inspect modes:
  - `report --vars [NAME ...]`
  - `report --gdb [--tail N]`
  - `report --rtt [--tail N]`
  - `report --verbose [--tail N]`
- `--tail` must be a hard-positive integer
- `--tail` applies only to streams

### Output contracts

- `report --vars [NAME ...]`
  - compact JSON object
  - top-level key `variables`
  - grouped by `locals`, `globals`, `watchpoints`, `unknown`
  - exact case-insensitive matching
  - preserve stored order
  - fail if requested names have no matches

- `report --gdb [--tail N]`
  - compact JSON object under `gdb`
  - include all stored GDB events, not only MI
  - include `console-output`, `prompt-marker`, `non_mi_line`, parse-error events
  - `tail N` means last `N` stored GDB session events across all kinds, in original order

- `report --rtt [--tail N]`
  - compact JSON object under `rtt`
  - include stored RTT lines and metadata
  - `tail N` means last `N` RTT lines

- combined inspect flags
  - emit one compact JSON object containing only requested sections

- `report --verbose [--tail N]`
  - emit one compact JSON object containing:
    - summary fields
    - grouped variable object
    - GDB parsed events
    - RTT lines
    - parsing/provenance metadata
  - `tail` affects stream sections only

## Implementation Phases

### Phase 1: Lock the contract in docs and tests first

#### Step 1.1: Write the new command contract

Update the planning/spec docs before code so the implementation has one source of truth.

1. Update `docs/specs/cli.md` to redefine the product model:
   - `fetch` = raw-only capture/build command
   - `report` = snapshot-only inspection command
   - `prompt` = snapshot-only prompt packaging
   - remove `snapshot` from the command list
2. Update `docs/specs/main.md`:
   - routing changes from `observe/snapshot/report/prompt` to `fetch/report/prompt`
   - remove shared variable selector section
   - add the new `report` inspect flag surface
3. Update `docs/specs/evidence.md`:
   - rename `cmd_observe` to `cmd_fetch`
   - remove `cmd_snapshot`
   - document snapshot-only resolution for `report` and `prompt`
4. Update `docs/specs/transcript.md` and `docs/specs/builder.md`:
   - state that full raw source payloads are embedded in snapshots
   - state that parsed GDB events remain stored alongside raw text
5. Update `docs/poc-definition.md`:
   - `observe` -> `fetch`
   - remove `snapshot` from the workflow

#### Step 1.2: Replace the old CLI expectations in tests

Before implementation, rewrite the intended test matrix so the new behavior is clear.

1. Mark current tests that will be deleted or rewritten:
   - all `snapshot` command tests
   - all `report --format` tests
   - all `--var-scope/--var-name/--var-detail` tests
2. Add new test names first in `tests/test_cli_flow.py`:
   - `test_fetch_writes_latest_snapshot_and_prints_operational_summary`
   - `test_report_requires_snapshot_and_tells_user_to_run_fetch`
   - `test_prompt_requires_snapshot_and_tells_user_to_run_fetch`
   - `test_report_vars_outputs_grouped_json_object`
   - `test_report_gdb_outputs_gdb_object`
   - `test_report_rtt_outputs_rtt_object`
   - `test_report_verbose_outputs_composite_json_object`
   - `test_report_tail_requires_positive_integer`
   - `test_report_vars_fails_when_requested_names_are_missing`
   - `test_fetch_discovery_failure_lists_checked_candidates`

### Phase 2: Expand the snapshot schema into the canonical evidence package

#### Step 2.1: Add explicit embedded source sections

Evolve `debugoracle/artifacts/models.py` so snapshots clearly separate summary data from embedded source payloads.

1. Introduce first-class source payload fields under a new top-level `sources` object.
2. Keep current top-level summary fields for cheap access:
   - `snapshot_id`, `captured_at`, `stop_reason`, `pc`, `lr`, `sp`, `frames`, `registers`, `variable_evidence`, `parse_warnings`, `provenance`
3. Add new source sections:
   - `sources.gdb.raw_text`
   - `sources.gdb.events`
   - `sources.gdb.event_count`
   - `sources.rtt.raw_text`
   - `sources.rtt.lines`
   - `sources.rtt.line_count`
4. Keep the stored order of GDB events and variable entries exactly as captured.
5. Bump `CURRENT_BUNDLE_SCHEMA_VERSION`.

#### Step 2.2: Define compatibility behavior for old snapshots

Do not break loading entirely, but do not fake parity either.

1. Update `InvestigationArtifact.from_dict()` to parse `sources` when present.
2. Keep best-effort support for old top-level fields such as:
   - `session_events`
   - `recent_rtt`
3. Define fallback policy:
   - default `report` summary may use legacy fields
   - `report --gdb`, `report --rtt`, and `--verbose` should fail clearly if required embedded source sections are absent
4. Update `tests/test_artifact_schema.py` to cover:
   - new schema round-trip
   - old schema load
   - inspect-mode incompatibility behavior on old snapshots

### Phase 3: Rewrite fetch/build flow around self-contained snapshots

#### Step 3.1: Rename `observe` to `fetch`

Keep the implementation lean by reusing the existing raw-resolution and bundle-building path in `debugoracle/cli/commands/evidence.py`.

1. Rename parser and dispatch wiring in `debugoracle/cli/main.py`.
2. Rename command entrypoint in `debugoracle/cli/commands/evidence.py` from `cmd_observe` to `cmd_fetch`.
3. Update command help strings so `fetch` clearly means:
   - resolve explicit or discovered raw inputs
   - build a snapshot
   - overwrite the default latest snapshot unless `--state-out` is provided

#### Step 3.2: Remove the `snapshot` command entirely

1. Delete parser registration for `snapshot`.
2. Remove `cmd_snapshot` usage from CLI dispatch.
3. Remove snapshot renderer dependencies from the command flow.
4. Keep the renderer module only if tests or internal helpers still need it; otherwise remove it in the same change or make it a thin private compatibility helper not exposed through CLI.

#### Step 3.3: Embed full source payloads during artifact construction

Update `debugoracle/pipeline/storage.py` and related builder flow.

1. Stop treating raw sidecar export as the primary persistence path.
2. Always embed full selected raw source payloads into the snapshot:
   - GDB raw transcript text
   - RTT raw text
3. Always embed derived convenience forms:
   - GDB ordered parsed event list
   - RTT line array
4. Keep top-level summary fields derived from the same stored data.
5. Remove `raw_exported` from the normal happy-path contract; only keep any raw-export logic if tests or migration helpers still need it temporarily.

#### Step 3.4: Keep `fetch` output operational, not interpretive

`fetch` should print only:

- snapshot id
- output path
- embedded sources
- source sizes/counts

1. Add source count/size calculation from embedded source sections.
2. Do not print stop reason, stack frame, or other report-like content.
3. Update tests to assert exact summary categories, not vague wording.

### Phase 4: Make `report` and `prompt` snapshot-only

#### Step 4.1: Remove raw rebuild resolution from `report`

1. In `debugoracle/cli/commands/evidence.py`, make `cmd_report()` load only a snapshot.
2. Default to discovered `latest_snapshot.json` when `--snapshot-file` is omitted.
3. If no snapshot exists:
   - fail hard
   - print a clear message telling the user to run `fetch`
4. Remove the use of raw evidence inputs from `report` parser/help text.

#### Step 4.2: Make `prompt` snapshot-only without redesigning prompt semantics

1. In `cmd_prompt()`, load only a snapshot.
2. Keep current prompt rendering behavior otherwise.
3. If no snapshot exists:
   - fail hard
   - tell the user to run `fetch`
4. Do not redesign `prompt --full` in this pass.

### Phase 5: Redesign the `report` CLI surface

#### Step 5.1: Replace formatter/filter flags with inspect modes

Update `debugoracle/cli/main.py`.

1. Remove:
   - `--format`
   - `--var-scope`
   - `--var-name`
   - `--var-detail`
2. Add inspect flags:
   - `--vars` with optional positional names semantics
   - `--gdb`
   - `--rtt`
   - `--verbose`
   - `--tail`
3. Keep combinations allowed.
4. Define parser validation for `--tail`:
   - integer
   - must be `> 0`
5. Keep `--tail` valid only when a stream section is requested:
   - `--gdb`
   - `--rtt`
   - `--verbose`
   - or any combination including `gdb`/`rtt`

#### Step 5.2: Lock exact inspect-mode semantics

1. No inspect flags:
   - plain-text human summary
2. `--vars [NAME ...]`:
   - compact JSON object
   - top-level key `variables`
   - grouped by `locals`, `globals`, `watchpoints`, `unknown`
   - exact case-insensitive matching
   - preserve stored order
   - fail if requested names have no matches
3. `--gdb [--tail N]`:
   - compact JSON object under `gdb`
   - include all stored GDB events, not only MI
   - include `console-output`, `prompt-marker`, `non_mi_line`, parse-error events
   - `tail N` means last `N` stored GDB session events across all kinds, in original order
4. `--rtt [--tail N]`:
   - compact JSON object under `rtt`
   - include stored RTT lines and metadata
   - `tail N` means last `N` RTT lines
5. Combined inspect flags:
   - emit one compact JSON object containing only requested sections
6. `--verbose [--tail N]`:
   - emit one compact JSON object containing:
     - summary fields
     - grouped variable object
     - GDB parsed events
     - RTT lines
     - parsing/provenance metadata
   - `tail` affects stream sections only

### Phase 6: Rewrite report rendering into two output families

#### Step 6.1: Keep the default summary human-readable

Update `debugoracle/renderers/report.py` and shared helpers.

1. Remove markdown output path for the default report.
2. Keep plain-text summary sections:
   - session summary
   - stack trace
   - registers
   - variable summary
   - parsing summary
   - unknowns/gaps
3. Add per-section next-step hints near relevant sections:
   - `report --vars`
   - `report --gdb`
   - `report --rtt`
4. Add explicit per-source statements that full embedded source data exists or is absent.

#### Step 6.2: Add structured inspect renderers

1. Create one shared composition helper that returns a Python dict for requested sections.
2. Reuse that helper for:
   - `--vars`
   - `--gdb`
   - `--rtt`
   - combined flags
   - `--verbose`
3. Keep each structured output compact on stdout:
   - `json.dumps(..., separators=(",", ":"))`
4. Avoid separate renderer logic branches that could drift.

### Phase 7: Clean up data and parser boundaries

#### Step 7.1: Remove dead selector plumbing

1. Delete `add_variable_selector_arguments()` from `debugoracle/cli/main.py`.
2. Remove `VariableRenderOptions` usage from report command flow where it only exists for old summary filtering.
3. Keep or refactor variable helper logic only where needed for:
   - grouped variable summary in default report
   - exact case-insensitive filtering in `--vars`

#### Step 7.2: Remove stale raw-export assumptions

1. Update provenance semantics so snapshot completeness is represented by embedded source sections, not sidecar exports.
2. Remove user-facing raw-export notices from `fetch`/`report`.
3. Keep parse warnings about missing evidence, but stop referring users to raw sidecars as the normal recovery path.

### Phase 8: Execute the full test rewrite

#### Step 8.1: CLI contract tests

In `tests/test_cli_flow.py` cover:

1. `fetch` command exists and `observe`/`snapshot` no longer do.
2. `fetch` writes `latest_snapshot.json`.
3. `fetch` prints snapshot id, output path, embedded sources, and source sizes/counts.
4. `report` and `prompt` fail without a snapshot and tell the user to run `fetch`.
5. `report` no longer accepts old flags.

#### Step 8.2: Structured report output tests

Cover:

1. `report --vars` no-filter output
2. `report --vars name1 name2` filtered output
3. no-match failure for `--vars`
4. `report --gdb` full stored event stream output
5. `report --gdb --tail N`
6. `report --rtt`
7. `report --rtt --tail N`
8. `report --verbose`
9. combined modes such as `report --vars --gdb`
10. `--tail <= 0` failure
11. `--tail` rejected when no stream section is requested

#### Step 8.3: Schema and compatibility tests

Cover:

1. new snapshot round-trip with embedded `sources`
2. old snapshot load compatibility
3. summary report on old snapshots
4. inspect-mode explicit failure on old snapshots without `sources.gdb` or `sources.rtt`

### Phase 9: Final documentation pass

#### Step 9.1: Update all user-facing references

1. Replace `observe` with `fetch`
2. Remove `snapshot`
3. Remove references to:
   - `report` rebuilding from raw
   - `prompt` rebuilding from raw
   - sidecar raw export as the primary full-data path
4. Update any examples and command descriptions in:
   - `docs/specs/cli.md`
   - `docs/specs/evidence.md`
   - `docs/specs/main.md`
   - `docs/specs/builder.md`
   - `docs/specs/transcript.md`
   - `docs/poc-definition.md`

#### Step 9.2: Keep this implementation plan in the repo

Document path:
`docs/fetch-report-redesign-plan.md`

Suggested stable sections:

1. Goal
2. Decisions locked in
3. Implementation phases
4. Test matrix
5. Compatibility notes

## Test Matrix

### Command-level behavior

- `dbgoracle fetch` replaces `observe`
- `dbgoracle snapshot` is gone
- `report` and `prompt` require a snapshot and point the user to `fetch`
- discovery failures list checked candidate paths

### Snapshot schema

- snapshots embed full selected source payloads and derived source structures
- new snapshots round-trip cleanly through save/load
- older snapshots still load best-effort
- inspect-mode failures are explicit when embedded source sections are missing

### Report outputs

- default `report` is plain-text human-readable
- `report --vars`, `--gdb`, `--rtt`, and `--verbose` emit compact JSON
- `report --vars` supports exact case-insensitive filtering and fails on no match
- `--tail` works only for stream sections and fails for `<= 0`
- combined inspect flags compose into one compact JSON object

## Compatibility Notes

- No alias or deprecation shim for `observe` or `snapshot`
- `prompt` redesign is deferred; only snapshot-only loading changes now
- snapshot size growth is acceptable in exchange for self-contained evidence
- combined inspect flags are supported and compose into one compact JSON object
