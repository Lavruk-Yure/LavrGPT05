from __future__ import annotations

import ast
import xml.etree.ElementTree
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AREA_PATH = ROOT / "core" / "algorithm_workspace_area.py"
POLICY_PATH = ROOT / "core" / "translation_policy.py"
WORKSPACE_UI_PATH = ROOT / "ui" / "algorithm_workspace_window.ui"
WORKSPACE_PY_PATH = ROOT / "ui" / "ui_algorithm_workspace_window.py"


def _method_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    source_lines = source.splitlines(keepends=True)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            assert node.end_lineno is not None
            return "".join(source_lines[node.lineno - 1 : node.end_lineno])  # noqa
    raise AssertionError(f"Method not found: {name}")


def _layout_number(root, layout_name: str, property_name: str) -> int:
    layout = root.find(f".//layout[@name='{layout_name}']")
    assert layout is not None
    value = layout.find(f"property[@name='{property_name}']/number")
    assert value is not None and value.text is not None
    return int(value.text)


def _widget_max_height(root, widget_name: str) -> int:
    widget = root.find(f".//widget[@name='{widget_name}']")
    assert widget is not None
    value = widget.find("property[@name='maximumSize']/size/height")
    assert value is not None and value.text is not None
    return int(value.text)


def main() -> None:
    area_source = AREA_PATH.read_text(encoding="utf-8")
    policy_source = POLICY_PATH.read_text(encoding="utf-8")
    ui_text = WORKSPACE_UI_PATH.read_text(encoding="utf-8")
    generated = WORKSPACE_PY_PATH.read_text(encoding="utf-8")
    root = xml.etree.ElementTree.fromstring(ui_text)

    refresh_source = _method_source(area_source, "_sync_workspace_runtime")

    csv_duplicate_removed = (
        "CSV {accepted}/{input}" not in area_source
        and "CSV {accepted}/{input}" not in policy_source
        and "accepted=history_report.accepted_rows" not in refresh_source
        and "input=history_report.input_rows" not in refresh_source
    )
    quality_fields_preserved = all(
        token in refresh_source
        for token in (
            "filtered=history_report.filtered_rows",
            "gaps=history_report.gap_count",
            "quotes=history_report.derived_quotes",
        )
    )
    ukrainian_quality_compact = (
        "пропущено {filtered} • розривів {gaps} • " in policy_source
        and "котирувань {quotes}" in policy_source
    )
    replay_row_compact = (
        _layout_number(root, "horizontalLayoutReplay", "spacing") == 4
        and _layout_number(root, "horizontalLayoutReplay", "topMargin") == 1
        and _layout_number(root, "horizontalLayoutReplay", "bottomMargin") == 1
        and _widget_max_height(root, "btnReplayPause") == 20
        and _widget_max_height(root, "btnReplayStep") == 20
        and _widget_max_height(root, "cmbReplaySpeed") == 20
        and "QPushButton#btnReplayPause," in ui_text
        and "max-height: 18px;" in ui_text
        and "font: 8pt &quot;Segoe UI&quot;;" in ui_text
    )
    generated_workspace_matches = all(
        token in generated
        for token in (
            "self.horizontalLayoutReplay.setSpacing(4)",
            "self.horizontalLayoutReplay.setContentsMargins(6, 1, 6, 1)",
            "self.btnReplayPause.setMaximumSize(QSize(16777215, 20))",
            "self.btnReplayStep.setMaximumSize(QSize(16777215, 20))",
            "self.cmbReplaySpeed.setMaximumSize(QSize(16777215, 20))",
        )
    )

    assert csv_duplicate_removed
    assert quality_fields_preserved
    assert ukrainian_quality_compact
    assert replay_row_compact
    assert generated_workspace_matches

    print("Algorithm Workspace Replay Status Compact result")
    print(f"  csv_duplicate_removed={csv_duplicate_removed}")
    print(f"  quality_fields_preserved={quality_fields_preserved}")
    print(f"  ukrainian_quality_compact={ukrainian_quality_compact}")
    print(f"  replay_row_compact={replay_row_compact}")
    print(f"  generated_workspace_matches={generated_workspace_matches}")
    print("ALGORITHM_WORKSPACE_REPLAY_STATUS_COMPACT_CHECK=OK")


if __name__ == "__main__":
    main()
