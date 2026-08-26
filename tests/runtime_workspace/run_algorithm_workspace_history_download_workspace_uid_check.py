# -*- coding: utf-8 -*-
"""Regression check для WSP history download workspace_uid + progress callback."""

from __future__ import annotations

import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import core.algorithm_workspace_area as area_module  # noqa: E402


class _FakeController:
    """Фіксує фактичний контракт Area -> Controller без broker requests."""

    def __init__(self, broker: str) -> None:
        self.broker = broker
        self.calls: list[dict[str, object]] = []

    @staticmethod
    def workspace_runtime(workspace_uid: str) -> None:
        _ = workspace_uid
        return None

    def load_workspace(self, workspace_uid: str) -> SimpleNamespace:
        _ = workspace_uid
        return SimpleNamespace(broker=self.broker)

    def download_workspace_ctrader_history(
        self,
        workspace_uid: str,
        runtime_engine: object,
        start_utc: datetime,
        end_utc: datetime,
        *,
        progress_callback: object | None = None,
    ) -> object:
        self.calls.append(
            {
                "broker": "CTRADER",
                "workspace_uid": workspace_uid,
                "runtime_engine": runtime_engine,
                "start_utc": start_utc,
                "end_utc": end_utc,
                "progress_callback": progress_callback,
            }
        )
        return object()

    def download_workspace_ib_history(
        self,
        workspace_uid: str,
        runtime_engine: object,
        start_utc: datetime,
        end_utc: datetime,
    ) -> object:
        self.calls.append(
            {
                "broker": "IB",
                "workspace_uid": workspace_uid,
                "runtime_engine": runtime_engine,
                "start_utc": start_utc,
                "end_utc": end_utc,
            }
        )
        return object()


class _FakeDialog:
    """Відтворює триаргументний callback після додавання progress indicator."""

    last_progress_callback: object | None = None

    def __init__(
        self,
        workspace: object,
        lang_mgr: object,
        parent: object,
        *,
        history_download: Callable[
            [datetime, datetime, Callable[..., None]],
            object,
        ],
    ) -> None:
        _ = workspace, lang_mgr, parent
        self._history_download = history_download
        self.downloaded_result = None
        self.use_for_replay_requested = False

    @staticmethod
    def _progress_callback(*args: object, **kwargs: object) -> None:
        _ = args, kwargs

    def exec(self) -> int:
        start_utc = datetime(2025, 1, 1, tzinfo=UTC)
        end_utc = datetime(2025, 1, 2, tzinfo=UTC)
        self.__class__.last_progress_callback = self._progress_callback
        self._history_download(
            start_utc,
            end_utc,
            self._progress_callback,
        )
        return 0


class _FakeArea:
    """Мінімальний self для прямої перевірки history-download handler."""

    def __init__(self, broker: str) -> None:
        self.controller = _FakeController(broker)
        self._runtime_engine = object()
        self._lang_mgr = None


def _run_broker_case(broker: str) -> tuple[str, dict[str, object]]:
    workspace_uid = str(uuid4())
    fake_area = _FakeArea(broker)
    handler = cast(
        Callable[[Any, str], None],
        getattr(
            area_module.AlgorithmWorkspaceArea,
            "_on_history_download_requested",
        ),
    )
    handler(fake_area, workspace_uid)
    assert len(fake_area.controller.calls) == 1
    call = fake_area.controller.calls[0]
    assert call["workspace_uid"] == workspace_uid
    return workspace_uid, call


def main() -> None:
    original_dialog = area_module.AlgorithmWorkspaceHistoryDownloadDialog
    try:
        area_module.AlgorithmWorkspaceHistoryDownloadDialog = _FakeDialog

        ctrader_uid, ctrader_call = _run_broker_case("CTRADER")
        ib_uid, ib_call = _run_broker_case("IB")
    finally:
        area_module.AlgorithmWorkspaceHistoryDownloadDialog = original_dialog

    assert ctrader_call["broker"] == "CTRADER"
    assert ctrader_call["workspace_uid"] == ctrader_uid
    assert ctrader_call["progress_callback"] is _FakeDialog.last_progress_callback

    assert ib_call["broker"] == "IB"
    assert ib_call["workspace_uid"] == ib_uid
    assert "progress_callback" not in ib_call

    print("Algorithm Workspace History Download Workspace UID result")
    print("  dialog_three_argument_download_contract=True")
    print("  ctrader_workspace_uid_preserved=True")
    print("  ctrader_progress_callback_forwarded=True")
    print("  ib_workspace_uid_preserved=True")
    print("  ib_progress_callback_does_not_replace_uid=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_HISTORY_DOWNLOAD_WORKSPACE_UID_CHECK=OK")


if __name__ == "__main__":
    main()
