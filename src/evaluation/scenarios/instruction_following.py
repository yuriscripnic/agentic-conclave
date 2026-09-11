"""The instruction-following scenario (spec §4.4.2).

Agents have no instruction channel: the human instruction is executed
deterministically by the player character. (a) player-attack-fidelity
verifies the instruction reaches the engine as an attack from Arin on
Orc Brute; (b) agents-attack-enemies verifies the AI party produces
legal attack proposals against the enemy roster. Offline (scripted
decisions) both hold and validate harness plumbing; live, (a) stays a
harness check and (b) measures whether the model proposes legal attacks.
Ground truth at seed 42: Arin's attack is accepted (a miss), zero
rejections.
"""

from __future__ import annotations

from evaluation.model import Scenario, ScenarioCheck, ScenarioResult

_PARTY_NAMES = ("Brix", "Mira", "Sera")
_ENEMY_NAMES = ("Goblin Scout", "Goblin Skulker", "Orc Brute")


def _player_attack_fidelity(result: ScenarioResult) -> bool:
    for run in result.runs:
        if not any(
            event.event_type == "attack_requested"
            and event.actor == "Arin"
            and event.target == "Orc Brute"
            for event in run.event_summaries
        ):
            return False
    return True


def _agents_attack_enemies(result: ScenarioResult) -> bool:
    for run in result.runs:
        agent_attacks = [
            event
            for event in run.event_summaries
            if event.event_type == "attack_requested" and event.actor in _PARTY_NAMES
        ]
        if not agent_attacks:
            return False
        if any(event.target not in _ENEMY_NAMES for event in agent_attacks):
            return False
    return True


def _no_rejections(result: ScenarioResult) -> bool:
    return result.metrics.get("rejection_count") == 0


INSTRUCTION_FOLLOWING = Scenario(
    name="instruction-following",
    description=(
        "One human instruction ('attack orc brute'): the instruction executes "
        "deterministically through the rules engine, and the AI party keeps "
        "proposing legal attacks against the enemy roster."
    ),
    seed=42,
    steps=("attack orc brute",),
    checks=(
        ScenarioCheck(
            name="player-attack-fidelity",
            description="Arin's attack lands on Orc Brute in every run",
            evaluate=_player_attack_fidelity,
        ),
        ScenarioCheck(
            name="agents-attack-enemies",
            description="every party-agent attack targets an enemy-roster name",
            evaluate=_agents_attack_enemies,
        ),
        ScenarioCheck(
            name="no-rejections",
            description="no action is rejected by the rules engine",
            evaluate=_no_rejections,
        ),
    ),
)