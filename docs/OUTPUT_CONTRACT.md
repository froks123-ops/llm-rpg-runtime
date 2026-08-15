# Player-visible output contract

Runtime v0.4 adds a deterministic structural validator for normal GM turns. The
validator protects the **shape** of player-visible output; it is not a replacement
for the campaign GM constitution, epistemic firewall, or semantic agency checks.

## Canonical order

Normal narrative turns use this order:

```text
1. Raport code block
2. scene header
3. narrative
4. technical footer
5. [>_]
```

The `Raport` is a protocol summary of completed checks, not chain-of-thought. It
may expose only player-safe information. Hidden facts remain redacted according to
the campaign's exposition gate.

### Report

The report is first and is fenced as `Raport`. It must end with:

```text
AGENCY TEST: PASS
LEAK TEST: PASS
```

Pure meta/OOG/bootstrap responses may omit the report when the caller explicitly
disables that requirement.

### Header

The first line after the report is inline code:

```text
``[Dzień <N> | Pora: <pora> | <lokacja> | <opcjonalna aura> | TRYB <n>: <NAZWA>]``
```

Both one- and two-backtick inline-code wrappers are accepted by the structural
validator for compatibility with existing campaign material.

### Narrative formatting

Dialogue:

```markdown
"Tekst dialogu."
```

Ordinary NPC thoughts, when exposition rules permit them:

```markdown
*Tekst myśli.*
```

An explicitly requested NPC monologue uses:

```markdown
---

**Monolog <NPC>**

*Treść monologu.*

---
```

The validator checks separators and an italicized monologue body when such a block
is present.

### Footer

The campaign constitution determines which state/RNG/canon lines are required in a
given turn. The final non-empty line is always:

```text
[>_]
```

Persistence implementation details such as provider revision IDs, transaction
journal IDs, schema dumps, PREPARED/ROLL_FORWARD recovery state, or raw Drive
routing must not appear in normal player-visible narration. The validator reports
known debug leaks as warnings.

## API

```python
from runtime.output_contract import validate_output

result = validate_output(text)
if not result.ok:
    for issue in result.errors:
        print(issue.code, issue.message)
```

For technical/bootstrap output:

```python
validate_output(
    text,
    require_report=False,
    require_header=False,
    require_footer=False,
)
```

`assert_valid_output()` is available for callers that prefer fail-fast behavior.

## Scope boundary

Structural validation can determine ordering, fences, header/footer presence,
report PASS markers, explicit monologue shape, and known persistence-debug leaks.
It cannot prove that prose preserved PC agency or that an NPC used only knowledge
available to that NPC. Those semantic guarantees remain enforced by project
instructions, structured epistemic context, and the campaign integrity layer.
