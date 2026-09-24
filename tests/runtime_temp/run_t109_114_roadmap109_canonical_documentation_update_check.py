"""T109-114 — RoadMap109 canonical documentation update check.

TEST_ONLY перевіряє, що MD7 містить стислий канонічний RoadMap109 closure
checkpoint і не залишає RoadMap107 partial-execution стан як поточний truth.
Production-файли тест не змінює і broker не викликає.
"""

from pathlib import Path

TEST_ID = "T109-114"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
MD7 = PROJECT_ROOT / "doc" / "LGE_Runtime_07.md"


def test_t109_114_roadmap109_canonical_documentation_update() -> None:
    text = MD7.read_text(encoding="utf-8")

    required = (
        "# LGE Runtime 07 — RoadMap101–109",
        "Дата актуалізації: 2026-09-24",
        "# 28. RoadMap109 — Workspace BROKER signal-to-execution production path",
        "WorkspaceTradeIntent",
        "WorkspaceRiskAccountSnapshot",
        "workspace_broker_execution_boundary_closed=True",
        "production_change_required=False",
        "WORKSPACE_BROKER_EXECUTION_FULL_PRODUCTION_CLOSURE_GREEN",
        "NO_ADDITIONAL_PRODUCTION_CHANGE_REQUIRED",
    )
    missing = [item for item in required if item not in text]

    assert not missing, f"MD7 missing canonical RoadMap109 markers: {missing}"
    assert "історичний стан superseded канонічним RoadMap109" in text

    print("T109-114_ROADMAP109_CANONICAL_DOCUMENTATION_UPDATE=OK")
    print("test_scope_test_only=True")
    print("production_change=False")
    print("broker_requests=0")
    print("actual_broker_execution_attempted=False")
    print("roadmap109_documentation_canonical=True")
    print("first_unresolved_boundary=ROADMAP109_CLOSURE_COMPLETE")
