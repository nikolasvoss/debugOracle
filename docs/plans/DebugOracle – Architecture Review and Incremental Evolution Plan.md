# DebugOracle – Architecture Review and Incremental Evolution Plan

## 1. Purpose

This document defines a structured review of DebugOracle's current architecture and potential future direction.

The goal is **not** to execute a broad rewrite.

The goal is to determine, one architectural area at a time:

- what already works well,
- what solves a real Embedded Engineering problem,
- what is unnecessarily complex,
- what duplicates functionality already implemented better elsewhere,
- what should remain part of DebugOracle,
- what should be simplified,
- what should be replaced,
- what should be added,
- and what should deliberately not be built.

The current implementation must be treated as evidence, not as sunk cost.

Existing code should be preserved when it is useful and well constructed.

Existing code should also be removed or replaced when there is a clearly better solution.

Do not optimize for minimizing deleted code.

Do not optimize for maximizing reuse.

Optimize for the simplest architecture that gives an Embedded Engineer and a coding agent genuinely useful embedded-debugging capabilities.

---

# 2. Core principle

Every architectural proposal in this document is a **hypothesis to test**, not a predetermined decision.

Examples:

> "SVD semantics should become a core DebugOracle capability."

This is a hypothesis.

> "GDB/MI should be delegated to gdb-mcp."

This is a hypothesis.

> "InvestigationArtifact is too complex."

This is a hypothesis.

For every such proposal:

1. inspect the actual implementation,
2. understand why it exists,
3. inspect its tests and consumers,
4. determine what problem it solves,
5. compare it with alternatives,
6. design the smallest useful experiment,
7. collect evidence,
8. make an explicit decision.

Do not refactor merely because another architecture looks cleaner.

---

# 3. Non-goals

Do not perform a Big-Bang rewrite.

Do not:

- migrate the whole project to another architecture at once,
- rewrite working functionality without evidence,
- remove compatibility paths before replacements are validated,
- introduce a large abstraction hierarchy speculatively,
- build another IDE,
- build another coding agent,
- build another compiler or build system,
- reimplement GDB,
- reimplement probe-rs,
- reproduce features merely because they exist in competitors,
- turn every useful concept into a framework.

Avoid creating abstractions that have only one concrete consumer unless they clearly reduce coupling or enable a near-term experiment.

---

# 4. Desired product question

All architectural decisions should ultimately support answering:

> What does DebugOracle enable an Embedded Engineer or coding agent to do significantly better than Codex/Claude + shell + GDB + existing MCP tools already can?

A capability is a strong candidate for DebugOracle core ownership if it adds **embedded-specific semantic understanding** rather than merely exposing an existing debugger command.

Candidate differentiation areas include:

- SVD-based peripheral semantics,
- Cortex-M semantics,
- interrupt/NVIC interpretation,
- fault interpretation,
- RTOS semantics,
- correlation between software and hardware state,
- compact agent-optimized hardware context,
- temporal consistency of observations,
- relevant context selection.

Commodity functionality should preferably be delegated.

Examples of likely commodity functionality:

- raw memory reads,
- raw register reads,
- GDB execution control,
- generic breakpoints,
- generic backtraces,
- generic C/C++ expression evaluation,
- probe discovery,
- firmware flashing,
- RTT transport,
- build command execution.

These classifications must still be validated.

---

# 5. Decision categories

Every reviewed area must end with exactly one primary classification.

## KEEP

The current approach is appropriate and should remain.

## KEEP + EXTEND

The current architecture is sound but missing important functionality.

## SIMPLIFY

The capability is useful, but the implementation or model is unnecessarily complex.

## REPLACE

The capability is useful, but another implementation or external project is clearly superior.

## EXTERNALIZE

Keep the capability available but remove it from the DebugOracle core.

## DEPRECATE

Keep temporarily for compatibility while migration occurs.

## REMOVE

The capability or abstraction no longer justifies its maintenance cost.

## BUILD

A genuinely missing capability should be implemented.

## DEFER

Potentially valuable, but not currently justified.

Every decision must include evidence.

---

# 6. Standard review procedure

For every architectural topic below, perform the following procedure independently.

## Step A – Inspect

Identify:

- implementation files,
- public APIs,
- CLI commands,
- models,
- tests,
- documentation,
- callers,
- dependencies,
- assumptions.

Do not evaluate only from README descriptions.

## Step B – State the problem

Write one short sentence:

> This component exists to solve ______.

If that sentence cannot be stated clearly, note that as an architectural warning.

## Step C – Evaluate current implementation

Assess:

- correctness,
- complexity,
- coupling,
- test quality,
- duplication,
- maintainability,
- agent usefulness,
- Embedded Engineering usefulness.

## Step D – Compare alternatives

Where relevant compare against:

- gdb-mcp,
- embedded-debugger-mcp,
- probe-rs,
- OpenOCD,
- GDB itself,
- existing SVD libraries,
- existing RTOS tooling,
- existing vendor/debug tooling.

Do not assume an external project is better merely because it exists.

Evaluate:

- feature coverage,
- API quality,
- maintenance activity,
- dependencies,
- integration cost,
- platform limitations,
- stability,
- test coverage,
- licensing,
- project risk.

## Step E – Minimal experiment

Before major replacement, define the smallest experiment capable of disproving or supporting the proposed direction.

Examples:

- connect gdb-mcp to one STM32/OpenOCD session,
- decode one STM32 timer completely through SVD,
- replace one RTT workflow with embedded-debugger-mcp,
- produce one semantic hardware snapshot.

## Step F – Decision

Record:

- KEEP / SIMPLIFY / REPLACE / etc.,
- evidence,
- intended change,
- migration impact,
- tests required,
- follow-up work.

Then stop.

Do not automatically proceed into adjacent architecture changes.

---

# 7. Review order

Use the order below.

Later decisions may depend on earlier results.

---

# REVIEW 1 – Product boundary and USP

## Hypothesis

DebugOracle's strongest long-term value may be:

> semantic embedded debugging for coding agents

rather than:

> a generic evidence engine.

Possible core differentiation:

1. embedded semantics,
2. cross-source correlation,
3. agent-optimized context.

Evidence/provenance may be implementation qualities rather than the user-facing product itself.

## Investigate

Read:

- README,
- GOAL,
- architecture documentation,
- strategy documents,
- current CLI,
- examples,
- tests.

Identify what the software currently promises.

Ask:

- What user problem is solved today?
- Which features are unique?
- Which features are infrastructure?
- Which features could Codex reproduce with shell commands?
- Which features materially reduce Embedded Engineering effort?

## Deliverable

Write a concise proposed product boundary:

### DebugOracle should own

...

### DebugOracle should integrate

...

### DebugOracle should not own

...

Do not modify architecture yet.

---

# REVIEW 2 – SVD subsystem

## Hypothesis

SVD-based semantic hardware inspection may be one of DebugOracle's strongest differentiators.

## Inspect

Review all:

- SVD parsing,
- `derivedFrom`,
- peripheral selection,
- register addressing,
- access semantics,
- live register reads,
- SVD discovery,
- tests,
- artifact representations.

Determine current support for:

- peripherals,
- registers,
- register arrays,
- clusters,
- fields,
- bit ranges,
- enumerated values,
- access types,
- reset values,
- descriptions,
- derived peripherals/registers/fields.

## Key question

Can DebugOracle convert:

`0x40012C00 = 0x81`

into something semantically useful such as:

`TIM1.CR1.CEN = enabled`

without the agent manually decoding register definitions?

## Minimal experiment

Implement or prototype:

`inspect TIM1.CR1`

with:

- register value,
- decoded fields,
- enum meaning,
- concise descriptions.

Then:

`inspect TIM1`

for one real STM32 target.

## Decision

Determine whether to:

- KEEP + EXTEND current parser,
- replace parser with an existing SVD library,
- use probe-rs metadata,
- combine approaches.

Do not assume the existing parser must survive.

---

# REVIEW 3 – SVD auto-discovery

## Hypothesis

A semantic debugger should usually determine the correct device description automatically.

## Investigate

Determine:

- how target MCU is identified today,
- where SVD files come from,
- whether STM32 packs/CMSIS packs can be used,
- whether probe-rs already solves part of this,
- fallback behavior.

## Desired UX

Ideally:

`connect`

followed by:

`STM32G474RE detected → matching SVD loaded`

without manual configuration.

## Decision

Design the minimum reliable solution.

---

# REVIEW 4 – Provenance

## Hypothesis

Provenance is useful but may currently be over-modeled.

## Inspect

Find every representation of:

- source,
- capture origin,
- timestamp,
- backend,
- file provenance,
- hardware state.

Determine which fields are actually consumed.

## Questions

What incorrect agent behavior does provenance prevent?

Which metadata is necessary for that?

Could the useful portion be represented simply as:

- source,
- captured_at,
- target,
- backend?

## Decision

KEEP, SIMPLIFY, or REMOVE individual fields.

Do not preserve metadata merely because the current schema contains it.

---

# REVIEW 5 – Freshness and `halt_id`

## Hypothesis

Temporal consistency may be one of the genuinely important internal properties of DebugOracle.

## Investigate

Determine how:

- `halt_id`,
- capture time,
- running/halted state,
- same-halt relationships,
- stale state

are implemented and used.

Construct concrete failure cases.

Example:

- RTT log from time A,
- register snapshot from halt B,
- peripheral snapshot from halt C.

Determine whether combining them could lead an agent to false conclusions.

## Decision

Keep only the minimum mechanism required to distinguish trustworthy correlations.

Potential minimal model:

- captured_at,
- halt_id,
- freshness,
- target_state.

---

# REVIEW 6 – InvestigationArtifact

## Hypothesis

The current artifact may duplicate state already maintained by the coding agent and may be more complex than necessary.

## Inspect

Map:

- every artifact field,
- every producer,
- every consumer,
- persistence behavior,
- renderer dependencies,
- schema migration history.

For every field ask:

> What breaks if this disappears?

## Compare models

Current rich InvestigationArtifact versus a smaller:

`Snapshot`

containing:

- snapshot_id,
- target,
- captured_at,
- halt_id,
- observations,
- warnings.

## Minimal experiment

Implement one semantic investigation using a lightweight Snapshot representation without removing the existing artifact.

Compare:

- complexity,
- output usefulness,
- token cost,
- debugging usefulness.

## Decision

KEEP / SIMPLIFY / DEPRECATE.

---

# REVIEW 7 – Pipeline architecture

## Hypothesis

The source → normalization → reduction → storage pipeline may be more general than current needs justify.

## Inspect

Trace one real input through the entire pipeline.

Document every transformation.

Ask:

- Which stages materially change the data?
- Which stages only rearrange structures?
- Which stages protect correctness?
- Which abstractions currently have only one implementation?

## Alternative

Evaluate a simpler flow:

`provider → semantic inspector → observation`

with optional persistence afterward.

## Constraint

Do not remove the pipeline until at least one full replacement path is demonstrated.

---

# REVIEW 8 – Source model versus Capability model

## Hypothesis

The current `SourceDescriptor` model may reflect passive evidence collection better than interactive agent debugging.

## Compare

Source-oriented:

- source family,
- persistence,
- parser,
- trigger.

Capability-oriented:

- operation,
- requires_halt,
- mutates_target,
- backend/provider,
- safety class.

Potential examples:

- `peripheral.inspect`
- `core.inspect`
- `fault.inspect`
- `interrupt.inspect`
- `target.continue`
- `target.breakpoint`.

## Experiment

Model only three existing operations as capabilities.

Do not migrate everything.

Assess whether this improves the public API and internal routing.

---

# REVIEW 9 – Safety architecture

## Hypothesis

The current read-only model should evolve into explicit safety classes rather than simply being removed.

## Proposed classes to evaluate

### READ

Non-mutating observation.

### CONTROL

Changes execution state but not persistent target contents.

Examples:

- halt,
- continue,
- step,
- breakpoint.

### MUTATE

Changes target state or firmware.

Examples:

- register write,
- memory write,
- flash.

## Investigate

Map existing policies and protections.

Determine which controls should be:

- allowed by default,
- configurable,
- explicitly enabled,
- confirmation-gated,
- prohibited.

## Deliverable

A small capability policy model.

Avoid creating a complex security framework.

---

# REVIEW 10 – GDB/MI implementation

## Hypothesis

DebugOracle should probably not maintain a general-purpose GDB/MI parser and controller if gdb-mcp provides a superior implementation.

## Inspect

Evaluate current:

- MI parser,
- process/session management,
- edge-case handling,
- tests,
- supported MI constructs,
- platform assumptions.

## Compare with gdb-mcp

Test specifically:

`Codex → gdb-mcp → arm-none-eabi-gdb → OpenOCD → STM32`

Required tests:

- connect,
- source breakpoint,
- continue,
- breakpoint hit,
- step,
- locals,
- expression evaluation,
- backtrace,
- registers,
- memory,
- watchpoint if available,
- session persistence.

## Critical requirement

Do not decide based on README claims.

Run a real STM32 experiment.

## Possible outcomes

### gdb-mcp works well

Freeze/deprecate generic MI functionality.

### gdb-mcp is unsuitable for STM32

Keep current MI path and document exactly why.

### partial fit

Use gdb-mcp for generic source debugging while retaining narrowly scoped DebugOracle integration.

---

# REVIEW 11 – Transcript-based GDB workflow

## Hypothesis

Parsing GDB/Cortex-Debug transcripts may remain valuable for offline analysis but should not be the primary live-agent interface.

## Investigate

Identify current use cases:

- live debugging,
- replay,
- bug reports,
- CI artifacts,
- historic investigations.

## Decision candidate

Retain as:

`offline/replay importer`

rather than:

`primary debugging transport`.

Test whether any important use case would be lost.

---

# REVIEW 12 – LiveDebugBackend

## Hypothesis

DebugOracle should not build and maintain a large family of generic hardware backends.

## Inspect

Current interface and implementations.

Determine what higher-level DebugOracle code genuinely needs from a target provider.

Try to reduce the interface to primitives such as:

- read_memory,
- read_core_registers,
- target_state,
- optionally halt/resume.

## Compare

- current backend,
- embedded-debugger-mcp,
- probe-rs,
- OpenOCD,
- GDB.

## Desired result

A thin provider boundary underneath semantic features.

---

# REVIEW 13 – embedded-debugger-mcp integration

## Hypothesis

embedded-debugger-mcp may be useful as a commodity hardware-control provider rather than something DebugOracle should duplicate.

## Test

Evaluate:

- probe discovery,
- connect,
- halt,
- resume,
- reset,
- memory read,
- register access,
- flash,
- RTT,
- fault diagnosis.

Assess:

- stability,
- response structure,
- performance,
- MCP integration overhead,
- compatibility with current targets.

## Decision

Possible:

- use directly as external tool,
- wrap selectively,
- borrow architecture only,
- integrate probe-rs directly,
- reject.

---

# REVIEW 14 – probe-rs

## Hypothesis

Direct probe-rs integration could eventually provide a cleaner embedded hardware backend than GDB/OpenOCD for some functionality.

## Evaluate

Do not implement first.

Determine:

- supported STM32 targets,
- ST-Link support,
- RTT,
- flash,
- breakpoint support,
- memory access,
- register access,
- debugging APIs,
- SVD/device metadata,
- Rust/Python integration cost.

Only build a proof of concept if embedded-debugger-mcp integration demonstrates clear benefit.

---

# REVIEW 15 – RTT

## Hypothesis

RTT data is valuable; RTT transport itself may be commodity infrastructure.

## Inspect

Current RTT:

- process management,
- discovery,
- buffering,
- parsing,
- lifecycle,
- tests.

## Compare

- probe-rs RTT,
- embedded-debugger-mcp RTT,
- current implementation.

## Separate

### Transport

How bytes are obtained.

### Semantics

How logs become useful debugging evidence.

DebugOracle may need the second without owning the first.

---

# REVIEW 16 – Cortex-M semantics

## Hypothesis

This should be a major DebugOracle capability.

## Required semantic model

Investigate:

- SCB,
- xPSR/IPSR,
- VTOR,
- exception state,
- system handlers,
- core registers.

Possible interface:

`inspect core`

Do not expose unnecessary raw architecture data unless useful.

---

# REVIEW 17 – Fault analysis

## Hypothesis

Fault interpretation is high-value embedded-specific functionality.

## Support target

- HardFault,
- MemManage,
- BusFault,
- UsageFault,
- relevant fault status registers,
- BFAR,
- MMFAR,
- exception stack frame,
- faulting PC,
- source mapping where available.

## Compare

embedded-debugger-mcp's existing `diagnose_fault` and exception-unwind capabilities.

Determine what DebugOracle can add semantically rather than duplicating them.

Possible differentiation:

- correlate fault with SVD state,
- correlate fault with current task,
- correlate fault with source and recent logs.

---

# REVIEW 18 – NVIC and interrupt semantics

## Hypothesis

Interrupt semantics are high-value and poorly represented by generic GDB tools.

## Minimum capabilities

`interrupts`

returning:

- IRQ name,
- enabled,
- pending,
- active,
- priority.

`inspect TIM1_UP`

returning relevant interrupt state.

## Integration

Use:

- NVIC registers,
- SVD interrupt mappings,
- vector table,
- Cortex-M state.

## Experiment

Implement this for one STM32 family first.

---

# REVIEW 19 – Peripheral-specific semantic inspectors

## Hypothesis

Generic SVD inspection may be sufficient for many cases; custom peripheral intelligence should only be added where it materially improves diagnosis.

Do NOT immediately build:

- `inspect_timer`,
- `inspect_dma`,
- `inspect_uart`,
- `inspect_spi`,
- etc.

First test generic SVD.

Only add specialized inspectors where they provide reasoning beyond field decoding.

Example justified specialization:

`inspect DMA1_CH3`

could summarize:

- enabled,
- direction,
- source/destination,
- transfer count,
- error flags,
- corresponding interrupt.

---

# REVIEW 20 – FreeRTOS semantics

## Hypothesis

RTOS semantic state may become one of the strongest DebugOracle capabilities but should come after SVD/Cortex-M fundamentals.

## Investigate existing options

Before implementation inspect:

- GDB FreeRTOS awareness,
- OpenOCD RTOS support,
- probe-rs RTOS capabilities,
- FreeRTOS kernel-aware tools.

## Desired minimum

`tasks`

showing:

- task name,
- state,
- priority,
- stack information.

Then:

`inspect MotorTask`

Potential future:

- queues,
- semaphores,
- mutexes,
- event groups,
- blocking relationships.

Do not implement full RTOS analysis in first iteration.

---

# REVIEW 21 – Snapshot

## Hypothesis

A compact semantic snapshot may be the most valuable agent-facing operation.

## Goal

One operation:

`snapshot`

should answer:

> What is important about the target right now?

Potential contents:

- target,
- halt reason,
- source location,
- core state,
- fault state,
- relevant interrupts,
- relevant peripherals,
- current RTOS task,
- recent important logs.

## Critical constraint

Snapshot must NOT mean:

> dump everything.

It should be token-conscious and semantically reduced.

## Experiment

Implement a manually scoped snapshot before designing automatic relevance algorithms.

---

# REVIEW 22 – Context reduction

## Hypothesis

DebugOracle can add significant value by reducing raw hardware state into agent-appropriate evidence.

## Compare

### Bad

Thousands of registers and entire manuals.

### Better

A small number of relevant semantic observations.

Evaluate:

- output size,
- information density,
- debugging success,
- agent tool-call count.

Do not introduce embeddings/LLM selection inside DebugOracle without demonstrated need.

---

# REVIEW 23 – Vendor documentation

## Hypothesis

Vendor documentation is valuable but PDF ingestion/search may not belong in the DebugOracle core.

## Inspect

Current:

- ingestion,
- indexing,
- search,
- optional dependencies,
- sidecars,
- CLI complexity,
- test burden.

## Separate capability

`knowledge.lookup`

from implementation.

Possible providers:

- current local implementation,
- external RAG,
- coding-agent search,
- user-provided docs.

## Decision

KEEP / EXTERNALIZE / SIMPLIFY.

Do not delete the current implementation before determining whether it offers unique embedded-specific value.

---

# REVIEW 24 – Build orchestration

## Hypothesis

DebugOracle should not become a build-system abstraction layer.

## Evaluate desired UX

A coding agent already has shell access.

Determine whether DebugOracle adds anything by wrapping:

- CMake,
- Ninja,
- Make,
- west,
- PlatformIO,
- ESP-IDF,
- STM32Cube tooling.

Likely decision:

leave project building to the coding agent.

Only retain build awareness if it is needed to locate ELF/SVD/debug artifacts.

---

# REVIEW 25 – Flash

## Hypothesis

Flashing is useful but commodity.

Compare:

- current implementation,
- OpenOCD,
- probe-rs,
- embedded-debugger-mcp,
- STM32CubeProgrammer.

DebugOracle should probably invoke rather than implement flashing.

---

# REVIEW 26 – CLI

## Hypothesis

The current CLI exposes too much setup and implementation detail for the desired agent-facing product.

## Audit

List every current command.

Classify:

- user-facing essential,
- agent-facing essential,
- setup/debugging command,
- legacy,
- internal.

## Desired future public surface

Evaluate whether a small API such as this is enough:

- `status`
- `inspect`
- `snapshot`
- `fault`
- `interrupts`
- `tasks`

Execution commands may remain in external debugger tooling.

Do not remove commands until their use is understood.

---

# REVIEW 27 – MCP interface

## Hypothesis

If coding agents become the main consumer, MCP may eventually be more appropriate than a large CLI.

Do not build MCP immediately.

First stabilize semantic operations.

Then map only high-value operations to MCP.

Avoid exposing one MCP tool for every internal function.

Prefer a small semantic surface.

---

# REVIEW 28 – Agent / Skill boundary

## Hypothesis

DebugOracle should provide evidence and semantic operations, while Codex/Claude performs hypothesis generation and experiment planning.

DebugOracle core should not own:

- autonomous reasoning loops,
- hypothesis scoring,
- agent memory,
- source-code editing strategy,
- general debugging plans.

A DebugOracle skill may teach the agent:

- when to inspect peripherals,
- when to inspect interrupts,
- when to inspect faults,
- how to correlate evidence.

Keep agent policy separate from hardware semantics.

---

# REVIEW 29 – Existing renderers

## Hypothesis

Multiple rendering paths may be unnecessary for an agent-first tool.

Evaluate which outputs are actually needed.

Likely minimum:

- structured JSON,
- concise human CLI output.

Preserve richer reports only if users actively benefit from them.

---

# REVIEW 30 – Tests and quality gates

Do not reduce test quality during simplification.

Classify current tests:

- core behavior,
- compatibility,
- obsolete architecture,
- parsing,
- integration,
- hardware.

For new semantic features require deterministic tests wherever possible.

## SVD

Use known SVD + known fake memory values.

## Cortex-M

Use synthetic register snapshots.

## NVIC

Use known bitmaps.

## Faults

Use synthetic fault register combinations.

## FreeRTOS

Use captured/synthetic kernel structures.

## Hardware

Add a small STM32 hardware-in-the-loop path when justified.

Prefer one known Nucleo target initially.

---

# 8. Required external-project evaluation

Maintain a comparison matrix for:

## gdb-mcp

Primary question:

> Can it reliably provide source-level STM32 debugging through arm-none-eabi-gdb + OpenOCD?

## embedded-debugger-mcp

Primary question:

> Can it reliably provide generic MCU/probe/debug primitives that DebugOracle should not duplicate?

## probe-rs

Primary question:

> Does direct integration eventually offer enough benefit to justify an additional implementation language/runtime boundary?

## LUXAR

Use mainly as product/workflow reference.

Do not adopt its agent architecture unless a concrete DebugOracle requirement justifies it.

---

# 9. No replacement without a replacement test

Before removing a subsystem, execute an equivalent real-world task through the proposed replacement.

Example:

Before removing GDB/MI support:

1. launch STM32 target,
2. connect through replacement,
3. set breakpoint,
4. continue,
5. hit breakpoint,
6. inspect locals,
7. evaluate expression,
8. obtain backtrace,
9. read registers,
10. repeat reliably.

Record result.

Only then make a migration decision.

---

# 10. Preferred implementation strategy

Use vertical slices.

Each slice should result in one independently useful improvement.

Example sequence:

## Slice 1

`inspect TIM1.CR1`

## Slice 2

`inspect TIM1`

## Slice 3

`interrupts`

## Slice 4

`inspect TIM1_UP`

## Slice 5

`fault`

## Slice 6

minimal `snapshot`

## Slice 7

external GDB backend experiment

## Slice 8

RTOS task inspection

Do not start Slice N+1 merely because Slice N exists.

Reassess after each one.

---

# 11. First concrete milestone

The first product experiment should be intentionally small.

Target:

> Demonstrate that DebugOracle can give Codex substantially better understanding of one real STM32 peripheral than raw GDB/OpenOCD can.

Implement:

`dbgoracle inspect TIM1`

for one target.

Output should include:

- detected target,
- peripheral base,
- register names,
- raw register values,
- decoded bitfields,
- enum meanings,
- access metadata where useful,
- target-state/freshness metadata,
- concise human explanation.

Then compare debugging with:

### A

Codex + raw GDB/OpenOCD.

### B

Codex + semantic DebugOracle output.

Record whether DebugOracle:

- requires fewer tool calls,
- requires less register-manual lookup,
- uses fewer tokens,
- reaches the correct interpretation more reliably.

Only if this is clearly useful should SVD semantics become the new core direction.

---

# 12. Second concrete milestone

Test external GDB control.

Connect:

`Codex → gdb-mcp → arm-none-eabi-gdb → OpenOCD → STM32`

Run a representative debugging scenario.

If successful, determine which current DebugOracle GDB components become redundant.

Do not remove them yet.

Mark them for deprecation.

---

# 13. Third concrete milestone

Combine the two worlds.

Example debugging question:

> Why is TIM1 interrupt not executing?

Agent obtains:

- source-level state from GDB,
- TIM1 semantic state from DebugOracle,
- NVIC semantic state from DebugOracle.

Success criterion:

The combined workflow is clearly more useful than either tool alone.

This validates DebugOracle's intended architectural position.

---

# 14. Architecture target to test

Do not implement this wholesale.

Use it as a reference architecture whose assumptions must be validated:

```text
                    Coding Agent
                         |
        +----------------+----------------+
        |                |                |
        v                v                v
      gdb-mcp        DebugOracle         shell
        |                |                |
        |          semantic layer         |
        |                |                |
        |       +--------+--------+       |
        |       |        |        |       |
        |      SVD    Cortex-M   RTOS     |
        |       |        |        |       |
        |       +--------+--------+       |
        |                |                |
        |         target provider         |
        |                |                |
        +----------------+----------------+
                         |
                        MCU
```

Possible provider implementations may include:

- embedded-debugger-mcp,
- OpenOCD,
- GDB,
- probe-rs.

The semantic layer should not depend unnecessarily on one transport.

---

# 15. Potential future DebugOracle core

Again, treat as a hypothesis.

```text
debugoracle/
├── inspect/
├── semantics/
│   ├── svd/
│   ├── cortex_m/
│   └── rtos/
├── providers/
├── context/
└── policy/
```

Do not reorganize the repository into this shape until individual reviews justify it.

Architecture follows validated capabilities, not the reverse.

---

# 16. Deletion policy

Deleting code is explicitly allowed.

A subsystem should be considered for deletion when:

- its problem is no longer relevant,
- a maintained external solution clearly performs the function better,
- the replacement has been validated,
- retaining both causes meaningful maintenance burden,
- the compatibility value is low.

When deleting:

1. identify behavior being removed,
2. identify replacement or reason it is unnecessary,
3. preserve relevant tests where applicable,
4. document migration,
5. remove dead configuration/docs,
6. avoid leaving duplicate architectures indefinitely.

---

# 17. Preservation policy

Existing code should be protected when:

- it contains domain-specific Embedded Engineering knowledge,
- it provides correctness guarantees unavailable elsewhere,
- it is well tested,
- external alternatives are weaker,
- replacing it adds dependency risk without meaningful user benefit.

Do not replace good code merely to reduce LOC.

---

# 18. Decision quality standard

Avoid statements such as:

- "this feels cleaner,"
- "this is more modern,"
- "MCP is better,"
- "Rust is better,"
- "probe-rs already does it,"
- "the current code is complicated."

Instead use statements such as:

> The existing MI implementation requires X LOC and Y tests, while gdb-mcp successfully performed the same seven STM32 operations in the hardware test. DebugOracle-specific callers only require A and B. Therefore REPLACE is justified.

or:

> The current SVD parser handles STM32 derived registers correctly, while tested external library X does not. Therefore KEEP + EXTEND is justified.

---

# 19. Ongoing architectural scorecard

After every review, update:

| Area | Current decision | Confidence | Replacement validated? | Action |
|---|---|---:|---:|---|
| SVD | | | | |
| Provenance | | | | |
| Freshness | | | | |
| InvestigationArtifact | | | | |
| Pipeline | | | | |
| Source model | | | | |
| Safety | | | | |
| GDB/MI | | | | |
| Transcript import | | | | |
| Live backend | | | | |
| RTT | | | | |
| Cortex-M | | | | |
| Faults | | | | |
| NVIC | | | | |
| FreeRTOS | | | | |
| Snapshot | | | | |
| Vendor docs | | | | |
| CLI | | | | |
| MCP | | | | |
| Agent skill | | | | |

Confidence:

- LOW
- MEDIUM
- HIGH

No architectural rewrite should be scheduled from a LOW-confidence decision.

---

# 20. Final objective

The review is successful if DebugOracle becomes **smaller in conceptual scope while more valuable during real embedded debugging**.

A desirable outcome could be:

DebugOracle does fewer things,

but the things it does are difficult to reproduce with generic coding-agent tooling.

The strongest candidate identity to test is:

> DebugOracle is a semantic embedded-debugging layer that gives coding agents meaningful access to MCU peripherals, Cortex-M state, interrupts, faults, RTOS state, and temporally consistent hardware context.

Whether that ultimately becomes the product direction must be demonstrated through the incremental experiments above rather than assumed.