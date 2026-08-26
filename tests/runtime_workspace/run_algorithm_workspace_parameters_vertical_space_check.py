# -*- coding: utf-8 -*-
"""Перевірка стабільної вертикальної геометрії Parameters WSP.

Контракт зберігає compact header labels і ScrollPerItem. RoadMap100 фіксує
корінь проблеми з «піврядком»: horizontal ``splitParameters`` не має змінювати
висоту через різний sizeHint правого FLOAT/CHOICE/BOOLEAN/group editor. Тест
перевіряє Designer policies, runtime stretch, послідовно вибирає типові group і
parameter nodes та вимагає незмінної висоти splitter/tree/viewport. Окремо
зберігається перевірка ``visualItemRect``: частково видимий нижній item
заборонений на кількох висотах dialog і позиціях scrollbar.
Broker execution і trading logic тест не запускає.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from xml.etree.ElementTree import fromstring

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QTreeWidgetItemIterator  # noqa: E402

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_ACCOUNT_MODE_PAPER,
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_DATA_MODE_REPLAY,
    WORKSPACE_STATE_RESTORED,
    AlgorithmWorkspace,
)
from core.algorithm_workspace_parameters_dialog import (  # noqa: E402
    AlgorithmWorkspaceParametersDialog,
)
from core.workspace_parameter_feature_policy import (  # noqa: E402
    workspace_parameter_feature_profile_for_edition,
)


def _workspace() -> AlgorithmWorkspace:
    """Створити production-сумісний Replay WSP для geometry acceptance."""
    return AlgorithmWorkspace.create(
        broker="IB",
        account_id="DUM513747",
        account_mode=WORKSPACE_ACCOUNT_MODE_PAPER,
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        data_mode=WORKSPACE_DATA_MODE_REPLAY,
        control_mode=WORKSPACE_CONTROL_MODE_AUTO,
        parameters={
            "macd_signal_enabled": True,
            "macd_signal_mode": "EXTENDED",
            "alligator_filter_enabled": True,
            "alligator_confirmation": "SAME_TIMEFRAME",
            "spread_limit": 0.00018,
            "warmup_bars": 25,
        },
        risk_settings={
            "risk_percent": 0.5,
            "maximum_position_volume": 1000.0,
            "maximum_open_positions": 2,
            "max_daily_loss_percent": 2.0,
            "require_stop_loss": True,
        },
        profit_protection={
            "max_profit_drawdown_percent": 30.0,
        },
    )


def _property_text(widget, name: str) -> str:
    prop = widget.find(f"./property[@name='{name}']")
    if prop is None:
        return ""
    return "".join(prop.itertext()).strip()


def _partial_visible_bottom_rows(
    dialog: AlgorithmWorkspaceParametersDialog,
) -> list[str]:
    """Повернути rows, що почались у viewport, але не вмістились повністю."""
    viewport_height = dialog.tree_parameters.viewport().height()
    partial: list[str] = []
    iterator = QTreeWidgetItemIterator(dialog.tree_parameters)
    while iterator.value() is not None:
        item = iterator.value()
        rect = dialog.tree_parameters.visualItemRect(item)
        if (
            rect.isValid()
            and rect.height() > 0
            and 0 <= rect.top() < viewport_height <= rect.bottom()
        ):
            partial.append(item.text(0))
        iterator += 1
    return partial


def _visual_row_height(dialog: AlgorithmWorkspaceParametersDialog) -> int:
    """Повернути висоту першого валідного visual row дерева."""
    iterator = QTreeWidgetItemIterator(dialog.tree_parameters)
    while iterator.value() is not None:
        rect = dialog.tree_parameters.visualItemRect(iterator.value())
        if rect.isValid() and rect.height() > 0:
            return int(rect.height())
        iterator += 1
    return 0


def _select_tree_code(
    dialog: AlgorithmWorkspaceParametersDialog,
    code: str,
) -> None:
    """Вибрати group/parameter за стабільним UserRole code."""
    iterator = QTreeWidgetItemIterator(dialog.tree_parameters)
    while iterator.value() is not None:
        item = iterator.value()
        if item.data(0, Qt.ItemDataRole.UserRole) == code:
            dialog.tree_parameters.setCurrentItem(item)
            return
        iterator += 1
    raise AssertionError(f"Tree code not found: {code}")


def _process_layout(app: QApplication, passes: int = 8) -> None:
    """Дати Qt завершити selection/layout/post-alignment проходи."""
    for _ in range(max(1, int(passes))):
        app.processEvents()


def main() -> None:
    ui_path = PROJECT_ROOT / "ui" / "algorithm_workspace_parameters_dialog.ui"
    generated_path = PROJECT_ROOT / "ui" / "ui_algorithm_workspace_parameters_dialog.py"
    root = fromstring(ui_path.read_text(encoding="utf-8"))

    workspace_label = root.find(".//widget[@name='lblWorkspace']")
    context_label = root.find(".//widget[@name='lblContext']")
    splitter = root.find(".//widget[@name='splitParameters']")
    tree = root.find(".//widget[@name='treeParameters']")
    editor = root.find(".//widget[@name='pnlEditor']")
    note = root.find(".//widget[@name='lblNote']")
    dialog_ui = root.find("./widget[@name='AlgorithmWorkspaceParametersDialog']")
    assert workspace_label is not None
    assert context_label is not None
    assert splitter is not None
    assert tree is not None
    assert editor is not None
    assert note is not None
    assert dialog_ui is not None

    workspace_policy = workspace_label.find("./property[@name='sizePolicy']/sizepolicy")
    context_policy = context_label.find("./property[@name='sizePolicy']/sizepolicy")
    splitter_policy = splitter.find("./property[@name='sizePolicy']/sizepolicy")
    editor_policy = editor.find("./property[@name='sizePolicy']/sizepolicy")
    note_policy = note.find("./property[@name='sizePolicy']/sizepolicy")
    assert workspace_policy is not None
    assert context_policy is not None
    assert splitter_policy is not None
    assert editor_policy is not None
    assert note_policy is not None
    assert workspace_policy.get("vsizetype") == "Maximum"
    assert context_policy.get("vsizetype") == "Maximum"
    assert splitter_policy.get("vsizetype") == "Expanding"
    assert editor_policy.get("vsizetype") == "Ignored"
    assert note_policy.get("vsizetype") == "Maximum"
    assert "70" in _property_text(workspace_label, "maximumSize")
    assert "70" in _property_text(context_label, "maximumSize")
    assert "ScrollPerItem" in _property_text(tree, "verticalScrollMode")
    assert "790" in _property_text(dialog_ui, "geometry")
    assert "650" in _property_text(dialog_ui, "minimumSize")

    generated = generated_path.read_text(encoding="utf-8")
    assert generated.count("setMaximumSize(QSize(16777215, 70))") >= 2
    assert (
        "setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerItem)" in generated
    )
    assert "resize(1040, 790)" in generated
    assert "setMinimumSize(QSize(900, 650))" in generated
    assert (
        "QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)"
        in generated
    )
    assert (
        "QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Ignored)"
        in generated
    )
    assert (
        "QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)"
        in generated
    )

    source = (
        PROJECT_ROOT / "core" / "algorithm_workspace_parameters_dialog.py"
    ).read_text(encoding="utf-8")
    assert "def _stabilize_parameter_splitter_height" in source
    assert "QSizePolicy.Policy.Expanding" in source
    assert "QSizePolicy.Policy.Ignored" in source
    assert "QSizePolicy.Policy.Maximum" in source
    assert "self.ui.verticalLayout.setStretchFactor(self.split_parameters, 1)" in source
    assert "def showEvent(self, event: QShowEvent)" in source
    assert "def _prepare_tree_viewport_alignment" in source
    assert "def _clear_tree_viewport_bottom_reserve" in source
    assert "def _schedule_tree_viewport_alignment" in source
    assert "def _run_tree_viewport_alignment_pass" in source
    assert "QTimer.singleShot(0, self._run_tree_viewport_alignment_pass)" in source
    assert "visualItemRect(iterator.value())" in source
    assert "visible_partial_height = viewport_height - rect.top()" in source
    assert "margins.bottom() + visible_partial_height" in source
    assert "def resizeEvent(self, event: QResizeEvent)" in source
    assert "raw_viewport_height = viewport_height +" not in source
    assert "% row_height" not in source
    assert "self.tree_parameters.viewportMargins()" in source
    assert "self.tree_parameters.setViewportMargins(" in source
    assert "self.tree_parameters.setMinimumHeight(" not in source
    assert "self.resize(self.width(), self.height() + correction)" not in source

    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    dialog = AlgorithmWorkspaceParametersDialog(
        _workspace(),
        None,
        feature_profile=workspace_parameter_feature_profile_for_edition("pro"),
        runtime_state=WORKSPACE_STATE_RESTORED,
    )
    checked_heights = (650, 671, 707, 743, 790)
    checked_viewports: list[int] = []
    for dialog_height in checked_heights:
        dialog.hide()
        dialog.resize(1040, dialog_height)
        dialog.show()
        for _ in range(8):
            app.processEvents()

        partial_rows = _partial_visible_bottom_rows(dialog)
        assert not partial_rows, (
            f"Partially visible parameter rows at height {dialog_height}: "
            f"{partial_rows}"
        )
        viewport_height = dialog.tree_parameters.viewport().height()
        row_height = _visual_row_height(dialog)
        assert viewport_height > 0
        assert row_height > 0

        scrollbar = dialog.tree_parameters.verticalScrollBar()
        probe_values = {scrollbar.minimum(), scrollbar.maximum()}
        if scrollbar.maximum() > scrollbar.minimum():
            probe_values.add((scrollbar.minimum() + scrollbar.maximum()) // 2)
        for value in sorted(probe_values):
            scrollbar.setValue(value)
            for _ in range(3):
                app.processEvents()
            partial_rows = _partial_visible_bottom_rows(dialog)
            assert not partial_rows, (
                f"Partially visible rows at height {dialog_height}, "
                f"scroll {value}: {partial_rows}"
            )

        checked_viewports.append(viewport_height)

    dialog.hide()
    dialog.resize(1040, 790)
    dialog.show()
    _process_layout(app)

    selection_codes = (
        "SIGNALS",
        "signals.macd_enabled",
        "signals.macd_signal_mode",
        "signals.macd_extremum_min_prominence",
        "signals.macd_extremum_to_cross_min_distance",
        "signals.macd_cross_angle_model",
        "signals.macd_cross_min_angle",
        "signals.macd_cross_min_abc_angle",
        "FILTERS",
        "filters.alligator_enabled",
        "filters.alligator_confirmation",
        "RISK_MANAGEMENT",
        "risk.risk_percent",
        "risk.maximum_position_volume",
        "risk.maximum_open_positions",
        "risk.max_daily_loss_percent",
        "risk.require_stop_loss",
        "risk.profit_drawdown_close_percent",
    )
    selection_geometry: list[tuple[int, int, int]] = []
    for code in selection_codes:
        _select_tree_code(dialog, code)
        _process_layout(app)
        partial_rows = _partial_visible_bottom_rows(dialog)
        assert not partial_rows, f"Partial rows after selecting {code}: {partial_rows}"
        selection_geometry.append(
            (
                dialog.split_parameters.height(),
                dialog.tree_parameters.height(),
                dialog.tree_parameters.viewport().height(),
            )
        )

    stable_geometry = set(selection_geometry)
    assert len(stable_geometry) == 1, (
        "Parameter selection changed splitter/tree geometry: "
        f"{dict(zip(selection_codes, selection_geometry, strict=True))}"
    )
    stable_splitter_height, stable_tree_height, stable_viewport_height = (
        selection_geometry[0]
    )

    dialog.close()
    app.processEvents()

    print("Algorithm Workspace Parameters Vertical Space result")
    print("  workspace_header_vertical_policy=Maximum")
    print("  context_header_vertical_policy=Maximum")
    print("  header_max_height=70")
    print("  tree_vertical_scroll_mode=ScrollPerItem")
    print("  splitter_vertical_policy=Expanding")
    print("  right_editor_vertical_policy=Ignored")
    print("  note_vertical_policy=Maximum")
    print("  splitter_root_stretch=1")
    print("  dialog_height=790")
    print("  dialog_minimum_height=650")
    print("  post_show_alignment=True")
    print("  post_layout_passes=4")
    print("  bottom_visible_parameter_row_alignment=LIVE_VISUAL_ITEM_RECT_EDGE")
    print("  bottom_visible_parameter_row_not_half_clipped=True")
    print("  viewport_bottom_reserve=PARTIAL_ITEM_VISIBLE_PIXELS")
    print("  checked_dialog_heights=" + ",".join(map(str, checked_heights)))
    print("  checked_viewport_heights=" + ",".join(map(str, checked_viewports)))
    print(f"  selection_probe_count={len(selection_codes)}")
    print(f"  stable_selection_splitter_height={stable_splitter_height}")
    print(f"  stable_selection_tree_height={stable_tree_height}")
    print(f"  stable_selection_viewport_height={stable_viewport_height}")
    print("  selection_does_not_change_tree_height=True")
    print("  live_qt_geometry_checked=True")
    print("  designer_ui_source=True")
    print("ALGORITHM_WORKSPACE_PARAMETERS_VERTICAL_SPACE_CHECK=OK")


if __name__ == "__main__":
    main()
