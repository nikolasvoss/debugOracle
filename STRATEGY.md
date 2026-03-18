# DebugOracle Strategy

`GOAL.md` defines the north star; this document defines the strategic sequencing and product bets that should guide near- to mid-term decisions.

## Time Horizon
This strategy is intended to guide the next 6-12 months of product decisions.

## Strategic Bet
Trustworthy debug evidence plus safe live state creates more value now than premature reasoning or autonomy.

If DebugOracle becomes the trusted evidence and live-insight layer for root-cause acceleration, richer human- and agent-assisted reasoning can compound on top of that foundation.

## Product Position
DebugOracle should help engineers move from fragmented debug evidence and read-only target insight to a usable investigation artifact.

It should not try to win by acting like a complete debugging brain before the underlying evidence, provenance, and safety model are dependable.

## Strategic Priorities

### 1. Trustworthy Evidence Capture
Support the real workflows engineers already use and preserve the evidence needed to understand a failure without unnecessary loss or distortion.

### 2. Safe Live Reads
Treat bounded, read-only access to current target state as a first-class product capability alongside captured logs and snapshots.

### 3. Provenance And Freshness
Make it obvious where data came from, how current it is, and whether it reflects captured artifacts or live state.

### 4. Reproducible Investigation Artifacts
Produce investigation artifacts that are inspectable, auditable, and reusable for downstream reasoning, sharing, and evaluation.

### 5. Interfaces For Downstream Reasoning
Expose evidence in forms that are useful for both humans and agents without coupling the product to a single interface, workflow, or vendor.

## What This Strategy Does Not Require
- A mandatory unified timeline engine
- One fixed schema as the product identity
- Premature autonomous debugging loops
- Opaque reasoning layers that weaken auditability
- Write access or intrusive target interaction
- A GUI-first experience

Timeline and correlation features may still be valuable, but they should be treated as supporting capabilities, not as the core strategy.

## Near- To Mid-Term Capability Thresholds
1. Reliable ingestion from existing debug workflows
2. Bounded and safe live-read capability
3. Strong provenance and freshness guarantees
4. Reproducible investigation artifacts
5. Evaluation using real debug sessions and known failure cases

## Later Leverage
Once the evidence, live-read, and provenance layers are trustworthy, DebugOracle can support more ambitious reasoning layers and eventually move closer to an autonomous debugging agent.

That future remains in scope, but it should be earned by reliability and auditability rather than assumed up front.

## Strategic Risks
- Building impressive reasoning on weak or incomplete evidence
- Blurring captured artifacts with current live state
- Losing trust through hidden transformations or poor provenance
- Overfitting the product to one workflow, interface, or data source
- Locking the product to one vendor or reasoning surface too early

## Decision Filters
- Trust before autonomy
- Evidence quality before reasoning sophistication
- Live reads must remain bounded and safe
- Investigation artifacts must preserve provenance and reproducibility
- No feature should make the system harder to audit

## Near-Term Success
DebugOracle is succeeding in the near term if it reliably gathers, structures, and exposes trustworthy debug evidence and live insight for downstream reasoning.

Near-term success does not require correct root-cause identification, autonomous decision making, or a fully autonomous debugging agent.
