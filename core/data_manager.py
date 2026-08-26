# data_manager.py
# --- Python 3.13---

import pandas as pd
from ib_insync import IB, Forex


class DataManager:
    def __init__(self, backend="ib", **kwargs):
        self.backend = backend.lower()
        if self.backend == "ib":
            self._init_ib(kwargs)
        elif self.backend == "ctrader":
            self._init_ctrader(kwargs)
        elif self.backend == "dummy":
            self._init_dummy()
        else:
            raise ValueError(f"Unknown backend: {backend}")

    def _init_ib(self, kwargs):
        self.ib = IB()
        host = kwargs.get("host", "127.0.0.1")
        port = kwargs.get("port", 7497)
        client_id = kwargs.get("client_id", 1)
        self.ib.connect(host, port, clientId=client_id)
        self.host = host
        self.port = port
        self.client_id = client_id

    def _init_ctrader(self, kwargs):
        self.access_token = kwargs.get("access_token", "")
        self.refresh_token = kwargs.get("refresh_token", "")
        self.account_id = kwargs.get("account_id", 0)
        # Тут можна додати ініціалізацію cTrader API клієнта

    def _init_dummy(self):
        # Заглушка для тестування
        pass

    # Методи IB:
    def get_forex_contract(self, symbol: str):
        if self.backend != "ib":
            raise NotImplementedError("get_forex_contract for IB only")
        contract = Forex(symbol)
        self.ib.qualifyContracts(contract)
        return contract

    def get_last_price(self, symbol: str) -> float:
        if self.backend != "ib":
            raise NotImplementedError("get_last_price for IB only")
        contract = self.get_forex_contract(symbol)
        ticker = self.ib.reqMktData(contract, "", False, False)
        self.ib.sleep(1)
        return ticker.last if ticker.last else 0.0

    def get_historical_data(self, symbol: str, duration="1 D", bar_size="5 mins"):
        if self.backend != "ib":
            raise NotImplementedError("get_historical_data for IB only")
        contract = self.get_forex_contract(symbol)
        bars = self.ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow="MIDPOINT",
            useRTH=False,
        )
        return pd.DataFrame(bars)

    # Методи cTrader можна додати тут пізніше

    # Заглушки або інші методи для dummy


# Приклад ініціалізації:
# dm_ib = DataManager(backend="ib", host="localhost", port=7497, client_id=1)
# dm_ctrader = DataManager(backend="ctrader", access_token="...", refresh_token="...",
# account_id=123)
# dm_dummy = DataManager(backend="dummy")
# 34567801234567890123456789012345678901234567890123456789012345678901234567890123456789
