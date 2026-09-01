"""run_t107_04_broker_completed_bar_delivery_contract_check.py — T107-04.

TEST_ONLY full-runtime regression відтворює BROKER live bucket lifecycle через
реальні ``RuntimeEngineWorkspaceMarketProvider`` і ``WorkspaceRuntime``. Локальний
fake RuntimeEngine повертає два різні quote snapshots одного M15 bucket, а потім
quote наступного bucket; мережа та broker execution не використовуються.

Локальний recorder підключено через штатний ``algorithm_factory`` лише для
фіксації фактичної межі runtime dispatch. Він не підмінює history, не змінює
production guards і не послаблює unique timestamp assertions. Реальний public
``WorkspaceMacdSignalSource`` окремо отримує фактичний BROKER event, який мав би
бути завершеним після rollover. Public Alligator observations перевіряються на
повторному timestamp; Stochastic mutation навмисно не читається через private
API і тому друкується як ``NOT_MEASURED``.

Runner формулює цільовий completed-bar-only contract і очікувано завершується
RED, доки partial bucket доходить до algorithm, попередній bucket не
dispatch-иться рівно один раз на rollover або MACD не приймає completed BROKER
bar. Replay, Candidate F, Alligator, Stochastic, SL/TP і Profit Drawdown тут не
змінюються та не перевіряються як торгові результати.
"""

from __future__ import annotations

import sys
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_DATA_MODE_BROKER,
    AlgorithmWorkspace,
)
from core.workspace_algorithm import (  # noqa: E402
    PassiveWorkspaceAlgorithm,
    WorkspaceAlgorithmError,
)
from core.workspace_alligator import (  # noqa: E402
    WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
    WorkspaceAlligatorFilter,
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_broker_market import (  # noqa: E402
    RuntimeEngineWorkspaceMarketProvider,
)
from core.workspace_macd import WorkspaceMacdSignalSource  # noqa: E402
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402

TEST_ID = "T107-04"
MODE = "RM107_T107_04_BROKER_COMPLETED_BAR_DELIVERY_CONTRACT_TEST_ONLY"
FIRST_BUCKET = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
NEXT_BUCKET = datetime(2026, 9, 1, 9, 15, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class FakeBar:
    """Один завершений historical bar для штатного broker warm-up path."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True, slots=True)
class FakeHistoryResult:
    """Мінімальний результат наявного history downloader contract."""

    bars: tuple[FakeBar, ...]


class FakeRuntimeEngine:
    """Подати deterministic quotes через наявний RuntimeEngine adapter API."""

    def __init__(self) -> None:
        self.execution_attempts = 0
        self.quote_calls = 0
        self.served_quote_timestamps: list[datetime] = []
        self._quote_index = 0
        self._quotes = (
            ("2026-09-01T09:00:02Z", 1.17000, 1.17020, 10.0),
            ("2026-09-01T09:07:30Z", 1.17030, 1.17050, 20.0),
            ("2026-09-01T09:15:01Z", 1.17040, 1.17060, 5.0),
        )

    @staticmethod
    def validate_workspace_broker_binding(
        broker_name: str,
        account_id: str | None,
    ) -> None:
        """Прийняти лише локальну CTRADER DEMO binding тесту."""
        if (str(broker_name).upper(), account_id) != ("CTRADER", "T10704"):
            raise RuntimeError("unexpected broker binding")

    @staticmethod
    def is_named_broker_connected(broker_name: str) -> bool:
        """Повернути локальний connected стан без мережевого виклику."""
        return str(broker_name).upper() == "CTRADER"

    @staticmethod
    def download_ctrader_historical_bars(**_kwargs: object) -> FakeHistoryResult:
        """Дати два strictly ordered completed bars для warm-up."""
        return FakeHistoryResult(
            bars=(
                FakeBar(
                    datetime(2026, 9, 1, 8, 30, tzinfo=UTC),
                    1.16920,
                    1.16960,
                    1.16910,
                    1.16950,
                    100.0,
                ),
                FakeBar(
                    datetime(2026, 9, 1, 8, 45, tzinfo=UTC),
                    1.16950,
                    1.17010,
                    1.16940,
                    1.16990,
                    120.0,
                ),
            )
        )

    def get_workspace_forex_quote_snapshot(
        self,
        broker_name: str,
        symbol_names: list[str],
    ) -> dict[str, object]:
        """Повернути наступний quote snapshot одного scripted lifecycle."""
        if str(broker_name).upper() != "CTRADER":
            raise RuntimeError("unexpected broker")
        symbols = tuple(sorted(str(symbol).upper() for symbol in symbol_names))
        if symbols != ("EURUSD",):
            raise RuntimeError("unexpected symbol set")
        index = min(self._quote_index, len(self._quotes) - 1)
        timestamp, bid, ask, volume = self._quotes[index]
        self._quote_index += 1
        self.quote_calls += 1
        self.served_quote_timestamps.append(
            datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        )
        return {
            "captured_utc": timestamp,
            "complete": True,
            "quotes": {
                "EURUSD": {
                    "symbol_name": "EURUSD",
                    "timestamp": timestamp,
                    "bid": bid,
                    "ask": ask,
                    "volume": volume,
                }
            },
            "subscribed_symbols": ["EURUSD"],
        }


class DispatchRecorderAlgorithm(PassiveWorkspaceAlgorithm):
    """Записати immutable events, які WorkspaceRuntime реально dispatch-ить."""

    def __init__(self, algorithm_id: str) -> None:
        super().__init__(algorithm_id)
        self.events: list[WorkspaceMarketEvent] = []

    def on_market_event(self, event: WorkspaceMarketEvent) -> None:
        """Зафіксувати один event після штатної started-state перевірки."""
        super().on_market_event(event)
        self.events.append(event)


def _workspace() -> AlgorithmWorkspace:
    """Побудувати мінімальний BROKER Live Read-only M15 workspace."""
    return AlgorithmWorkspace.create(
        broker="CTRADER",
        account_id="T10704",
        account_mode="DEMO",
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        data_mode=WORKSPACE_DATA_MODE_BROKER,
        parameters={
            "warmup_bars": 2,
            "spread_limit": 0.00100,
        },
    )


def _strictly_increasing(events: tuple[WorkspaceMarketEvent, ...]) -> bool:
    """Перевірити strict unique timestamp contract без його послаблення."""
    return all(
        current.timestamp > previous.timestamp
        for previous, current in zip(events, events[1:])
    )


def main() -> None:
    """Відтворити lifecycle та завершити RED із точним переліком порушень."""
    engine = FakeRuntimeEngine()
    provider = RuntimeEngineWorkspaceMarketProvider(engine)
    recorder = DispatchRecorderAlgorithm("RailAlgorithm")
    runtime = WorkspaceRuntime(
        _workspace(),
        algorithm_factory=lambda _algorithm_id: recorder,
        broker_market_provider=provider,
    )
    runtime.begin_start()
    runtime.complete_start()
    recorder.events.clear()

    first_event = runtime.advance_broker_market()
    updated_event = runtime.advance_broker_market()
    events_before_rollover = tuple(recorder.events)
    rollover_event = runtime.advance_broker_market()
    dispatched = tuple(recorder.events)

    same_bucket_updates = sum(
        FIRST_BUCKET <= timestamp < NEXT_BUCKET
        for timestamp in engine.served_quote_timestamps
    )
    timestamp_counts = Counter(event.timestamp for event in dispatched)
    same_timestamp_events_dispatched = timestamp_counts[FIRST_BUCKET]
    partial_bucket_reached_algorithm = bool(events_before_rollover)
    previous_bucket_dispatched_once_on_rollover = bool(
        len(events_before_rollover) == 0
        and len(dispatched) == 1
        and dispatched[0].timestamp == FIRST_BUCKET
        and rollover_event is not None
        and rollover_event.timestamp == FIRST_BUCKET
    )
    completed_timestamps_strictly_increasing = _strictly_increasing(dispatched)

    completed_broker_event = rollover_event
    if completed_broker_event is None:
        raise AssertionError("rollover did not produce a completed BROKER event")
    macd = WorkspaceMacdSignalSource.from_parameters({})
    macd_observations_before = len(macd.observations)
    macd.on_market_event(completed_broker_event)
    macd_accepts_broker_completed_bar = (
        len(macd.observations) == macd_observations_before + 1
    )

    production_algorithm = WorkspaceMacdAlligatorReplayAlgorithm("RailAlgorithm")
    production_algorithm.configure(
        runtime.context,
        dict(runtime.algorithm_parameters),
    )
    production_algorithm.start()
    production_macd = production_algorithm.source
    production_alligator = production_algorithm.signal_filter
    if production_macd is None or production_alligator is None:
        raise AssertionError("production components were not configured")
    production_macd_before = len(production_macd.observations)
    production_alligator_before = len(production_alligator.observations)
    production_algorithm.on_market_event(completed_broker_event)
    production_components_received_one_completed_bar = bool(
        len(production_macd.observations) == production_macd_before + 1
        and len(production_alligator.observations)
        == production_alligator_before + 1
    )
    production_algorithm.stop()

    stochastic_partial_state_mutation_detected = "NOT_MEASURED"
    alligator_duplicate_timestamp_rejected: bool | str = "NOT_APPLICABLE"
    alligator_partial_state_mutation_detected: bool | str = "NOT_APPLICABLE"
    if (
        first_event is not None
        and updated_event is not None
        and first_event.timestamp == updated_event.timestamp
    ):
        alligator = WorkspaceAlligatorFilter(
            enabled=True,
            confirmation_mode=WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
            timeframe="M15",
        )
        alligator.on_market_event(first_event)
        observations_before_repeat = len(alligator.observations)
        try:
            alligator.on_market_event(updated_event)
        except WorkspaceAlgorithmError as exc:
            alligator_duplicate_timestamp_rejected = (
                "strictly ordered and unique" in str(exc)
            )
        else:
            alligator_duplicate_timestamp_rejected = False
        alligator_partial_state_mutation_detected = (
            len(alligator.observations) != observations_before_repeat
        )

    contract_failures: list[str] = []
    if partial_bucket_reached_algorithm:
        contract_failures.append("partial current M15 bucket reached algorithm")
    if same_timestamp_events_dispatched > 1:
        contract_failures.append("same M15 timestamp was dispatched more than once")
    if not previous_bucket_dispatched_once_on_rollover:
        contract_failures.append(
            "previous M15 bucket was not dispatched exactly once on rollover"
        )
    if not completed_timestamps_strictly_increasing:
        contract_failures.append("algorithm timestamps are not strictly increasing")
    if not macd_accepts_broker_completed_bar:
        contract_failures.append("MACD ignored canonical completed BROKER bar")
    if not production_components_received_one_completed_bar:
        contract_failures.append(
            "production MACD/Alligator did not receive one completed BROKER bar"
        )
    completed_bar_contract_satisfied = not contract_failures

    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    print(f"same_bucket_updates={same_bucket_updates}")
    print(
        "same_timestamp_events_dispatched="
        f"{same_timestamp_events_dispatched}"
    )
    print(
        "partial_bucket_reached_algorithm="
        f"{partial_bucket_reached_algorithm}"
    )
    print(
        "previous_bucket_dispatched_once_on_rollover="
        f"{previous_bucket_dispatched_once_on_rollover}"
    )
    print(
        "completed_timestamps_strictly_increasing="
        f"{completed_timestamps_strictly_increasing}"
    )
    print(
        "macd_accepts_broker_completed_bar="
        f"{macd_accepts_broker_completed_bar}"
    )
    print(
        "production_components_received_one_completed_bar="
        f"{production_components_received_one_completed_bar}"
    )
    print(
        "stochastic_partial_state_mutation_detected="
        f"{stochastic_partial_state_mutation_detected}"
    )
    print(
        "alligator_duplicate_timestamp_rejected="
        f"{alligator_duplicate_timestamp_rejected}"
    )
    print(
        "alligator_partial_state_mutation_detected="
        f"{alligator_partial_state_mutation_detected}"
    )
    print(f"completed_bar_contract_satisfied={completed_bar_contract_satisfied}")
    print("broker_requests=0")
    print(f"broker_execution_attempted={engine.execution_attempts > 0}")
    print("production_logic_changed=False")

    if not completed_bar_contract_satisfied:
        print(f"contract_violations={' | '.join(contract_failures)}")
        print("T107_04_BROKER_COMPLETED_BAR_DELIVERY_CONTRACT=RED")
        raise AssertionError(
            "BROKER completed-bar delivery contract violated: "
            + "; ".join(contract_failures)
        )

    print("contract_violations=NONE")
    print("T107_04_BROKER_COMPLETED_BAR_DELIVERY_CONTRACT=GREEN")


if __name__ == "__main__":
    main()
