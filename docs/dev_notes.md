these notes are just for the developer. not for agent use.

- reduce to short error, when no input data was found.
- add mcu detection to warn about mismatched svd file.
- fetch is capture-only. report is inspection-only.
- optional SVD-backed register catalog capture uses `fetch --svd-file <file>`.
- default report stays short and points users to `report --regs-list` and `report --regs`.
- halt detect logic could be flaky.
- add tests with live openocd backend.
- add simpler setup script/instruction
- clean system paths 
- rework stream capture