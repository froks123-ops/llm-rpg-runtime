# Cloud mode

Cloud mode targets environments where the LLM can call storage and Python-like tools but cannot depend on a permanently running local service.

Recommended campaign storage layout:

```text
00_MANIFEST
01_HEAD
02_ACTIVE_STATE
03_NPC_STATE
04_THREADS_CLOCKS
05_FACTS_DIVERGENCE
06_EVENT_LOG
07_CHECKPOINTS/
08_ARCHIVE/
```

## Retrieval policy

1. Bootstrap from the manifest and HEAD.
2. Load only present NPC records and active threads.
3. Load fact records relevant to those entities and the current scene.
4. Search archive only when active state/provenance indicates older detail is required.
5. Never use a retconned/superseded event as a source of current NPC knowledge or consequences.

## Save policy

- validate state before write;
- diff previous and proposed state;
- append meaningful changes to the event log;
- use optimistic concurrency when available;
- checkpoint at scene/session boundaries and before destructive migrations.
