# brokers/broker_factory.py
"""Фабрика для створення брокерських адаптерів (IB, cTrader, інші)."""

from typing import Any

from brokers.ctrader_adapter import CTraderAdapter
from brokers.ib_adapter import IBAdapter
from core.lang_manager import LangManager

lang = LangManager()


def create_broker(name: str, **kwargs: Any):
    """Повертає екземпляр адаптера брокера за його назвою.

    Parameters
    ----------
    name : str
        Ідентифікатор брокера: 'ib' або 'ctrader'.
    kwargs : dict
        Аргументи, які передаються конструктору адаптера.

    Returns
    -------
    BrokerAdapter
        Екземпляр відповідного класу адаптера.
    """
    name = name.lower().strip()

    if name == "ib":
        return IBAdapter(**kwargs)
    if name in {"ctrader", "c-trader"}:
        return CTraderAdapter(**kwargs)

    raise ValueError(lang.t("unknown_broker").format(name=name))
