import pytest

from domain.character.vitals import HitPoints
from domain.common.errors import ValidationError


def test_hit_points_validate_construction() -> None:
    with pytest.raises(ValidationError):
        HitPoints(current=-1, maximum=10)
    with pytest.raises(ValidationError):
        HitPoints(current=11, maximum=10)
    with pytest.raises(ValidationError):
        HitPoints(current=5, maximum=0)


def test_damage_clamps_at_zero() -> None:
    hp = HitPoints(current=3, maximum=10)
    reduced = hp.apply_damage(5)
    assert reduced.current == 0
    assert reduced.maximum == 10
    assert reduced.is_defeated is True


def test_damage_rejects_negative_amount() -> None:
    with pytest.raises(ValidationError):
        HitPoints(current=5, maximum=10).apply_damage(-1)


def test_healing_clamps_at_maximum_and_zero_hp_is_not_defeated_after_heal() -> None:
    hp = HitPoints(current=0, maximum=10)
    healed = hp.apply_healing(99)
    assert healed.current == 10
    assert healed.is_defeated is False


def test_damage_returns_new_immutable_value() -> None:
    hp = HitPoints(current=10, maximum=10)
    reduced = hp.apply_damage(4)
    assert hp.current == 10
    assert reduced.current == 6
    assert reduced.is_defeated is False
