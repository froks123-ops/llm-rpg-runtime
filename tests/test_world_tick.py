import pytest

from runtime.world_tick import tick_goal


def test_tick_seeded_is_reproducible():
    goal = {"id": "goal", "status": "active", "dc": 60}
    assert tick_goal("npc", goal, seed=42) == tick_goal("npc", goal, seed=42)


def test_inactive_goal_is_skipped_without_roll():
    result = tick_goal("npc", {"id": "goal", "status": "paused", "dc": 60}, seed=42)
    assert result.outcome == "skipped"
    assert result.roll is None


def test_invalid_dc_is_rejected():
    with pytest.raises(ValueError):
        tick_goal("npc", {"id": "goal", "status": "active", "dc": 101}, seed=1)
