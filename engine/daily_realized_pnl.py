"""Broker-neutral aggregation canonical realized PnL за UTC account day."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Mapping, Sequence


@dataclass(frozen=True, slots=True)
class BrokerDailyRealizedPnlResult:
    """Результат causal account-day aggregation без broker access."""

    broker: str
    account_id: str
    day_start_utc: datetime
    day_end_utc: datetime
    evaluation_utc: datetime
    success: bool
    daily_realized_pnl: float | None
    event_count: int
    failure_reason: str = ""


def aggregate_broker_daily_realized_pnl(
    *,
    broker: str,
    account_id: str,
    events: Sequence[Mapping[str, object]],
    evaluation_utc: datetime,
    source_complete: bool,
) -> BrokerDailyRealizedPnlResult:
    """Агрегувати observed canonical events у поточному UTC account day."""
    broker_name = str(broker or "").strip().upper()
    account = str(account_id or "").strip()
    evaluation = _require_aware_utc(evaluation_utc, "evaluation_utc")
    day_start = evaluation.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    if broker_name not in {"IB", "CTRADER"}:
        return _failure(
            broker_name,
            account,
            day_start,
            day_end,
            evaluation,
            "Unsupported broker for daily realized PnL aggregation.",
        )
    if not account:
        return _failure(
            broker_name,
            account,
            day_start,
            day_end,
            evaluation,
            "Broker account identity is missing.",
        )
    if not source_complete:
        return _failure(
            broker_name,
            account,
            day_start,
            day_end,
            evaluation,
            "Canonical realized-event source is incomplete.",
        )

    seen: set[tuple[str, str, str]] = set()
    total = 0.0
    count = 0

    for event in events:
        event_broker = str(event.get("broker") or "").strip().upper()
        event_account = str(event.get("account_id") or "").strip()
        if event_broker != broker_name or event_account != account:
            continue

        identity = _event_identity(event, broker_name)
        if not identity:
            return _failure(
                broker_name,
                account,
                day_start,
                day_end,
                evaluation,
                "Canonical realized event identity is missing.",
            )

        timestamp = _event_timestamp(event, broker_name)
        if timestamp is None:
            return _failure(
                broker_name,
                account,
                day_start,
                day_end,
                evaluation,
                "Canonical realized event timestamp is invalid.",
            )

        if timestamp >= evaluation:
            continue
        if not day_start <= timestamp < day_end:
            continue

        amount = _finite_float(event.get("net_realized_pnl"))
        if amount is None:
            return _failure(
                broker_name,
                account,
                day_start,
                day_end,
                evaluation,
                "Canonical net_realized_pnl is missing or invalid.",
            )

        key = broker_name, account, identity
        if key in seen:
            continue
        seen.add(key)
        total += amount
        count += 1

    return BrokerDailyRealizedPnlResult(
        broker=broker_name,
        account_id=account,
        day_start_utc=day_start,
        day_end_utc=day_end,
        evaluation_utc=evaluation,
        success=True,
        daily_realized_pnl=total,
        event_count=count,
    )


def _event_identity(event: Mapping[str, object], broker: str) -> str:
    field_name = "exec_id" if broker == "IB" else "deal_id"
    return str(event.get(field_name) or "").strip()


def _event_timestamp(
    event: Mapping[str, object],
    broker: str,
) -> datetime | None:
    if broker == "IB":
        value = str(event.get("execution_time") or "").strip()
        if not value:
            return None
        try:
            parsed = datetime.strptime(value, "%Y%m%d %H:%M:%S UTC")
        except ValueError:
            return None
        return parsed.replace(tzinfo=UTC)

    raw = event.get("execution_timestamp")
    try:
        milliseconds = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    if milliseconds <= 0:
        return None
    try:
        return datetime.fromtimestamp(milliseconds / 1000.0, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _require_aware_utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _finite_float(value: object) -> float | None:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _failure(
    broker: str,
    account_id: str,
    day_start: datetime,
    day_end: datetime,
    evaluation: datetime,
    reason: str,
) -> BrokerDailyRealizedPnlResult:
    return BrokerDailyRealizedPnlResult(
        broker=broker,
        account_id=account_id,
        day_start_utc=day_start,
        day_end_utc=day_end,
        evaluation_utc=evaluation,
        success=False,
        daily_realized_pnl=None,
        event_count=0,
        failure_reason=reason,
    )
