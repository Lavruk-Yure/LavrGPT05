# ctrader_dummy.py

"""Клас DummyCTrader містить у собі всю логіку мок-API.
Клас DummyCTraderBroker виступає адаптером,
який делегує виклики методів обʼєкта DummyCTrader."""
import uuid


class DummyCTrader:
    def __init__(self):
        self.balance = 10_000
        self.open_orders = {}
        self.positions = {}

    def get_account_info(self):
        return {"account_id": "DUMMY001", "balance": self.balance, "currency": "USD"}

    def place_order(self, symbol, volume, side, order_type, price=None):
        order_id = str(uuid.uuid4())
        order = {
            "id": order_id,
            "symbol": symbol,
            "volume": volume,
            "side": side,
            "type": order_type,
            "price": price,
            "status": "filled" if order_type == "market" else "open",
        }
        self.open_orders[order_id] = order

        # Якщо ордер ринковий — одразу створюємо позицію
        if order_type == "market":
            self.positions[symbol] = {
                "symbol": symbol,
                "volume": volume,
                "side": side,
                "avg_price": price if price else 1.2345,
            }

        return order_id

    def cancel_order(self, order_id):
        if order_id in self.open_orders:
            self.open_orders[order_id]["status"] = "cancelled"
            return True
        return False

    def get_open_orders(self):
        return [o for o in self.open_orders.values() if o["status"] == "open"]

    def get_positions(self):
        return list(self.positions.values())


class DummyCTraderBroker:
    def __init__(self):
        self.api = DummyCTrader()

    def get_account_info(self):
        return self.api.get_account_info()

    def place_order(self, symbol, volume, side, order_type="market", price=None):
        return self.api.place_order(symbol, volume, side, order_type, price)

    def cancel_order(self, order_id):
        return self.api.cancel_order(order_id)

    def get_open_orders(self):
        return self.api.get_open_orders()

    def get_positions(self):
        return self.api.get_positions()
