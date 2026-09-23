"""constants.py — canonical constants і початкові WSP risk limits.

Модуль визначає persisted risk keys, безпечні defaults, risk decisions і
broker-neutral FX position-size contract. Canonical Workspace volume означає
кількість одиниць base currency тільки для FX; це не broker-native volume і
не conversion quote-currency loss у currency торгового рахунку.
"""

from __future__ import annotations

# Ключі persisted risk_settings конкретного WSP.
WORKSPACE_RISK_SETTING_RISK_PERCENT = "risk_percent"
WORKSPACE_RISK_SETTING_MAXIMUM_POSITION_VOLUME = "maximum_position_volume"
WORKSPACE_RISK_SETTING_MAXIMUM_OPEN_POSITIONS = "maximum_open_positions"
WORKSPACE_RISK_SETTING_MAX_DAILY_LOSS_PERCENT = "max_daily_loss_percent"
WORKSPACE_RISK_SETTING_REQUIRE_STOP_LOSS = "require_stop_loss"


# Broker-neutral contract для volume у WSP risk chain. Числові значення
# maximum_position_volume -> requested_volume -> approved_volume зберігаються
# без conversion; одна BASE_UNIT означає одну одиницю base currency FX symbol.
WORKSPACE_VOLUME_UNIT_BASE_UNITS = "BASE_UNITS"
WORKSPACE_VOLUME_SCOPE_FX_POSITION_SIZE_ONLY = "FX_POSITION_SIZE_ONLY"
WORKSPACE_CANONICAL_VOLUME_UNIT = WORKSPACE_VOLUME_UNIT_BASE_UNITS
WORKSPACE_CANONICAL_VOLUME_SCOPE = WORKSPACE_VOLUME_SCOPE_FX_POSITION_SIZE_ONLY
WORKSPACE_CANONICAL_VOLUME_FIELDS = (
    "maximum_position_volume",
    "requested_volume",
    "approved_volume",
)


# Безпечні початкові policy limits для відсутніх
# legacy/future settings.
DEFAULT_WORKSPACE_RISK_PERCENT = 0.5
DEFAULT_WORKSPACE_MAXIMUM_POSITION_VOLUME = 1000.0
DEFAULT_WORKSPACE_MAXIMUM_OPEN_POSITIONS = 2
DEFAULT_WORKSPACE_MAX_DAILY_LOSS_PERCENT = 2.0
DEFAULT_WORKSPACE_REQUIRE_STOP_LOSS = True


# Детерміноване account-середовище для Replay.
REPLAY_RISK_SETTING_EQUITY = "risk_equity"
REPLAY_RISK_SETTING_DAILY_REALIZED_PNL = "risk_daily_realized_pnl"
REPLAY_RISK_SETTING_OPEN_POSITIONS_COUNT = "risk_open_positions_count"

MINIMUM_REPLAY_RISK_EQUITY = 100.0
MAXIMUM_REPLAY_RISK_EQUITY = 100_000.0
DEFAULT_REPLAY_RISK_EQUITY = 1_000.0
DEFAULT_REPLAY_RISK_DAILY_REALIZED_PNL = 0.0
DEFAULT_REPLAY_RISK_OPEN_POSITIONS_COUNT = 0


# Підсумкові рішення risk evaluator.
RISK_DECISION_ALLOW = "ALLOW"
RISK_DECISION_BLOCK = "BLOCK"
RISK_DECISIONS = (
    RISK_DECISION_ALLOW,
    RISK_DECISION_BLOCK,
)


# Позитивний результат: запит пройшов усі risk guards.
RISK_REASON_APPROVED = "RISK_APPROVED"


# Готовність WSP Runtime і відповідність broker/account binding.
RISK_REASON_RUNTIME_NOT_READY = "RUNTIME_NOT_READY"
RISK_REASON_ACCOUNT_BINDING_MISMATCH = "ACCOUNT_BINDING_MISMATCH"
RISK_REASON_ACCOUNT_SNAPSHOT_MISSING = "ACCOUNT_SNAPSHOT_MISSING"
RISK_REASON_ACCOUNT_SNAPSHOT_TIMESTAMP_MISSING = (
    "ACCOUNT_SNAPSHOT_TIMESTAMP_MISSING"
)
RISK_REASON_ACCOUNT_SNAPSHOT_FUTURE = "ACCOUNT_SNAPSHOT_FUTURE"
RISK_REASON_ACCOUNT_SNAPSHOT_STALE = "ACCOUNT_SNAPSHOT_STALE"
RISK_REASON_DAILY_PNL_SNAPSHOT_MISSING = "DAILY_PNL_SNAPSHOT_MISSING"
RISK_REASON_OPEN_POSITIONS_SNAPSHOT_MISSING = "OPEN_POSITIONS_SNAPSHOT_MISSING"


# Валідність market data та допустимість spread.
RISK_REASON_MARKET_INVALID = "MARKET_INVALID"
RISK_REASON_SPREAD_BLOCKED = "SPREAD_BLOCKED"


# Наявність Stop Loss і ризик окремої операції.
RISK_REASON_STOP_LOSS_REQUIRED = "STOP_LOSS_REQUIRED"
RISK_REASON_INVALID_LOSS_AT_STOP = "INVALID_LOSS_AT_STOP"
RISK_REASON_RISK_PERCENT_EXCEEDED = "RISK_PERCENT_EXCEEDED"


# Ліміти обсягу та кількості відкритих позицій.
RISK_REASON_MAXIMUM_POSITION_VOLUME_EXCEEDED = "MAXIMUM_POSITION_VOLUME_EXCEEDED"
RISK_REASON_MAXIMUM_OPEN_POSITIONS_REACHED = "MAXIMUM_OPEN_POSITIONS_REACHED"


# Денний ліміт збитку для account або WSP policy.
RISK_REASON_DAILY_LOSS_LIMIT_REACHED = "DAILY_LOSS_LIMIT_REACHED"
