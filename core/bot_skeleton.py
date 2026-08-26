# core/bot_skeleton.py
"""
Базовий шаблон торгового бота (Skeleton)
Використовується для тестів, прототипування або симуляції торгового циклу.
"""

import asyncio

import ccxt.async_support as ccxt  # для асинхронних бірж через CCXT


class DataFeed:
    """Забезпечує отримання OHLCV-даних із біржі."""

    def __init__(self, exchange):
        self.exchange = exchange

    async def fetch_ohlcv(self, symbol, timeframe="1m", limit=100):
        """Отримує OHLCV (open-high-low-close-volume) дані."""
        return await self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)


class Strategy:
    """Проста стратегія EMA crossover (демо)."""

    def __init__(self):
        pass

    def signal(self, ohlcv):  # noqa
        """Повертає торговий сигнал: 'buy', 'sell' або None."""
        closes = [c[4] for c in ohlcv]
        if len(closes) < 50:
            return None

        short = sum(closes[-9:]) / 9
        long = sum(closes[-21:]) / 21

        if short > long:
            return "buy"
        elif short < long:
            return "sell"
        return None


class Executor:
    """Виконує ордери — поки що в режимі симуляції (paper trading)."""

    def __init__(self, exchange):
        self.exchange = exchange

    async def place_order(self, symbol, side, amount, price=None):  # noqa
        """Виконує або логічно симулює ордер."""
        print(f"ORDER {side.upper()} {amount} {symbol} @ {price or 'market'}")

        #  коли буде готово, розкоментуй для реальної торгівлі:

        # return await self.exchange.create_order(
        #     symbol, "limit" if price else "market", side, amount, price
        # )


async def main():
    """Запускає нескінченний торговий цикл."""
    exchange = ccxt.binance({"enableRateLimit": True})
    df = DataFeed(exchange)
    strat = Strategy()
    execu = Executor(exchange)
    symbol = "BTC/USDT"

    while True:
        ohlcv = await df.fetch_ohlcv(symbol, "1m", 200)
        s = strat.signal(ohlcv)
        if s:
            await execu.place_order(symbol, s, amount=0.001)
        await asyncio.sleep(60)  # чекати наступного бару


if __name__ == "__main__":
    asyncio.run(main())
