"""The goblin-skirmish scenario (spec §4.4.1): two strikes, two goblins down.

Ground truth at seed 42 (offline scripted gateways): both strikes are
accepted, there are zero rejections, and both goblins are defeated. The
original draft repeated "attack goblin scout", which fails its own
no-rejections check - the scout dies during step 2's pre-drain because the
AI party attacks it too. Under the R1 grid the strikes are range-bound and
the fight outlives two steps, so the human keeps striking the orc (the last
foe standing on the shipped map) until the engine ends the combat; at other
seeds a strike can still land on a foe the AI party dropped first, which
fails no-rejections by design of static human scripts.

R2 retune: agent weapons now resolve through the ruleset (R2 spec §5), which
changes the seeded dice order, so the strikes were re-searched at seed 42:
two scout strikes then orc strikes until the engine ends the combat.
"""

from __future__ import annotations

from evaluation.model import Scenario, ScenarioCheck, ScenarioResult

_ENEMY_NAMES = ("Goblin Scout", "Goblin Skulker")


def _no_rejections(result: ScenarioResult) -> bool:
    return result.metrics.get("rejection_count") == 0


def _skirmish_enemies_defeated(result: ScenarioResult) -> bool:
    for run in result.runs:
        defeated = {
            event.actor
            for event in run.event_summaries
            if event.event_type == "character_defeated"
        }
        if not set(_ENEMY_NAMES) <= defeated:
            return False
    return True


def _runs_are_consistent(result: ScenarioResult) -> bool:
    agreement = result.metrics.get("consistency_agreement")
    return agreement is None or agreement == 1.0


GOBLIN_SKIRMISH = Scenario(
    name="goblin-skirmish",
    description=(
        "Two human strikes at the goblin screen while the AI party fights on: "
        "every proposed action must pass rules validation and both goblins fall."
    ),
    seed=42,
    # R2 retune (seeded dice order changed with ruleset-resolved weapons):
    # two scout strikes, then orc strikes until the engine ends the combat.
    steps=("attack goblin scout", "attack goblin scout")
    + ("attack orc brute",) * 10,
    repeat_runs=2,
    checks=(
        ScenarioCheck(
            name="no-rejections",
            description="no action is rejected by the rules engine",
            evaluate=_no_rejections,
        ),
        ScenarioCheck(
            name="skirmish-enemies-defeated",
            description="Goblin Scout and Goblin Skulker are defeated in every run",
            evaluate=_skirmish_enemies_defeated,
        ),
        ScenarioCheck(
            name="consistent-runs",
            description="same-seed repeated runs produce identical event sequences",
            evaluate=_runs_are_consistent,
        ),
    ),
)