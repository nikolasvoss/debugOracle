# Workspace setup and file discovery

`debugoracle-input/` is an optional convenience folder created for a fresh workspace. It accepts any project-related files and subfolders. Discovery checks it first, then bounded common workspace locations. It recognizes PDFs, SVDs, ELF files, OpenOCD configuration, and supported captured debug artifacts; it avoids dependency, cache, and virtual-environment folders and never guesses between ambiguous candidates.

User-owned VS Code files are never overwritten; DebugOracle reports the required merge action instead.
