# Architecture

## Separation of responsibilities

The runtime separates concerns that are commonly collapsed into one giant prompt:

1. **GM policy** — agency rules, simulation principles and narrative constraints.
2. **Canonical state** — current world, PC/NPC, thread and fact projections.
3. **Epistemic state** — who knows, suspects, believes or remembers which proposition.
4. **Deterministic mechanics** — RNG, validation, diffs, world ticks and lifecycle rules.
5. **Event history** — why durable state changed.
6. **Archive retrieval** — older narrative loaded only when provenance/relevance requires it.

## Turn lifecycle

```text
player declaration
      |
read manifest + transaction journal + revisions
      |
recover interrupted save or fail closed
      |
identify present NPCs / active threads
      |
assemble GM truth + actor-scoped views
      |
resolve required deterministic mechanics
      |
LLM generates GM response
      |
extract proposed durable changes
      |
schema validation
      |
cross-document integrity
      |
state diff -> mutation event
      |
journal PREPARED
      |
write state docs -> event log -> HEAD -> manifest LAST
      |
journal IDLE
      |
readback + preflight
```

## Epistemic firewall

The context pack deliberately separates:

- `gm_truth` — active true/subjective facts needed to simulate the world;
- `player_epistemic_view` — PC `knows / suspects / believes / remembers` from `active_state`;
- `player_view` — compatibility view of PC-visible facts;
- `ooc_view` — facts shown to the human user but not known by the PC;
- `npc_views.<id>` — `knows / suspects / believes / remembers` for each present NPC.

NPC/player fact views omit GM truth status, dependencies and source provenance.

## Persistence contract

The runtime is storage-agnostic. A provider adapter supplies stable document IDs and revision tokens. Writes use optimistic concurrency.

Multi-document cloud saves use two durable control records:

1. a stable **transaction journal** containing the prepared roll-forward envelope;
2. the **manifest**, written last, as the commit pointer for the canonical snapshot.

The journal envelope records each changed document's ID, base revision, BEFORE hash, AFTER hash and intended AFTER content. On restart, recovery is automatic only when every fresh document matches one of those two hashes. Any third value is treated as a concurrent/external edit and blocks automatic writes.

Provider revision history is useful audit evidence but is not a substitute for explicit campaign checkpoints.

## Context ranking

Structured routing precedes archive search. Candidate facts are scored using deterministic signals: explicit request, pinning, active-thread linkage, current-scene provenance, present actors, PC-only relevance, explicit epistemic references and importance. Only the configured top budget enters the hot context.

This is intentionally not pure vector RAG. Semantic archive retrieval may locate source scenes, but structured canonical state decides which propositions are active and who may use them.
