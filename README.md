# DebugOracle

DebugOracle is a passive embedded-debug evidence packager for ChatGPT. It reads a GDB/MI transcript plus optional RTT logs, builds a bounded evidence bundle, and renders either a local evidence report or a ChatGPT-ready prompt.

## Commands

```bash
./dbgoracle observe --gdb-mi tests/fixtures/sample.mi --rtt tests/fixtures/sample.rtt
./dbgoracle snapshot --snapshot-file .dbgoracle/latest_snapshot.json --format markdown
./dbgoracle prompt --gdb-mi tests/fixtures/sample.mi --rtt tests/fixtures/sample.rtt --goal "Explain the current system state"
./dbgoracle report --snapshot-file .dbgoracle/latest_snapshot.json
tail -f /path/to/cortex-debug-shared-mi.log | ./dbgoracle snapshot --gdb-mi-stream --format json
printf "*stopped,reason=\"breakpoint-hit\",...\\n^done,register-values=[...]" | ./dbgoracle snapshot --gdb-mi - --format json
```

## Notes

- v1 is read-only and does not call an LLM.
- `prompt` produces text or Markdown that you can paste into ChatGPT.
- Source-code enrichment and agentic capabilities are placeholders in this version.
