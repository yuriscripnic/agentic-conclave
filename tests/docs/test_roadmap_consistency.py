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


CLAUDE_MD = ROOT / "CLAUDE.md"


def test_claude_md_states_the_gate() -> None:
    assert GATE in _read(CLAUDE_MD)


def test_claude_md_expands_phase_2_into_the_rules_core() -> None:
    text = _read(CLAUDE_MD)
    positions = [text.index(row) for row in RULES_CORE_ROWS]
    assert positions == sorted(positions)


def test_claude_md_states_the_freeze_licence() -> None:
    assert FREEZE in _read(CLAUDE_MD)


IMPL_PLAN = ROOT / "docs/Agentic Conclave-Implementation Plan.md"


def test_implementation_plan_states_the_gate() -> None:
    assert GATE in _read(IMPL_PLAN)


def test_implementation_plan_has_three_parts() -> None:
    text = _read(IMPL_PLAN)
    for heading in ("Part I", "Part II", "Part III"):
        assert heading in text


def test_implementation_plan_marks_part_three_frozen() -> None:
    assert FROZEN in _read(IMPL_PLAN)


def test_implementation_plan_states_the_freeze_licence() -> None:
    assert FREEZE in _read(IMPL_PLAN)


ROOT_README = ROOT / "README.md"


def test_root_readme_points_at_the_roadmap() -> None:
    text = _read(ROOT_README)
    assert "docs/superpowers/plans/README.md" in text
    assert "Rules Core" in text
