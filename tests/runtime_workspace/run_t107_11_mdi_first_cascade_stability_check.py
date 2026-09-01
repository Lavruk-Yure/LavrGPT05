"""run_t107_11_mdi_first_cascade_stability_check.py — T107-11.

TEST_ONLY offscreen Qt regression створює чотири реальні WSP через
``AlgorithmWorkspaceArea`` у live-подібному normal/visible стані, задає різні
попередні geometry, активує один WSP і викликає production Cascade рівно один
раз для acceptance. Runner фіксує viewport, frames, normalized size, offsets,
relative size ratios і client visibility. Другий Cascade викликається лише як
діагностичне порівняння final geometry та не може виправити перший сценарій.

Preferred-size threshold навмисно не вигадується: runner друкує factual ratios
і точний structural факт, чи normalized frame разом із cascade offsets займає
весь viewport. Він не викликає Tile, minimize, maximize, manual resize після
контрольного Cascade, ``repaint()`` або ``update()``; не запускає WSP runtime,
broker requests, Replay чи Candidate F і не змінює production, MD7 або
localization.
"""

from __future__ import annotations

import os
import sys
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

TEST_ID = "T107-11"
MODE = "RM107_T107_11_MDI_FIRST_CASCADE_STABILITY_TEST_ONLY"
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


def _sizes_normalized(geometries: tuple[QRect, ...]) -> bool:
    """Перевірити єдиний frame size для всіх елементів Cascade."""
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


def _fills_viewport_after_offsets(
    geometries: tuple[QRect, ...],
    viewport: QRect,
) -> bool:
    """Перевірити точне заповнення viewport frame-ом плюс cascade offsets."""
    if not geometries or not _sizes_normalized(geometries):
        return False
    max_x_offset = max(geometry.x() - viewport.x() for geometry in geometries)
    max_y_offset = max(geometry.y() - viewport.y() for geometry in geometries)
    frame = geometries[0]
    return bool(
        frame.width() + max_x_offset == viewport.width()
        and frame.height() + max_y_offset == viewport.height()
    )


def _geometry_text(geometries: tuple[QRect, ...]) -> str:
    """Сформувати компактний factual geometry список."""
    return ";".join(
        f"{geometry.x()},{geometry.y()},{geometry.width()},{geometry.height()}"
        for geometry in geometries
    )


def _offset_text(geometries: tuple[QRect, ...]) -> str:
    """Сформувати factual список cascade offsets."""
    return ";".join(
        f"{offset.x()},{offset.y()}" for offset in _ordered_offsets(geometries)
    )


def main() -> None:
    """Порівняти перший production Cascade з другим diagnostic Cascade."""
    app = QApplication.instance() or QApplication([])
    with TemporaryDirectory() as temp_dir:
        repository = SessionRepository(Path(temp_dir) / "Session")
        controller = AlgorithmWorkspaceController(repository)
        area = AlgorithmWorkspaceArea(controller=controller)
        area.resize(1280, 820)
        area.show()
        _process_events(app)

        workspace_specs = (
            ("CTRADER", "T1071101", WORKSPACE_ACCOUNT_MODE_DEMO, "EURUSD", "M15"),
            ("CTRADER", "T1071102", WORKSPACE_ACCOUNT_MODE_DEMO, "EURUSD", "M1"),
            ("CTRADER", "T1071103", WORKSPACE_ACCOUNT_MODE_DEMO, "GBPUSD", "M15"),
            ("IB", "T1071104", WORKSPACE_ACCOUNT_MODE_PAPER, "EURUSD", "M15"),
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
            subwindow.showNormal()
            subwindow.show()
        active_subwindow = typed_subwindows[2]
        area.mdi.setActiveSubWindow(active_subwindow)
        _process_events(app)
        live_like_state_ready = bool(
            area.mdi.activeSubWindow() is active_subwindow
            and all(subwindow.isVisible() for subwindow in typed_subwindows)
            and all(not subwindow.isMinimized() for subwindow in typed_subwindows)
        )

        area.cascade_windows()
        _process_events(app)
        viewport = QRect(area.mdi.viewport().rect())
        first_geometries = tuple(
            QRect(subwindow.geometry()) for subwindow in typed_subwindows
        )
        first_cascade_frames_visible = all(
            subwindow.isVisible() for subwindow in typed_subwindows
        )
        first_cascade_not_minimized = all(
            not subwindow.isMinimized() for subwindow in typed_subwindows
        )
        first_cascade_content_visible = all(
            _content_visible(window) for window in typed_windows
        )
        first_cascade_sizes_normalized = _sizes_normalized(first_geometries)
        first_cascade_offsets_valid = _offsets_valid(first_geometries)
        first_cascade_within_viewport = _within_viewport(first_geometries, viewport)
        first_frame = first_geometries[0]
        first_cascade_frame_width_ratio = first_frame.width() / viewport.width()
        first_cascade_frame_height_ratio = first_frame.height() / viewport.height()
        first_cascade_nearly_viewport_sized = _fills_viewport_after_offsets(
            first_geometries,
            viewport,
        )
        first_cascade_layout_valid = bool(
            live_like_state_ready
            and first_cascade_frames_visible
            and first_cascade_not_minimized
            and first_cascade_content_visible
            and first_cascade_sizes_normalized
            and first_cascade_offsets_valid
            and first_cascade_within_viewport
        )

        area.cascade_windows()
        _process_events(app)
        second_geometries = tuple(
            QRect(subwindow.geometry()) for subwindow in typed_subwindows
        )
        second_cascade_changes_geometry = second_geometries != first_geometries
        second_cascade_required = second_cascade_changes_geometry
        first_cascade_final_geometry_stable = not second_cascade_changes_geometry
        live_symptom_not_reproduced_offscreen = not second_cascade_changes_geometry
        first_cascade_preferred_size_reasonable = "NOT_DECIDED"
        mdi_first_cascade_contract_satisfied = bool(
            first_cascade_layout_valid
            and first_cascade_final_geometry_stable
            and not second_cascade_required
        )

        area.hide()
        area.deleteLater()
        _process_events(app)

    contract_violations: list[str] = []
    if not live_like_state_ready:
        contract_violations.append(
            "live-like normal/visible active WSP state was not ready"
        )
    if not first_cascade_frames_visible:
        contract_violations.append("first Cascade hid one or more WSP frames")
    if not first_cascade_not_minimized:
        contract_violations.append("first Cascade left a WSP minimized")
    if not first_cascade_content_visible:
        contract_violations.append("first Cascade hid WSP client content")
    if not first_cascade_sizes_normalized:
        contract_violations.append("first Cascade produced different WSP sizes")
    if not first_cascade_offsets_valid:
        contract_violations.append("first Cascade offsets are invalid")
    if not first_cascade_within_viewport:
        contract_violations.append("first Cascade geometry exceeds MDI viewport")
    if second_cascade_changes_geometry:
        contract_violations.append("second Cascade changed first-pass geometry")

    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    print(f"workspace_count={WORKSPACE_COUNT}")
    print(f"live_like_state_ready={live_like_state_ready}")
    print(
        "mdi_viewport_geometry="
        f"{viewport.x()},{viewport.y()},{viewport.width()},{viewport.height()}"
    )
    print(f"initial_geometries={_geometry_text(initial_geometries)}")
    print(f"first_cascade_geometries={_geometry_text(first_geometries)}")
    print(f"first_cascade_offsets={_offset_text(first_geometries)}")
    print(f"first_cascade_frames_visible={first_cascade_frames_visible}")
    print(f"first_cascade_not_minimized={first_cascade_not_minimized}")
    print(f"first_cascade_content_visible={first_cascade_content_visible}")
    print(f"first_cascade_sizes_normalized={first_cascade_sizes_normalized}")
    print(f"first_cascade_offsets_valid={first_cascade_offsets_valid}")
    print(f"first_cascade_within_viewport={first_cascade_within_viewport}")
    print(f"first_cascade_frame_width_ratio={first_cascade_frame_width_ratio:.6f}")
    print(f"first_cascade_frame_height_ratio={first_cascade_frame_height_ratio:.6f}")
    print(f"first_cascade_nearly_viewport_sized={first_cascade_nearly_viewport_sized}")
    print(f"first_cascade_layout_valid={first_cascade_layout_valid}")
    print(f"second_cascade_geometries={_geometry_text(second_geometries)}")
    print(f"second_cascade_changes_geometry={second_cascade_changes_geometry}")
    print(f"second_cascade_required={second_cascade_required}")
    print(
        "first_cascade_final_geometry_stable="
        f"{first_cascade_final_geometry_stable}"
    )
    print(
        "first_cascade_preferred_size_reasonable="
        f"{first_cascade_preferred_size_reasonable}"
    )
    print(
        "live_symptom_not_reproduced_offscreen="
        f"{live_symptom_not_reproduced_offscreen}"
    )
    print(
        "mdi_first_cascade_contract_satisfied="
        f"{mdi_first_cascade_contract_satisfied}"
    )
    print("broker_requests=0")
    print("broker_execution_attempted=False")
    print("production_logic_changed=False")

    if not mdi_first_cascade_contract_satisfied:
        print(f"contract_violations={' | '.join(contract_violations)}")
        print("T107_11_MDI_FIRST_CASCADE_STABILITY=RED")
        raise AssertionError(
            "MDI first Cascade stability contract violated: "
            + "; ".join(contract_violations)
        )

    print("contract_violations=NONE")
    print("T107_11_MDI_FIRST_CASCADE_STABILITY=GREEN")


if __name__ == "__main__":
    main()
