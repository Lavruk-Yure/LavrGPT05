# brokers/ctrader_adapter.py
"""Адаптер для роботи з cTrader Open API (через REST).
Підтримує режим demo/live.
"""

import logging
from typing import Any

import requests

from brokers.broker_adapter import BrokerAdapter
from core.lang_manager import LangManager

lang = LangManager()


class CTraderAdapter(BrokerAdapter):
    """Реалізація брокерського адаптера для cTrader."""

    def __init__(
        self,
        api_token: str,
        demo: bool = True,
        logger: logging.Logger | None = None,
    ) -> None:
        """Підключення до cTrader API."""
        self.api_token = api_token
        self.logger = logger or logging.getLogger(__name__)
        self.base_url = (
            "https://demo.ctraderapi.com" if demo else "https://api.spotware.com"
        )
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json",
            }
        )
        self.logger.info(
            lang.t("ctrader_connected").format(
                mode=lang.t("demo") if demo else lang.t("real")
            )
        )

    def send_order(
        self,
        symbol: str,
        side: str,
        volume: float,
        price: float | None = None,
        sl: float | None = None,
        tp: float | None = None,
    ) -> Any:
        """Відправлення ринкового ордера."""
        endpoint = f"{self.base_url}/trading/openpositions"
        data = {
            "symbol": symbol,
            "volume": volume,
            "tradeType": "Buy" if side.upper() == "BUY" else "Sell",
        }
        if sl:
            data["stopLoss"] = sl
        if tp:
            data["takeProfit"] = tp

        response = self.session.post(endpoint, json=data)
        if response.status_code == 201:
            order_id = response.json().get("id")
            self.logger.info(
                lang.t("ctrader_order_sent").format(
                    side=side, symbol=symbol, order_id=order_id
                )
            )

            return order_id

        self.logger.error(
            lang.t("ctrader_order_send_error").format(response=response.text)
        )
        return None

    def cancel_order(self, order_id: Any) -> None:
        """Скасування ордера."""
        endpoint = f"{self.base_url}/trading/orders/{order_id}"
        response = self.session.delete(endpoint)
        if response.status_code == 200:
            self.logger.info(
                lang.t("ctrader_order_cancelled").format(order_id=order_id)
            )
        else:
            self.logger.error(
                lang.t("ctrader_order_cancel_error").format(
                    order_id=order_id, response=response.text
                )
            )

    def get_balance(self) -> float:
        """Отримати баланс торгового рахунку."""
        endpoint = f"{self.base_url}/trading/accounts"
        response = self.session.get(endpoint)
        if response.status_code == 200:
            accounts = response.json()
            return accounts[0].get("balance", 0.0)
        return 0.0

    def get_positions(self) -> list[dict[str, Any]]:
        """Отримати список відкритих позицій."""
        endpoint = f"{self.base_url}/trading/openpositions"
        response = self.session.get(endpoint)
        if response.status_code == 200:
            return response.json()
        return []
