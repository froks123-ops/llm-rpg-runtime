# Retcons

Retcons are treated as destructive canonical operations.

## Required sequence

1. checkpoint current canonical state;
2. identify target fact/event IDs;
3. compute retcon impact without writing;
4. inspect missing targets and relationship rebuild flags;
5. validate the post-retcon projection;
6. write affected documents with optimistic concurrency;
7. append the retcon event;
8. update HEAD and manifest last;
9. read back and run preflight.

## Deterministic cascade

A retconned fact invalidates:

- itself;
- active facts that list it under `depends_on`;
- NPC knowledge references to those facts;
- active threads depending on those facts;
- events producing or depending on those facts;
- later events depending on invalidated events.

Relationship records citing invalidated fact IDs as evidence are stripped of that evidence and marked `needs_rebuild`.

## Why aggregate values are not blindly reversed

If trust changed 40 -> 60 because of event A, then later 60 -> 70 because of unrelated event B, simply applying A's inverse would incorrectly produce 40. Correct rollback requires replay from a known checkpoint or an explicit corrective transaction. The runtime therefore flags affected aggregates rather than pretending an unsafe inverse is canonical.
