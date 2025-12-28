# brokers/ib_adapter.py
"""Адаптер для роботи з Interactive Brokers (IB Gateway / TWS)
через бібліотеку ib_insync.
"""

import logging

from ib_insync import IB, Forex, MarketOrder

from brokers.broker_adapter import BrokerAdapter
from core.lang_manager import LangManager

lang = LangManager()


class IBAdapter(BrokerAdapter):
    """Реалізація брокерського адаптера для Interactive Brokers."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 7497,
        client_id: int = 1,
        logger: logging.Logger | None = None,
    ) -> None:
        """Підключення до IB Gateway або TWS."""
        self.ib = IB()
        self.logger = logger or logging.getLogger(__name__)
        self.ib.connect(host, port, clientId=client_id)
        self.logger.info(lang.t("ib_connected"))

    def send_order(
        self,
        symbol: str,
        side: str,
        volume: float,
        price: float | None = None,
        sl: float | None = None,
        tp: float | None = None,
    ) -> int:
        """Відправлення ринкового ордера."""
        contract = Forex(symbol)
        order_type = "BUY" if side.upper() == "BUY" else "SELL"
        order = MarketOrder(order_type, volume)

        qualified = self.ib.qualifyContracts(contract)[0]
        trade = self.ib.placeOrder(qualified, order)

        order_id = trade.order.orderId
        self.logger.info(
            lang.t("ib_order_sent").format(side=side, symbol=symbol, order_id=order_id)
        )
        return order_id

    def cancel_order(self, order_id: int) -> None:
        """Скасування ордера."""
        for trade in self.ib.trades():
            if trade.order.orderId == order_id:
                self.ib.cancelOrder(trade.order)
                self.logger.info(lang.t("ib_order_cancelled").format(order_id=order_id))
                return
        self.logger.warning(lang.t("ib_order_not_found").format(order_id=order_id))

    def get_balance(self) -> float:
        """Отримати баланс рахунку (NetLiquidation)."""
        summary = self.ib.accountSummary()
        for item in summary:
            if item.tag == "NetLiquidation":
                return float(item.value)
        return 0.0

    def get_positions(self) -> list:
        """Отримати відкриті позиції."""
        return self.ib.positions()
