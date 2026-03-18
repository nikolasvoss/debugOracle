# models

- Module: `models`
- Code Path: `debugoracle/models.py`
- Public Entrypoints: `EvidenceBundle`, `SessionEvent`, `StackFrame`, `InvestigationRequest`, `PromptPackage`
- Last Updated: `2026-03-18`

## Purpose

Define the core typed data structures exchanged across the package.

## Responsibilities

- Represent snapshot evidence, prompt requests, and rendered prompt packages.
- Convert bundle payloads to and from plain dictionaries.
- Centralize schema-version defaults and compatibility-friendly coercion helpers.

## Notes

- Changes here have cross-module impact because most package boundaries depend on these dataclasses.
