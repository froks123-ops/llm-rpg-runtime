# llm-rpg-runtime

> **Status: early alpha / v0.1.0**

A deterministic support layer for long-running LLM-as-GM RPG campaigns.

The runtime is designed around one premise: **the LLM should narrate and judge fiction, but it should not be trusted as the sole source of randomness, persistent state, NPC knowledge, or long-term continuity.**

## Goals

- keep player agency outside GM control;
- move randomness to deterministic tools;
- validate structured state before persistence;
- audit state mutations with structured diffs;
- scope NPC knowledge explicitly;
- assemble scene-local context instead of brute-forcing the full transcript;
- support off-screen world/NPC progression without making the LLM its own random-number generator;
- treat transcripts as archive, not as the canonical current state.

## v0.1 modules

| Module | Purpose |
|---|---|
| `runtime/rng.py` | `SystemRandom` by default; seeded RNG for reproducible tests |
| `runtime/state_validate.py` | JSON Schema Draft 2020-12 validation |
| `runtime/state_diff.py` | dependency-free structured state diff |
| `runtime/context_assembler.py` | scene-scoped NPC/thread/fact selection |
| `runtime/world_tick.py` | deterministic NPC/world goal resolution |

## Architecture

```text
            GM / LLM
               |
        Context Assembler
        /      |       \
      HEAD    STATE    FACTS
               |       known_by
               |
       deterministic layer
       /       |        \
     RNG    validation  world ticks
               |
            state diff
               |
        persistence adapter
```

The cloud-first target is ChatGPT Project + persistent storage (currently Google Drive). A later local mode is expected to add vector retrieval, richer diffing, automated regression tests, and a full filesystem-backed campaign store.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -e ".[dev]"
pytest
```

Example validation:

```python
from runtime.state_validate import validate_file

errors = validate_file(
    "examples/minimal/npc_state.json",
    "schemas/npc_state.schema.json",
)
assert errors == []
```

Seeded test RNG:

```python
from runtime.rng import d100

assert d100(seed=123).value == d100(seed=123).value
```

Normal runtime calls omit the seed and use `random.SystemRandom()`.

## Design rules

1. **No LLM-generated RNG when randomness matters.**
2. **Canonical structured state beats stale transcript text.**
3. **State is validated before persistence.**
4. **State mutations are diffed and auditable.**
5. **NPC knowledge is explicit and scoped.**
6. **Only scene-relevant context is loaded into the active GM payload.**
7. **Retcons/supersession must invalidate downstream knowledge and consequences, not merely add another sentence to memory.**
8. **The full transcript remains recoverable archive, not the active source of truth.**

## Roadmap

See [`docs/ROADMAP.md`](docs/ROADMAP.md). Near-term work focuses on a production-ready cloud mode, followed by optional local enhancements (`sqlite-vec`, richer deep diffs, semantic archive retrieval, regression/eval tooling).

## Influences and licensing

See [`ATTRIBUTION.md`](ATTRIBUTION.md). This repository is MIT-licensed original code. In particular, no AGPL code from `open-tabletop-gm` is incorporated.
