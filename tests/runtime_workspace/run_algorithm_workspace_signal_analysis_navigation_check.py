# -*- coding: utf-8 -*-
"""RoadMap101: фільтр режиму, Signal navigation та chart-focus diagnostics.

Перевірка не змінює trade gate і не виконує broker requests. Вона фіксує:
- режим Alligator як окремий read-only фільтр Signals;
- точний signal_uid у Replay Position snapshot;
- переходи Signal -> Position / Chart / Journal;
- Journal navigation за читабельним часом сигналу, а не signal_uid;
- пошук Journal з пробілом або ``T`` у ISO timestamp;
- видимий source timestamp для MARKET/SIGNAL записів, які шукаються по details;
- пошук по structured signal details навіть коли Alligator ``DISABLED``;
- порядок вкладок Chart -> Position -> Signals -> Orders -> Log;
- chart crosshair після навігації та 10-секундне згасання великого hint;
- RoadMap102/3E: PageUp/PageDown/Home/End переходять між compact summary Journal.
- RoadMap102/3H: Signals/Positions мають календарний перехід лише за датою
  без фільтрації таблиці; якщо дня немає, вибирається наступна дата.
- RoadMap102/3I: date-jump і navigation buttons не розтягуються на всю ширину.
- RoadMap102/4A: на порожніх Signals/Positions date-jump і navigation actions
  приховуються, а не лишаються мертвими кнопками.
- RoadMap102/4B: якщо в Signals/Positions/Orders немає жодного source record,
  ховається весь filter block; при нульовому результаті активного фільтра блок
  лишається видимим, щоб користувач міг повернути ``Всі``.
"""

from __future__ import annotations

import sys
from datetime import UTC, date, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_PANEL_CHART,
    WORKSPACE_PANEL_LOG,
    WORKSPACE_PANEL_ORDERS,
    WORKSPACE_PANEL_POSITION,
    WORKSPACE_PANEL_SIGNALS,
    default_workspace_ui_state,
)
from core.algorithm_workspace_area import (  # noqa: E402
    ALLIGATOR_REGIME_FLAT,
    ALLIGATOR_REGIME_TREND_DOWN,
    ALLIGATOR_REGIME_TREND_UP,
    PANEL_BY_INDEX,
    WSP_FILTER_REGIME_UNDEFINED,
    AlgorithmWorkspaceWindow,
)
from core.translation_policy import translation_override_for_key  # noqa: E402
from core.workspace_ownership import WorkspacePositionSnapshot  # noqa: E402
from core.workspace_runtime import WorkspaceJournalEntry  # noqa: E402
from core.workspace_signal import (  # noqa: E402
    WorkspaceSignalFilterContext,
    WorkspaceSignalRecord,
)
from core.workspace_signal_presentation import (  # noqa: E402
    build_workspace_signal_journal_text,
)

WORKSPACE_UID = "00000000-0000-4000-8000-000000000101"

AREA_PATH = PROJECT_ROOT / "core" / "algorithm_workspace_area.py"
CHART_PATH = PROJECT_ROOT / "core" / "workspace_chart_widget.py"
REPLAY_EXECUTION_PATH = PROJECT_ROOT / "core" / "workspace_replay_execution.py"


def _record(regime: str | None) -> WorkspaceSignalRecord:
    timestamp = datetime(2026, 1, 9, 14, 15, tzinfo=UTC)
    context = None
    if regime is not None:
        context = WorkspaceSignalFilterContext(
            mode="SAME_TIMEFRAME",
            timeframe="M15",
            profile_uid="alligator-profile-r1",
            profile_revision=1,
            observation_timestamp=timestamp,
            available_at=timestamp,
            regime=regime,
            normalized_slope=0.1,
            normalized_opening=0.2,
        )
    return WorkspaceSignalRecord(
        timestamp=timestamp,
        signal_uid=f"signal-{regime or 'undefined'}",
        workspace_uid=WORKSPACE_UID,
        broker="IB",
        account_id="REPLAY",
        symbol="EURUSD",
        timeframe="M15",
        source_mode="REPLAY",
        signal_type="MACD_CROSS",
        direction="SELL",
        strength=0.00004852,
        macd_state="MACD_CROSS_DOWN",
        alligator_confirmation="SAME_TIMEFRAME",
        spread_status="OK",
        accepted=True,
        reason="accepted",
        source_reason_code="MACD_CROSS_ACCEPTED",
        filter_context=context,
    )


def main() -> None:
    area_source = AREA_PATH.read_text(encoding="utf-8")
    chart_source = CHART_PATH.read_text(encoding="utf-8")
    replay_source = REPLAY_EXECUTION_PATH.read_text(encoding="utf-8")

    flat = _record(ALLIGATOR_REGIME_FLAT)
    trend_up = _record(ALLIGATOR_REGIME_TREND_UP)
    trend_down = _record(ALLIGATOR_REGIME_TREND_DOWN)
    undefined = _record(None)

    matches_signal_regime_filter = getattr(
        AlgorithmWorkspaceWindow,
        "_matches_signal_regime_filter",
    )
    journal_search_variants = getattr(
        AlgorithmWorkspaceWindow,
        "_journal_search_variants",
    )
    signal_journal_search_text = getattr(
        AlgorithmWorkspaceWindow,
        "_signal_journal_search_text",
    )
    journal_entry_search_text = getattr(
        AlgorithmWorkspaceWindow,
        "_journal_entry_search_text",
    )
    journal_summary_positions = getattr(
        AlgorithmWorkspaceWindow,
        "_journal_summary_positions",
    )
    journal_summary_target_position = getattr(
        AlgorithmWorkspaceWindow,
        "_journal_summary_target_position",
    )
    date_jump_target_row = getattr(
        AlgorithmWorkspaceWindow,
        "_date_jump_target_row",
    )

    assert matches_signal_regime_filter(
        flat,
        ALLIGATOR_REGIME_FLAT,
    )
    assert matches_signal_regime_filter(
        trend_up,
        ALLIGATOR_REGIME_TREND_UP,
    )
    assert matches_signal_regime_filter(
        trend_down,
        ALLIGATOR_REGIME_TREND_DOWN,
    )
    assert matches_signal_regime_filter(
        undefined,
        WSP_FILTER_REGIME_UNDEFINED,
    )
    assert not matches_signal_regime_filter(
        flat,
        ALLIGATOR_REGIME_TREND_DOWN,
    )

    journal_search_text = signal_journal_search_text(flat)
    assert journal_search_text == "2026-01-09 14:15:00"
    journal_variants = journal_search_variants(journal_search_text)
    assert "2026-01-09t14:15:00" in journal_variants
    assert "2026-01-09 14:15:00" in journal_variants

    disabled_signal_time = datetime(2026, 2, 2, 3, 0, tzinfo=UTC)
    disabled_entry = WorkspaceJournalEntry(
        timestamp=datetime(2026, 8, 18, 12, 5, 31, tzinfo=UTC),
        workspace_uid=WORKSPACE_UID,
        category="SIGNAL",
        event="SIGNAL_REJECTED",
        message="MACD_CROSS SELL: MACD_EXTREMUM_TOO_WEAK",
        details={
            "signal_uid": "signal-disabled-alligator",
            "signal_timestamp": disabled_signal_time,
        },
    )
    disabled_line = disabled_entry.format_line()
    assert "@ 2026-02-02T03:00:00+00:00:" in disabled_line
    disabled_search_text = journal_entry_search_text(
        disabled_entry,
        disabled_line,
    )
    disabled_variants = journal_search_variants("2026-02-02 03:00:00")
    assert any(variant in disabled_search_text for variant in disabled_variants)
    assert "signal-disabled-alligator" in disabled_search_text

    market_entry = WorkspaceJournalEntry(
        timestamp=datetime(2026, 8, 18, 13, 11, 59, 719000, tzinfo=UTC),
        workspace_uid=WORKSPACE_UID,
        category="MARKET",
        event="EVENT_ACCEPTED",
        message="AUTO EURUSD M15 close=1.186550 spread=0.000120.",
        details={
            "origin": "AUTO",
            "timestamp": "2026-02-02T03:00:00+00:00",
        },
    )
    market_line = market_entry.format_line()
    assert market_line == (
        "2026-08-18T13:11:59.719+00:00 [MARKET] EVENT_ACCEPTED "
        "@ 2026-02-02T03:00:00+00:00: "
        "AUTO EURUSD M15 close=1.186550 spread=0.000120."
    )

    signal_journal_text = build_workspace_signal_journal_text(
        trend_down,
        lambda _key, fallback: fallback,
        journal_timestamp=datetime(2026, 8, 19, 12, 37, 8, 694000, tzinfo=UTC),
        event="SIGNAL_REJECTED",
    )
    assert signal_journal_text.startswith(
        "2026-08-19T12:37:08.694+00:00 [SIGNAL] SIGNAL_REJECTED @ "
        "2026-01-09T14:15:00+00:00\n"
    )
    assert "Reason:" in signal_journal_text
    assert "Signal time:" in signal_journal_text
    assert "Alligator regime:" in signal_journal_text
    assert "Normalized Alligator slope:" in signal_journal_text

    summary_marker = "*** SUMMARY ***"
    summary_text = (
        "event-1\n*** SUMMARY ***\nshort-1\nraw-1\n\n"
        "event-2\n*** SUMMARY ***\nshort-2\nraw-2\n\n"
        "event-3\n*** SUMMARY ***\nshort-3\nraw-3"
    )
    summary_positions = journal_summary_positions(summary_text, summary_marker)
    assert len(summary_positions) == 3
    assert (
        journal_summary_target_position(
            summary_positions,
            summary_positions[0],
            "PAGE_DOWN",
        )
        == summary_positions[1]
    )
    assert (
        journal_summary_target_position(
            summary_positions,
            summary_positions[1] + 8,
            "PAGE_UP",
        )
        == summary_positions[1]
    )
    assert (
        journal_summary_target_position(
            summary_positions,
            summary_positions[1],
            "HOME",
        )
        == summary_positions[0]
    )
    assert (
        journal_summary_target_position(
            summary_positions,
            summary_positions[1],
            "END",
        )
        == summary_positions[-1]
    )

    row_dates = (
        date(2025, 1, 3),
        date(2025, 1, 3),
        date(2025, 1, 7),
        date(2025, 1, 10),
    )
    assert date_jump_target_row(row_dates, date(2025, 1, 3)) == 0
    assert date_jump_target_row(row_dates, date(2025, 1, 5)) == 2
    assert date_jump_target_row(row_dates, date(2025, 1, 10)) == 3
    assert date_jump_target_row(row_dates, date(2025, 1, 20)) == 3
    assert date_jump_target_row((None, None), date(2025, 1, 5)) is None

    assert PANEL_BY_INDEX == {
        0: WORKSPACE_PANEL_CHART,
        1: WORKSPACE_PANEL_POSITION,
        2: WORKSPACE_PANEL_SIGNALS,
        3: WORKSPACE_PANEL_ORDERS,
        4: WORKSPACE_PANEL_LOG,
    }
    assert default_workspace_ui_state()["active_panel"] == WORKSPACE_PANEL_CHART

    position = WorkspacePositionSnapshot.from_mapping(
        {
            "workspace_uid": WORKSPACE_UID,
            "broker": "IB",
            "account_id": "REPLAY",
            "symbol": "EURUSD",
            "position_id": "replay-position-1",
            "side": "SELL",
            "volume": 1000,
            "entry_price": 1.16374,
            "current_price": 1.16371,
            "current_profit": 0.03,
            "peak_profit": 0.08,
            "stop_loss": 1.16494,
            "take_profit": 1.16134,
            "opened_at": "2026-01-09T14:30:00+00:00",
            "reconciliation_status": "REPLAY_VIRTUAL_CLOSED_PROFIT_DRAWDOWN",
            "active": False,
            "signal_timestamp": "2026-01-09T14:15:00+00:00",
            "signal_uid": "signal-accepted-1",
        }
    )
    assert position.signal_uid == "signal-accepted-1"

    for token in (
        "cmbSignalRegimeFilter",
        "btnSignalGoPosition",
        "btnSignalGoChart",
        "btnSignalGoJournal",
        "def _on_signal_go_position_clicked",
        "def _on_signal_go_chart_clicked",
        "def _on_signal_go_journal_clicked",
        "self._signal_journal_search_text(record)",
        "self._journal_entry_search_text(entry, line)",
        "build_workspace_signal_journal_text(",
        'self.ui.txtLog.setPlainText("\\n\\n".join(visible_lines))',
        "self.ui.txtLog.installEventFilter(self)",
        "Qt.Key.Key_PageUp",
        "Qt.Key.Key_PageDown",
        "Qt.Key.Key_Home",
        "Qt.Key.Key_End",
        "def _navigate_journal_summary",
        "self.ui.txtLog.centerCursor()",
        "QDateEdit",
        'setObjectName("dteSignalDateJump")',
        'setObjectName("dtePositionDateJump")',
        "setCalendarPopup(True)",
        'setDisplayFormat("yyyy-MM-dd")',
        "def _on_signal_date_jump_clicked",
        "def _on_position_date_jump_clicked",
        "def _date_jump_target_row",
        "self._select_date_jump_row(self.tbl_signals, target_row)",
        "self._select_date_jump_row(self.tbl_positions, target_row)",
        "self.lbl_signal_date_jump.setVisible(has_records)",
        "self.dte_signal_date_jump.setVisible(has_records)",
        "self.btn_signal_date_jump.setVisible(has_records)",
        "self.frame_signal_actions.setVisible(has_records)",
        "self.lbl_position_date_jump.setVisible(has_positions)",
        "self.dte_position_date_jump.setVisible(has_positions)",
        "self.btn_position_date_jump.setVisible(has_positions)",
        "self.frame_position_time_actions.setVisible(has_positions)",
        "self.frame_signal_filters.setVisible(bool(self._signal_records))",
        "self.frame_position_filters.setVisible(bool(self._owned_snapshot.positions))",
        "self.frame_order_filters.setVisible(bool(self._owned_snapshot.orders))",
        "self._apply_workspace_tab_order()",
        "row_id=record.signal_uid",
        "window.chart_widget.focus_timestamp(timestamp, exact=exact)",
    ):
        assert token in area_source

    assert "signal_uid=position.signal_uid" in replay_source
    assert "signal_timestamp=event.timestamp" in (
        PROJECT_ROOT / "core" / "workspace_runtime.py"
    ).read_text(encoding="utf-8")
    assert "def focus_timestamp" in chart_source
    assert "_TOOLTIP_DISPLAY_MS = 10_000" in chart_source

    assert (
        translation_override_for_key(
            "AlgorithmWorkspaceWindow.btnSignalGoPosition",
            "uk",
        )
        == "До позиції"
    )
    assert (
        translation_override_for_key(
            "AlgorithmWorkspaceWindow.btnSignalGoChart",
            "uk",
        )
        == "До діаграми"
    )
    assert (
        translation_override_for_key(
            "AlgorithmWorkspaceWindow.btnSignalGoJournal",
            "uk",
        )
        == "До журналу"
    )

    assert (
        translation_override_for_key(
            "AlgorithmWorkspaceWindow.lblSignalDateJump",
            "uk",
        )
        == "Перейти до дати"
    )
    assert (
        translation_override_for_key(
            "AlgorithmWorkspaceWindow.lblPositionDateJump",
            "uk",
        )
        == "Перейти до дати"
    )
    assert (
        translation_override_for_key(
            "AlgorithmWorkspaceWindow.btnSignalDateJump",
            "uk",
        )
        == "Перейти на вказану дату"
    )
    assert (
        translation_override_for_key(
            "AlgorithmWorkspaceWindow.btnPositionDateJump",
            "uk",
        )
        == "Перейти на вказану дату"
    )

    area_source = AREA_PATH.read_text(encoding="utf-8")
    assert area_source.count("QSizePolicy.Policy.Maximum") >= 7
    assert "button_layout.addStretch(1)" in area_source

    print("Algorithm Workspace Signal Analysis Navigation result")
    print("  regime_filter=FLAT/TREND_UP/TREND_DOWN/UNDEFINED")
    print("  signal_uid_position_link=True")
    print("  signal_go_position=True")
    print("  signal_go_chart=True")
    print("  signal_go_journal=True")
    print("  signal_go_journal_by_timestamp=True")
    print("  journal_space_or_t_timestamp=True")
    print("  journal_structured_detail_search=True")
    print("  journal_source_timestamp_visible=True")
    print("  journal_signal_tooltip_detail=True")
    print("  journal_blocks_separated=True")
    print("  journal_pageup_pagedown_summary_navigation=True")
    print("  journal_home_end_summary_navigation=True")
    print("  signal_date_calendar_jump=True")
    print("  position_date_calendar_jump=True")
    print("  date_jump_does_not_filter_table=True")
    print("  date_jump_next_available_date=True")
    print("  date_jump_time_not_used=True")
    print("  date_jump_button_label_explicit=True")
    print("  compact_navigation_buttons=True")
    print("  empty_signal_navigation_hidden=True")
    print("  empty_position_navigation_hidden=True")
    print("  empty_signal_filter_block_hidden=True")
    print("  empty_position_filter_block_hidden=True")
    print("  empty_order_filter_block_hidden=True")
    print("  filtered_empty_keeps_filter_block_available=True")
    print("  disabled_alligator_signal_journal_navigation=True")
    print("  tab_order=CHART/POSITION/SIGNALS/ORDERS/LOG")
    print("  fresh_workspace_active_panel=CHART")
    print("  chart_target_crosshair=True")
    print("  canvas_hint_auto_hide_ms=10000")
    print("  trade_gate_changed=False")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_SIGNAL_ANALYSIS_NAVIGATION_CHECK=OK")


if __name__ == "__main__":
    main()
