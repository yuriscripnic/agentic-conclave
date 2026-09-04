from domain.rules.checks import CheckResolver
from domain.rules.dice import DiceRoller, RollMode


def _seed_with_natural(rolls: list[int]) -> int:
    """Find a seed whose d20 sequence equals `rolls`."""

    def sequence_matches(seed: int) -> bool:
        roller = DiceRoller(seed=seed)
        return [roller.roll_d20().natural for _ in rolls] == rolls

    return next(seed for seed in range(100_000) if sequence_matches(seed))


def test_ability_check_totals_and_dc() -> None:
    seed = _seed_with_natural([15])
    result = CheckResolver(DiceRoller(seed=seed)).ability_check(modifier=3, dc=17)
    assert result.roll == 15
    assert result.modifier == 3
    assert result.total == 18
    assert result.dc == 17
    assert result.success is True


def test_ability_check_proficiency_adds_bonus() -> None:
    seed = _seed_with_natural([10])
    result = CheckResolver(DiceRoller(seed=seed)).ability_check(
        modifier=1, dc=15, proficient=True, proficiency_bonus=2
    )
    assert result.total == 13
    assert result.success is False


def test_saving_throw_success_and_failure() -> None:
    pass_seed = _seed_with_natural([18])
    passed = CheckResolver(DiceRoller(seed=pass_seed)).saving_throw(modifier=1, dc=15)
    assert passed.success is True
    assert passed.mode == RollMode.NORMAL

    fail_seed = _seed_with_natural([2])
    failed = CheckResolver(DiceRoller(seed=fail_seed)).saving_throw(modifier=1, dc=15)
    assert failed.success is False


def test_attack_roll_natural_twenty_always_hits_and_crits() -> None:
    seed = _seed_with_natural([20])
    result = CheckResolver(DiceRoller(seed=seed)).attack_roll(
        attack_bonus=0, target_ac=30
    )
    assert result.is_critical is True
    assert result.is_critical_miss is False
    assert result.hit is True


def test_attack_roll_natural_one_always_misses() -> None:
    seed = _seed_with_natural([1])
    result = CheckResolver(DiceRoller(seed=seed)).attack_roll(
        attack_bonus=25, target_ac=1
    )
    assert result.is_critical_miss is True
    assert result.is_critical is False
    assert result.hit is False


def test_attack_roll_hit_and_miss_by_total() -> None:
    hit_seed = _seed_with_natural([12])
    hit = CheckResolver(DiceRoller(seed=hit_seed)).attack_roll(
        attack_bonus=5, target_ac=16
    )
    assert hit.total == 17
    assert hit.hit is True
    assert hit.is_critical is False

    miss_seed = _seed_with_natural([7])
    miss = CheckResolver(DiceRoller(seed=miss_seed)).attack_roll(
        attack_bonus=5, target_ac=16
    )
    assert miss.total == 12
    assert miss.hit is False


def test_attack_roll_with_advantage_mode() -> None:
    seed = _seed_with_natural([4])
    result = CheckResolver(DiceRoller(seed=seed)).attack_roll(
        attack_bonus=2, target_ac=10, mode=RollMode.ADVANTAGE
    )
    assert result.mode == RollMode.ADVANTAGE
    # Advantage consumes two d20 rolls from the same RNG stream; mirror them.
    mirror = DiceRoller(seed=seed)
    first = mirror.roll_d20().all_rolls[0]
    second = mirror.roll_d20().all_rolls[0]
    assert result.roll == max(first, second)
    assert result.total == result.roll + 2
