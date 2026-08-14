# Cloud runtime runbook

This runbook is the operational sequence for a long-running campaign whose canonical
state is stored in cloud-native JSON documents (for example Google Docs).

The runtime code is authoritative for state semantics. Project/system GM rules remain
a higher-level policy layer: the persistence runtime must never grant the GM authority
over the player character that the campaign rules prohibit.

## 1. Fresh-chat bootstrap

Do **not** begin fiction until bootstrap returns READY.

```text
read committed manifest
        ↓
read stable transaction journal declared by manifest
        ↓
read exact canonical document IDs from manifest
        ↓
cloud bootstrap gate
  ├─ journal IDLE → schema + semantic preflight
  ├─ journal PREPARED → crash recovery first
  └─ routing/hash/integrity conflict → BLOCKED
        ↓
READY
        ↓
assemble hot context
```

Minimum canonical documents:

- manifest;
- HEAD;
- active PC state;
- NPC state;
- thread/world-process state;
- fact/divergence register;
- append-only event log.

Never use Drive filename search as the primary source of truth once stable document IDs
are known. IDs in the committed manifest win over duplicate names.

## 2. Recovery gate

A `PREPARED` journal means the previous process may have stopped mid-save. **Do not
narrate another turn while recovery is pending.**

For each document in the envelope compare a fresh canonical-content hash with:

- `before_sha256` → write did not land;
- `after_sha256` → intended write already landed;
- neither → `UNEXPECTED`, automatic recovery is blocked.

Safe outcomes:

- all BEFORE → write the full recorded sequence;
- prefix AFTER + suffix BEFORE, manifest BEFORE → write only the suffix;
- all AFTER → canonical commit completed; clear stale journal only.

Unsafe outcomes:

- any UNEXPECTED content;
- manifest AFTER while an earlier canonical write is BEFORE;
- wrong document ID/routing;
- malformed/corrupted envelope.

In unsafe cases preserve evidence and require explicit inspection. Never "repair" by
blindly overwriting a human edit.

## 3. Context assembly

Start with structured state, not transcript search.

Hot context should normally include:

1. HEAD/current scene;
2. active PC state and PC epistemic buckets;
3. present NPC records;
4. active thread/world-process records;
5. deterministically ranked relevant facts;
6. OOC-only facts in a separate view when required.

Actor views use stable fact IDs and keep these categories separate:

- `knows`;
- `suspects`;
- `believes`;
- `remembers`.

`ooc` means the human user saw the information; it does **not** mean the player
character knows it.

Archive retrieval is cold fallback. Follow provenance/source refs to the relevant old
scene only when hot/warm structured state is insufficient. Retconned audit archives are
never a source of current truth or actor knowledge.

## 4. Deterministic resolution

When a result requires randomness, use runtime RNG (normally `SystemRandom`), not the
LLM's choice. Use a seed only for tests/replay.

The deterministic result is resolved first; the LLM interprets/narrates that result
second.

The same principle applies to world ticks and off-screen goals: mechanics determine the
outcome before prose explains it.

## 5. Preparing a durable turn

Not every response requires a save. Save only when durable campaign state changes.

For a durable turn:

1. begin from the freshly bootstrapped canonical documents;
2. construct proposed post-turn documents in memory;
3. validate JSON Schemas;
4. run cross-document semantic integrity;
5. diff BEFORE vs AFTER;
6. create the immutable mutation event;
7. append the event and advance HEAD/manifest pointers in the transaction projection;
8. run post-event preflight;
9. determine the changed document set;
10. build the save envelope using fresh provider revisions.

The LLM may propose meaning. The runtime validates and records the durable state change.

## 6. Cloud commit protocol

Order is part of correctness.

```text
A. write journal = PREPARED envelope
B. write changed canonical documents in runtime write order
C. write manifest LAST  ← commit pointer
D. fresh readback
E. if committed, clear journal = IDLE
F. preflight/readback verification
```

Current default canonical order:

```text
active_state
npc_state
thread_state
facts
event_log
head
manifest
```

Only changed documents are written, while preserving this relative order. Every native
Google Docs mutation uses the fresh `requiredRevisionId` obtained before that write.

`runtime/google_docs.py` can build full-document replacement requests from paragraph end
indexes returned by a Docs read.

## 7. Checkpoints

Provider revision history is not the checkpoint system.

Create an explicit hashed checkpoint:

- before destructive migration/retcon;
- at important scene/session boundaries;
- according to campaign policy (for example scene boundary or several meaningful turns).

Checkpoint verification hashes canonical logical JSON, not Google Docs formatting.

## 8. Retcons

A retcon is a dependency operation, not a new contradictory note.

Before applying a destructive retcon:

1. verify/create checkpoint;
2. identify target fact/event IDs;
3. calculate dependent fact/event/thread/goal impacts;
4. remove invalid fact IDs from PC/NPC epistemic buckets;
5. mark relationship basis that now requires rebuild;
6. route HEAD away from invalidated threads when needed;
7. append an immutable retcon/invalidation event;
8. run full preflight;
9. commit through the normal journal-first / manifest-last protocol.

Never resurrect material from a retconned audit archive unless a later explicit canon
operation re-establishes it.

## 9. Failure policy

Fail closed on state integrity, not on fiction creativity.

- malformed JSON → stop state mutation;
- schema error → stop state mutation;
- missing/duplicate IDs → stop state mutation;
- knowledge-scope contradiction → stop state mutation;
- stale provider revision → re-read and re-plan, do not force write;
- unexpected recovery hash → block automatic recovery;
- archive ambiguity → retrieve the exact source before asserting canon.

A failed save/recovery must not be papered over by continuing narration as though the
write succeeded.
