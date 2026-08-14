# Changelog

## 0.3.0

### Added

- provider-neutral cloud-native JSON document parser and revision receipts;
- persistent multi-document save envelopes with BEFORE/AFTER hashes and target content;
- stable transaction journal with `IDLE` / `PREPARED` states;
- fail-closed roll-forward recovery for interrupted cloud saves;
- cloud bootstrap orchestrator that gates normal play behind routing, recovery and preflight;
- transaction journal routing in campaign manifest schema;
- real Google Drive partial-write recovery verification in an isolated test campaign;
- pure Google Docs full-replacement request planner using paragraph end indexes;
- full turn-commit → event → preflight → save-envelope regression across every crash boundary;
- cloud runtime operational runbook for fresh-chat bootstrap, recovery, save and retcon procedures.

### Changed

- cloud save contract is now journal-first and manifest-last;
- a stale prepared journal after a completed commit is cleared without rewriting canonical documents;
- unexpected concurrent/external document content blocks automatic recovery.

## 0.2.0

### Added

- stable fact-ID epistemic model for `knows / suspects / believes / remembers`;
- `known_by` token grammar for player-character, OOC, NPC and faction-scoped retrieval hints;
- fact lifecycle helpers with guarded singleton-state supersession;
- deterministic retcon cascade through fact dependencies;
- cross-document retcon planning for NPC knowledge, threads, events and relationship rebuild flags;
- append-only event helpers with fact/event dependency invalidation;
- checkpoint hashing and tamper verification;
- campaign-level transactions with schema validation, mutation events, event-log append, manifest sequence update and HEAD pointer update;
- cross-document campaign integrity auditor;
- storage-agnostic optimistic-concurrency write intents with manifest-last ordering;
- campaign preflight report;
- expanded deterministic RNG (`dice`, advantage/disadvantage, chance, sample);
- GitHub CI workflow and permanent ZIP updater workflow;
- schemas for manifest, HEAD, active PC state, threads, event log and checkpoint manifests;
- conservative AI Studio exporter/importer with explicit canonical/retconned chunk ranges;
- deterministic fact ranking/budget and explicit cold-fact requests for context assembly.

### Changed

- context assembly now returns separate `gm_truth`, `player_epistemic_view`, compatibility `player_view`, `ooc_view` and per-NPC epistemic views;
- actor views intentionally omit truth metadata and provenance;
- PC/NPC knowledge examples now reference stable fact IDs rather than free-text statements;
- world ticks route randomness through the central RNG module and skip inactive goals without consuming RNG;
- retcons now clean invalid fact references from PC epistemic state as well as NPC state and route HEAD away from invalidated threads.

### Compatibility

- v0.1 fact lifecycle value `canonical` remains accepted as an active fact during migration.
