# -*- coding: utf-8 -*-
"""Перевірка повної історії Signals після завершення Historical Replay."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_ACCOUNT_MODE_PAPER,
    WORKSPACE_CONTROL_MODE_MANUAL,
    WORKSPACE_DATA_MODE_REPLAY,
    AlgorithmWorkspace,
)
from core.workspace_alligator import (  # noqa: E402
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_broker_market import (  # noqa: E402
    WorkspaceBrokerMarketProviderProtocol,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_runtime import (  # noqa: E402
    MAX_WORKSPACE_SIGNAL_RECORDS,
    WorkspaceRuntime,
)
from core.workspace_signal import WorkspaceSignalRecord  # noqa: E402
from engine.runtime_constants import (  # noqa: E402
    WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
    WORKSPACE_REPLAY_SOURCE_CSV,
)

HISTORY_FILE = (
    PROJECT_ROOT
    / "data"
    / "history"
    / "IB"
    / "EURUSD"
    / "M15"
    / "2026-01-02_2026-07-27_IB_EURUSD_M15.csv"
)


class BrokerRequestProbe(WorkspaceBrokerMarketProviderProtocol):
    """Фіксувати будь-яку неочікувану спробу broker market-data."""

    def __init__(self) -> None:
        self.requests = 0

    def start_workspace(
        self,
        *,
        workspace_uid: str,
        broker: str,
        account_id: str | None,
        symbol: str,
        timeframe: str,
        warmup_bars: int,
        spread_limit: float,
    ) -> tuple[WorkspaceMarketEvent, ...]:
        _ = (
            workspace_uid,
            broker,
            account_id,
            symbol,
            timeframe,
            warmup_bars,
            spread_limit,
        )
        self.requests += 1
        return ()

    def poll_workspace(self, workspace_uid: str) -> WorkspaceMarketEvent | None:
        _ = workspace_uid
        self.requests += 1
        return None

    def is_workspace_broker_connected(self, workspace_uid: str) -> bool:
        _ = workspace_uid
        self.requests += 1
        return True

    def suspend_workspace(self, workspace_uid: str) -> None:
        _ = workspace_uid
        self.requests += 1

    def resume_workspace(
        self,
        workspace_uid: str,
    ) -> tuple[WorkspaceMarketEvent, ...]:
        _ = workspace_uid
        self.requests += 1
        return ()

    def stop_workspace(self, workspace_uid: str) -> None:
        _ = workspace_uid
        self.requests += 1


def _workspace() -> AlgorithmWorkspace:
    return AlgorithmWorkspace.create(
        broker="IB",
        account_id="DUM513747",
        account_mode=WORKSPACE_ACCOUNT_MODE_PAPER,
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        data_mode=WORKSPACE_DATA_MODE_REPLAY,
        control_mode=WORKSPACE_CONTROL_MODE_MANUAL,
        parameters={
            "macd_signal_enabled": True,
            "macd_signal_mode": "LINEAR",
            "alligator_filter_enabled": True,
            "alligator_confirmation": WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
            "warmup_bars": 2,
            "spread_limit": 0.00020,
        },
        replay_settings={
            "source_type": WORKSPACE_REPLAY_SOURCE_CSV,
            "file_path": str(HISTORY_FILE),
            "source_timezone": "UTC",
            "delimiter": ",",
            "decimal_separator": ".",
            "spread": 0.00012,
            "speed": 1000,
        },
    )


def main() -> None:
    workspace = _workspace()
    algorithm = WorkspaceMacdAlligatorReplayAlgorithm(workspace.algorithm)
    broker_probe = BrokerRequestProbe()
    complete_records: list[WorkspaceSignalRecord] = []
    runtime = WorkspaceRuntime(
        workspace,
        algorithm_factory=lambda _algorithm_id: algorithm,
        broker_market_provider=broker_probe,
        signal_record_observer=complete_records.append,
    )
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None

    bounded_during_replay_verified = False
    while not session.completed:
        runtime.advance_replay(max_events=100)
        if (
            not session.completed
            and len(complete_records) > MAX_WORKSPACE_SIGNAL_RECORDS
        ):
            bounded = runtime.signal_records()
            ui_records = runtime.signal_records_for_ui()
            assert len(bounded) == MAX_WORKSPACE_SIGNAL_RECORDS
            assert ui_records == bounded
            bounded_during_replay_verified = True

    bounded = runtime.signal_records()
    completed_ui = runtime.signal_records_for_ui()
    assert bounded_during_replay_verified
    assert len(complete_records) > MAX_WORKSPACE_SIGNAL_RECORDS
    assert len(bounded) == MAX_WORKSPACE_SIGNAL_RECORDS
    assert bounded == tuple(complete_records[-MAX_WORKSPACE_SIGNAL_RECORDS:])
    assert completed_ui == tuple(complete_records)
    assert completed_ui[0].timestamp < bounded[0].timestamp
    assert broker_probe.requests == 0

    area_source = (PROJECT_ROOT / "core" / "algorithm_workspace_area.py").read_text(
        encoding="utf-8"
    )
    assert "window.set_signal_records(runtime.signal_records_for_ui())" in area_source

    print("Algorithm Workspace Completed Replay Signal History result")
    print("  runtime_bounded_signal_limit=1000")
    print(f"  complete_signal_records={len(complete_records)}")
    print(f"  bounded_signal_records={len(bounded)}")
    print(f"  completed_replay_ui_records={len(completed_ui)}")
    print(f"  bounded_first={bounded[0].timestamp.isoformat()}")
    print(f"  complete_first={completed_ui[0].timestamp.isoformat()}")
    print("  during_running_replay_ui_bounded=True")
    print("  after_completed_replay_ui_full_history=True")
    print("  live_runtime_signal_limit_preserved=True")
    print("  broker_requests=0")
    print("ALGORITHM_WORKSPACE_COMPLETED_REPLAY_SIGNAL_HISTORY_CHECK=OK")


if __name__ == "__main__":
    main()
