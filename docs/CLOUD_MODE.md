# Cloud mode

Cloud mode targets environments where the LLM can call persistent-storage tools but cannot depend on a permanently running local daemon.

Recommended logical layout:

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
09_CONTEXT_PACK_DEBUG
10_SAVE_JOURNAL
```

## Read policy

1. Read the last committed manifest.
2. Resolve the manifest's stable `transaction_journal_id`.
3. Read the journal before entering normal play.
4. If `PREPARED`, assess recovery from fresh provider reads; roll forward only recorded BEFORE documents, never overwrite unexpected third content.
5. Once the journal is `IDLE`, assemble exact canonical document routing from manifest IDs.
6. Run schema + semantic preflight.
7. Fetch/assemble present NPCs, active threads and relevant facts under the deterministic budget.
8. Follow provenance into archive only when current state is insufficient.
9. Never use retconned/superseded facts as current truth or actor knowledge.

## Save policy

1. read fresh provider revisions;
2. prepare the entire post-turn transaction in memory;
3. run JSON Schema validation;
4. run semantic integrity/preflight;
5. compute diff and mutation event;
6. for destructive changes, create/verify a checkpoint first;
7. build a save envelope containing document IDs, base revisions, BEFORE/AFTER hashes and intended AFTER content;
8. write the stable transaction journal as `PREPARED`;
9. write changed canonical documents with `requiredRevisionId`/equivalent;
10. write event log and HEAD when changed;
11. write manifest **last**;
12. read back the committed state;
13. clear the journal to `IDLE`;
14. run preflight again.

### Crash recovery

A fresh process never guesses whether a partial save completed. `runtime/cloud_documents.py` classifies each envelope document from fresh reads:

- `BEFORE` — write did not land;
- `AFTER` — intended write already landed;
- `UNEXPECTED` — neither recorded hash; automatic recovery stops.

If a mix of BEFORE/AFTER exists while manifest is BEFORE, recovery writes only the remaining BEFORE documents in original order. If every document is AFTER but the journal is still PREPARED, the commit succeeded and only the stale journal is cleared. If the manifest is AFTER while an earlier document is BEFORE, recovery blocks because the commit pointer advanced out of order.

## Google Drive note

Native Google Docs can be used as persistent JSON containers when the ChatGPT connector cannot upload arbitrary local JSON files. `runtime/cloud_documents.py` reconstructs JSON from paragraph-oriented reads and treats Google Docs revision IDs as optimistic-concurrency tokens.

This protocol has been exercised against real Google Docs with an intentional crash after the first canonical write: recovery detected `active_state=AFTER`, `manifest=BEFORE`, wrote only the manifest, recognized `COMMITTED`, and then cleared the journal to `IDLE`.

`runtime/google_docs.py` converts `get_document_text` paragraph metadata into the two raw Docs operations required for an in-place full JSON replacement (`deleteContentRange`, then `insertText`). The caller still supplies the fresh provider `requiredRevisionId`; request planning never weakens optimistic concurrency.

A second real-provider test prepared a transaction and then changed one canonical document to a third, unrecorded value. Recovery classified it as `UNEXPECTED`, returned `BLOCKED`, and produced zero write intents.

## Context budget and fallback

Cloud mode should prefer stable IDs and structured routing over broad Drive search. When a scene needs older narrative detail, follow provenance/source refs into `08_ARCHIVE/` and retrieve only the pointed scene/chapter. Exact/keyword Drive search is a fallback; it is not treated as a semantic source of canonical truth.
