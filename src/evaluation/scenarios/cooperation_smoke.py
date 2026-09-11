"""The cooperation-smoke scenario (spec §4.4.3): one say, party traffic.

Ground truth at seed 42 (offline): the say triggers a GM reaction with no
state change, the drain-driven fight produces party traffic (the scripted
agents always post one), and nothing is rejected.
"""

from __future__ import annotations

from evaluation.model import Scenario, ScenarioCheck, ScenarioResult


def _party_messages_exchanged(result: ScenarioResult) -> bool:
    count = result.metrics.get("party_message_count")
    return isinstance(count, int) and count >= 1


def _no_rejections(result: ScenarioResult) -> bool:
    return result.metrics.get("rejection_count") == 0


COOPERATION_SMOKE = Scenario(
    name="cooperation-smoke",
    description=(
        "The party holds the line: one human 'say' reaches the GM while the "
        "AI party fights, proving party traffic flows and no action is rejected."
    ),
    seed=42,
    steps=("say hold the line",),
    checks=(
        ScenarioCheck(
            name="party-messages-exchanged",
            description="at least one party message is posted during the run",
            evaluate=_party_messages_exchanged,
        ),
        ScenarioCheck(
            name="no-rejections",
            description="no action is rejected by the rules engine",
            evaluate=_no_rejections,
        ),
    ),
)