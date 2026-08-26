from __future__ import annotations

import ast
import xml.etree.ElementTree
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHART_WIDGET_PATH = ROOT / "core" / "workspace_chart_widget.py"
WORKSPACE_UI_PATH = ROOT / "ui" / "algorithm_workspace_window.ui"
WORKSPACE_PY_PATH = ROOT / "ui" / "ui_algorithm_workspace_window.py"
AREA_UI_PATH = ROOT / "ui" / "algorithm_workspace_area.ui"
AREA_PY_PATH = ROOT / "ui" / "ui_algorithm_workspace_area.py"
MAIN_UI_PATH = ROOT / "ui" / "main_app.ui"
MAIN_PY_PATH = ROOT / "ui" / "ui_main_app.py"


def _property_number(
    root: xml.etree.ElementTree.Element,
    owner_tag: str,
    owner_name: str,
    property_name: str,
) -> int:
    owner = root.find(f".//{owner_tag}[@name='{owner_name}']")
    assert owner is not None
    prop = owner.find(f"property[@name='{property_name}']/number")
    assert prop is not None and prop.text is not None
    return int(prop.text)


def _layout_margin(
    root: xml.etree.ElementTree.Element,
    layout_name: str,
    margin_name: str,
) -> int:
    return _property_number(root, "layout", layout_name, margin_name)


def _size_dimension(
    root: xml.etree.ElementTree.Element,
    widget_name: str,
    property_name: str,
    dimension: str,
) -> int:
    widget = root.find(f".//widget[@name='{widget_name}']")
    assert widget is not None
    value = widget.find(f"property[@name='{property_name}']/size/{dimension}")
    assert value is not None and value.text is not None
    return int(value.text)


def _size_height(
    root: xml.etree.ElementTree.Element,
    widget_name: str,
    property_name: str,
) -> int:
    return _size_dimension(root, widget_name, property_name, "height")


def _size_width(
    root: xml.etree.ElementTree.Element,
    widget_name: str,
    property_name: str,
) -> int:
    return _size_dimension(root, widget_name, property_name, "width")


def _widget_style(
    root: xml.etree.ElementTree.Element,
    widget_name: str,
) -> str:
    widget = root.find(f".//widget[@name='{widget_name}']")
    assert widget is not None
    style = widget.find("property[@name='styleSheet']/string")
    assert style is not None and style.text is not None
    return " ".join(style.text.split())


def _generated_call_args(
    source: str,
    owner_name: str,
    method_name: str,
) -> tuple[int, ...] | None:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != method_name:
            continue
        owner = func.value
        if not isinstance(owner, ast.Attribute):
            continue
        if not isinstance(owner.value, ast.Name) or owner.value.id != "self":
            continue
        if owner.attr != owner_name:
            continue
        values: list[int] = []
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, int):
                values.append(arg.value)
                continue
            if isinstance(arg, ast.Call):
                nested_values = [
                    nested.value
                    for nested in arg.args
                    if isinstance(nested, ast.Constant)
                    and isinstance(nested.value, int)
                ]
                values.extend(nested_values)
        return tuple(values)
    return None


def _menu_maximum_height(root: xml.etree.ElementTree.Element) -> int:
    menu = root.find(".//widget[@name='menuBarMain']")
    assert menu is not None
    height = menu.find("property[@name='maximumSize']/size/height")
    assert height is not None and height.text is not None
    return int(height.text)


def main() -> None:
    chart_source = CHART_WIDGET_PATH.read_text(encoding="utf-8")
    workspace_source = WORKSPACE_PY_PATH.read_text(encoding="utf-8")
    area_source = AREA_PY_PATH.read_text(encoding="utf-8")
    main_source = MAIN_PY_PATH.read_text(encoding="utf-8")
    workspace_ui_text = WORKSPACE_UI_PATH.read_text(encoding="utf-8")
    area_ui_text = AREA_UI_PATH.read_text(encoding="utf-8")
    main_ui_text = MAIN_UI_PATH.read_text(encoding="utf-8")
    workspace_root = xml.etree.ElementTree.fromstring(workspace_ui_text)
    area_root = xml.etree.ElementTree.fromstring(area_ui_text)
    main_root = xml.etree.ElementTree.fromstring(main_ui_text)

    chart_rows_compact = all(
        token in chart_source
        for token in (
            "_CHART_CONTROL_HEIGHT = 14",
            "_CHART_CONTROL_WIDTH = 42",
            "_CHART_CONTROL_FONT_POINT_SIZE = 8",
            '"QPushButton { min-height: 0px; max-height: 14px; "',
            '"padding: 0px 4px; }"',
            "button.setStyleSheet(_CHART_CONTROL_STYLE)",
            "header.setSpacing(2)",
            "macd_controls.setSpacing(2)",
        )
    )
    right_info_gutter = all(
        token in chart_source
        for token in (
            "_CHART_INFO_GUTTER_WIDTH = 100.0",
            "right_margin = _CHART_INFO_GUTTER_WIDTH + 12.0",
            'display_label = "Hist" if label == "Histogram" else label',
            'self.lbl_help = QLabel("?", self)',
        )
    )

    splitter_range_relaxed = all(
        token in chart_source
        for token in (
            "self.setMinimumHeight(120)",
            "self.setMinimumHeight(56)",
            "self.splitter.setChildrenCollapsible(False)",
            "self.splitter.setSizes([300, 120])",
        )
    )

    workspace_top_compact = (
        _property_number(
            workspace_root,
            "layout",
            "verticalLayout",
            "spacing",
        )
        == 4
        and _property_number(
            workspace_root,
            "layout",
            "gridLayoutHeader",
            "verticalSpacing",
        )
        == 2
        and _property_number(
            workspace_root,
            "layout",
            "gridLayoutInfo",
            "verticalSpacing",
        )
        == 3
        and _layout_margin(
            workspace_root,
            "horizontalLayoutSummary",
            "topMargin",
        )
        == 2
        and _layout_margin(
            workspace_root,
            "horizontalLayoutSummary",
            "bottomMargin",
        )
        == 2
        and _property_number(
            workspace_root,
            "layout",
            "horizontalLayoutReplay",
            "spacing",
        )
        == 4
        and _layout_margin(
            workspace_root,
            "horizontalLayoutReplay",
            "topMargin",
        )
        == 1
        and _layout_margin(
            workspace_root,
            "horizontalLayoutReplay",
            "bottomMargin",
        )
        == 1
    )

    area_button_names = ("btnNew", "btnCascade", "btnTile")
    area_button_heights = tuple(
        (
            _size_height(area_root, name, "minimumSize"),
            _size_height(area_root, name, "maximumSize"),
        )
        for name in area_button_names
    )
    lock_heights = (
        _size_height(area_root, "btnWorkspaceLock", "minimumSize"),
        _size_height(area_root, "btnWorkspaceLock", "maximumSize"),
    )
    area_button_styles = tuple(
        _widget_style(area_root, name) for name in area_button_names
    )
    lock_style = _widget_style(area_root, "btnWorkspaceLock")
    area_toolbar_compact = (
        _property_number(area_root, "layout", "verticalLayout", "spacing") <= 6
        and _layout_margin(area_root, "verticalLayout", "topMargin") <= 8
        and _layout_margin(area_root, "verticalLayout", "bottomMargin") <= 8
        and all(maximum <= 26 for _, maximum in area_button_heights)
        and lock_heights[1] <= 26
        and all(
            "min-height: 0px;" in style
            and "max-height: 24px;" in style
            and "padding: 0px 10px;" in style
            for style in area_button_styles
        )
        and "min-height: 0px;" in lock_style
        and "max-height: 24px;" in lock_style
        and "padding: 0px;" in lock_style
    )

    generated_area_values = {
        "spacing": _generated_call_args(area_source, "verticalLayout", "setSpacing"),
        "margins": _generated_call_args(
            area_source, "verticalLayout", "setContentsMargins"
        ),
        "btnNew_max": _generated_call_args(area_source, "btnNew", "setMaximumSize"),
        "btnCascade_max": _generated_call_args(
            area_source, "btnCascade", "setMaximumSize"
        ),
        "btnTile_max": _generated_call_args(area_source, "btnTile", "setMaximumSize"),
        "lock_max": _generated_call_args(
            area_source, "btnWorkspaceLock", "setMaximumSize"
        ),
        "lock_icon": _generated_call_args(
            area_source, "btnWorkspaceLock", "setIconSize"
        ),
    }
    expected_generated_area_values = {
        "spacing": (
            _property_number(area_root, "layout", "verticalLayout", "spacing"),
        ),
        "margins": (
            _layout_margin(area_root, "verticalLayout", "leftMargin"),
            _layout_margin(area_root, "verticalLayout", "topMargin"),
            _layout_margin(area_root, "verticalLayout", "rightMargin"),
            _layout_margin(area_root, "verticalLayout", "bottomMargin"),
        ),
        "btnNew_max": (
            _size_width(area_root, "btnNew", "maximumSize"),
            _size_height(area_root, "btnNew", "maximumSize"),
        ),
        "btnCascade_max": (
            _size_width(area_root, "btnCascade", "maximumSize"),
            _size_height(area_root, "btnCascade", "maximumSize"),
        ),
        "btnTile_max": (
            _size_width(area_root, "btnTile", "maximumSize"),
            _size_height(area_root, "btnTile", "maximumSize"),
        ),
        "lock_max": (
            _size_width(area_root, "btnWorkspaceLock", "maximumSize"),
            _size_height(area_root, "btnWorkspaceLock", "maximumSize"),
        ),
        "lock_icon": (
            _size_width(area_root, "btnWorkspaceLock", "iconSize"),
            _size_height(area_root, "btnWorkspaceLock", "iconSize"),
        ),
    }
    generated_area_matches = all(
        generated_area_values[key] is not None
        and generated_area_values[key][-len(expected) :] == expected  # noqa
        for key, expected in expected_generated_area_values.items()
    )

    workspace_header_rows_compact = (
        _property_number(
            workspace_root,
            "layout",
            "gridLayoutHeader",
            "verticalSpacing",
        )
        == 2
        and "max-height: 24px;" in workspace_ui_text
        and "max-height: 22px;" in workspace_ui_text
        and "padding: 0px 10px;" in workspace_ui_text
        and "padding: 0px 8px;" in workspace_ui_text
    )

    workspace_styles_compact = all(
        token in workspace_ui_text
        for token in (
            "padding: 0px 6px;",
            "max-height: 24px;",
            "max-height: 22px;",
            "max-height: 18px;",
            "font: 8pt &quot;Segoe UI&quot;;",
            "padding: 4px 10px;",
        )
    )

    generated_workspace_matches = all(
        token in workspace_source
        for token in (
            "self.verticalLayout.setSpacing(4)",
            "self.gridLayoutHeader.setVerticalSpacing(2)",
            "self.gridLayoutInfo.setVerticalSpacing(3)",
            "self.horizontalLayoutSummary.setContentsMargins(8, 2, 8, 2)",
            "self.horizontalLayoutReplay.setSpacing(4)",
            "self.horizontalLayoutReplay.setContentsMargins(6, 1, 6, 1)",
            "self.btnReplayPause.setMaximumSize(QSize(16777215, 20))",
            "self.btnReplayStep.setMaximumSize(QSize(16777215, 20))",
            "self.cmbReplaySpeed.setMaximumSize(QSize(16777215, 20))",
        )
    )

    market_banner_preserved = (
        "padding: 5px 12px;" in main_ui_text
        and "background-color: #8b1e1e;" in main_ui_text
        and _menu_maximum_height(main_root) == 29
    )
    generated_main_matches = all(
        token in main_source
        for token in (
            "padding: 5px 12px;",
            "self.menuBarMain.setMaximumSize(QSize(16777215, 29))",
            "self.menuBarMain.setGeometry(QRect(0, 0, 800, 29))",
        )
    )

    assert chart_rows_compact
    assert right_info_gutter
    assert splitter_range_relaxed
    assert workspace_top_compact
    assert area_toolbar_compact
    assert generated_area_matches, f"generated_area_values={generated_area_values}"
    assert workspace_header_rows_compact
    assert workspace_styles_compact
    assert generated_workspace_matches
    assert market_banner_preserved
    assert generated_main_matches

    print("Algorithm Workspace Chart Compact Layout result")
    print(f"  chart_rows_compact={chart_rows_compact}")
    print(f"  right_info_gutter={right_info_gutter}")
    print(f"  splitter_range_relaxed={splitter_range_relaxed}")
    print(f"  workspace_top_compact={workspace_top_compact}")
    print(f"  area_toolbar_compact={area_toolbar_compact}")
    print(f"  area_button_heights={area_button_heights}")
    print(f"  lock_heights={lock_heights}")
    print("  area_size_hints_are_diagnostic_only=True")
    print(f"  generated_area_matches={generated_area_matches}")
    print(f"  generated_area_values={generated_area_values}")
    print(f"  expected_generated_area_values={expected_generated_area_values}")
    print(f"  workspace_header_rows_compact={workspace_header_rows_compact}")
    print(f"  workspace_styles_compact={workspace_styles_compact}")
    print(f"  generated_workspace_matches={generated_workspace_matches}")
    print(f"  market_banner_preserved={market_banner_preserved}")
    print(f"  generated_main_matches={generated_main_matches}")
    print("ALGORITHM_WORKSPACE_CHART_COMPACT_LAYOUT_CHECK=OK")


if __name__ == "__main__":
    main()
