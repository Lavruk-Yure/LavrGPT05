"""Synthetic RuntimeEngine order-mode identity and persistence check."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.runtime_account_state import RuntimeAccountState  # noqa: E402
from engine.runtime_broker_health import RuntimeBrokerHealth  # noqa: E402
from engine.runtime_engine import RuntimeEngine  # noqa: E402


class _CTraderService:
    """Minimal cTrader service that records the broker-bound comment."""

    def __init__(self) -> None:
        self.comments: list[str] = []
        self._account_state = RuntimeAccountState(
            broker_name="CTRADER",
            account_id="46368962",
            currency="USD",
        )

    @staticmethod
    def connect_demo() -> object | None:
        raise AssertionError("Unexpected connect_demo call")

    @staticmethod
    def connect_live() -> object | None:
        raise AssertionError("Unexpected connect_live call")

    @staticmethod
    def disconnect() -> None:
        return None

    @staticmethod
    def reconnect() -> object | None:
        raise AssertionError("Unexpected reconnect call")

    @staticmethod
    def get_positions() -> list:
        return []

    @staticmethod
    def get_broker_health() -> RuntimeBrokerHealth:
        return RuntimeBrokerHealth()

    def get_account_state(self) -> RuntimeAccountState:
        return self._account_state

    @staticmethod
    def get_account_list() -> list[dict]:
        return []

    def place_market_order(
        self,
        symbol_name: str,
        side: str,
        lots: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        comment: str = "LGE manual order",
    ) -> dict[str, Any]:
        _ = symbol_name, side, lots, stop_loss, take_profit
        self.comments.append(comment)
        return {"order_id": "501"}

    @staticmethod
    def close_position(
        position_id: int | str,
        lots: float | None = None,
    ) -> object:
        _ = position_id, lots
        raise AssertionError("Unexpected close_position call")

    @staticmethod
    def modify_position_sl_tp(
        position_id: int | str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> dict:
        _ = position_id, stop_loss, take_profit
        raise AssertionError("Unexpected modify_position_sl_tp call")


def main() -> int:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test.db"
        engine = RuntimeEngine(db_path=str(db_path))
        service = _CTraderService()
        service_for_test: Any = service
        engine.set_ctrader_runtime_service(service_for_test)
        engine.set_active_broker("CTRADER", require_connected=False)

        result = engine.place_manual_market_order(
            symbol_name="EURUSD",
            side="BUY",
            lots=0.01,
            comment="Signal 17",
            control_mode="SEMI",
        )

        assert service.comments == ["[LGE:S] Signal 17"]
        assert result["control_mode"] == "SEMI"
        assert result["display_comment"] == "Signal 17"
        assert result["broker_comment"] == "[LGE:S] Signal 17"

        connection = sqlite3.connect(db_path)
        try:
            trade_row = connection.execute(
                """
                SELECT source, comment
                FROM trades
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
            plan_source = connection.execute(
                "SELECT source FROM order_plans ORDER BY id DESC LIMIT 1"
            ).fetchone()[0]
            order_row = connection.execute(
                """
                SELECT source, broker_comment
                FROM broker_orders
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
        finally:
            connection.close()
            engine.connection.close()

        assert trade_row == ("SEMI", "Signal 17")
        assert plan_source == "SEMI"
        assert order_row == ("SEMI", "[LGE:S] Signal 17")

    print("RuntimeEngine order identity result")
    print("  broker_comment=[LGE:S] Signal 17")
    print("  display_comment=Signal 17")
    print("  trade_source=SEMI")
    print("  trade_comment=Signal 17")
    print("  order_plan_source=SEMI")
    print("  broker_order_source=SEMI")
    print("  broker_order_comment=[LGE:S] Signal 17")
    print("RUNTIME_ENGINE_ORDER_IDENTITY_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
