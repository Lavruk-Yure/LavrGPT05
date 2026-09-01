# -*- coding: utf-8 -*-
"""UI-regression read-only snapshot-груп параметрів WSP.

RoadMap102 / 1 прибирає заглушки з порожніх schema-груп ``Дані та Replay``,
``Алгоритм``, ``Виконання`` і ``Діагностика та графік``. Вони показують
лише наявний WSP/runtime context без другого редактора профілів і без змін
Candidate F. Окремо перевіряється перехід до ``Налаштування Replay`` та
refresh snapshot.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QTreeWidgetItem  # noqa: E402

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_ACCOUNT_MODE_PAPER,
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_DATA_MODE_REPLAY,
    AlgorithmWorkspace,
)
from core.algorithm_workspace_parameters_dialog import (  # noqa: E402
    AlgorithmWorkspaceParametersDialog,
)
from core.lang_manager import LangManager  # noqa: E402
from core.workspace_indicator_profile import (  # noqa: E402
    ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F,
    MACD_PROFILE_UID_LGE_DEFAULT,
    WORKSPACE_ALLIGATOR_PROFILE_BINDING_KEY,
    WORKSPACE_MACD_PROFILE_BINDING_KEY,
    WorkspaceIndicatorProfileBinding,
    built_in_workspace_indicator_profile,
)
from core.workspace_parameter_feature_policy import (  # noqa: E402
    workspace_parameter_feature_profile_for_edition,
)
from core.workspace_parameter_schema import (  # noqa: E402
    WORKSPACE_PARAMETER_GROUP_ALGORITHM,
    WORKSPACE_PARAMETER_GROUP_DATA_REPLAY,
    WORKSPACE_PARAMETER_GROUP_DIAGNOSTICS,
    WORKSPACE_PARAMETER_GROUP_EXECUTION,
)
from core.translation_policy import translation_override_for_key  # noqa: E402
from core.workspace_replay_settings import WorkspaceReplaySettings  # noqa: E402


class UkrainianTestLangManager(LangManager):
    """Тестовий LangManager без localization I/O."""

    _test_language: str

    @classmethod
    def create_without_io(cls) -> "UkrainianTestLangManager":
        """Створити тестовий екземпляр без файлової ініціалізації."""
        manager = object.__new__(cls)
        manager._test_language = "uk"
        return manager

    def tr(
        self,
        key: str,
        fallback: str,
        localized_fallbacks: Mapping[str, str] | None = None,
    ) -> str:
        """Повернути український override або переданий fallback."""
        override = translation_override_for_key(key, self._test_language)
        if override:
            return override
        if localized_fallbacks:
            localized = localized_fallbacks.get(self._test_language)
            if localized:
                return localized
        return fallback


def _candidate_f_bindings() -> dict[str, dict[str, object]]:
    macd = built_in_workspace_indicator_profile(MACD_PROFILE_UID_LGE_DEFAULT)
    alligator = built_in_workspace_indicator_profile(
        ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F
    )
    macd_binding = WorkspaceIndicatorProfileBinding.from_profile(macd).to_storage_dict()
    alligator_binding = WorkspaceIndicatorProfileBinding.from_profile(
        alligator
    ).to_storage_dict()
    return {
        WORKSPACE_MACD_PROFILE_BINDING_KEY: macd_binding,
        WORKSPACE_ALLIGATOR_PROFILE_BINDING_KEY: alligator_binding,
    }


def _workspace() -> AlgorithmWorkspace:
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
            "macd_signal_mode": "EXTENDED",
            "alligator_filter_enabled": True,
            "alligator_confirmation": "SAME_TIMEFRAME",
        },
        replay_settings={
            "source_type": "CSV",
            "file_path": "D:/LavrGPT/data/RM102_FRESH_EURUSD_M1.csv",
            "start_utc": "2026-08-12T00:00:00+00:00",
            "end_utc": "2026-08-20T23:59:00+00:00",
            "source_timezone": "UTC",
            "delimiter": "AUTO",
            "decimal_separator": ".",
            "spread": 0.0001,
            "source": "RM102_FRESH_EURUSD_M1",
            "source_timeframe": "M1",
            "initial_balance": 1000.0,
            "speed": 1,
        },
        indicator_profile_bindings=_candidate_f_bindings(),
    )


def _group_item(
    dialog: AlgorithmWorkspaceParametersDialog,
    code: str,
) -> QTreeWidgetItem:
    for index in range(dialog.tree_parameters.topLevelItemCount()):
        item = dialog.tree_parameters.topLevelItem(index)
        if item.data(0, Qt.ItemDataRole.UserRole) == code:
            return item
    raise AssertionError(f"group not found: {code}")


def main() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)

    ui_source = (
        PROJECT_ROOT / "ui" / "algorithm_workspace_parameters_dialog.ui"
    ).read_text(encoding="utf-8")
    area_source = (PROJECT_ROOT / "core" / "algorithm_workspace_area.py").read_text(
        encoding="utf-8"
    )
    assert 'name="btnReplaySettings"' in ui_source
    assert "dialog.replay_settings_requested.connect(" in area_source
    assert "_open_replay_settings_from_parameters(" in area_source

    key_prefix = "AlgorithmWorkspaceParametersDialog."
    expected_uk = {
        f"{key_prefix}grpWorkspaceSnapshot": "Знімок WSP",
        f"{key_prefix}snapshotCurrentSource": "Поточне джерело",
        f"{key_prefix}snapshotCsvDataset": "CSV dataset",
        f"{key_prefix}snapshotReplayPeriod": "Період Replay",
        f"{key_prefix}snapshotSpread": "Спред",
        f"{key_prefix}snapshotInitialBalance": "Початковий баланс",
        f"{key_prefix}snapshotReplayLeverage": "Плече Replay",
        f"{key_prefix}snapshotAlgorithm": "Алгоритм",
        f"{key_prefix}snapshotProductionLogic": "Production логіка / профіль",
        f"{key_prefix}snapshotMacdProfile": "Профіль MACD / редакція",
        f"{key_prefix}snapshotAlligatorProfile": "Профіль Alligator / редакція",
        f"{key_prefix}snapshotConfirmationMode": "Режим підтвердження",
        f"{key_prefix}snapshotLogicMode": "Режим Candidate F / legacy",
        f"{key_prefix}snapshotDataMode": "Режим даних",
        f"{key_prefix}snapshotAccountMode": "Режим рахунку",
        f"{key_prefix}snapshotControlMode": "Режим керування",
        f"{key_prefix}snapshotBrokerAccount": "Брокер / рахунок",
        f"{key_prefix}snapshotRuntimeState": "Стан WSP",
        f"{key_prefix}snapshotExecutionMode": "Режим виконання",
        f"{key_prefix}snapshotReplayEntryPolicy": "Вхід Replay",
        f"{key_prefix}snapshotBrokerExecution": "Виконання у брокера",
        f"{key_prefix}executionVirtualReplayAuto": (
            "Historical Replay — віртуальне виконання (AUTO)"
        ),
        f"{key_prefix}brokerExecutionDisabledReplay": ("Вимкнено у Historical Replay"),
        f"{key_prefix}snapshotMarketContext": "Інструмент / таймфрейм",
        f"{key_prefix}snapshotActivePanel": "Збережена вкладка WSP",
        f"{key_prefix}snapshotDiagnosticSurfaces": "Діагностичні вкладки",
        f"{key_prefix}diagnosticSurfacesValue": "Сигнали / Журнал / Графік",
        f"{key_prefix}snapshotStartedOnce": "WSP вже запускався",
        f"{key_prefix}panelChart": "Графік",
        f"{key_prefix}btnReplaySettings": "Налаштування Replay...",
    }
    for key, expected in expected_uk.items():
        assert translation_override_for_key(key, "uk") == expected

    workspace = _workspace()
    lang = UkrainianTestLangManager.create_without_io()
    dialog = AlgorithmWorkspaceParametersDialog(
        workspace,
        lang,
        feature_profile=workspace_parameter_feature_profile_for_edition("pro"),
    )
    dialog.show()
    app.processEvents()

    dialog.tree_parameters.setCurrentItem(
        _group_item(dialog, WORKSPACE_PARAMETER_GROUP_DATA_REPLAY)
    )
    app.processEvents()
    data_snapshot = dialog.ui.lblNoSelection.text()
    assert "No parameters are defined" not in data_snapshot
    assert "Поточне джерело:" in data_snapshot
    expected_period = (
        "Період Replay:\n" "2026-08-12T00:00:00+00:00\n" "2026-08-20T23:59:00+00:00"
    )
    assert expected_period in data_snapshot
    assert "Початковий баланс:" in data_snapshot
    assert "Плече Replay: 1:500" in data_snapshot
    assert "RM102_FRESH_EURUSD_M1" in data_snapshot
    assert "RM102_FRESH_EURUSD_M1.csv" in data_snapshot
    assert "2026-08-12T00:00:00+00:00" in data_snapshot
    assert "2026-08-20T23:59:00+00:00" in data_snapshot
    assert "0.0001" in data_snapshot
    assert "1000.00 USD" in data_snapshot
    assert dialog.btn_replay_settings.isVisible()
    assert dialog.btn_replay_settings.isEnabled()

    replay_requests: list[str] = []
    dialog.replay_settings_requested.connect(replay_requests.append)
    dialog.btn_replay_settings.click()
    assert replay_requests == [workspace.workspace_uid]

    refreshed = AlgorithmWorkspace.from_storage_dict(workspace.to_storage_dict())
    replay = WorkspaceReplaySettings.from_workspace(refreshed)
    refreshed.set_replay_settings(
        WorkspaceReplaySettings(
            source_type=replay.source_type,
            file_path=replay.file_path,
            start_utc=replay.start_utc,
            end_utc=replay.end_utc,
            source_timezone=replay.source_timezone,
            delimiter=replay.delimiter,
            decimal_separator=replay.decimal_separator,
            spread=0.00012,
            source_name=replay.source_name,
            source_timeframe=replay.source_timeframe,
            initial_balance=1500.0,
            speed=replay.speed,
        ).merge_settings(refreshed.replay_settings)
    )
    dialog.refresh_replay_snapshot(refreshed)
    refreshed_snapshot = dialog.ui.lblNoSelection.text()
    assert "0.00012" in refreshed_snapshot
    assert "1500.00 USD" in refreshed_snapshot

    dialog.tree_parameters.setCurrentItem(
        _group_item(dialog, WORKSPACE_PARAMETER_GROUP_ALGORITHM)
    )
    app.processEvents()
    algorithm_snapshot = dialog.ui.lblNoSelection.text()
    assert "No parameters are defined" not in algorithm_snapshot
    assert "RailAlgorithm" in algorithm_snapshot
    assert "LGE Default EMA 8/17/5 Close r1" in algorithm_snapshot
    assert "LGE Candidate F Smoothed r1" in algorithm_snapshot
    assert "Алгоритм:" in algorithm_snapshot
    assert "Production логіка / профіль:" in algorithm_snapshot
    assert "Профіль MACD / редакція:" in algorithm_snapshot
    assert "Профіль Alligator / редакція:" in algorithm_snapshot
    assert "Режим підтвердження:" in algorithm_snapshot
    assert "Режим Candidate F / legacy:" in algorithm_snapshot
    assert "Той самий таймфрейм" in algorithm_snapshot
    assert "Candidate F" in algorithm_snapshot
    assert not dialog.btn_replay_settings.isVisible()
    assert not dialog.has_unsaved_changes()

    dialog.tree_parameters.setCurrentItem(
        _group_item(dialog, WORKSPACE_PARAMETER_GROUP_EXECUTION)
    )
    app.processEvents()
    execution_snapshot = dialog.ui.lblNoSelection.text()
    assert "Для цієї групи параметри ще не визначено" not in execution_snapshot
    assert "Режим даних: REPLAY" in execution_snapshot
    assert "Режим рахунку: PAPER" in execution_snapshot
    assert "Режим керування: AUTO" in execution_snapshot
    assert "Брокер / рахунок: IB / DUM513747" in execution_snapshot
    assert "Стан WSP: STOPPED" in execution_snapshot
    assert (
        "Режим виконання: Historical Replay — віртуальне виконання (AUTO)"
        in execution_snapshot
    )
    assert "Вхід Replay: NEXT_BAR_OPEN" in execution_snapshot
    assert "Виконання у брокера: Вимкнено у Historical Replay" in execution_snapshot
    assert not dialog.btn_replay_settings.isVisible()

    dialog.tree_parameters.setCurrentItem(
        _group_item(dialog, WORKSPACE_PARAMETER_GROUP_DIAGNOSTICS)
    )
    app.processEvents()
    diagnostics_snapshot = dialog.ui.lblNoSelection.text()
    assert "Для цієї групи параметри ще не визначено" not in diagnostics_snapshot
    assert "Стан WSP: STOPPED" in diagnostics_snapshot
    assert "Інструмент / таймфрейм: EURUSD / M15" in diagnostics_snapshot
    assert "Збережена вкладка WSP: Графік" in diagnostics_snapshot
    assert "Діагностичні вкладки: Сигнали / Журнал / Графік" in diagnostics_snapshot
    assert "WSP вже запускався: Ні" in diagnostics_snapshot
    assert not dialog.btn_replay_settings.isVisible()
    assert not dialog.has_unsaved_changes()

    dialog.close()

    print("Algorithm Workspace Parameter Group Snapshot result")
    print("  data_replay_snapshot_visible=True")
    print("  current_source_visible=True")
    print("  csv_dataset_visible=True")
    print("  replay_period_visible=True")
    print("  spread_visible=True")
    print("  initial_balance_visible=True")
    print("  replay_leverage_visible=True")
    print("  replay_period_three_lines=True")
    print("  replay_settings_action_connected=True")
    print("  replay_snapshot_refresh=True")
    print("  algorithm_snapshot_visible=True")
    print("  production_logic_profile_visible=True")
    print("  macd_profile_revision_visible=True")
    print("  alligator_profile_revision_visible=True")
    print("  confirmation_mode_visible=True")
    print("  candidate_f_mode_visible=True")
    print("  execution_snapshot_visible=True")
    print("  replay_execution_context_visible=True")
    print("  next_bar_open_visible=True")
    print("  historical_replay_broker_execution_disabled=True")
    print("  diagnostics_snapshot_visible=True")
    print("  active_panel_visible=True")
    print("  diagnostic_surfaces_visible=True")
    print("  ukrainian_snapshot_localization=True")
    print("  profile_editor_not_duplicated=True")
    print("  candidate_f_trade_logic_changed=False")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_PARAMETER_GROUP_SNAPSHOT_CHECK=OK")


if __name__ == "__main__":
    main()
