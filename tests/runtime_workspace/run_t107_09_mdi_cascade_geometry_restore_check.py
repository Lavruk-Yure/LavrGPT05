"""run_t107_09_mdi_cascade_geometry_restore_check.py — T107-09.

TEST_ONLY offscreen Qt regression створює чотири реальні WSP через
``AlgorithmWorkspaceArea`` і вимірює фактичний production Cascade path.
Сценарій A починається з різних валідних geometry та одним викликом
``cascade_windows()`` перевіряє normal state, client visibility, однаковий
розмір frames, послідовні cascade offsets і межі актуального MDI viewport.
Сценарій B повторює Cascade лише як idempotency measurement, а сценарій C
штатно мінімізує два WSP і перевіряє їх одноразове відновлення Cascade.

Runner не викликає Tile, maximize, ручний resize після контрольного Cascade,
``repaint()`` або ``update()``. Він не запускає WSP runtime, broker requests,
Replay чи Candidate F і не змінює production, Session користувача, MD7 або
localization. RED формується після друку factual geometry та конкретних
порушень cascade contract, а не через випадковий Qt exception.
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

TEST_ID = "T107-09"
MODE = "RM107_T107_09_MDI_CASCADE_GEOMETRY_RESTORE_TEST_ONLY"
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


def _geometry_text(geometries: tuple[QRect, ...]) -> str:
    """Сформувати компактний factual geometry список для RED evidence."""
    return ";".join(
        f"{geometry.x()},{geometry.y()},{geometry.width()},{geometry.height()}"
        for geometry in geometries
    )


def _offset_text(geometries: tuple[QRect, ...]) -> str:
    """Сформувати factual список cascade offsets."""
    offsets = _ordered_offsets(geometries)
    return ";".join(f"{offset.x()},{offset.y()}" for offset in offsets)


def main() -> None:
    """Виміряти три Cascade сценарії без layout workaround."""
    app = QApplication.instance() or QApplication([])
    with TemporaryDirectory() as temp_dir:
        repository = SessionRepository(Path(temp_dir) / "Session")
        controller = AlgorithmWorkspaceController(repository)
        area = AlgorithmWorkspaceArea(controller=controller)
        area.resize(1280, 820)
        area.show()
        _process_events(app)

        workspace_specs = (
            ("CTRADER", "T1070901", WORKSPACE_ACCOUNT_MODE_DEMO, "EURUSD", "M15"),
            ("CTRADER", "T1070902", WORKSPACE_ACCOUNT_MODE_DEMO, "EURUSD", "M1"),
            ("CTRADER", "T1070903", WORKSPACE_ACCOUNT_MODE_DEMO, "GBPUSD", "M15"),
            ("IB", "T1070904", WORKSPACE_ACCOUNT_MODE_PAPER, "EURUSD", "M15"),
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
        _process_events(app)

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
        first_cascade_layout_correct = bool(
            first_cascade_frames_visible
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
        second_cascade_geometry_stable = second_geometries == first_geometries
        second_cascade_required = not second_cascade_geometry_stable

        minimized_subwindows = typed_subwindows[:2]
        minimized_windows = typed_windows[:2]
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
        minimized_workspaces_restored_by_cascade = all(
            not subwindow.isMinimized() for subwindow in minimized_subwindows
        )
        post_minimize_cascade_content_visible = all(
            _content_visible(window) for window in minimized_windows
        )
        post_minimize_cascade_sizes_normalized = _sizes_normalized(
            post_minimize_geometries
        )
        post_minimize_cascade_offsets_valid = _offsets_valid(
            post_minimize_geometries
        )
        post_minimize_cascade_within_viewport = _within_viewport(
            post_minimize_geometries,
            viewport,
        )
        post_minimize_cascade_correct = bool(
            minimized_workspaces_restored_by_cascade
            and post_minimize_cascade_content_visible
            and post_minimize_cascade_sizes_normalized
            and post_minimize_cascade_offsets_valid
            and post_minimize_cascade_within_viewport
        )
        tile_required_to_recover = not post_minimize_cascade_correct
        mdi_cascade_contract_satisfied = bool(
            first_cascade_layout_correct
            and second_cascade_geometry_stable
            and not second_cascade_required
            and minimized_before_cascade == 2
            and post_minimize_cascade_correct
            and not tile_required_to_recover
        )

        area.hide()
        area.deleteLater()
        _process_events(app)

    contract_violations: list[str] = []
    if not first_cascade_frames_visible:
        contract_violations.append("first Cascade hid one or more WSP frames")
    if not first_cascade_not_minimized:
        contract_violations.append("first Cascade left a WSP minimized")
    if not first_cascade_content_visible:
        contract_violations.append("first Cascade hid WSP client content")
    if not first_cascade_sizes_normalized:
        contract_violations.append("first Cascade produced different WSP sizes")
    if not first_cascade_offsets_valid:
        contract_violations.append("first Cascade offsets are not uniform and diagonal")
    if not first_cascade_within_viewport:
        contract_violations.append("first Cascade geometry exceeds MDI viewport")
    if not second_cascade_geometry_stable:
        contract_violations.append("second Cascade changed the geometry scheme")
    if minimized_before_cascade != 2:
        contract_violations.append("two WSP were not minimized before Cascade")
    if not minimized_workspaces_restored_by_cascade:
        contract_violations.append("Cascade did not restore minimized WSP state")
    if not post_minimize_cascade_content_visible:
        contract_violations.append("restored WSP client content is not visible")
    if not post_minimize_cascade_sizes_normalized:
        contract_violations.append("post-minimize Cascade produced different WSP sizes")
    if not post_minimize_cascade_offsets_valid:
        contract_violations.append("post-minimize Cascade offsets are invalid")
    if not post_minimize_cascade_within_viewport:
        contract_violations.append("post-minimize Cascade exceeds MDI viewport")

    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    print(f"workspace_count={WORKSPACE_COUNT}")
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
    print(f"first_cascade_layout_correct={first_cascade_layout_correct}")
    print(f"second_cascade_geometries={_geometry_text(second_geometries)}")
    print(f"second_cascade_geometry_stable={second_cascade_geometry_stable}")
    print(f"second_cascade_required={second_cascade_required}")
    print(f"minimized_before_cascade={minimized_before_cascade}")
    print(
        "minimized_workspaces_restored_by_cascade="
        f"{minimized_workspaces_restored_by_cascade}"
    )
    print(
        "post_minimize_cascade_content_visible="
        f"{post_minimize_cascade_content_visible}"
    )
    print(
        "post_minimize_cascade_geometries="
        f"{_geometry_text(post_minimize_geometries)}"
    )
    print(
        "post_minimize_cascade_offsets="
        f"{_offset_text(post_minimize_geometries)}"
    )
    print(
        "post_minimize_cascade_sizes_normalized="
        f"{post_minimize_cascade_sizes_normalized}"
    )
    print(
        "post_minimize_cascade_offsets_valid="
        f"{post_minimize_cascade_offsets_valid}"
    )
    print(
        "post_minimize_cascade_within_viewport="
        f"{post_minimize_cascade_within_viewport}"
    )
    print(f"tile_required_to_recover={tile_required_to_recover}")
    print(f"mdi_cascade_contract_satisfied={mdi_cascade_contract_satisfied}")
    print("broker_requests=0")
    print("broker_execution_attempted=False")
    print("production_logic_changed=False")

    if not mdi_cascade_contract_satisfied:
        print(f"contract_violations={' | '.join(contract_violations)}")
        print("T107_09_MDI_CASCADE_GEOMETRY_RESTORE=RED")
        raise AssertionError(
            "MDI Cascade geometry/restore contract violated: "
            + "; ".join(contract_violations)
        )

    print("contract_violations=NONE")
    print("T107_09_MDI_CASCADE_GEOMETRY_RESTORE=GREEN")


if __name__ == "__main__":
    main()
