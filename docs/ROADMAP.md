# Roadmap

## v0.2 — state model

- schemas for manifest, HEAD, threads/clocks and event records;
- stable fact IDs in NPC knowledge rather than free-text facts;
- explicit retcon/supersession propagation;
- relationship schema;
- mutation/event provenance.

## v0.3 — cloud persistence

- Google Drive adapter;
- revision-aware writes;
- checkpoint creation/readback;
- append-only event log helper;
- campaign bootstrap from manifest.

## v0.4 — context assembler

- deterministic entity routing;
- knowledge firewall checks;
- provenance-driven archive fallback;
- context budgets and priority tiers.

## v0.5 — world simulation

- goal lifecycle;
- off-screen heartbeat/timeskip;
- faction/world clocks;
- collision/conflict handling;
- deterministic resolution with LLM interpretation after the result.

## v0.6 — evaluation

- agency regression tests;
- NPC knowledge-silo tests;
- retcon tests;
- state hallucination tests;
- model-to-model comparison harness.

## v1.0 — cloud production target

A campaign should be resumable in a fresh chat from manifest + persistent state + selective archive retrieval without requiring the full prior transcript in active context.
