# State model

## Canonical documents

A cloud campaign should expose these logical documents regardless of storage provider:

```text
manifest
head
active_state
npc_state
thread_state
facts
event_log
checkpoints/
archive/
```

`manifest` and `head` route retrieval. The remaining documents hold current projections and history.

## Facts versus beliefs

The fact ledger is a proposition registry. Each record has a lifecycle (`active`, `superseded`, `retconned`) and may have GM truth metadata:

- `true`
- `false`
- `unknown`
- `subjective`

PC (`active_state.knowledge`) and NPC epistemic state reference fact IDs through:

- `knows`
- `suspects`
- `believes`
- `remembers`

This lets an NPC believe a proposition that the GM knows is false without turning that belief into campaign truth.

## `known_by`

`known_by` is a compact retrieval/audience hint:

- omitted / `null` -> public;
- `[]` -> secret;
- `player` -> player-character/in-character knowledge;
- `ooc` -> shown to the human user, but not known by the player character;
- `npc:<id>` -> one NPC;
- `faction:<name>` -> members of a faction.

Explicit NPC epistemic buckets take precedence over inferred `known_by` routing.

## State slots

Facts that represent exactly one current value may use a `state_key`, for example:

```text
npc:seiji:location
item:yaku:holder
place:gate:controller
```

There must be at most one active fact in each slot. Replacement is guarded: only an exact state-key predecessor can be superseded automatically.

## Causality

`depends_on` means a proposition becomes invalid when any listed prerequisite is retconned. This is a hard dependency used for deterministic cascade invalidation.

## OOC/meta visibility

OOC visibility is not an epistemic bucket for the player character. It exists to support table conventions such as visible NPC internal monologues, cutaways or GM-only exposition that the human user may read while the PC remains ignorant. `ooc_view` must never be merged into `active_state.knowledge`.
