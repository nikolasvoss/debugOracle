# DebugOracle Agent Runbook (offline, snapshot-first)

Goal:
- Verify a captured debug session in `/home/niko/Dokumente/Bastelei/stm32_1/.dbgoracle` quickly and safely.
- Keep this runbook read-only unless you explicitly need a re-bundle.

## Hard rule

Do **not** run `dbgoracle observe` as part of routine verification.

`observe` is a snapshot rebuild action (it writes `latest_snapshot.json` and optional raw sidecars).
Use it only when you need to regenerate the snapshot after collecting new MI/RTT logs.

## Workspace defaults (fixed for this workflow)

- Workspace root: `/home/niko/Dokumente/Bastelei/stm32_1`
- Artifacts: `/home/niko/Dokumente/Bastelei/stm32_1/.dbgoracle`

## Verification sequence (preferred)

1. **Health and freshness gate**

```bash
WORKSPACE=/home/niko/Dokumente/Bastelei/stm32_1
SNAPSHOT_FILE=$WORKSPACE/.dbgoracle/latest_snapshot.json
STATUS_FILE=$WORKSPACE/.dbgoracle/agent-status.json

if ! dbgoracle status --workspace-root "$WORKSPACE" --format json | tee "$STATUS_FILE"; then
  echo "Outcome: FAIL"
  echo "Reason: status command failed."
  exit 1
fi
```

Interpret `status` output:

- PASS gate: `.snapshot.exists == true` **and** `.snapshot.stale == false`
- REVIEW gate: `.parse_warning_count > 0` or `.health == "degraded"`  
  (do not fail automatically; require explicit review note)
- FAIL gate:
  - status JSON missing or not readable
  - `.snapshot.exists == false`
  - `.snapshot.age_seconds` is older than your allowed recapture threshold
  - MI/RTT source missing when expected by your session policy

If `jq` exists, you can evaluate deterministically with:

```bash
if ! jq -e '.snapshot.exists == true and .snapshot.stale == false' "$STATUS_FILE" >/dev/null; then
  echo "Outcome: FAIL"
  exit 1
fi

PARSE_WARNINGS=$(jq -r '.parse_warning_count // 0' "$STATUS_FILE")
if [ "$PARSE_WARNINGS" -gt 0 ] || [ "$(jq -r '.health // "unknown"' "$STATUS_FILE")" = "degraded" ]; then
  echo "Outcome: REVIEW"
fi
```

If `.status` output cannot be parsed by tools, inspect the printed JSON fields directly and apply the same rules.

2. **Render human-readable report**

```bash
dbgoracle report --workspace-root /home/niko/Dokumente/Bastelei/stm32_1 --snapshot-file "$SNAPSHOT_FILE" --format markdown
```

3. **Render snapshot (automation/automation-friendly export)**

```bash
dbgoracle snapshot --workspace-root /home/niko/Dokumente/Bastelei/stm32_1 --snapshot-file "$SNAPSHOT_FILE" --format json
```

4. **Create LLM handoff prompt**

```bash
dbgoracle prompt --workspace-root /home/niko/Dokumente/Bastelei/stm32_1 --snapshot-file "$SNAPSHOT_FILE" --goal "Explain why the target stopped here" --full --format markdown
```

5. **Agent exit contract**

Emit one of these outcomes for automation:

- `Outcome: PASS` (all required checks passed, no blocking quality issues)
- `Outcome: REVIEW` (passes structurally; includes parse warnings or degraded status; proceed with caution)
- `Outcome: FAIL` (stale/missing snapshot or command failure)
```

## If status or checks fail

- Stop autonomous decision flow and request a new capture.
- Re-run capture, then run `observe` only intentionally if you need a refreshed snapshot:

```bash
cd /home/niko/Dokumente/Bastelei/stm32_1
dbgoracle observe --workspace-root /home/niko/Dokumente/Bastelei/stm32_1 --state-out "$SNAPSHOT_FILE"
```

- For parse warnings, continue only with explicit review notes and avoid concluding a fix without human verification.

## Safety notes

- MI/RTT logs can contain sensitive firmware/runtime state.
- Prefer sharing `report`/`prompt` outputs over raw traces.
- Avoid exposing raw traces unless necessary and approved.
