"""Scenario registry (spec §4.2): SCENARIOS maps names to concrete scenarios."""

from collections.abc import Mapping

from evaluation.errors import EvaluationError
from evaluation.model import Scenario
from evaluation.scenarios.cooperation_smoke import COOPERATION_SMOKE
from evaluation.scenarios.goblin_skirmish import GOBLIN_SKIRMISH
from evaluation.scenarios.instruction_following import INSTRUCTION_FOLLOWING

SCENARIOS: Mapping[str, Scenario] = {
    "goblin-skirmish": GOBLIN_SKIRMISH,
    "instruction-following": INSTRUCTION_FOLLOWING,
    "cooperation-smoke": COOPERATION_SMOKE,
}


def get_scenario(name: str) -> Scenario:
    """Look up a scenario by name; unknown names are harness misuse (§5)."""
    try:
        return SCENARIOS[name]
    except KeyError:
        raise EvaluationError(f"unknown scenario: {name!r}") from None