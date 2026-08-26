# market_availability_state.py
"""
Market availability state model.

RoadMap67:
- broker-independent market availability layer;
- cTrader heuristic/fallback support;
- IB heuristic support;
- no UI dependency;
- no order execution.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


MARKET_OPEN = "MARKET_OPEN"
MARKET_CLOSED = "MARKET_CLOSED"
MARKET_PREOPEN = "MARKET_PREOPEN"
MARKET_HALTED = "MARKET_HALTED"
MARKET_UNKNOWN = "MARKET_UNKNOWN"

FOREX_WEEKEND_HEURISTIC = "FOREX_WEEKEND_HEURISTIC"
FOREX_WEEKDAY_HEURISTIC = "FOREX_WEEKDAY_HEURISTIC"

CTRADER_FOREX_WEEKEND_HEURISTIC = "CTRADER_FOREX_WEEKEND_HEURISTIC"
CTRADER_FOREX_WEEKDAY_HEURISTIC = "CTRADER_FOREX_WEEKDAY_HEURISTIC"

IB_FOREX_WEEKEND_HEURISTIC = "IB_FOREX_WEEKEND_HEURISTIC"
IB_FOREX_WEEKDAY_HEURISTIC = "IB_FOREX_WEEKDAY_HEURISTIC"

BROKER_ERROR_MARKET_CLOSED = "BROKER_ERROR_MARKET_CLOSED"
BROKER_SYMBOL_SESSION = "BROKER_SYMBOL_SESSION"
CTRADER_SYMBOL_STATUS = "CTRADER_SYMBOL_STATUS"
IB_MARKET_RULES = "IB_MARKET_RULES"
UNKNOWN = "UNKNOWN"


@dataclass(slots=True)
class MarketAvailabilityResult:
    """
    Canonical market availability result.
    """

    state: str
    source: str
    symbol_name: str
    broker: str
    checked_utc: datetime
    reason: str
    can_place_market_order: bool
    can_place_pending_order: bool


def utc_now() -> datetime:
    """
    Return timezone-aware UTC datetime.
    """
    return datetime.now(UTC)


def is_forex_symbol(symbol_name: str) -> bool:
    """
    Return True for simple FX-style symbols.

    Examples:
    - EURUSD
    - GBPUSD
    - USDJPY
    """
    normalized = symbol_name.strip().upper()
    return len(normalized) == 6 and normalized.isalpha()


def is_forex_weekend(checked_utc: datetime) -> bool:
    """
    Detect standard Forex weekend close window.

    UTC weekday:
    - Monday    = 0
    - Tuesday   = 1
    - Wednesday = 2
    - Thursday  = 3
    - Friday    = 4
    - Saturday  = 5
    - Sunday    = 6

    Practical first implementation:
    - Saturday: closed
    - Sunday before 22:00 UTC: closed
    - Friday after 22:00 UTC: closed
    """
    if checked_utc.tzinfo is None:
        checked_utc = checked_utc.replace(tzinfo=UTC)

    weekday = checked_utc.weekday()
    hour = checked_utc.hour

    if weekday == 5:
        return True

    if weekday == 6 and hour < 22:
        return True

    if weekday == 4 and hour >= 22:
        return True

    return False


def detect_forex_market_state(
    *,
    symbol_name: str,
    broker: str,
    checked_utc: datetime | None = None,
    weekend_source: str = FOREX_WEEKEND_HEURISTIC,
    weekday_source: str = FOREX_WEEKDAY_HEURISTIC,
) -> MarketAvailabilityResult:
    """
    Detect Forex market availability using first-level UTC heuristic.
    """
    checked = checked_utc or utc_now()
    broker_name = broker.strip().upper()
    symbol = symbol_name.strip().upper()

    if not is_forex_symbol(symbol):
        logger.debug(
            "Market availability unknown: non-Forex symbol | broker=%s | " "symbol=%s",
            broker_name,
            symbol,
        )
        return MarketAvailabilityResult(
            state=MARKET_UNKNOWN,
            source=UNKNOWN,
            symbol_name=symbol,
            broker=broker_name,
            checked_utc=checked,
            reason="Symbol is not recognized as a simple Forex pair.",
            can_place_market_order=False,
            can_place_pending_order=False,
        )

    if is_forex_weekend(checked):
        logger.debug(
            "Forex market closed by weekend heuristic | broker=%s | "
            "symbol=%s | checked_utc=%s",
            broker_name,
            symbol,
            checked.isoformat(),
        )
        return MarketAvailabilityResult(
            state=MARKET_CLOSED,
            source=weekend_source,
            symbol_name=symbol,
            broker=broker_name,
            checked_utc=checked,
            reason="Forex weekend close window.",
            can_place_market_order=False,
            can_place_pending_order=True,
        )

    logger.debug(
        "Forex market open by weekday heuristic | broker=%s | "
        "symbol=%s | checked_utc=%s",
        broker_name,
        symbol,
        checked.isoformat(),
    )
    return MarketAvailabilityResult(
        state=MARKET_OPEN,
        source=weekday_source,
        symbol_name=symbol,
        broker=broker_name,
        checked_utc=checked,
        reason="Forex weekday open window.",
        can_place_market_order=True,
        can_place_pending_order=True,
    )


def detect_ctrader_market_state(
    *,
    symbol_name: str = "EURUSD",
    checked_utc: datetime | None = None,
) -> MarketAvailabilityResult:
    """
    Detect cTrader market availability.

    Current RoadMap67 implementation:
    - Forex heuristic;
    - broker error fallback is handled separately.
    """
    return detect_forex_market_state(
        symbol_name=symbol_name,
        broker="CTRADER",
        checked_utc=checked_utc,
        weekend_source=CTRADER_FOREX_WEEKEND_HEURISTIC,
        weekday_source=CTRADER_FOREX_WEEKDAY_HEURISTIC,
    )


def detect_ib_market_state(
    *,
    symbol_name: str = "EURUSD",
    checked_utc: datetime | None = None,
) -> MarketAvailabilityResult:
    """
    Detect IB market availability.

    Current RoadMap67 implementation:
    - Forex heuristic only;
    - real IB trading-hours parsing will be added later.
    """
    return detect_forex_market_state(
        symbol_name=symbol_name,
        broker="IB",
        checked_utc=checked_utc,
        weekend_source=IB_FOREX_WEEKEND_HEURISTIC,
        weekday_source=IB_FOREX_WEEKDAY_HEURISTIC,
    )


def market_closed_from_broker_error(
    *,
    broker: str,
    symbol_name: str,
    error_code: str,
    description: str,
    checked_utc: datetime | None = None,
) -> MarketAvailabilityResult:
    """
    Convert broker MARKET_CLOSED error into canonical market state.
    """
    checked = checked_utc or utc_now()
    broker_name = broker.strip().upper()
    symbol = symbol_name.strip().upper()
    normalized_error = error_code.strip().upper()

    if normalized_error == "MARKET_CLOSED":
        logger.debug(
            "Broker MARKET_CLOSED fallback used | broker=%s | symbol=%s | "
            "description=%s",
            broker_name,
            symbol,
            description,
        )
        return MarketAvailabilityResult(
            state=MARKET_CLOSED,
            source=BROKER_ERROR_MARKET_CLOSED,
            symbol_name=symbol,
            broker=broker_name,
            checked_utc=checked,
            reason=description,
            can_place_market_order=False,
            can_place_pending_order=True,
        )

    return MarketAvailabilityResult(
        state=MARKET_UNKNOWN,
        source=UNKNOWN,
        symbol_name=symbol,
        broker=broker_name,
        checked_utc=checked,
        reason=description,
        can_place_market_order=False,
        can_place_pending_order=False,
    )


def detect_market_state(
    *,
    broker: str,
    symbol_name: str = "EURUSD",
    checked_utc: datetime | None = None,
) -> MarketAvailabilityResult:
    """
    Broker-independent market availability entry point.
    """
    broker_name = broker.strip().upper()

    if broker_name == "CTRADER":
        return detect_ctrader_market_state(
            symbol_name=symbol_name,
            checked_utc=checked_utc,
        )

    if broker_name == "IB":
        return detect_ib_market_state(
            symbol_name=symbol_name,
            checked_utc=checked_utc,
        )

    checked = checked_utc or utc_now()

    logger.debug(
        "Market availability unknown: unsupported broker | broker=%s | " "symbol=%s",
        broker_name,
        symbol_name,
    )

    return MarketAvailabilityResult(
        state=MARKET_UNKNOWN,
        source=UNKNOWN,
        symbol_name=symbol_name.strip().upper(),
        broker=broker_name,
        checked_utc=checked,
        reason="Unsupported broker for market availability check.",
        can_place_market_order=False,
        can_place_pending_order=False,
    )
