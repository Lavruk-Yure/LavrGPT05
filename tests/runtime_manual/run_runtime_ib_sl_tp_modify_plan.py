# run_runtime_ib_sl_tp_modify_plan.py
"""
Real IB Paper SL/TP modify plan-only diagnostic.

RoadMap88:
- підключається до TWS;
- читає реальні positions і open orders;
- будує production SL/TP modify plan;
- блокує будь-який placeOrder/cancelOrder;
- не змінює broker state.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from unittest.mock import patch

from ibapi.client import EClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.broker_position import BrokerPosition  # noqa: E402
from engine.ib_adapter import IBAdapter  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)


def _format_price(value: float | None) -> str:
    """
    Показати optional broker price.
    """
    if value is None:
        return "None"

    return str(value)


def _read_optional_price(
    prompt: str,
    current_value: float | None,
) -> float | None:
    """
    Прочитати нове значення SL/TP.

    Enter:
        залишити поточне значення.

    -:
        видалити protection leg.

    Число:
        встановити нову ціну.
    """
    while True:
        raw_value = input(prompt).strip()

        if not raw_value:
            return current_value

        if raw_value == "-":
            return None

        normalized_value = raw_value.replace(",", ".")

        try:
            price = float(normalized_value)
        except ValueError:
            print("Введи число, Enter або '-'.")
            continue

        if price <= 0.0:
            print("Ціна має бути більшою за нуль.")
            continue

        return price


def _select_position_index(
    positions: list[BrokerPosition],
) -> int:
    """
    Вибрати індекс однієї IB position.
    """
    print()
    print("IB Paper positions:")

    for index, position in enumerate(positions, start=1):
        print(
            f"  {index}. "
            f"{position.position_id} | "
            f"side={position.side} | "
            f"volume={position.volume} | "
            f"SL={_format_price(position.stop_loss)} | "
            f"TP={_format_price(position.take_profit)}"
        )

    if len(positions) == 1:
        print()
        print("Автоматично вибрано єдину position.")
        return 0

    selected_position_index: int | None = None

    while selected_position_index is None:
        raw_index = input(f"Вибери position [1-{len(positions)}]: ").strip()

        try:
            entered_index = int(raw_index)
        except ValueError:
            print("Введи номер position.")
            continue

        if 1 <= entered_index <= len(positions):
            selected_position_index = entered_index - 1
        else:
            print("Номер position поза допустимим діапазоном.")

    return selected_position_index


def main() -> int:
    """
    Побудувати реальний IB SL/TP plan без execution.
    """
    host = os.getenv("IB_HOST", "127.0.0.1")
    port = int(os.getenv("IB_PORT", "7497"))
    client_id = int(os.getenv("IB_CLIENT_ID", "2"))

    adapter = IBAdapter(
        host=host,
        port=port,
        client_id=client_id,
        logger=logger,
    )

    try:
        connected = adapter.connect()

        print(f"connected={connected}")
        print(f"broker_state={adapter.broker_state}")

        if not connected:
            print("IB_SL_TP_MODIFY_REAL_PLAN=FAILED_CONNECTION")
            return 1

        positions = adapter.get_positions()

        if not positions:
            print("positions_count=0")
            print("IB_SL_TP_MODIFY_REAL_PLAN=SKIPPED_NO_POSITIONS")
            return 0

        selected_position_index = _select_position_index(
            positions,
        )
        position = positions[selected_position_index]

        print()
        print("Selected position:")
        print(f"  position_id={position.position_id}")
        print(f"  symbol={position.symbol_name}")
        print(f"  side={position.side}")
        print(f"  volume={position.volume}")
        print(f"  current_stop_loss={position.stop_loss}")
        print(f"  current_take_profit={position.take_profit}")

        print()
        print("Enter — залишити поточне значення.")
        print("-     — видалити SL або TP.")
        print("Число — встановити нову ціну.")

        stop_loss = _read_optional_price(
            prompt=(
                "New Stop Loss " f"[current={_format_price(position.stop_loss)}]: "
            ),
            current_value=position.stop_loss,
        )

        take_profit = _read_optional_price(
            prompt=(
                "New Take Profit " f"[current={_format_price(position.take_profit)}]: "
            ),
            current_value=position.take_profit,
        )

        with (
            patch.object(
                EClient,
                "placeOrder",
                side_effect=AssertionError(
                    "placeOrder() called in plan-only diagnostic"
                ),
            ),
            patch.object(
                EClient,
                "cancelOrder",
                side_effect=AssertionError(
                    "cancelOrder() called in plan-only diagnostic"
                ),
            ),
        ):
            result = adapter.modify_position_sl_tp(
                position_id=position.position_id,
                stop_loss=stop_loss,
                take_profit=take_profit,
            )

        print()
        print("IB SL/TP real plan:")
        print(f"  broker_position_id={result['broker_position_id']}")
        print(f"  account_id={result['account_id']}")
        print(f"  symbol_name={result['symbol_name']}")
        print(f"  position_side={result['position_side']}")
        print(f"  position_volume={result['position_volume']}")
        print(f"  protective_action={result['protective_action']}")
        print(f"  current_stop_loss={result['current_stop_loss']}")
        print(f"  current_take_profit={result['current_take_profit']}")
        print(f"  new_stop_loss={result['new_stop_loss']}")
        print(f"  new_take_profit={result['new_take_profit']}")
        print(f"  stop_loss_action={result['stop_loss_action']}")
        print(f"  take_profit_action={result['take_profit_action']}")
        print(f"  requires_oca_group={result['requires_oca_group']}")
        print(f"  oca_relink_legs={result['oca_relink_legs']}")
        print(f"  blocked={result['blocked']}")
        print(f"  blocked_flags={result['blocked_flags']}")
        print(f"  reason={result['reason']}")
        print(f"  plan_only={result['plan_only']}")
        print(f"  executed={result['executed']}")

        if result["plan_only"] is not True:
            raise AssertionError("Plan-only flag is not True")

        if result["executed"] is not False:
            raise AssertionError("Executed flag is not False")

        print("IB_SL_TP_MODIFY_REAL_PLAN=OK")
        return 0

    except Exception as exc:  # noqa: BLE001
        logger.exception("IB SL/TP real plan diagnostic failed.")
        print("IB_SL_TP_MODIFY_REAL_PLAN=FAILED")
        print(f"reason={exc}")
        return 1

    finally:
        adapter.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
