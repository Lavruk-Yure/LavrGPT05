# -*- coding: utf-8 -*-
"""Runtime check for centralized LGE translation policy."""

from __future__ import annotations

import sys
import tempfile
import types
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import PySide6  # noqa: F401
except ModuleNotFoundError:

    class _FakeOpenModeFlag:
        ReadOnly = 1

    class _FakeQIODevice:
        OpenModeFlag = _FakeOpenModeFlag

    class _FakeQFile:
        def __init__(self, path: str) -> None:
            self._path = path

        def open(self, _mode: object) -> bool:
            _ = self._path
            return False

        @staticmethod
        def exists(_path: str) -> bool:
            return False

    class _FakeQIcon:
        def __init__(self, _path: str = "") -> None:
            pass

    qt_core = types.ModuleType("PySide6.QtCore")
    qt_core.QFile = _FakeQFile
    qt_core.QIODevice = _FakeQIODevice
    qt_gui = types.ModuleType("PySide6.QtGui")
    qt_gui.QIcon = _FakeQIcon
    pyside6 = types.ModuleType("PySide6")
    sys.modules["PySide6"] = pyside6
    sys.modules["PySide6.QtCore"] = qt_core
    sys.modules["PySide6.QtGui"] = qt_gui

from core.ai_translator import AITranslator  # noqa: E402
from core.lang_manager import LangManager  # noqa: E402
from core.translation_policy import (  # noqa: E402
    apply_central_translation_overrides,
    translation_context_for_key,
    translation_override_for_key,
)
import core.ai_translator as ai_translator_module  # noqa: E402


class _FakeDeepLResponse:
    status_code = 200
    text = '{"translations":[{"text":"Вимкнено"}]}'

    @staticmethod
    def json() -> dict[str, object]:
        return {"translations": [{"text": "Вимкнено"}]}


def _manager_without_files() -> LangManager:
    manager = object.__new__(LangManager)
    setattr(manager, "_strings", {"lang_active": {"code": "uk"}})
    setattr(manager, "_fallback", {})
    setattr(manager, "_languages", {"en": "English", "uk": "Українська"})
    setattr(manager, "_current_lang", "uk")
    setattr(manager, "save_strings_file", lambda: None)
    setattr(
        manager,
        "_auto_translate",
        lambda _target_lang, _text, **_kwargs: "",
    )
    return manager


def main() -> None:
    key = "AlgorithmWorkspaceParametersDialog.alligatorDisabled"
    context = translation_context_for_key(key, "uk")
    polish_context = translation_context_for_key(key, "pl")

    assert "algorithmic-trading workspace" in context
    assert "timeframe = таймфрейм" in context
    assert "Replay = Replay" in context
    assert "timeframe = interwał" in polish_context
    assert "drawdown = obsunięcie" in polish_context
    assert translation_override_for_key(key, "uk") == "Вимкнено"
    external_key = "OrdersPage.tooltipExternalExecutionResidual"
    persisted_external_key = "OrdersPage.tooltipPersistedExternalExecutionResidual"
    assert "точними виконаннями поза ордерами LGE" in str(
        translation_override_for_key(external_key, "uk")
    )
    assert "раніше підтвердженими точними доказами" in str(
        translation_override_for_key(persisted_external_key, "uk")
    )
    guidance_expectations = {
        "uk": ("Зовнішня експозиція", "помаранч"),
        "pl": ("Ekspozycja zewnętrzna", "pomarańcz"),
        "de": ("Externe Exposition", "orange"),
        "fr": ("Exposition externe", "orange"),
    }
    for guidance_key in (
        "AlgorithmWorkspaceWindow.safetyHoldTooltip",
        "AlgorithmWorkspaceJournal.safetyHoldActiveMessage",
        "AlgorithmWorkspaceArea.externalExposureDetectedMessage",
        "OrdersPage.msgExternalExposureOrderBlocked",
    ):
        for language, (row_type, color_word) in guidance_expectations.items():
            guidance = str(translation_override_for_key(guidance_key, language))
            assert "BROKER" in guidance
            assert row_type in guidance
            assert color_word not in guidance.casefold()

    manager = _manager_without_files()
    result = manager.tr(key, "Disabled")
    strings = getattr(manager, "_strings")
    assert result == "Вимкнено"
    assert strings[key] == {
        "en": "Disabled",
        "uk": "Вимкнено",
        "pl": "Wyłączone",
    }

    catalog: dict[str, object] = {
        "WorkspaceDataSource.broker": {
            "en": "Broker data",
            "uk": "Дані про брокера",
        },
        "AlgorithmWorkspaceWindow.btnHistoryDownload": {
            "en": "Download history",
            "uk": "Історична інформація",
        },
        "AlgorithmWorkspaceWindow.btnReplaySettings": {
            "en": "Replay settings",
            "uk": "Налаштування повтору",
        },
        "AlgorithmWorkspaceHistoryDownloadDialog.windowTitle": {
            "en": "Historical data download",
            "uk": "Завантаження даних",
        },
        "AlgorithmWorkspaceHistoryDownloadDialog.lblPlannedFile": {
            "en": "Planned CSV file:",
            "uk": "План:",
        },
        "AlgorithmWorkspaceHistoryDownloadDialog.btnUseForReplay": {
            "en": "Use for Replay",
            "uk": "Використати",
        },
        "AlgorithmWorkspaceHistoryDownloadDialog.coverageStartsLater": {
            "en": "Broker history starts later",
            "uk": "Історія починається пізніше",
        },
        "AlgorithmWorkspaceHistoryDownloadDialog.note": {
            "en": "The requested dates define the broker query.",
            "uk": "Дати визначають запит.",
        },
        "AlgorithmWorkspaceReplayDialog.btnDownloadIb": {
            "en": "Download from IB...",
            "uk": "Завантажити з інтерактивного брокера...",
        },
        "AlgorithmWorkspaceReplayDialog.downloadInProgress": {
            "en": "Downloading historical data from {broker}...",
            "uk": "Завантажую історію...",
        },
        "AlgorithmWorkspaceReplayDialog.messageOk": {
            "en": "OK",
            "uk": "OK",
        },
        "AlgorithmWorkspaceReplayDialog.ibInvalidEndDateTime": {
            "en": "IB rejected the request because the end date or time "
            "format is invalid.\n\nTechnical details: {details}",
            "uk": "IB request error: {details}",
        },
        "AlgorithmWorkspaceReplayDialog.lblSourceName": {
            "en": "Source label:",
            "uk": "Оригінальний текст:",
        },
        "AlgorithmWorkspaceReplayDialog.grpDownloadRange": {
            "en": "History download period",
            "uk": "Період історії",
        },
        "AlgorithmWorkspaceReplayDialog.lblDownloadStartDate": {
            "en": "Start date:",
            "uk": "Початок:",
        },
        "AlgorithmWorkspaceReplayDialog.lblDownloadEndDate": {
            "en": "End date:",
            "uk": "Кінець:",
        },
        "AlgorithmWorkspaceReplayDialog.lblDownloadTimezone": {
            "en": "Download date time zone:",
            "uk": "Часовий пояс:",
        },
        "AlgorithmWorkspaceReplayDialog.downloadTimezoneInvalid": {
            "en": "Unknown history download time zone: {timezone}.",
            "uk": "Невідомий часовий пояс: {timezone}.",
        },
        "AlgorithmWorkspaceReplayDialog.grpRange": {
            "en": "Replay test period and time zone",
            "uk": "Період Replay",
        },
        "AlgorithmWorkspaceReplayDialog.chkStartEnabled": {
            "en": "Use test start UTC:",
            "uk": "Використовуйте час за UTC:",
        },
        "AlgorithmWorkspaceReplayDialog.chkEndEnabled": {
            "en": "Use test end UTC:",
            "uk": "Завершення UTC:",
        },
        "AlgorithmWorkspaceReplayDialog.note": {
            "en": "The Replay test period filters accepted CSV rows.",
            "uk": "Фільтр періоду.",
        },
        "AlgorithmWorkspaceReplayDialog.delimiterTab": {
            "en": "Tab",
            "uk": "Вкладка",
        },
        "AlgorithmWorkspaceWindow.tabPosition": {
            "en": "Position",
            "uk": "Посада",
        },
        "AlgorithmWorkspaceState.running": {
            "en": "RUNNING",
            "uk": "Біг",
        },
        "AlgorithmWorkspaceWindow.replayConfiguredTooltip": {
            "en": "Historical Replay configured: {source}",
            "uk": "Історичний повтор налаштовано: {source}",
        },
        "AlgorithmReplayState.completed": {
            "en": "COMPLETED",
            "uk": "Завершено",
        },
        "AlgorithmWorkspaceStartupPhase.warmup": {
            "en": "WARMUP",
            "uk": "Розминка",
        },
        "CTraderConnectionDialog.btnClose": {
            "en": "Close",
            "uk": "Скасувати",
        },
        "IBConnectionDialog.btnClose": {
            "en": "Close",
            "uk": "Скасувати",
        },
        "SettingsPageTrading.btnClose": {
            "en": "Close",
            "uk": "Скасувати",
        },
        "Unrelated.key": {
            "en": "Unrelated",
            "uk": "Без змін",
        },
    }
    override_updates = apply_central_translation_overrides(catalog)
    history_button_entry = catalog["AlgorithmWorkspaceWindow.btnHistoryDownload"]
    replay_entry = catalog["AlgorithmWorkspaceWindow.btnReplaySettings"]
    assert isinstance(history_button_entry, dict)
    assert isinstance(replay_entry, dict)
    assert history_button_entry["uk"] == "Завантажити історію"
    assert history_button_entry["pl"] == "Pobierz historię"
    broker_data_entry = catalog["WorkspaceDataSource.broker"]
    assert isinstance(broker_data_entry, dict)
    assert broker_data_entry["uk"] == "Дані брокера"
    assert replay_entry["uk"] == "Налаштування Replay"
    assert replay_entry["pl"] == "Ustawienia Replay"
    history_title_entry = catalog["AlgorithmWorkspaceHistoryDownloadDialog.windowTitle"]
    history_planned_entry = catalog[
        "AlgorithmWorkspaceHistoryDownloadDialog.lblPlannedFile"
    ]
    history_replay_entry = catalog[
        "AlgorithmWorkspaceHistoryDownloadDialog.btnUseForReplay"
    ]
    history_coverage_entry = catalog[
        "AlgorithmWorkspaceHistoryDownloadDialog.coverageStartsLater"
    ]
    history_note_entry = catalog["AlgorithmWorkspaceHistoryDownloadDialog.note"]
    ib_download_entry = catalog["AlgorithmWorkspaceReplayDialog.btnDownloadIb"]
    download_progress_entry = catalog[
        "AlgorithmWorkspaceReplayDialog.downloadInProgress"
    ]
    message_ok_entry = catalog["AlgorithmWorkspaceReplayDialog.messageOk"]
    invalid_end_datetime_entry = catalog[
        "AlgorithmWorkspaceReplayDialog.ibInvalidEndDateTime"
    ]
    source_name_entry = catalog["AlgorithmWorkspaceReplayDialog.lblSourceName"]
    download_group_entry = catalog["AlgorithmWorkspaceReplayDialog.grpDownloadRange"]
    download_start_entry = catalog[
        "AlgorithmWorkspaceReplayDialog.lblDownloadStartDate"
    ]
    download_end_entry = catalog["AlgorithmWorkspaceReplayDialog.lblDownloadEndDate"]
    download_timezone_entry = catalog[
        "AlgorithmWorkspaceReplayDialog.lblDownloadTimezone"
    ]
    invalid_download_timezone_entry = catalog[
        "AlgorithmWorkspaceReplayDialog.downloadTimezoneInvalid"
    ]
    replay_range_entry = catalog["AlgorithmWorkspaceReplayDialog.grpRange"]
    start_entry = catalog["AlgorithmWorkspaceReplayDialog.chkStartEnabled"]
    end_entry = catalog["AlgorithmWorkspaceReplayDialog.chkEndEnabled"]
    note_entry = catalog["AlgorithmWorkspaceReplayDialog.note"]
    tab_entry = catalog["AlgorithmWorkspaceReplayDialog.delimiterTab"]
    position_entry = catalog["AlgorithmWorkspaceWindow.tabPosition"]
    running_entry = catalog["AlgorithmWorkspaceState.running"]
    configured_entry = catalog["AlgorithmWorkspaceWindow.replayConfiguredTooltip"]
    completed_entry = catalog["AlgorithmReplayState.completed"]
    warmup_entry = catalog["AlgorithmWorkspaceStartupPhase.warmup"]
    ctrader_close_entry = catalog["CTraderConnectionDialog.btnClose"]
    ib_close_entry = catalog["IBConnectionDialog.btnClose"]
    settings_close_entry = catalog["SettingsPageTrading.btnClose"]
    assert isinstance(history_title_entry, dict)
    assert isinstance(history_planned_entry, dict)
    assert isinstance(history_replay_entry, dict)
    assert isinstance(history_coverage_entry, dict)
    assert isinstance(history_note_entry, dict)
    assert isinstance(ib_download_entry, dict)
    assert isinstance(download_progress_entry, dict)
    assert isinstance(message_ok_entry, dict)
    assert isinstance(invalid_end_datetime_entry, dict)
    assert isinstance(source_name_entry, dict)
    assert isinstance(download_group_entry, dict)
    assert isinstance(download_start_entry, dict)
    assert isinstance(download_end_entry, dict)
    assert isinstance(download_timezone_entry, dict)
    assert isinstance(invalid_download_timezone_entry, dict)
    assert isinstance(replay_range_entry, dict)
    assert isinstance(start_entry, dict)
    assert isinstance(end_entry, dict)
    assert isinstance(note_entry, dict)
    assert isinstance(tab_entry, dict)
    assert isinstance(position_entry, dict)
    assert isinstance(running_entry, dict)
    assert isinstance(configured_entry, dict)
    assert isinstance(completed_entry, dict)
    assert isinstance(warmup_entry, dict)
    assert isinstance(ctrader_close_entry, dict)
    assert isinstance(ib_close_entry, dict)
    assert isinstance(settings_close_entry, dict)
    assert history_title_entry["uk"] == "Завантаження історичних даних"
    assert history_title_entry["pl"] == "Pobieranie danych historycznych"
    assert history_planned_entry["uk"] == "Запланований CSV-файл:"
    assert history_replay_entry["uk"] == "Використати для Replay"
    assert history_replay_entry["pl"] == "Użyj w Replay"
    assert "Брокер не повернув барів" in history_coverage_entry["uk"]
    assert "Broker nie zwrócił barów" in history_coverage_entry["pl"]
    assert history_note_entry["uk"].startswith("Вибрані дати")
    assert history_note_entry["pl"].startswith("Wybrane daty")
    assert ib_download_entry["uk"] == "Завантажити з IB..."
    assert download_progress_entry["uk"] == (
        "Завантаження історичних даних з {broker}..."
    )
    assert message_ok_entry["uk"] == "Зрозуміло"
    assert invalid_end_datetime_entry["uk"].startswith("IB відхилив запит")
    assert source_name_entry["uk"] == "Назва джерела:"
    assert source_name_entry["pl"] == "Nazwa źródła:"
    assert download_group_entry["uk"] == "Період завантаження історії"
    assert download_start_entry["uk"] == "Дата початку:"
    assert download_end_entry["uk"] == "Дата завершення:"
    assert download_timezone_entry["uk"] == ("Часовий пояс періоду завантаження:")
    assert invalid_download_timezone_entry["uk"].startswith(
        "Невідомий часовий пояс завантаження історії"
    )
    assert replay_range_entry["uk"] == "Період тесту Replay і часовий пояс"
    assert replay_range_entry["pl"] == "Okres testu Replay i strefa czasowa"
    assert start_entry["uk"] == "Початок тесту UTC:"
    assert start_entry["pl"] == "Początek testu UTC:"
    assert end_entry["uk"] == "Кінець тесту UTC:"
    assert end_entry["pl"] == "Koniec testu UTC:"
    assert note_entry["uk"].startswith("Період тесту Replay")
    assert note_entry["pl"].startswith("Okres testu Replay")
    assert tab_entry["uk"] == "Табуляція"
    assert position_entry["uk"] == "Позиція"
    assert position_entry["pl"] == "Pozycja"
    assert running_entry["uk"] == "ПРАЦЮЄ"
    assert running_entry["pl"] == "DZIAŁA"
    assert configured_entry["uk"] == "Replay налаштовано: {source}"
    assert completed_entry["uk"] == "ЗАВЕРШЕНО"
    assert completed_entry["pl"] == "ZAKOŃCZONO"
    assert warmup_entry["uk"] == "ПРОГРІВ"
    assert warmup_entry["pl"] == "ROZGRZEWKA"
    assert ctrader_close_entry["uk"] == "Закрити"
    assert ctrader_close_entry["pl"] == "Zamknij"
    assert ib_close_entry["uk"] == "Закрити"
    assert ib_close_entry["pl"] == "Zamknij"
    assert settings_close_entry["uk"] == "Закрити"
    assert settings_close_entry["pl"] == "Zamknij"
    assert override_updates == 54

    captured_payloads: list[dict[str, str]] = []

    def fake_post(
        _url: str,
        *,
        data: dict[str, str],
        headers: dict[str, str],
        timeout: int,
    ) -> _FakeDeepLResponse:
        assert headers["Authorization"].startswith("DeepL-Auth-Key ")
        assert timeout == 20
        captured_payloads.append(dict(data))
        return _FakeDeepLResponse()

    original_post = ai_translator_module.requests.post
    ai_translator_module.requests.post = fake_post
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            translator = AITranslator(
                {
                    "translator": {
                        "provider": "deepl",
                        "deepl_key_1": "TEST_KEY",
                    }
                },
                lang_dir=Path(temp_dir),
            )
            first = translator.translate(
                "Disabled",
                "uk",
                context=context,
            )
            second = translator.translate(
                "Disabled",
                "uk",
                context=context,
            )
            third = translator.translate(
                "Disabled",
                "uk",
                context="Different context",
            )
    finally:
        ai_translator_module.requests.post = original_post

    assert first == "Вимкнено"
    assert second == "Вимкнено"
    assert third == "Вимкнено"
    assert len(captured_payloads) == 2
    assert captured_payloads[0]["context"] == context
    assert captured_payloads[1]["context"] == "Different context"

    print("Centralized Translation Policy result")
    print("  prefix_context=True")
    print("  glossary_context=True")
    print("  polish_glossary_context=True")
    print("  centralized_override=True")
    print("  color_independent_external_guidance=True")
    print("  regular_tr_call=True")
    print(f"  rebuild_override_updates={override_updates}")
    print("  history_download_dialog_overrides=True")
    print("  replay_dialog_overrides=True")
    print("  workspace_ui_overrides=True")
    print("  polish_workspace_overrides=True")
    print("  broker_connection_close_overrides=True")
    print("  settings_close_override=True")
    print("  deepl_context_payload=True")
    print("  context_aware_cache=True")
    print("TRANSLATION_POLICY_CHECK=OK")


if __name__ == "__main__":
    main()
