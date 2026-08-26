# ctrader_lot.py
"""
Перерахунок FX lot <-> cTrader Open API volume.

Зафіксовано по факту тестів для поточного demo-оточення:
- 0.01 lot (мінімальний FX lot у UI) відповідає мінімальному
  значенню volume для Open API = 100000
- звідси:
  1.00 lot = 10_000_000 api-volume

Увага:
це правило зафіксоване для поточного broker/account environment
і має використовуватись у наших cTrader FX тестах та адаптері.
"""

from __future__ import annotations

API_VOLUME_PER_1_LOT_FX = 10_000_000
MIN_LOT_FX = 0.01
MIN_API_VOLUME_FX = int(API_VOLUME_PER_1_LOT_FX * MIN_LOT_FX)


def lots_to_api_volume(lots: float) -> int:
    """Перевести FX lots у cTrader Open API volume."""
    return int(round(lots * API_VOLUME_PER_1_LOT_FX))


def api_volume_to_lots(api_volume: int) -> float:
    """Перевести cTrader Open API volume у FX lots."""
    return float(api_volume) / float(API_VOLUME_PER_1_LOT_FX)


def normalize_fx_lots(lots: float) -> float:
    """Нормалізувати lots до мінімального FX значення."""
    if lots < MIN_LOT_FX:
        return MIN_LOT_FX
    return lots


def normalize_fx_api_volume(api_volume: int) -> int:
    """Нормалізувати Open API volume до мінімального FX значення."""
    if api_volume < MIN_API_VOLUME_FX:
        return MIN_API_VOLUME_FX
    return api_volume
