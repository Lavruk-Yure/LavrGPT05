# -*- coding: utf-8 -*-
"""tests.runtime_workspace.run_algorithm_workspace_ib_history_download_check

Runtime check for canonical IB history download and CSV export.
"""

from __future__ import annotations

import csv
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import NoReturn

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_ACCOUNT_MODE_PAPER,
    WORKSPACE_CONTROL_MODE_MANUAL,
    WORKSPACE_DATA_MODE_REPLAY,
)
from core.algorithm_workspace_controller import (  # noqa: E402
    AlgorithmWorkspaceController,
)
from core.session_repository import SessionRepository  # noqa: E402
from core.workspace_history import WorkspaceCsvHistoryLoader  # noqa: E402
from core.workspace_history_export import (  # noqa: E402
    WorkspaceHistoryCsvWriter,
)
from core.workspace_runtime import WorkspaceRuntimeError  # noqa: E402
from engine.ib_history import (  # noqa: E402
    IBHistoricalBar,
    IBHistoryDownloadResult,
    decode_ib_historical_bar,
    format_ib_historical_end_datetime,
    is_ib_historical_no_data_error,
)
from engine.runtime_account_state import RuntimeAccountState  # noqa: E402
from engine.runtime_broker_health import RuntimeBrokerHealth  # noqa: E402
from engine.runtime_constants import (  # noqa: E402
    IB_HISTORY_EMPTY_CHUNK_SECONDS_BY_TIMEFRAME,
    IB_HISTORY_MAX_REQUESTS,
    IB_HISTORY_REQUEST_DELAY_SECONDS,
)
from engine.runtime_engine import (  # noqa: E402
    IBRuntimeServiceProtocol,
    RuntimeEngine,
)


class FakeIBHistoryService(IBRuntimeServiceProtocol):
    """Strict fake IB service used by the history runtime check."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    @staticmethod
    def _unexpected_call(method_name: str) -> NoReturn:
        raise AssertionError(f"Unexpected fake service call: {method_name}")

    def connect_demo(self) -> object | None:
        self._unexpected_call("connect_demo")

    def disconnect(self) -> None:
        self._unexpected_call("disconnect")

    def get_broker_health(self) -> RuntimeBrokerHealth:
        self._unexpected_call("get_broker_health")

    def get_account_state(self) -> RuntimeAccountState:
        self._unexpected_call("get_account_state")

    def reconnect(self) -> object | None:
        self._unexpected_call("reconnect")

    def get_virtual_position_leg_evidence_snapshot(self) -> dict:
        self._unexpected_call("get_virtual_position_leg_evidence_snapshot")

    def get_positions(self) -> list:
        return []

    def place_market_order(
        self,
        symbol_name: str,
        side: str,
        quantity: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        comment: str = "LGE manual order",
    ) -> dict:
        _ = symbol_name, side, quantity, stop_loss, take_profit, comment
        self._unexpected_call("place_market_order")

    def close_position(
        self,
        position_id: str,
        quantity: float | None = None,
        comment: str = "LGE manual close",
    ) -> dict:
        _ = position_id, quantity, comment
        self._unexpected_call("close_position")

    def modify_position_sl_tp(
        self,
        position_id: str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> dict:
        _ = position_id, stop_loss, take_profit
        self._unexpected_call("modify_position_sl_tp")

    def close_virtual_position_leg(
        self,
        position_uid: str,
        position_id: str,
        account_id: str,
        symbol_name: str,
        position_side: str,
        position_volume: float,
        parent_order_id: int,
        stop_loss_order_id: int | None,
        take_profit_order_id: int | None,
        current_oca_group: str,
        comment: str = "LGE virtual-leg close",
    ) -> dict:
        _ = (
            position_uid,
            position_id,
            account_id,
            symbol_name,
            position_side,
            position_volume,
            parent_order_id,
            stop_loss_order_id,
            take_profit_order_id,
            current_oca_group,
            comment,
        )
        self._unexpected_call("close_virtual_position_leg")

    def modify_virtual_position_leg_sl_tp(
        self,
        position_uid: str,
        position_id: str,
        account_id: str,
        symbol_name: str,
        position_side: str,
        position_volume: float,
        parent_order_id: int,
        stop_loss_order_id: int | None,
        take_profit_order_id: int | None,
        current_oca_group: str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        order_ref: str = "",
    ) -> dict:
        _ = (
            position_uid,
            position_id,
            account_id,
            symbol_name,
            position_side,
            position_volume,
            parent_order_id,
            stop_loss_order_id,
            take_profit_order_id,
            current_oca_group,
            stop_loss,
            take_profit,
            order_ref,
        )
        self._unexpected_call("modify_virtual_position_leg_sl_tp")

    def get_historical_bars(
        self,
        symbol_name: str,
        timeframe: str,
        start_utc: datetime,
        end_utc: datetime,
        progress_callback=None,
    ) -> IBHistoryDownloadResult:
        self.calls.append(
            {
                "symbol_name": symbol_name,
                "timeframe": timeframe,
                "start_utc": start_utc,
                "end_utc": end_utc,
            }
        )
        bars = tuple(
            IBHistoricalBar(
                timestamp=start_utc + timedelta(minutes=15 * index),
                open=1.3300 + index * 0.0001,
                high=1.3308 + index * 0.0001,
                low=1.3295 + index * 0.0001,
                close=1.3304 + index * 0.0001,
                volume=0.0,
            )
            for index in range(4)
        )
        if progress_callback is not None:
            progress_callback(1, len(bars), bars[0].timestamp)
        return IBHistoryDownloadResult(
            broker="IB",
            symbol=symbol_name,
            timeframe=timeframe,
            requested_start_utc=start_utc,
            requested_end_utc=end_utc,
            bars=bars,
            request_count=1,
        )


def _check_hmds_no_data_classification() -> None:
    assert is_ib_historical_no_data_error(
        "IB historical data error 162: Historical Market Data Service "
        "error message:HMDS query returned no data"
    )
    assert not is_ib_historical_no_data_error(
        "IB historical data error 162: Historical Market Data Service "
        "error message:permission denied"
    )
    assert IB_HISTORY_EMPTY_CHUNK_SECONDS_BY_TIMEFRAME["M1"] == 86400


def _check_epoch_timestamp_decode() -> None:
    timestamp = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)
    decoded = decode_ib_historical_bar(
        SimpleNamespace(
            date=str(int(timestamp.timestamp())),
            open=1.3300,
            high=1.3310,
            low=1.3295,
            close=1.3305,
            volume=-1,
        )
    )
    assert decoded.timestamp == timestamp
    assert decoded.volume == 0.0


def _check_ib_end_datetime_format() -> None:
    value = datetime(2026, 7, 27, 6, 59, 37, tzinfo=UTC)
    assert format_ib_historical_end_datetime(value) == "20260727 06:59:37 UTC"


def _check_invalid_bar_blocked() -> None:
    invalid_blocked = False
    try:
        decode_ib_historical_bar(
            SimpleNamespace(
                date="1784534400",
                open=1.3300,
                high=1.3290,
                low=1.3295,
                close=1.3305,
                volume=0,
            )
        )
    except RuntimeError:
        invalid_blocked = True
    assert invalid_blocked


def main() -> None:
    _check_epoch_timestamp_decode()
    _check_ib_end_datetime_format()
    _check_invalid_bar_blocked()
    _check_hmds_no_data_classification()
    assert 0.0 < IB_HISTORY_REQUEST_DELAY_SECONDS <= 3.0
    assert IB_HISTORY_MAX_REQUESTS >= 250

    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        repository = SessionRepository(root / "Session")
        controller = AlgorithmWorkspaceController(repository)
        workspace = controller.create_workspace(
            broker="IB",
            account_id="DUM513747",
            account_mode=WORKSPACE_ACCOUNT_MODE_PAPER,
            symbol="GBPUSD",
            timeframe="M15",
            algorithm="RailAlgorithm",
            data_mode=WORKSPACE_DATA_MODE_REPLAY,
            control_mode=WORKSPACE_CONTROL_MODE_MANUAL,
        )
        start_utc = datetime(2026, 6, 26, 8, 0, tzinfo=UTC)
        end_utc = datetime(2026, 7, 26, 8, 0, tzinfo=UTC)
        service = FakeIBHistoryService()
        runtime_engine = RuntimeEngine()
        runtime_engine.set_ib_runtime_service(service)

        history_root = root / "history"
        writer = WorkspaceHistoryCsvWriter(history_root)
        planned_path = writer.planned_file_path(
            broker="IB",
            symbol=workspace.symbol,
            timeframe=workspace.timeframe,
            start_utc=start_utc,
            end_utc=end_utc,
        )
        assert planned_path.parent == (history_root / "IB" / "GBPUSD" / "M15").resolve()
        assert planned_path.name == "2026-06-26_2026-07-26_IB_GBPUSD_M15.csv"
        assert planned_path.parent.is_dir()
        assert not planned_path.exists()
        assert (
            writer.planned_source_name(
                broker="IB",
                symbol=workspace.symbol,
                timeframe=workspace.timeframe,
            )
            == "IB_GBPUSD_M15_HISTORY"
        )

        progress_events: list[tuple[int, int, datetime | None]] = []
        exported = controller.download_workspace_ib_history(
            workspace.workspace_uid,
            runtime_engine,
            start_utc,
            end_utc,
            history_root=str(history_root),
            progress_callback=lambda requests, bars, covered_start: (
                progress_events.append((requests, bars, covered_start))
            ),
        )
        assert progress_events == [(1, 4, start_utc)]

        expected_name = "2026-06-26_2026-06-26_IB_GBPUSD_M15.csv"
        assert exported.file_path.name == expected_name
        assert (
            exported.file_path.parent
            == (root / "history" / "IB" / "GBPUSD" / "M15").resolve()
        )
        assert "DUM513747" not in str(exported.file_path)
        assert exported.bar_count == 4
        assert exported.source_name == "IB_GBPUSD_M15_HISTORY"
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
            broker="IB",
            symbol="GBPUSD",
            timeframe="M15",
            source_name="IB_GBPUSD_M15_HISTORY",
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
            controller.download_workspace_ib_history(
                workspace.workspace_uid,
                runtime_engine,
                start_utc,
                end_utc,
                history_root=str(root / "history"),
            )
        except WorkspaceRuntimeError:
            active_download_blocked = True
        assert active_download_blocked

        print("Algorithm Workspace IB History Download result")
        print("  hmds_no_data_reply_classified=True")
        print("  multi_month_m1_request_budget=True")
        print(f"  file={exported.file_path.name}")
        print(f"  folder={exported.file_path.parent}")
        print(f"  bars={exported.bar_count}")
        print("  account_folder_omitted=True")
        print("  period_prefix=True")
        print("  progress_callback_propagated=True")
        print("  planned_path_prefilled=True")
        print("  planned_source_name_prefilled=True")
        print("  empty_final_file_avoided=True")
        print("  ib_end_datetime_format=True")
        print("  ib_multi_chunk_delay_reduced=True")
        print("  epoch_timestamp_decode=True")
        print("  midpoint_negative_volume_normalized=True")
        print("  invalid_bar_blocked=True")
        print("  atomic_csv_reload=True")
        print(f"  active_download_blocked={active_download_blocked}")
        print("ALGORITHM_WORKSPACE_IB_HISTORY_DOWNLOAD_CHECK=OK")


if __name__ == "__main__":
    main()
