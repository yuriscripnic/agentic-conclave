"""The roadmap ordering is stated in four documents; these tests keep them agreeing."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLANS_README = ROOT / "docs/superpowers/plans/README.md"

GATE = (
    "PART II GATE: No Part III work resumes, and no new agentic plan is "
    "written, until R10 and the Bridge are complete."
)

FREEZE = (
    "FROZEN ADAPTER LICENCE: Part III adapters may be updated only enough to "
    "keep the existing suite green; no new agent capability is added until the "
    "Bridge."
)

RULES_CORE_ROWS = [
    "R1 Grid & space",
    "R2 Ruleset & data",
    "R3 Actions",
    "R4 Conditions",
    "R5 Life & death",
    "R6 Skills & contests",
    "R7 Inventory",
    "R8 Progression",
    "R9 Spellcasting",
    "R10 Conformance",
]

FROZEN = "Frozen (pending Rules Core)"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_plans_readme_states_the_gate() -> None:
    assert GATE in _read(PLANS_README)


def test_plans_readme_lists_rules_core_in_order() -> None:
    text = _read(PLANS_README)
    positions = [text.index(row) for row in RULES_CORE_ROWS]
    assert positions == sorted(positions)


def test_plans_readme_freezes_part_three() -> None:
    assert FROZEN in _read(PLANS_README)
