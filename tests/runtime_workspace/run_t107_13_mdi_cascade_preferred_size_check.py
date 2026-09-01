"""run_t107_13_mdi_cascade_preferred_size_check.py — T107-13.

TEST_ONLY offscreen Qt regression створює чотири реальні WSP через
``AlgorithmWorkspaceArea`` і перевіряє production Cascade preferred-size
contract. Очікуваний frame виводиться причинно з актуального viewport,
фактичних Qt cascade offsets, кількості WSP та production minimum frame size:
від max-fit віднімається одна WSP-частка лише регульованого діапазону між
minimum і max-fit.

Runner перевіряє normalized geometry, viewport bounds, content visibility,
повторний Cascade, minimize/restore та наступний production Tile. Він не
запускає WSP runtime, broker requests, Replay чи Candidate F і не змінює
production, Session користувача, MD7 або localization.
"""

from __future__ import annotations

import math
import os
import sys
from itertools import combinations
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_ACCOUNT_MODE_DEMO,
    WORKSPACE_ACCOUNT_MODE_PAPER,
    WORKSPACE_DATA_MODE_BROKER,
)
from core.algorithm_workspace_area import (  # noqa: E402
    AlgorithmMdiSubWindow,
    AlgorithmWorkspaceArea,
    AlgorithmWorkspaceWindow,
)
from core.algorithm_workspace_controller import (  # noqa: E402
    AlgorithmWorkspaceController,
)
from core.session_repository import SessionRepository  # noqa: E402

TEST_ID = "T107-13"
MODE = "RM107_T107_13_MDI_CASCADE_PREFERRED_SIZE_TEST_ONLY"
WORKSPACE_COUNT = 4


def _process_events(app: QApplication) -> None:
    """Дати Qt завершити один production layout/state transition."""
    app.processEvents()
    app.processEvents()


def _content_visible(window: AlgorithmWorkspaceWindow) -> bool:
    """Перевірити Qt visibility state клієнта й активної вкладки."""
    current_content = window.tabs_workspace.currentWidget()
    return bool(
        current_content is not None
        and window.isVisible()
        and window.tabs_workspace.isVisible()
        and current_content.isVisible()
    )


def _equal_size(geometries: tuple[QRect, ...]) -> bool:
    """Перевірити єдиний frame size для всіх WSP."""
    return len({(geometry.width(), geometry.height()) for geometry in geometries}) == 1


def _ordered_offsets(geometries: tuple[QRect, ...]) -> tuple[QPoint, ...]:
    """Повернути offsets між frames у порядку від верхнього лівого."""
    ordered = sorted(geometries, key=lambda geometry: (geometry.x(), geometry.y()))
    return tuple(
        ordered[index].topLeft() - ordered[index - 1].topLeft()
        for index in range(1, len(ordered))
    )


def _offsets_valid(geometries: tuple[QRect, ...]) -> bool:
    """Перевірити рівномірний додатний diagonal cascade offset."""
    offsets = _ordered_offsets(geometries)
    if len(offsets) != WORKSPACE_COUNT - 1:
        return False
    first = offsets[0]
    return bool(
        first.x() > 0
        and first.y() > 0
        and all(offset == first for offset in offsets[1:])
    )


def _within_viewport(geometries: tuple[QRect, ...], viewport: QRect) -> bool:
    """Перевірити додатну geometry і повне перебування у MDI viewport."""
    return all(
        geometry.isValid()
        and geometry.width() > 0
        and geometry.height() > 0
        and viewport.contains(geometry)
        for geometry in geometries
    )


def _preferred_extent(
    maximum_extent: int,
    minimum_extent: int,
    workspace_count: int,
) -> int:
    """Незалежно обчислити contract extent із minimum, max-fit і WSP count."""
    if maximum_extent <= minimum_extent:
        return maximum_extent
    adjustable_extent = maximum_extent - minimum_extent
    reserve = math.ceil(adjustable_extent / max(1, workspace_count))
    return max(minimum_extent, maximum_extent - reserve)


def _tile_layout_valid(geometries: tuple[QRect, ...], viewport: QRect) -> bool:
    """Перевірити 2x2 Tile bounds, overlap і близький розмір клітинок."""
    if len(geometries) != WORKSPACE_COUNT:
        return False
    widths = tuple(geometry.width() for geometry in geometries)
    heights = tuple(geometry.height() for geometry in geometries)
    no_overlap = all(
        first.intersected(second).isEmpty()
        for first, second in combinations(geometries, 2)
    )
    return bool(
        _within_viewport(geometries, viewport)
        and no_overlap
        and max(widths) - min(widths) <= 1
        and max(heights) - min(heights) <= 1
        and min(geometry.left() for geometry in geometries) == viewport.left()
        and min(geometry.top() for geometry in geometries) == viewport.top()
        and max(geometry.right() for geometry in geometries) == viewport.right()
        and max(geometry.bottom() for geometry in geometries) == viewport.bottom()
    )


def _geometry_text(geometries: tuple[QRect, ...]) -> str:
    """Сформувати компактний factual geometry список."""
    return ";".join(
        f"{geometry.x()},{geometry.y()},{geometry.width()},{geometry.height()}"
        for geometry in geometries
    )


def main() -> None:
    """Перевірити Cascade preferred size та суміжні MDI contracts."""
    app = QApplication.instance() or QApplication([])
    with TemporaryDirectory() as temp_dir:
        repository = SessionRepository(Path(temp_dir) / "Session")
        controller = AlgorithmWorkspaceController(repository)
        area = AlgorithmWorkspaceArea(controller=controller)
        area.resize(1280, 820)
        area.show()
        _process_events(app)

        workspace_specs = (
            ("CTRADER", "T1071301", WORKSPACE_ACCOUNT_MODE_DEMO, "EURUSD", "M15"),
            ("CTRADER", "T1071302", WORKSPACE_ACCOUNT_MODE_DEMO, "EURUSD", "M1"),
            ("CTRADER", "T1071303", WORKSPACE_ACCOUNT_MODE_DEMO, "GBPUSD", "M15"),
            ("IB", "T1071304", WORKSPACE_ACCOUNT_MODE_PAPER, "EURUSD", "M15"),
        )
        workspace_uids: list[str] = []
        for broker, account_id, account_mode, symbol, timeframe in workspace_specs:
            workspace = area.create_workspace(
                broker=broker,
                account_id=account_id,
                account_mode=account_mode,
                symbol=symbol,
                timeframe=timeframe,
                algorithm="RailAlgorithm",
                data_mode=WORKSPACE_DATA_MODE_BROKER,
            )
            workspace_uids.append(workspace.workspace_uid)
        _process_events(app)

        subwindows = tuple(
            area.workspace_subwindow(workspace_uid) for workspace_uid in workspace_uids
        )
        windows = tuple(
            area.workspace_window(workspace_uid) for workspace_uid in workspace_uids
        )
        if not all(
            isinstance(subwindow, AlgorithmMdiSubWindow) for subwindow in subwindows
        ):
            raise AssertionError("production MDI subwindows were not created")
        if not all(isinstance(window, AlgorithmWorkspaceWindow) for window in windows):
            raise AssertionError("production WSP client widgets were not created")
        typed_subwindows = tuple(
            subwindow
            for subwindow in subwindows
            if isinstance(subwindow, AlgorithmMdiSubWindow)
        )
        typed_windows = tuple(
            window for window in windows if isinstance(window, AlgorithmWorkspaceWindow)
        )

        minimum_width = max(
            subwindow.minimumWidth() for subwindow in typed_subwindows
        )
        minimum_height = max(
            subwindow.minimumHeight() for subwindow in typed_subwindows
        )
        initial_geometries = (
            QRect(24, 20, 580, 420),
            QRect(78, 58, 700, 460),
            QRect(142, 96, 640, 500),
            QRect(206, 134, 760, 540),
        )
        for subwindow, geometry in zip(
            typed_subwindows,
            initial_geometries,
            strict=True,
        ):
            subwindow.apply_system_geometry(geometry)
        area.mdi.setActiveSubWindow(typed_subwindows[2])
        _process_events(app)

        area.cascade_windows()
        _process_events(app)
        viewport = QRect(area.mdi.viewport().rect())
        cascade_geometries = tuple(
            QRect(subwindow.geometry()) for subwindow in typed_subwindows
        )
        offsets = _ordered_offsets(cascade_geometries)
        cascade_offset = offsets[0] if offsets else QPoint()
        max_x_offset = max(
            geometry.x() - viewport.x() for geometry in cascade_geometries
        )
        max_y_offset = max(
            geometry.y() - viewport.y() for geometry in cascade_geometries
        )
        maximum_width = viewport.width() - max_x_offset
        maximum_height = viewport.height() - max_y_offset
        expected_width = _preferred_extent(
            maximum_width,
            minimum_width,
            WORKSPACE_COUNT,
        )
        expected_height = _preferred_extent(
            maximum_height,
            minimum_height,
            WORKSPACE_COUNT,
        )
        preferred_width = cascade_geometries[0].width()
        preferred_height = cascade_geometries[0].height()
        frame_width_ratio = preferred_width / viewport.width()
        frame_height_ratio = preferred_height / viewport.height()
        all_frames_equal_size = _equal_size(cascade_geometries)
        all_frames_within_viewport = _within_viewport(
            cascade_geometries,
            viewport,
        )
        all_contents_visible = all(
            _content_visible(window) for window in typed_windows
        )
        cascade_offsets_valid = _offsets_valid(cascade_geometries)
        preferred_size_matches_formula = bool(
            preferred_width == expected_width
            and preferred_height == expected_height
        )
        preferred_size_above_minimum = bool(
            preferred_width >= minimum_width
            and preferred_height >= minimum_height
        )
        preferred_size_reduced_from_max_fit = bool(
            preferred_width < maximum_width
            and preferred_height < maximum_height
        )

        area.cascade_windows()
        _process_events(app)
        second_cascade_geometries = tuple(
            QRect(subwindow.geometry()) for subwindow in typed_subwindows
        )
        second_cascade_geometry_stable = (
            second_cascade_geometries == cascade_geometries
        )

        minimized_subwindows = typed_subwindows[:2]
        for subwindow in minimized_subwindows:
            subwindow.showMinimized()
        _process_events(app)
        minimized_before_cascade = sum(
            subwindow.isMinimized() for subwindow in typed_subwindows
        )
        area.cascade_windows()
        _process_events(app)
        post_minimize_geometries = tuple(
            QRect(subwindow.geometry()) for subwindow in typed_subwindows
        )
        minimized_workspaces_restored = bool(
            minimized_before_cascade == 2
            and all(not subwindow.isMinimized() for subwindow in minimized_subwindows)
            and all(_content_visible(window) for window in typed_windows[:2])
            and _equal_size(post_minimize_geometries)
            and _within_viewport(post_minimize_geometries, viewport)
            and _offsets_valid(post_minimize_geometries)
        )

        area.tile_windows()
        _process_events(app)
        tile_viewport = QRect(area.mdi.viewport().rect())
        tile_geometries = tuple(
            QRect(subwindow.geometry()) for subwindow in typed_subwindows
        )
        tile_regression_green = bool(
            _tile_layout_valid(tile_geometries, tile_viewport)
            and all(_content_visible(window) for window in typed_windows)
        )
        preferred_size_contract_satisfied = bool(
            preferred_size_matches_formula
            and preferred_size_above_minimum
            and preferred_size_reduced_from_max_fit
            and all_frames_equal_size
            and all_frames_within_viewport
            and all_contents_visible
            and cascade_offsets_valid
            and second_cascade_geometry_stable
            and minimized_workspaces_restored
            and tile_regression_green
        )

        area.hide()
        area.deleteLater()
        _process_events(app)

    contract_violations: list[str] = []
    if not preferred_size_matches_formula:
        contract_violations.append("preferred size does not match causal formula")
    if not preferred_size_above_minimum:
        contract_violations.append("preferred size is below production minimum")
    if not preferred_size_reduced_from_max_fit:
        contract_violations.append("preferred frame still consumes maximum fit")
    if not all_frames_equal_size:
        contract_violations.append("Cascade frame sizes differ")
    if not all_frames_within_viewport:
        contract_violations.append("Cascade frames exceed MDI viewport")
    if not all_contents_visible:
        contract_violations.append("Cascade client content is not visible")
    if not cascade_offsets_valid:
        contract_violations.append("Cascade offsets are invalid")
    if not second_cascade_geometry_stable:
        contract_violations.append("second Cascade changed geometry")
    if not minimized_workspaces_restored:
        contract_violations.append("Cascade did not restore minimized WSP")
    if not tile_regression_green:
        contract_violations.append("production Tile regression failed")

    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    print(f"viewport_size={viewport.width()}x{viewport.height()}")
    print(f"workspace_count={WORKSPACE_COUNT}")
    print(f"production_minimum_size={minimum_width}x{minimum_height}")
    print(f"cascade_offset={cascade_offset.x()}x{cascade_offset.y()}")
    print(f"maximum_fit_size={maximum_width}x{maximum_height}")
    print(f"preferred_frame_size={preferred_width}x{preferred_height}")
    print(f"expected_preferred_size={expected_width}x{expected_height}")
    print(f"frame_width_ratio={frame_width_ratio:.6f}")
    print(f"frame_height_ratio={frame_height_ratio:.6f}")
    print(f"cascade_geometries={_geometry_text(cascade_geometries)}")
    print(f"all_frames_equal_size={all_frames_equal_size}")
    print(f"all_frames_within_viewport={all_frames_within_viewport}")
    print(f"all_contents_visible={all_contents_visible}")
    print(f"cascade_offsets_valid={cascade_offsets_valid}")
    print(f"preferred_size_matches_formula={preferred_size_matches_formula}")
    print(f"preferred_size_above_minimum={preferred_size_above_minimum}")
    print(
        "preferred_size_reduced_from_max_fit="
        f"{preferred_size_reduced_from_max_fit}"
    )
    print(f"second_cascade_geometry_stable={second_cascade_geometry_stable}")
    print(f"minimized_before_cascade={minimized_before_cascade}")
    print(f"minimized_workspaces_restored={minimized_workspaces_restored}")
    print(f"tile_regression_green={tile_regression_green}")
    print(
        "preferred_size_contract_satisfied="
        f"{preferred_size_contract_satisfied}"
    )
    print("broker_requests=0")
    print("broker_execution_attempted=False")
    print("production_logic_changed=False")

    if not preferred_size_contract_satisfied:
        print(f"contract_violations={' | '.join(contract_violations)}")
        print("T107_13_MDI_CASCADE_PREFERRED_SIZE=RED")
        raise AssertionError(
            "MDI Cascade preferred-size contract violated: "
            + "; ".join(contract_violations)
        )

    print("contract_violations=NONE")
    print("T107_13_MDI_CASCADE_PREFERRED_SIZE=GREEN")


if __name__ == "__main__":
    main()
