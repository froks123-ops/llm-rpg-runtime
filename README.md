# llm-rpg-runtime

> **Status: early alpha / v0.4.0**

A deterministic support layer for long-running LLM-as-GM RPG campaigns.

The core premise is simple: **the LLM may narrate and judge fiction, but it must not be the only source of randomness, persistent state, NPC knowledge, retcons, or long-term continuity.**

## Current runtime surface

| Area | Module | Purpose |
|---|---|---|
| RNG | `runtime/rng.py` | `SystemRandom` at runtime; seeded replay/testing; dice/chance/weighted choice |
| Shape validation | `runtime/state_validate.py` | JSON Schema Draft 2020-12 validation |
| Semantic integrity | `runtime/integrity.py` | cross-document IDs, lifecycle, HEAD, thread, event and knowledge checks |
| State audit | `runtime/state_diff.py` | dependency-free structured diffs |
| Facts | `runtime/facts.py` | active lifecycle, state-slot supersession, retcon cascade |
| Knowledge | `runtime/knowledge.py` | PC/NPC/faction scopes, separate OOC scope and epistemic buckets |
| Context | `runtime/context_assembler.py` | ranked/budgeted GM truth, PC epistemics, OOC view and per-NPC views |
| Events | `runtime/events.py` | append-only mutation/provenance records and invalidation |
| Retcons | `runtime/retcon.py` | cross-document impact plan |
| Checkpoints | `runtime/checkpoint.py` | deterministic snapshot hashes and tamper verification |
| Transactions | `runtime/transaction.py` + `campaign_transaction.py` | validate → diff → event → integrity plan |
| Persistence | `runtime/persistence.py` | optimistic-concurrency write intents, manifest last |
| Preflight | `runtime/preflight.py` | one-shot campaign readiness audit |
| World simulation | `runtime/world_tick.py` | deterministic off-screen goal resolution |
| Cloud documents | `runtime/cloud_documents.py` | native-document JSON parsing, save envelopes and roll-forward recovery |
| Cloud bootstrap | `runtime/cloud_bootstrap.py` | journal gate → recovery decision → semantic preflight |
| Output contract | `runtime/output_contract.py` | structural Raport → header → narrative → footer validation and debug-leak warnings |

## Architecture

```text
                       GM / LLM
                          |
                   Context Assembler
                /          |          \
           GM truth    PC view    OOC/meta    NPC views
                \         |         |         /
                  epistemic firewall
                          |
                 deterministic layer
           /        /        |         \
         RNG   world ticks  schema   integrity
                          \    |    /
                         state diff
                             |
                        event record
                             |
                     persistence plan
          state docs -> event log -> HEAD -> MANIFEST
```

Cloud saves use a persistent transaction journal plus a manifest commit pointer. The adapter writes `journal=PREPARED` first, canonical documents next, the manifest **last**, then clears the journal to `IDLE`. Storage adapters use provider revision IDs for optimistic concurrency. A fresh bootstrap refuses normal play while a prepared journal still needs recovery.

## Epistemics

NPC and PC state reference **stable fact IDs**, not copied prose:

```json
{
  "knowledge": {
    "knows": ["fact.scout.missing"],
    "suspects": ["fact.road.unsafe-rumor"],
    "believes": [],
    "remembers": []
  }
}
```

A fact may be true, false, unknown or subjective from the GM perspective. NPC/PC context strips that truth metadata so the model cannot casually leak omniscient provenance into an actor's viewpoint.

`player` and `ooc` are deliberately different scopes:

- `player` = the player character can use the proposition in-character;
- `ooc` = the human user has been shown the proposition (for example an NPC internal monologue), but the player character does **not** gain that knowledge.

`active_state.knowledge` gives the PC the same epistemic buckets as NPCs. This allows the PC to believe or suspect something false without promoting that belief to GM truth.

## Context budget

`context_assembler.assemble()` does not load every active fact. It ranks candidate facts deterministically and applies a configurable budget (`max_facts`, default `36`). Explicitly requested fact IDs outrank the normal scene routing, followed by pinned/current-thread/current-scene/present-actor relevance. The retrieval trace exposes selected scores for debugging.

This keeps long campaigns selective without letting a semantic search engine decide canonical truth. Archive retrieval remains a fallback when the structured state points to older source material.

## Retcons

A retcon is a lifecycle operation, not another memory note. `plan_retcon()` can:

- mark targeted facts as retconned;
- cascade through `depends_on` facts;
- remove invalid fact IDs from NPC epistemic buckets;
- invalidate dependent active threads;
- invalidate fact-producing/dependent events and event chains;
- strip invalid relationship basis facts and mark those relationships `needs_rebuild`.

The runtime intentionally does **not** perform unsafe blind rollback of later aggregate values. Those are rebuilt from checkpoint/event history or corrected by an explicit transaction.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -e ".[dev]"
pytest
```

Normal RNG omits a seed:

```python
from runtime.rng import d100, roll_dice

percentile = d100()
attack = roll_dice("d20+7")
```

Seeded tests/replays are deterministic:

```python
assert d100(seed=123).value == d100(seed=123).value
```

## Crash-safe cloud bootstrap

Normal play is gated by a fail-closed startup sequence:

```text
manifest read
   ↓
exact canonical routing
   ↓
transaction journal
   ├─ IDLE → schema + semantic preflight → READY
   ├─ PREPARED + BEFORE/AFTER only → ROLL_FORWARD
   ├─ PREPARED + all AFTER → clear stale journal
   └─ unexpected third content / bad routing → BLOCKED
```

The recovery envelope stores before/after hashes plus intended after-content for changed documents. It never overwrites a value whose current hash is neither the recorded BEFORE nor AFTER state.

## Cloud target

Current target architecture:

```text
ChatGPT Project      -> GM constitution / policy
llm-rpg-runtime      -> deterministic state semantics
Google Drive         -> persistent campaign state and archive
GitHub               -> canonical runtime source
```

The repository does not contain private campaign data.

## Repository updates

From v0.2 onward the repository contains **Apply runtime update** in GitHub Actions. Future updates can be delivered as a single `runtime-update.zip`; the workflow applies only runtime-owned paths, commits the result and removes the ZIP.

## Tests

The suite covers RNG, schemas, knowledge silos, hidden facts, supersession, retcon cascades, event invalidation, checkpoints, semantic integrity, transactions, save ordering, cloud document parsing, persistent journal recovery, bootstrap gating, AI Studio import shapes and player-visible output structure. GitHub Actions runs the suite on Python 3.11 and 3.13.

## Design rules

1. No LLM-generated RNG when randomness matters.
2. Canonical structured state beats stale transcript text.
3. Shape validation and semantic integrity both run before persistence.
4. Durable changes are diffed and event-sourced for auditability.
5. NPC knowledge is explicit and actor-scoped.
6. Truth/provenance is separated from actor-visible context.
7. Retcons invalidate downstream dependencies instead of coexisting with them.
8. Full transcript is archive, not active source of truth.
9. Cloud writes use optimistic concurrency, persist a recovery journal first, and commit the manifest last.
10. A fresh process must resolve a prepared journal before normal play.
11. Destructive migrations/retcons require an explicit checkpoint first.
12. Normal narrative output follows the validated Raport → header → narrative → footer contract; persistence internals stay hidden.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`docs/STATE_MODEL.md`](docs/STATE_MODEL.md), [`docs/RETCONS.md`](docs/RETCONS.md), [`docs/CLOUD_MODE.md`](docs/CLOUD_MODE.md) the operational [`docs/CLOUD_RUNTIME_RUNBOOK.md`](docs/CLOUD_RUNTIME_RUNBOOK.md) and [`docs/OUTPUT_CONTRACT.md`](docs/OUTPUT_CONTRACT.md).

## Influences and licensing

See [`ATTRIBUTION.md`](ATTRIBUTION.md). This repository is MIT-licensed original code. No AGPL source code from `open-tabletop-gm` is incorporated.
