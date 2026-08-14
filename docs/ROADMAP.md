# Roadmap

## v0.2 — state and integrity model — implemented

- stable fact IDs and epistemic buckets;
- truth versus belief separation;
- known-by scopes;
- guarded supersession;
- retcon cascade and cross-document impact planning;
- event dependencies;
- checkpoint hashing;
- campaign transaction planning;
- semantic preflight/integrity audit;
- optimistic-concurrency write ordering;
- GitHub CI and permanent ZIP updater.

## v0.3 — cloud campaign adapter — implemented

- native-document JSON reconstruction and fail-closed parsing;
- exact manifest routing + revision-aware document handles;
- persistent save envelope with BEFORE/AFTER hashes and intended target content;
- stable transaction journal (`IDLE` / `PREPARED`);
- roll-forward recovery after interrupted multi-document saves;
- cloud bootstrap gate: routing → journal recovery → schema/integrity preflight;
- real Google Drive partial-write/crash/recovery integration test;
- production Bleach AU shadow migration with journal-bound manifest/checkpoint.


Release verification includes a public scale fixture, full-write-order crash soak tests, a real Google Drive partial-write recovery, and a real external-edit blocking test.

## v0.4 — retrieval and archive expansion

- deterministic entity routing and fact budgets (core already implemented in v0.2);
- provenance-driven archive fallback;
- chapter/scene retrieval interface;
- knowledge-firewall regression evaluator;
- optional semantic candidate retrieval behind structured truth routing.

## v0.5 — world simulation

- goal lifecycle and cadence policy;
- off-screen heartbeat/timeskip;
- faction/world processes;
- conflict/collision handling;
- deterministic resolution with LLM interpretation after the result.

## v0.6 — evaluation

- agency regression suite;
- NPC knowledge-silo leakage tests;
- retcon/state-conflict tests;
- model-to-model comparison harness;
- optional Promptfoo integration.

## v1.0 — cloud production target

A campaign can resume in a fresh chat from manifest + persistent state + selective archive retrieval without the full prior transcript in active context.
