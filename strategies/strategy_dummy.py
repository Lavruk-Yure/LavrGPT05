# strategy_dummy.py


class DummyStrategy:
    def generate_signal(self, candles):
        if len(candles) < 20:
            return None
        last_price = candles[-1]["close"]
        prev_price = candles[-2]["close"]

        if last_price > prev_price:
            return ("long", last_price * 0.99, last_price * 1.02)
        elif last_price < prev_price:
            return ("short", last_price * 1.01, last_price * 0.98)
        return None
