these notes are just for the developer. not for agent use.

- observe and snapshot usage unclear.
- reduce to short error, when no input data was found.
- the agent does not know well enough how to use the tool. either use self-discovery of the tool or add better description.
- prompt i think is not needed. report with flags would be better.
- add mcu detection to warn about mismatched svd file.
- fetch is capture-only. report is inspection-only.
- optional SVD-backed register catalog capture uses `fetch --svd-file <file>`.
- default report stays short and points users to `report --regs-list` and `report --regs`.
- halt detect logic could be flaky.
- add tests with live openocd backend.
- add simpler setup script/instruction
- clean system paths 