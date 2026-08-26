# -*- coding: utf-8 -*-
"""Перевірка canonical cTrader history download, CSV та progress callback.

Тест не звертається до брокера: fake service перевіряє service/controller
контракт, збереження CSV і передачу progress без broker execution.
"""

from __future__ import annotations

import csv
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import NoReturn

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_ACCOUNT_MODE_DEMO,
    WORKSPACE_CONTROL_MODE_MANUAL,
    WORKSPACE_DATA_MODE_REPLAY,
)
from core.algorithm_workspace_controller import (  # noqa: E402
    AlgorithmWorkspaceController,
)
from core.session_repository import SessionRepository  # noqa: E402
from core.workspace_history import WorkspaceCsvHistoryLoader  # noqa: E402
from core.workspace_runtime import WorkspaceRuntimeError  # noqa: E402
from engine.ctrader_history import (  # noqa: E402
    CTraderHistoricalBar,
    CTraderHistoryDownloadResult,
    CTraderHistoryProgressCallback,
    decode_ctrader_trendbars,
    next_ctrader_history_chunk_end,
)
from engine.runtime_account_state import RuntimeAccountState  # noqa: E402
from engine.runtime_broker_health import RuntimeBrokerHealth  # noqa: E402
from engine.runtime_engine import (  # noqa: E402
    CTraderRuntimeServiceProtocol,
    RuntimeEngine,
)


class FakeCTraderService(CTraderRuntimeServiceProtocol):
    def __init__(self) -> None:
        self.calls: list[dict] = []

    @staticmethod
    def _unexpected_call(method_name: str) -> NoReturn:
        raise AssertionError(f"Unexpected fake service call: {method_name}")

    def connect_demo(self) -> object | None:
        self._unexpected_call("connect_demo")

    def connect_live(self) -> object | None:
        self._unexpected_call("connect_live")

    def disconnect(self) -> None:
        self._unexpected_call("disconnect")

    def reconnect(self) -> object | None:
        self._unexpected_call("reconnect")

    def get_historical_trendbars(
        self,
        symbol_name: str,
        timeframe: str,
        start_utc: datetime,
        end_utc: datetime,
        progress_callback: CTraderHistoryProgressCallback | None = None,
    ) -> CTraderHistoryDownloadResult:
        self.calls.append(
            {
                "symbol_name": symbol_name,
                "timeframe": timeframe,
                "start_utc": start_utc,
                "end_utc": end_utc,
            }
        )
        bars = tuple(
            CTraderHistoricalBar(
                timestamp=start_utc + timedelta(minutes=15 * index),
                open=1.1700 + index * 0.0001,
                high=1.1708 + index * 0.0001,
                low=1.1695 + index * 0.0001,
                close=1.1704 + index * 0.0001,
                volume=100 + index,
            )
            for index in range(4)
        )
        if progress_callback is not None:
            progress_callback(1, len(bars), bars[0].timestamp)
        return CTraderHistoryDownloadResult(
            broker="CTRADER",
            symbol=symbol_name,
            timeframe=timeframe,
            requested_start_utc=start_utc,
            requested_end_utc=end_utc,
            bars=bars,
            request_count=1,
        )

    def get_positions(self) -> list:
        return []

    def get_broker_health(self) -> RuntimeBrokerHealth:
        self._unexpected_call("get_broker_health")

    def get_account_state(self) -> RuntimeAccountState:
        self._unexpected_call("get_account_state")

    def get_account_list(self) -> list[dict]:
        return []

    def place_market_order(
        self,
        symbol_name: str,
        side: str,
        lots: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        comment: str = "LGE manual order",
    ) -> dict:
        _ = (
            symbol_name,
            side,
            lots,
            stop_loss,
            take_profit,
            comment,
        )
        self._unexpected_call("place_market_order")

    def close_position(
        self,
        position_id: int | str,
        lots: float | None = None,
    ) -> object:
        _ = position_id, lots
        self._unexpected_call("close_position")

    def modify_position_sl_tp(
        self,
        position_id: int | str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> dict:
        _ = position_id, stop_loss, take_profit
        self._unexpected_call("modify_position_sl_tp")


def _check_relative_price_decode() -> None:
    from types import SimpleNamespace

    payload = SimpleNamespace(
        trendbar=[
            SimpleNamespace(
                utcTimestampInMinutes=int(
                    datetime(2026, 7, 20, 8, 0, tzinfo=UTC).timestamp() // 60
                ),
                low=117000,
                deltaOpen=10,
                deltaClose=80,
                deltaHigh=120,
                volume=125,
            )
        ]
    )
    decoded = decode_ctrader_trendbars(payload)
    assert len(decoded) == 1
    assert decoded[0].low == 1.17
    assert decoded[0].open == 1.1701
    assert decoded[0].close == 1.1708
    assert decoded[0].high == 1.1712


def _check_invalid_trendbar_blocked() -> None:
    from types import SimpleNamespace

    payload = SimpleNamespace(
        trendbar=[
            SimpleNamespace(
                utcTimestampInMinutes=0,
                low=117000,
                deltaOpen=10,
                deltaClose=80,
                deltaHigh=120,
                volume=125,
            )
        ]
    )
    invalid_blocked = False
    try:
        decode_ctrader_trendbars(payload)
    except RuntimeError:
        invalid_blocked = True
    assert invalid_blocked


def _check_backward_pagination_without_has_more() -> None:
    from types import SimpleNamespace

    requested_start = datetime(2026, 1, 1, tzinfo=UTC)
    earliest = datetime(2026, 5, 14, 7, 45, tzinfo=UTC)
    bars = [
        CTraderHistoricalBar(
            timestamp=earliest,
            open=1.17,
            high=1.18,
            low=1.16,
            close=1.175,
            volume=100,
        )
    ]
    payload = SimpleNamespace(hasMore=False)
    assert payload.hasMore is False

    next_to_ms = next_ctrader_history_chunk_end(
        bars,
        requested_start,
    )
    assert next_to_ms == int(earliest.timestamp() * 1000) - 1

    covered_start = next_ctrader_history_chunk_end(
        [
            CTraderHistoricalBar(
                timestamp=requested_start,
                open=1.17,
                high=1.18,
                low=1.16,
                close=1.175,
                volume=100,
            )
        ],
        requested_start,
    )
    assert covered_start is None


def main() -> None:
    _check_relative_price_decode()
    _check_invalid_trendbar_blocked()
    _check_backward_pagination_without_has_more()
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        repository = SessionRepository(root / "Session")
        controller = AlgorithmWorkspaceController(repository)
        workspace = controller.create_workspace(
            broker="CTRADER",
            account_id="46368962",
            account_mode=WORKSPACE_ACCOUNT_MODE_DEMO,
            symbol="GBPUSD",
            timeframe="M15",
            algorithm="RailAlgorithm",
            data_mode=WORKSPACE_DATA_MODE_REPLAY,
            control_mode=WORKSPACE_CONTROL_MODE_MANUAL,
        )
        start_utc = datetime(2026, 6, 26, 8, 0, tzinfo=UTC)
        end_utc = datetime(2026, 7, 26, 8, 0, tzinfo=UTC)
        service = FakeCTraderService()
        runtime_engine = RuntimeEngine()
        runtime_engine.set_ctrader_runtime_service(service)
        progress_events: list[tuple[int, int, datetime | None]] = []

        exported = controller.download_workspace_ctrader_history(
            workspace.workspace_uid,
            runtime_engine,
            start_utc,
            end_utc,
            history_root=str(root / "history"),
            progress_callback=lambda requests, bars, covered_start: (
                progress_events.append((requests, bars, covered_start))
            ),
        )
        assert progress_events == [(1, 4, start_utc)]

        expected_name = "2026-06-26_2026-06-26_CTRADER_GBPUSD_M15.csv"
        assert exported.file_path.name == expected_name
        assert (
            exported.file_path.parent
            == (root / "history" / "CTRADER" / "GBPUSD" / "M15").resolve()
        )
        assert "46368962" not in str(exported.file_path)
        assert exported.bar_count == 4
        assert exported.source_name == "CTRADER_GBPUSD_M15_HISTORY"
        assert len(service.calls) == 1

        with exported.file_path.open(
            "r",
            encoding="utf-8",
            newline="",
        ) as handle:
            rows = list(csv.DictReader(handle))
        assert len(rows) == 4
        assert tuple(rows[0]) == (
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
        )

        loaded = WorkspaceCsvHistoryLoader().load(
            file_path=exported.file_path,
            broker="CTRADER",
            symbol="GBPUSD",
            timeframe="M15",
            source_name="CTRADER_GBPUSD_M15_HISTORY",
            source_timezone="UTC",
            delimiter="AUTO",
            decimal_separator=".",
            default_spread=0.00012,
        )
        assert len(loaded.events) == 4
        assert loaded.events[0].timestamp == start_utc

        runtime = controller.ensure_workspace_runtime(workspace.workspace_uid)
        runtime.begin_start()
        active_download_blocked = False
        try:
            controller.download_workspace_ctrader_history(
                workspace.workspace_uid,
                runtime_engine,
                start_utc,
                end_utc,
                history_root=str(root / "history"),
            )
        except WorkspaceRuntimeError:
            active_download_blocked = True
        assert active_download_blocked

        print("Algorithm Workspace cTrader History Download result")
        print(f"  file={exported.file_path.name}")
        print(f"  folder={exported.file_path.parent}")
        print(f"  bars={exported.bar_count}")
        print("  account_folder_omitted=True")
        print("  period_prefix=True")
        print("  relative_price_decode=True")
        print("  invalid_trendbar_blocked=True")
        print("  backward_pagination_without_has_more=True")
        print("  progress_callback_propagated=True")
        print("  atomic_csv_reload=True")
        print(f"  active_download_blocked={active_download_blocked}")
        print("ALGORITHM_WORKSPACE_CTRADER_HISTORY_DOWNLOAD_CHECK=OK")


if __name__ == "__main__":
    main()
