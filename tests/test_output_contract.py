import pytest

from runtime.output_contract import assert_valid_output, validate_output


def valid_turn(*, monologue: bool = False) -> str:
    narrative = '"Dobrze."'
    if monologue:
        narrative += "\n\n---\n\n**Monolog Ukitake**\n\n*To wymaga uwagi.*\n\n---"
    return f"""```Raport
WEJŚCIE PUBLICZNE: odpowiedź Seijiego
TRYB: 4 DIALOG
AKTYWNI NPC: Ukitake
AGENCY TEST: PASS
LEAK TEST: PASS
```
``[Dzień 2 | Pora: Popołudnie | Ugendō | Ciepło | TRYB 4: DIALOG]``

{narrative}

[STAN: stabilny]
[>_]"""


def test_valid_normal_turn_passes():
    result = validate_output(valid_turn())
    assert result.ok
    assert result.errors == ()
    assert result.warnings == ()


def test_report_must_precede_header_and_end_with_passes():
    malformed = valid_turn().replace("```Raport", "``[Dzień 2 | Pora: Popołudnie | Ugendō | TRYB 4: DIALOG]``\n```Raport", 1)
    result = validate_output(malformed)
    assert not result.ok
    assert "report.missing" in {issue.code for issue in result.errors}


def test_header_is_required_after_report():
    malformed = valid_turn().replace(
        "``[Dzień 2 | Pora: Popołudnie | Ugendō | Ciepło | TRYB 4: DIALOG]``",
        "Ugendō",
    )
    result = validate_output(malformed)
    assert "header.invalid" in {issue.code for issue in result.errors}


def test_footer_sentinel_must_be_last():
    malformed = valid_turn() + "\nextra"
    result = validate_output(malformed)
    assert "footer.sentinel" in {issue.code for issue in result.errors}


def test_persistence_debug_is_warning_not_player_contract_error():
    text = valid_turn().replace("[STAN: stabilny]", "[STAN: stabilny]\ntransaction_journal_id=abc")
    result = validate_output(text)
    assert result.ok
    assert "persistence.transaction_journal_id" in {issue.code for issue in result.warnings}


def test_explicit_monologue_block_passes():
    assert validate_output(valid_turn(monologue=True)).ok


def test_monologue_requires_italic_body_and_separators():
    malformed = valid_turn().replace(
        '"Dobrze."',
        "**Monolog Ukitake**\nTo wymaga uwagi.",
    )
    result = validate_output(malformed)
    codes = {issue.code for issue in result.errors}
    assert "monologue.open_separator" in codes
    assert "monologue.italic_body" in codes


def test_meta_response_can_disable_narrative_contract():
    result = validate_output(
        "Bootstrap: READY",
        require_report=False,
        require_header=False,
        require_footer=False,
    )
    assert result.ok


def test_assert_valid_output_raises_codes():
    with pytest.raises(ValueError, match="footer.sentinel"):
        assert_valid_output(valid_turn() + "\nextra")
