# Architecture

## Separation of responsibilities

The runtime separates four concerns that are often collapsed into one LLM prompt:

1. **GM policy** — agency rules, simulation principles, narrative constraints.
2. **Canonical state** — current world, character, NPC, thread, and fact state.
3. **Deterministic mechanics** — RNG, validation, diffs, world ticks.
4. **Archive retrieval** — only relevant historical material is brought back into active context.

## Turn lifecycle

```text
player declaration
      |
read HEAD + active state
      |
identify present NPCs / active threads
      |
assemble scoped context
      |
resolve required deterministic mechanics
      |
LLM generates GM response
      |
extract proposed durable state changes
      |
validate -> diff -> persist -> event log
```

## Knowledge isolation

NPC knowledge should be modeled explicitly rather than inferred from global campaign truth. The current schema supports four practical buckets:

- `knows`
- `suspects`
- `believes`
- `remembers`

Facts may also carry `known_by`, `witnesses`, provenance, and supersession metadata. Future versions should normalize these into stable fact IDs rather than free-text strings.

## Persistence

Cloud mode should use stable IDs and optimistic concurrency where the backend supports it. Google Docs/Drive can provide revision IDs for fail-fast writes. Campaign checkpoints should be explicit artifacts; provider revision history is not considered a sufficient checkpoint mechanism by itself.

## Local mode

Future local mode can add:

- filesystem/JSON canonical state;
- sqlite + sqlite-vec archive index;
- local embeddings;
- DeepDiff or equivalent;
- automated prompt/regression evaluation;
- richer relationship/knowledge graph queries.
