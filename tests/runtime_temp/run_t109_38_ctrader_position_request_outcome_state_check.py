"""T109-38: cTrader position request terminal outcome state check.

Призначення:
- перевірити production repair, який відокремлює SUCCESS, REQUEST_ERROR,
  TIMEOUT і DISCONNECTED для cTrader reconcile positions request;
- довести, що успішній порожній snapshot більше не можна сплутати з
  deferred error, timeout або disconnect;
- не вводити broker-neutral snapshot DTO і не підключати Workspace submit.

Pipeline:
CTraderAdapter.get_positions() -> fake local client/deferred -> terminal callback
-> positions_request_outcome / positions_request_failure_reason.

Causality / safety:
- реальний broker client не створюється і мережевих request немає;
- усі completion paths моделюються локальними fake objects;
- broker_requests=0;
- trading logic, controller і Replay не змінюються.

Assertions / outputs:
- SUCCESS для ProtoOAReconcileRes з порожнім payload;
- REQUEST_ERROR для deferred errback;
- TIMEOUT для request без completion;
- DISCONNECTED до request і під час активного request;
- failure reason не змішується з SUCCESS;
- наступна межа повертається до broker-neutral snapshot mapping.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Callable

TEST_ID = "T109-38"
PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

ctrader_module = importlib.import_module("engine.ctrader_adapter")
connection_state_module = importlib.import_module("engine.broker_connection_state")

CTraderAdapter = getattr(ctrader_module, "CTraderAdapter")
CTraderRuntimeConfig = getattr(ctrader_module, "CTraderRuntimeConfig")
BrokerConnectionState = getattr(connection_state_module, "BrokerConnectionState")

OUTCOME_SUCCESS = getattr(
    ctrader_module,
    "CTRADER_POSITION_REQUEST_OUTCOME_SUCCESS",
)
OUTCOME_REQUEST_ERROR = getattr(
    ctrader_module,
    "CTRADER_POSITION_REQUEST_OUTCOME_REQUEST_ERROR",
)
OUTCOME_TIMEOUT = getattr(
    ctrader_module,
    "CTRADER_POSITION_REQUEST_OUTCOME_TIMEOUT",
)
OUTCOME_DISCONNECTED = getattr(
    ctrader_module,
    "CTRADER_POSITION_REQUEST_OUTCOME_DISCONNECTED",
)


class _Payload:
    """TEST_ONLY empty reconcile response payload."""

    position: list[object] = []


class _Deferred:
    """TEST_ONLY Deferred subset used by CTraderAdapter.get_positions()."""

    def __init__(self, error: object | None = None) -> None:
        self._error = error

    # noinspection PyPep8Naming
    def addErrback(
        self,
        callback: Callable[[object], Any],
    ) -> None:  # noqa: N802
        """Invoke the errback immediately when a local failure is configured."""

        if self._error is not None:
            callback(self._error)


class _FakeClient:
    """TEST_ONLY client that never touches cTrader network transport."""

    def __init__(
        self,
        adapter: Any,
        mode: str,
    ) -> None:
        self.adapter = adapter
        self.mode = mode
        self.send_calls = 0

    def send(self, _request: object) -> _Deferred:
        """Complete one request locally according to the configured mode."""

        self.send_calls += 1
        if self.mode == "SUCCESS":
            callback = getattr(self.adapter, "_on_reconcile_res")
            callback(_Payload())
            return _Deferred()
        if self.mode == "REQUEST_ERROR":
            return _Deferred(RuntimeError("TEST_ONLY deferred error"))
        if self.mode == "DISCONNECTED":
            callback = getattr(self.adapter, "_on_disconnected")
            callback(self, "TEST_ONLY disconnect")
            return _Deferred()
        return _Deferred()


def _new_adapter() -> Any:
    """Create a disconnected production adapter without starting a client."""

    config = CTraderRuntimeConfig(
        client_id="TEST_ONLY",
        client_secret="TEST_ONLY",
        access_token="TEST_ONLY",
        ctid_trader_account_id=1,
        account_mode="DEMO",
    )
    return CTraderAdapter(config=config)


def _connected_adapter(mode: str) -> tuple[Any, _FakeClient]:
    """Create a connected adapter backed only by a local fake client."""

    adapter = _new_adapter()
    adapter.state.connection_state = BrokerConnectionState.CONNECTED
    fake_client = _FakeClient(adapter, mode)
    adapter.client = fake_client
    return adapter, fake_client


def main() -> None:
    """Run deterministic terminal-outcome checks with no broker requests."""

    disconnected = _new_adapter()
    disconnected_positions = disconnected.get_positions()
    assert disconnected_positions == []
    assert disconnected.positions_request_outcome == OUTCOME_DISCONNECTED
    assert disconnected.positions_request_failure_reason

    success, success_client = _connected_adapter("SUCCESS")
    success_positions = success.get_positions()
    assert success_positions == []
    assert success.positions_request_outcome == OUTCOME_SUCCESS
    assert success.positions_request_failure_reason == ""
    assert success_client.send_calls == 1

    request_error, error_client = _connected_adapter("REQUEST_ERROR")
    error_positions = request_error.get_positions()
    assert error_positions == []
    assert request_error.positions_request_outcome == OUTCOME_REQUEST_ERROR
    assert "TEST_ONLY deferred error" in request_error.positions_request_failure_reason
    assert error_client.send_calls == 1

    timeout, timeout_client = _connected_adapter("TIMEOUT")
    original_timeout = getattr(ctrader_module, "CTRADER_POSITIONS_TIMEOUT_SECONDS")
    setattr(ctrader_module, "CTRADER_POSITIONS_TIMEOUT_SECONDS", 0.0)
    try:
        timeout_positions = timeout.get_positions()
    finally:
        setattr(
            ctrader_module,
            "CTRADER_POSITIONS_TIMEOUT_SECONDS",
            original_timeout,
        )
    assert timeout_positions == []
    assert timeout.positions_request_outcome == OUTCOME_TIMEOUT
    assert timeout.positions_request_failure_reason == "cTrader reconcile timeout."
    assert timeout_client.send_calls == 1

    late_success = getattr(timeout, "_on_reconcile_res")
    late_success(_Payload())
    assert timeout.positions_request_outcome == OUTCOME_TIMEOUT

    mid_disconnect, disconnect_client = _connected_adapter("DISCONNECTED")
    mid_disconnect_positions = mid_disconnect.get_positions()
    assert mid_disconnect_positions == []
    assert mid_disconnect.positions_request_outcome == OUTCOME_DISCONNECTED
    assert "TEST_ONLY disconnect" in mid_disconnect.positions_request_failure_reason
    assert disconnect_client.send_calls == 1

    print(f"{TEST_ID}_CTRADER_POSITION_REQUEST_OUTCOME_STATE=OK")
    print("production_change=True")
    print("success_outcome_distinct=True")
    print("request_error_outcome_distinct=True")
    print("timeout_outcome_distinct=True")
    print("disconnected_outcome_distinct=True")
    print("empty_success_not_conflated_with_error=True")
    print("late_success_cannot_overwrite_terminal_failure=True")
    print("failure_reason_preserved=True")
    print("broker_neutral_snapshot_dto_wired=False")
    print("workspace_controller_submission_wiring=False")
    print("broker_requests=0")
    print(
        "first_unresolved_boundary="
        "BROKER_POSITION_SNAPSHOT_RESULT_TYPE_AND_ADAPTER_MAPPING"
    )
    print(
        "boundary_contract=BROKER_NEUTRAL_POSITION_SNAPSHOT_MUST_MAP_DISTINCT_"
        "CTRADER_TERMINAL_OUTCOMES_BEFORE_EMPTY_SUCCESS_CAN_MEAN_CONFIRMED_FLAT"
    )
    print("factual_verdict=A. CTRADER_POSITION_REQUEST_OUTCOME_STATE_GREEN")


if __name__ == "__main__":
    main()
