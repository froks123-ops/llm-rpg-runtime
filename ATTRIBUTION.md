# Attribution and design influences

`llm-rpg-runtime` is original code released under the MIT License. Its architecture was informed by public work in the LLM/TTRPG tooling ecosystem.

## Questforge

Repository: `adrianmelic/codex-questforge` — MIT License.

Ideas studied include portable campaign state, canonical manifests, checkpoint/save semantics, deterministic dice tooling, and separation between active state and session archives.

No Questforge source file is vendored in this repository.

## NarrativeEngine-P

Repository: `Sagesheep/NarrativeEngine-P` — MIT License.

Ideas studied include scoped NPC knowledge, witness tracking, divergence/supersession, context gathering, archive retrieval, NPC goals, and off-screen world progression.

No NarrativeEngine-P source file is vendored in this repository.

## open-tabletop-gm

Repository: `Bobby-Gray/open-tabletop-gm` — GNU Affero General Public License v3.0 or later.

The project was reviewed for high-level architectural ideas such as deterministic mechanical tooling and scene-scoped relationship/context retrieval. **No AGPL source code is copied, vendored, translated, or linked into this repository.** Any similar functionality here is an independent implementation from general architectural concepts.

## Future optional integrations

Potential future local-mode integrations such as DeepDiff, sqlite-vec, NetworkX, and Promptfoo remain external dependencies or development tools and are not vendored here.
