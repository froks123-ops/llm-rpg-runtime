import pytest

from runtime.rng import chance, d100, roll_dice, sample, weighted_choice


def test_seeded_rng_is_reproducible():
    assert d100(seed=123).value == d100(seed=123).value


def test_weighted_choice_seeded_is_reproducible():
    assert weighted_choice(["a", "b"], [1, 3], seed=7) == weighted_choice(
        ["a", "b"], [1, 3], seed=7
    )


def test_dice_notation_and_advantage_are_reproducible():
    normal = roll_dice("2d6+3", seed=9)
    assert normal == roll_dice("2d6+3", seed=9)
    assert len(normal.rolls) == 2
    assert normal.total == sum(normal.rolls) + 3

    advantage = roll_dice("d20", mode="advantage", seed=4)
    assert advantage.kept == (max(advantage.rolls),)
    assert advantage.dropped == (min(advantage.rolls),)


def test_invalid_advantage_and_percent_are_rejected():
    with pytest.raises(ValueError):
        roll_dice("2d20", mode="advantage", seed=1)
    with pytest.raises(ValueError):
        chance(101, seed=1)


def test_sample_is_seeded():
    assert sample([1, 2, 3, 4], 2, seed=5) == sample([1, 2, 3, 4], 2, seed=5)
