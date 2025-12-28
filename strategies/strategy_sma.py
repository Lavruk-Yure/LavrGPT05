# strategy_sma.py


class SMAStrategy:
    """
    Simple Moving Average (SMA) crossover trading strategy.

    Атрибути:
        sma_fast (int): Параметр швидкого SMA.
        sma_slow (int): Параметр повільного SMA.
        sl_coef (float): Коефіцієнт для визначення стоп-лоссу (як відсоток від ціни).
        rr_ratio (float): Співвідношення ризику до прибутку для тейк-профіту.
    """

    def __init__(
        self,
        sma_fast: int = 3,
        sma_slow: int = 5,
        sl_coef: float = 0.01,
        rr_ratio: float = 2.0,
    ):
        """
        Ініціалізація параметрів стратегії.

        :param sma_fast: Період швидкої SMA
        :param sma_slow: період повільної SMA
        :param sl_coef: коефіцієнт стоп-лоссу (відсоток від ціни)
        :param rr_ratio: співвідношення ризику до прибутку
        """
        self.sma_fast = sma_fast
        self.sma_slow = sma_slow
        self.sl_coef = sl_coef  # стоп як відсоток від ціни
        self.rr_ratio = rr_ratio
        self.prev_fast = None
        self.prev_slow = None

    def generate_signal(self, candles):
        """
        Генерує торговий сигнал на основі перетину SMA.

        Сигнал "long" генерується, якщо швидка SMA перетинає повільну знизу вверх.
        Сигнал "short" генерується, якщо швидка SMA перетинає повільну зверху вниз.

        :param candles: Список словників зі свічками,
         кожна свічка має ключ 'close' для закриття.
        :return: Кортеж (side, stop_loss, take_profit) або None, якщо сигнал відсутній.
        """
        if len(candles) < self.sma_slow:
            return None

        closes = [c["close"] for c in candles]

        sma_fast = sum(closes[-self.sma_fast :]) / self.sma_fast
        sma_slow = sum(closes[-self.sma_slow :]) / self.sma_slow

        signal = None
        if self.prev_fast is not None and self.prev_slow is not None:
            # Long: fast SMA перетинає slow SMA знизу вгору
            if self.prev_fast <= self.prev_slow and sma_fast > sma_slow:
                entry_price = closes[-1]
                stop_loss = entry_price * (1 - self.sl_coef)
                take_profit = entry_price + (entry_price - stop_loss) * self.rr_ratio
                signal = ("long", stop_loss, take_profit)

            # Short: fast SMA перетинає slow SMA зверху вниз
            elif self.prev_fast >= self.prev_slow and sma_fast < sma_slow:
                entry_price = closes[-1]
                stop_loss = entry_price * (1 + self.sl_coef)
                take_profit = entry_price - (stop_loss - entry_price) * self.rr_ratio
                signal = ("short", stop_loss, take_profit)

        self.prev_fast = sma_fast
        self.prev_slow = sma_slow
        return signal
