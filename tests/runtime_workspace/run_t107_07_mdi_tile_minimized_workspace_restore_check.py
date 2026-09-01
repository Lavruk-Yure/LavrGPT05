"""run_t107_07_mdi_tile_minimized_workspace_restore_check.py — T107-07.

TEST_ONLY offscreen Qt regression створює чотири реальні WSP через
``AlgorithmWorkspaceArea`` і штатні ``AlgorithmMdiSubWindow``. Сценарій A
накладає початкові frames, один раз викликає production ``tile_windows()`` та
вимірює visibility, geometry, overlap і покриття MDI viewport. Сценарій B
мінімізує два WSP через ``showMinimized()``, один раз викликає той самий Tile і
перевіряє frame/client visibility та ненульовий розмір центрального content.

Runner навмисно не виконує другий Tile, maximize/restore, resize, update або
repaint після контрольного виклику. Він не запускає WSP runtime, broker requests,
Replay чи Candidate F і не змінює production, Session користувача, MD7 або
localization. RED формується лише після друку конкретних порушень layout
contract, а не через випадковий Qt exception.
"""

from __future__ import annotations

import os
import sys
from itertools import combinations
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect  # noqa: E402
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

TEST_ID = "T107-07"
MODE = "RM107_T107_07_MDI_TILE_MINIMIZED_WORKSPACE_RESTORE_TEST_ONLY"
WORKSPACE_COUNT = 4


def _process_events(app: QApplication) -> None:
    """Дати Qt завершити один production layout/state transition."""
    app.processEvents()
    app.processEvents()


def _geometries_valid(
    geometries: tuple[QRect, ...],
    viewport: QRect,
) -> bool:
    """Перевірити додатний розмір і перебування frames у MDI viewport."""
    return all(
        geometry.isValid()
        and geometry.width() > 0
        and geometry.height() > 0
        and viewport.contains(geometry)
        for geometry in geometries
    )


def _geometries_do_not_overlap(geometries: tuple[QRect, ...]) -> bool:
    """Повернути True, якщо tiled frames не мають спільної площі."""
    return all(
        first.intersected(second).isEmpty()
        for first, second in combinations(geometries, 2)
    )


def _tiled_area_expected(
    geometries: tuple[QRect, ...],
    viewport: QRect,
) -> bool:
    """Перевірити 2x2 bounds, близькі розміри й суттєве покриття viewport."""
    if len(geometries) != WORKSPACE_COUNT or viewport.width() <= 0:
        return False
    left = min(geometry.left() for geometry in geometries)
    top = min(geometry.top() for geometry in geometries)
    right = max(geometry.right() for geometry in geometries)
    bottom = max(geometry.bottom() for geometry in geometries)
    widths = tuple(geometry.width() for geometry in geometries)
    heights = tuple(geometry.height() for geometry in geometries)
    covered_area = sum(geometry.width() * geometry.height() for geometry in geometries)
    viewport_area = viewport.width() * viewport.height()
    return bool(
        left == viewport.left()
        and top == viewport.top()
        and right == viewport.right()
        and bottom == viewport.bottom()
        and max(widths) - min(widths) <= 1
        and max(heights) - min(heights) <= 1
        and covered_area >= viewport_area * 0.95
    )


def _content_visible(window: AlgorithmWorkspaceWindow) -> bool:
    """Перевірити фактичну visibility клієнта й активної центральної вкладки."""
    current_content = window.tabs_workspace.currentWidget()
    return bool(
        current_content is not None
        and window.isVisible()
        and window.tabs_workspace.isVisible()
        and current_content.isVisible()
        and not window.visibleRegion().isEmpty()
        and not current_content.visibleRegion().isEmpty()
    )


def _content_nonzero_size(window: AlgorithmWorkspaceWindow) -> bool:
    """Перевірити ненульову geometry WSP client і центрального content."""
    current_content = window.tabs_workspace.currentWidget()
    return bool(
        current_content is not None
        and window.width() > 0
        and window.height() > 0
        and current_content.width() > 0
        and current_content.height() > 0
    )


def _geometry_text(geometries: tuple[QRect, ...]) -> str:
    """Сформувати компактний factual geometry список для RED evidence."""
    return ";".join(
        f"{geometry.x()},{geometry.y()},{geometry.width()},{geometry.height()}"
        for geometry in geometries
    )


def main() -> None:
    """Виміряти перший Tile та один Tile після minimize без лікувальних дій."""
    app = QApplication.instance() or QApplication([])
    with TemporaryDirectory() as temp_dir:
        repository = SessionRepository(Path(temp_dir) / "Session")
        controller = AlgorithmWorkspaceController(repository)
        area = AlgorithmWorkspaceArea(controller=controller)
        area.resize(1280, 820)
        area.show()
        _process_events(app)

        workspace_specs = (
            ("CTRADER", "T1070701", WORKSPACE_ACCOUNT_MODE_DEMO, "EURUSD", "M15"),
            ("CTRADER", "T1070702", WORKSPACE_ACCOUNT_MODE_DEMO, "EURUSD", "M1"),
            ("CTRADER", "T1070703", WORKSPACE_ACCOUNT_MODE_DEMO, "GBPUSD", "M15"),
            ("IB", "T1070704", WORKSPACE_ACCOUNT_MODE_PAPER, "EURUSD", "M15"),
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

        overlap_geometry = QRect(24, 24, 720, 480)
        for subwindow in typed_subwindows:
            subwindow.apply_system_geometry(overlap_geometry)
        _process_events(app)
        overlapping_before_tile = not _geometries_do_not_overlap(
            tuple(QRect(subwindow.geometry()) for subwindow in typed_subwindows)
        )

        area.tile_windows()
        _process_events(app)
        viewport = QRect(area.mdi.viewport().rect())
        first_tile_geometries = tuple(
            QRect(subwindow.geometry()) for subwindow in typed_subwindows
        )
        first_tile_frames_visible = all(
            subwindow.isVisible() for subwindow in typed_subwindows
        )
        first_tile_not_minimized = all(
            not subwindow.isMinimized() for subwindow in typed_subwindows
        )
        first_tile_geometries_valid = _geometries_valid(
            first_tile_geometries,
            viewport,
        )
        first_tile_non_overlapping = _geometries_do_not_overlap(first_tile_geometries)
        first_tile_expected_area = _tiled_area_expected(
            first_tile_geometries,
            viewport,
        )
        first_tile_layout_correct = bool(
            overlapping_before_tile
            and first_tile_frames_visible
            and first_tile_not_minimized
            and first_tile_geometries_valid
            and first_tile_non_overlapping
            and first_tile_expected_area
        )
        second_tile_required = not first_tile_layout_correct

        minimized_subwindows = typed_subwindows[:2]
        minimized_windows = typed_windows[:2]
        for subwindow in minimized_subwindows:
            subwindow.showMinimized()
        _process_events(app)
        minimized_before_tile = sum(
            subwindow.isMinimized() for subwindow in typed_subwindows
        )

        area.tile_windows()
        _process_events(app)
        restored_geometries = tuple(
            QRect(subwindow.geometry()) for subwindow in typed_subwindows
        )
        minimized_workspaces_restored_by_tile = all(
            not subwindow.isMinimized() for subwindow in minimized_subwindows
        )
        restored_workspace_frames_visible = all(
            subwindow.isVisible() for subwindow in minimized_subwindows
        )
        restored_workspace_content_visible = all(
            _content_visible(window) for window in minimized_windows
        )
        restored_workspace_content_nonzero_size = all(
            _content_nonzero_size(window) for window in minimized_windows
        )
        post_minimize_tile_layout_valid = bool(
            _geometries_valid(restored_geometries, viewport)
            and _geometries_do_not_overlap(restored_geometries)
            and _tiled_area_expected(restored_geometries, viewport)
        )
        manual_maximize_restore_required = not bool(
            minimized_workspaces_restored_by_tile
            and restored_workspace_frames_visible
            and restored_workspace_content_visible
            and restored_workspace_content_nonzero_size
            and post_minimize_tile_layout_valid
        )
        mdi_layout_contract_satisfied = bool(
            first_tile_layout_correct
            and minimized_before_tile == 2
            and not second_tile_required
            and not manual_maximize_restore_required
        )

        area.hide()
        area.deleteLater()
        _process_events(app)

    contract_violations: list[str] = []
    if not first_tile_layout_correct:
        contract_violations.append("first production Tile did not form a valid grid")
    if minimized_before_tile != 2:
        contract_violations.append("two WSP were not minimized before Tile")
    if not minimized_workspaces_restored_by_tile:
        contract_violations.append("Tile did not restore minimized WSP state")
    if not restored_workspace_frames_visible:
        contract_violations.append("restored WSP frames are not visible")
    if not restored_workspace_content_visible:
        contract_violations.append("restored WSP client content is not visible")
    if not restored_workspace_content_nonzero_size:
        contract_violations.append("restored WSP client content has zero size")
    if not post_minimize_tile_layout_valid:
        contract_violations.append("post-minimize Tile geometry is invalid")

    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    print(f"workspace_count={WORKSPACE_COUNT}")
    print(
        "mdi_viewport_geometry="
        f"{viewport.x()},{viewport.y()},{viewport.width()},{viewport.height()}"
    )
    print(f"first_tile_geometries={_geometry_text(first_tile_geometries)}")
    print(f"first_tile_frames_visible={first_tile_frames_visible}")
    print(f"first_tile_not_minimized={first_tile_not_minimized}")
    print(f"first_tile_geometries_valid={first_tile_geometries_valid}")
    print(f"first_tile_non_overlapping={first_tile_non_overlapping}")
    print(f"first_tile_expected_area={first_tile_expected_area}")
    print(f"first_tile_layout_correct={first_tile_layout_correct}")
    print(f"second_tile_required={second_tile_required}")
    print(f"minimized_before_tile={minimized_before_tile}")
    print(
        "minimized_workspaces_restored_by_tile="
        f"{minimized_workspaces_restored_by_tile}"
    )
    print("restored_workspace_frames_visible=" f"{restored_workspace_frames_visible}")
    print("restored_workspace_content_visible=" f"{restored_workspace_content_visible}")
    print(
        "restored_workspace_content_nonzero_size="
        f"{restored_workspace_content_nonzero_size}"
    )
    print(f"post_minimize_tile_geometries={_geometry_text(restored_geometries)}")
    print(f"post_minimize_tile_layout_valid={post_minimize_tile_layout_valid}")
    print("manual_maximize_restore_required=" f"{manual_maximize_restore_required}")
    print(f"mdi_layout_contract_satisfied={mdi_layout_contract_satisfied}")
    print("broker_requests=0")
    print("broker_execution_attempted=False")
    print("production_logic_changed=False")

    if not mdi_layout_contract_satisfied:
        print(f"contract_violations={' | '.join(contract_violations)}")
        print("T107_07_MDI_TILE_MINIMIZED_WORKSPACE_RESTORE=RED")
        raise AssertionError(
            "MDI Tile/minimized workspace restore contract violated: "
            + "; ".join(contract_violations)
        )

    print("contract_violations=NONE")
    print("T107_07_MDI_TILE_MINIMIZED_WORKSPACE_RESTORE=GREEN")


if __name__ == "__main__":
    main()
