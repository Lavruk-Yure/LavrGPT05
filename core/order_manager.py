# core/order_manager.py
"""Менеджер виставляння ордерів у різних режимах роботи:
manual, semi_auto, auto.

Працює через підключений брокерський адаптер (IB, cTrader тощо)
та модуль аналізу сигналів (analyzer).
"""

import logging
from enum import Enum
from typing import Any

from core.lang_manager import LangManager

lang = LangManager()


class OrderMode(Enum):
    """Режим роботи менеджера ордерів."""

    MANUAL = "manual"
    SEMI_AUTO = "semi_auto"
    AUTO = "auto"


class OrderManager:
    """Керує логікою виставляння ордерів залежно від режиму."""

    def __init__(
        self,
        mode: OrderMode = OrderMode.MANUAL,
        broker: Any | None = None,
        analyzer: Any | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.mode = mode
        self.broker = broker  # IBAdapter, CTraderAdapter, тощо
        self.analyzer = analyzer  # модуль аналізу / пояснення сигналів
        self.logger = logger or logging.getLogger(__name__)

    # -------------------------- Керування режимом --------------------------

    def set_mode(self, mode: OrderMode) -> None:
        """Змінює режим роботи менеджера."""
        self.mode = mode
        self.logger.info(lang.t("mode_changed").format(mode=mode.value.upper()))

    # -------------------------- Виставляння ордера ------------------------

    def place_order(
        self,
        symbol: str,
        side: str,
        volume: float,
        price: float | None = None,
        sl: float | None = None,
        tp: float | None = None,
    ) -> Any:
        """Основна точка входу для виставляння ордерів."""
        if self.mode == OrderMode.MANUAL:
            return self._manual_order(symbol, side, volume, price, sl, tp)

        if self.mode == OrderMode.SEMI_AUTO:
            return self._semi_auto_order(symbol, side, volume, price, sl, tp)

        if self.mode == OrderMode.AUTO:
            return self._auto_order(symbol, side, volume, price, sl, tp)

        # Запобігання помилковим режимам
        self.logger.warning(lang.t("unknown_mode").format(mode=self.mode))  # noqa
        return None  # noqa

    # -------------------------- Режими роботи -----------------------------

    def _manual_order(
        self, symbol: str, side: str, volume: float, price, sl, tp
    ) -> None:
        """Ручний режим — трейдер підтверджує угоду самостійно."""
        _ = price  # параметр не використовується, але потрібен для сумісності
        self.logger.info(lang.t("manual_mode_order_not_sent"))
        self.logger.info(
            lang.t("manual_trade_confirmation").format(
                symbol=symbol, side=side, volume=volume, sl=sl, tp=tp
            )
        )
        return None

    def _semi_auto_order(
        self, symbol: str, side: str, volume: float, price, sl, tp
    ) -> Any:
        """Напівавтоматичний режим — трейдер підтверджує після аналізу."""
        justification = (
            self.analyzer.analyze(symbol, side) if self.analyzer else "Без пояснення."
        )
        self.logger.info(lang.t("semi_auto_signal").format(symbol=symbol, side=side))
        self.logger.info(
            lang.t("justification_text").format(justification=justification)
        )
        confirm = input(lang.t("confirm_trade") + " ")
        if confirm.lower() == "y":
            return self._send_to_broker(symbol, side, volume, price, sl, tp)

        self.logger.info(lang.t("trade_rejected_by_trader"))
        return None

    def _auto_order(self, symbol: str, side: str, volume: float, price, sl, tp) -> Any:
        """Автоматичний режим — ордер виконується без підтвердження."""
        self.logger.info(lang.t("auto_mode_order_executing"))
        return self._send_to_broker(symbol, side, volume, price, sl, tp)

    # -------------------------- Відправлення брокеру ----------------------

    def _send_to_broker(
        self, symbol: str, side: str, volume: float, price, sl, tp
    ) -> Any:
        """Відправляє ордер брокеру через адаптер."""
        if not self.broker:
            self.logger.error(lang.t("broker_not_connected"))
            return None

        order_id = self.broker.send_order(symbol, side, volume, price, sl, tp)
        self.logger.info(lang.t("order_sent_to_broker").format(order_id=order_id))
        return order_id
