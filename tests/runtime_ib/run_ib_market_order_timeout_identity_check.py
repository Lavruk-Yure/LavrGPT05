"""Synthetic IB MARKET timeout identity and callback-race check."""

from __future__ import annotations

import importlib
import logging
import sys
import threading
import types
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _install_ibapi_stubs() -> None:
    """Install minimal ibapi modules only when the package is unavailable."""

    class _FlexibleObject:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

    package = types.ModuleType("ibapi")
    package.__path__ = []
    modules = {
        "ibapi": package,
        "ibapi.client": types.ModuleType("ibapi.client"),
        "ibapi.contract": types.ModuleType("ibapi.contract"),
        "ibapi.execution": types.ModuleType("ibapi.execution"),
        "ibapi.order": types.ModuleType("ibapi.order"),
        "ibapi.order_cancel": types.ModuleType("ibapi.order_cancel"),
        "ibapi.wrapper": types.ModuleType("ibapi.wrapper"),
    }
    setattr(modules["ibapi.client"], "EClient", _FlexibleObject)
    setattr(modules["ibapi.contract"], "Contract", _FlexibleObject)
    setattr(modules["ibapi.execution"], "ExecutionFilter", _FlexibleObject)
    setattr(modules["ibapi.order"], "Order", _FlexibleObject)
    setattr(modules["ibapi.order_cancel"], "OrderCancel", _FlexibleObject)
    setattr(modules["ibapi.wrapper"], "EWrapper", _FlexibleObject)
    sys.modules.update(modules)


def _load_adapter_types():
    try:
        adapter_module = importlib.import_module("engine.ib_adapter")
    except ModuleNotFoundError as error:
        if not str(error.name or "").startswith("ibapi"):
            raise

        _install_ibapi_stubs()
        adapter_module = importlib.import_module("engine.ib_adapter")

    errors_module = importlib.import_module("engine.ib_order_errors")
    return adapter_module.IBAdapter, errors_module.IBMarketOrderTimeoutError


class _NonSignallingEvent:
    """Model a missed event signal while preserving callback rows."""

    @staticmethod
    def clear() -> None:
        return None

    @staticmethod
    def wait(timeout: float) -> bool:
        if timeout < 0.0:
            raise ValueError("timeout must not be negative")
        return False


class _Wrapper:
    """Minimal wrapper state consumed by place_market_order()."""

    def __init__(self, *, status: str) -> None:
        self.order_event = _NonSignallingEvent()
        self.open_orders: list[dict[str, Any]] = []
        self.order_statuses: list[dict[str, Any]] = []
        self.order_errors: list[str] = []
        self.active_order_id: int | None = None
        self.active_order_ids: set[int] = set()
        self.next_valid_id = 700
        self.status = status


class _Client:
    """Publish one orderStatus row without setting the terminal event."""

    def __init__(self, wrapper: _Wrapper) -> None:
        self.wrapper = wrapper
        self.order_ids: list[int] = []
        self.order_refs: list[str] = []

    # noinspection PyPep8Naming
    def placeOrder(self, order_id, _contract, order) -> None:  # noqa: N802
        order_id_value = int(order_id)
        self.order_ids.append(order_id_value)
        self.order_refs.append(str(getattr(order, "orderRef", "") or ""))
        filled = 1000.0 if self.wrapper.status.upper() == "FILLED" else 0.0
        remaining = 0.0 if filled else 1000.0
        self.wrapper.order_statuses.append(
            {
                "order_id": order_id_value,
                "status": self.wrapper.status,
                "filled": filled,
                "remaining": remaining,
                "avg_fill_price": 1.1426 if filled else 0.0,
            }
        )


def _build_adapter(adapter_type, *, status: str) -> tuple[Any, _Client]:
    wrapper = _Wrapper(status=status)
    adapter = adapter_type.__new__(adapter_type)
    adapter._connected = True
    adapter._wrapper = wrapper
    client = _Client(wrapper)
    adapter._client = client
    adapter._client_id = 1
    adapter._logger = logging.getLogger(__name__)
    adapter._order_id_lock = threading.RLock()
    return adapter, client


def main() -> int:
    adapter_type, timeout_error_type = _load_adapter_types()
    timed_out, timed_out_client = _build_adapter(
        adapter_type,
        status="Submitted",
    )

    try:
        timed_out.place_market_order(
            symbol_name="EURUSD",
            side="BUY",
            quantity=1000.0,
        )
    except timeout_error_type as error:
        assert error.order_id == 700
        assert error.symbol_name == "EURUSD"
        assert error.side == "BUY"
        assert error.quantity == 1000.0
        assert error.current_client_id == 1
        assert error.child_order_ids == ()
        assert error.stop_loss_order_id is None
        assert error.take_profit_order_id is None
        assert error.comment == "[LGE:M] LGE manual order"
        assert timed_out_client.order_refs == ["[LGE:M] LGE manual order"]
        assert "Do not repeat the order" in str(error)
    else:
        raise AssertionError("Missed MARKET callback did not raise typed timeout")

    filled, filled_client = _build_adapter(
        adapter_type,
        status="Filled",
    )
    result = filled.place_market_order(
        symbol_name="EURUSD",
        side="BUY",
        quantity=1000.0,
    )

    assert result["parent_order_id"] == "700"
    assert result["status"] == "FILLED"
    assert result["filled"] == 1000.0
    assert result["control_mode"] == "MANUAL"
    assert result["display_comment"] == "LGE manual order"
    assert result["broker_comment"] == "[LGE:M] LGE manual order"
    assert filled_client.order_refs == ["[LGE:M] LGE manual order"]

    print("IB MARKET timeout identity result")
    print("  timeout_order_id=700")
    print("  duplicate_order_warning=True")
    print("  timeout_identity_metadata=True")
    print("  broker_comment_prefix=[LGE:M]")
    print("  filled_status_without_event_accepted=True")
    print("IB_MARKET_ORDER_TIMEOUT_IDENTITY_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
