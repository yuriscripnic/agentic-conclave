import pytest

from domain.common.errors import ValidationError
from domain.rules.dice import DIE_SIZES, DiceRoller, RollMode


def test_same_seed_same_sequence() -> None:
    first = DiceRoller(seed=12345)
    second = DiceRoller(seed=12345)
    sequence_a = [first.roll(2, 6).total for _ in range(10)]
    sequence_b = [second.roll(2, 6).total for _ in range(10)]
    assert sequence_a == sequence_b


def test_different_seeds_differ_somewhere() -> None:
    first = DiceRoller(seed=1)
    second = DiceRoller(seed=2)
    sequence_a = [first.roll_d20().total for _ in range(20)]
    sequence_b = [second.roll_d20().total for _ in range(20)]
    assert sequence_a != sequence_b


@pytest.mark.parametrize("die_size", DIE_SIZES)
def test_single_die_within_range(die_size: int) -> None:
    roller = DiceRoller(seed=99)
    for _ in range(50):
        result = roller.roll(1, die_size)
        assert 1 <= result.all_rolls[0] <= die_size


def test_roll_multiple_dice_with_modifier() -> None:
    result = DiceRoller(seed=5).roll(3, 6, modifier=2)
    assert len(result.all_rolls) == 3
    assert sum(result.all_rolls) + 2 == result.total
    assert result.kept_rolls == result.all_rolls


def test_roll_rejects_invalid_count_or_die_size() -> None:
    roller = DiceRoller(seed=1)
    with pytest.raises(ValidationError):
        roller.roll(0, 6)
    with pytest.raises(ValidationError):
        roller.roll(1, 7)
    with pytest.raises(ValidationError):
        roller.roll(1, 3)


def test_advantage_keeps_higher_of_two_d20() -> None:
    roller = DiceRoller(seed=8)
    for _ in range(30):
        result = roller.roll_d20(mode=RollMode.ADVANTAGE)
        assert len(result.all_rolls) == 2
        assert result.kept_rolls == (max(result.all_rolls),)


def test_disadvantage_keeps_lower_of_two_d20() -> None:
    roller = DiceRoller(seed=8)
    for _ in range(30):
        result = roller.roll_d20(mode=RollMode.DISADVANTAGE)
        assert result.kept_rolls == (min(result.all_rolls),)


def test_advantage_requires_single_d20() -> None:
    roller = DiceRoller(seed=1)
    with pytest.raises(ValidationError):
        roller.roll(2, 20, mode=RollMode.ADVANTAGE)
    with pytest.raises(ValidationError):
        roller.roll(1, 6, mode=RollMode.ADVANTAGE)


def test_natural_is_exposed_for_d20_only() -> None:
    roller = DiceRoller(seed=8)
    d20 = roller.roll_d20()
    assert d20.natural == d20.kept_rolls[0]
    assert roller.roll(1, 6).natural is None


def test_natural_twenty_and_one_are_reachable() -> None:
    crit_seed = next(s for s in range(1000) if DiceRoller(seed=s).roll_d20().natural == 20)
    fumble_seed = next(s for s in range(1000) if DiceRoller(seed=s).roll_d20().natural == 1)
    assert DiceRoller(seed=crit_seed).roll_d20().natural == 20
    assert DiceRoller(seed=fumble_seed).roll_d20().natural == 1


def test_roll_expression_parses_common_forms() -> None:
    roller = DiceRoller(seed=11)
    result = roller.roll_expression("2d6+1")
    assert len(result.all_rolls) == 2
    assert result.total == sum(result.all_rolls) + 1

    single = roller.roll_expression("d20")
    assert len(single.all_rolls) == 1
    assert single.modifier == 0

    negative = roller.roll_expression("1d8-2")
    assert negative.total == negative.all_rolls[0] - 2


def test_roll_expression_rejects_malformed_input() -> None:
    roller = DiceRoller(seed=1)
    for expression in ("banana", "2d7", "0d6", "d", "2d6+1d4"):
        with pytest.raises(ValidationError):
            roller.roll_expression(expression)
