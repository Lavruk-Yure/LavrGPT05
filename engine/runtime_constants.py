# -*- coding: utf-8 -*-
"""engine.runtime_constants

Технічні runtime-константи LGE для:
- WSP Replay, історичних даних і chart;
- алгоритмічних параметрів та guards;
- runtime scheduler, watch і reconnect;
- cTrader та IB broker runtime;
- IB SL/TP, virtual legs, position groups і reconciliation.
"""

from __future__ import annotations


# =============================================================================
# Forex: канонічні symbol/pip conventions
# =============================================================================

# Підтримані ISO-like currency codes для fail-closed Forex symbol resolver.
FOREX_CURRENCY_CODES = frozenset(
    {
        "AUD",
        "CAD",
        "CHF",
        "CNH",
        "CZK",
        "DKK",
        "EUR",
        "GBP",
        "HKD",
        "HUF",
        "JPY",
        "MXN",
        "NOK",
        "NZD",
        "PLN",
        "SEK",
        "SGD",
        "TRY",
        "USD",
        "ZAR",
    }
)

# Один pip для звичайної Forex quote currency та для JPY quote.
FOREX_STANDARD_PIP_SIZE = 0.0001
FOREX_JPY_QUOTE_PIP_SIZE = 0.01


def resolve_forex_pip_size(symbol: str) -> float:
    """Повернути канонічний pip size для 6-letter Forex symbol."""
    normalized = str(symbol or "").strip().upper()
    if len(normalized) != 6 or not normalized.isalpha():
        raise ValueError("Forex pip size requires canonical 6-letter symbol")
    base = normalized[:3]
    quote = normalized[3:]
    if base not in FOREX_CURRENCY_CODES or quote not in FOREX_CURRENCY_CODES:
        raise ValueError("Forex pip size supports verified Forex symbols only")
    if quote == "JPY":
        return FOREX_JPY_QUOTE_PIP_SIZE
    return FOREX_STANDARD_PIP_SIZE


# =============================================================================
# WSP Replay: джерела та імпорт історичних даних
# =============================================================================

# Підтримувані джерела історії для WSP Replay.
WORKSPACE_REPLAY_SOURCE_SYNTHETIC = "SYNTHETIC"
WORKSPACE_REPLAY_SOURCE_CSV = "CSV"
WORKSPACE_REPLAY_SOURCES = (
    WORKSPACE_REPLAY_SOURCE_SYNTHETIC,
    WORKSPACE_REPLAY_SOURCE_CSV,
)
DEFAULT_WORKSPACE_REPLAY_SOURCE = WORKSPACE_REPLAY_SOURCE_SYNTHETIC

# Naive timestamps у CSV трактуються у цій часовій зоні.
DEFAULT_WORKSPACE_HISTORY_TIMEZONE = "UTC"

# AUTO використовує csv.Sniffer для comma/semicolon/tab/pipe файлів.
DEFAULT_WORKSPACE_HISTORY_DELIMITER = "AUTO"

# Підтримувані роздільники CSV; tab зберігається як символ табуляції.
WORKSPACE_HISTORY_DELIMITERS = ("AUTO", ",", ";", "\t", "|")

# Десятковий роздільник історичних числових значень.
DEFAULT_WORKSPACE_HISTORY_DECIMAL_SEPARATOR = "."
WORKSPACE_HISTORY_DECIMAL_SEPARATORS = (".", ",")

# Початковий список часових зон у Replay dialog; поле лишається editable.
WORKSPACE_HISTORY_TIMEZONE_CHOICES = (
    "UTC",
    "Europe/Kyiv",
    "Europe/London",
    "America/New_York",
)

# Spread для OHLC-файлів без bid/ask або spread колонок.
# Канонічне значення задається в pips; raw fallback зберігає попередню
# поведінку для non-Forex symbols, де Forex pip convention не застосовна.
DEFAULT_WORKSPACE_HISTORY_SPREAD_PIPS = 1.2
DEFAULT_WORKSPACE_HISTORY_SPREAD = (
    DEFAULT_WORKSPACE_HISTORY_SPREAD_PIPS * FOREX_STANDARD_PIP_SIZE
)


def resolve_workspace_history_default_spread(symbol: str) -> float:
    """Повернути symbol-aware default Replay spread у raw price units."""
    try:
        pip_size = resolve_forex_pip_size(symbol)
    except ValueError:
        return DEFAULT_WORKSPACE_HISTORY_SPREAD
    return DEFAULT_WORKSPACE_HISTORY_SPREAD_PIPS * pip_size


# =============================================================================
# cTrader: завантаження історичних trend bars
# =============================================================================

# Open API trendbar periods використовують broker enum, а не хвилини.
CTRADER_TRENDBAR_PERIOD_BY_TIMEFRAME = {
    "M1": 1,
    "M5": 5,
    "M15": 7,
    "M30": 8,
    "H1": 9,
    "H4": 10,
    "D1": 12,
}

# Максимальна кількість trend bars в одному response chunk.
CTRADER_HISTORY_CHUNK_SIZE = 5000

# Граничний час очікування однієї відповіді з історією.
CTRADER_HISTORY_TIMEOUT_SECONDS = 30.0

# Захист від некоректної нескінченної послідовності hasMore.
CTRADER_HISTORY_MAX_REQUESTS = 200

# Невелика пауза між history-запитами для уникнення request bursts.
CTRADER_HISTORY_REQUEST_DELAY_SECONDS = 0.25


# =============================================================================
# Interactive Brokers: завантаження історичних bars
# =============================================================================

# Значення точно відповідають TWS API barSizeSetting strings.
IB_HISTORY_BAR_SIZE_BY_TIMEFRAME = {
    "M1": "1 min",
    "M5": "5 mins",
    "M15": "15 mins",
    "M30": "30 mins",
    "H1": "1 hour",
    "H4": "4 hours",
    "D1": "1 day",
}

# Безпечні chunks утримують кожну відповідь у межах кількох тисяч bars.
IB_HISTORY_DURATION_BY_TIMEFRAME = {
    "M1": "1 D",
    "M5": "1 W",
    "M15": "1 M",
    "M30": "1 M",
    "H1": "1 M",
    "H4": "6 M",
    "D1": "1 Y",
}

# Тривалість одного завершеного bar для backward pagination.
IB_HISTORY_BAR_SECONDS_BY_TIMEFRAME = {
    "M1": 60,
    "M5": 300,
    "M15": 900,
    "M30": 1800,
    "H1": 3600,
    "H4": 14400,
    "D1": 86400,
}

# Граничний час очікування одного history request.
IB_HISTORY_TIMEOUT_SECONDS = 45.0

# Максимальна кількість chunks одного history download. M1 завантажується
# денними chunks, тому кілька місяців історії потребують сотень запитів.
IB_HISTORY_MAX_REQUESTS = 400

# Порожні крайні chunks (сьогодні, вихідні, свята) можна безпечно
# пропускати назад, але не нескінченно у випадку справжньої помилки HMDS.
IB_HISTORY_MAX_CONSECUTIVE_EMPTY_REQUESTS = 7

# Крок назад після HMDS "query returned no data". Він відповідає
# канонічній duration кожного timeframe і використовується тільки тоді,
# коли IB не повернув жодного bar для поточного chunk.
IB_HISTORY_EMPTY_CHUNK_SECONDS_BY_TIMEFRAME = {
    "M1": 86400,
    "M5": 604800,
    "M15": 2678400,
    "M30": 2678400,
    "H1": 2678400,
    "H4": 15811200,
    "D1": 31622400,
}

# Застосовується лише між кількома chunks. Для M1+ зберігається мала
# пауза без колишньої десятисекундної затримки після кожного chunk.
IB_HISTORY_REQUEST_DELAY_SECONDS = 2.1


# =============================================================================
# WSP chart: history buffer, visible range і zoom limits
# =============================================================================

# Максимальна кількість ринкових подій у пам'яті одного графіка.
DEFAULT_WORKSPACE_CHART_MAX_EVENTS = 2000

# Початкова кількість видимих bars після відкриття графіка.
DEFAULT_WORKSPACE_CHART_VISIBLE_EVENTS = 120

# Мінімальна кількість видимих bars після збільшення масштабу.
MIN_WORKSPACE_CHART_VISIBLE_EVENTS = 12

# Максимальна кількість видимих bars після зменшення масштабу.
MAX_WORKSPACE_CHART_VISIBLE_EVENTS = 500


# =============================================================================
# WSP algorithm parameters: MACD, Alligator, spread і warm-up
# =============================================================================

# Storage key і початковий стан незалежного джерела сигналу MACD.
WORKSPACE_MACD_SIGNAL_ENABLED_KEY = "macd_signal_enabled"
DEFAULT_WORKSPACE_MACD_SIGNAL_ENABLED = True

# Режими формування MACD-сигналу в межах окремого WSP.
WORKSPACE_MACD_SIGNAL_MODE_LINEAR = "LINEAR"
WORKSPACE_MACD_SIGNAL_MODE_EXTENDED = "EXTENDED"
WORKSPACE_MACD_SIGNAL_MODES = (
    WORKSPACE_MACD_SIGNAL_MODE_LINEAR,
    WORKSPACE_MACD_SIGNAL_MODE_EXTENDED,
)

# RoadMap99 EXTENDED MACD quality thresholds. LINEAR keeps classic crossover.
WORKSPACE_MACD_EXTREMUM_MIN_PROMINENCE_KEY = (
    "macd_extremum_min_prominence"
)
WORKSPACE_MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE_KEY = (
    "macd_extremum_to_cross_min_distance"
)
WORKSPACE_MACD_CROSS_MIN_ANGLE_KEY = "macd_cross_min_angle"
WORKSPACE_MACD_CROSS_ANGLE_MODEL_KEY = "macd_cross_angle_model"
WORKSPACE_MACD_CROSS_MIN_ABC_ANGLE_KEY = "macd_cross_min_abc_angle"

WORKSPACE_MACD_CROSS_ANGLE_MODEL_LEGACY = "LEGACY_CALIBRATED"
WORKSPACE_MACD_CROSS_ANGLE_MODEL_ABC = "ABC_REALTIME_SCALED"
WORKSPACE_MACD_CROSS_ANGLE_MODELS = (
    WORKSPACE_MACD_CROSS_ANGLE_MODEL_LEGACY,
    WORKSPACE_MACD_CROSS_ANGLE_MODEL_ABC,
)

DEFAULT_WORKSPACE_MACD_EXTREMUM_MIN_PROMINENCE = 0.00001
DEFAULT_WORKSPACE_MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE = 0.00005
DEFAULT_WORKSPACE_MACD_CROSS_MIN_ANGLE = 45.0
DEFAULT_WORKSPACE_MACD_CROSS_ANGLE_MODEL = WORKSPACE_MACD_CROSS_ANGLE_MODEL_LEGACY
DEFAULT_WORKSPACE_MACD_CROSS_MIN_ABC_ANGLE = 2.0

# RoadMap101: reference-defaults, які матеріалізуються лише у НОВОМУ WSP.
# Persisted/legacy WSP без цих keys продовжують використовувати історичні
# DEFAULT_WORKSPACE_* fallback-и вище, тому старі Replay не мігрують мовчки.
# Значення не є універсальними для інших symbol/timeframe/regime.
NEW_WORKSPACE_MACD_SIGNAL_MODE = WORKSPACE_MACD_SIGNAL_MODE_EXTENDED
# Reference-defaults для нового WSP задаються у pips, а raw values
# обчислюються за symbol. Старі raw constants лишаються legacy fallback для
# persisted/non-Forex WSP і не мігруються приховано.
NEW_WORKSPACE_MACD_EXTREMUM_MIN_PROMINENCE_PIPS = 0.15
NEW_WORKSPACE_MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE_PIPS = 0.5
NEW_WORKSPACE_MACD_EXTREMUM_MIN_PROMINENCE = (
    NEW_WORKSPACE_MACD_EXTREMUM_MIN_PROMINENCE_PIPS * FOREX_STANDARD_PIP_SIZE
)
NEW_WORKSPACE_MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE = (
    NEW_WORKSPACE_MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE_PIPS
    * FOREX_STANDARD_PIP_SIZE
)
NEW_WORKSPACE_MACD_CROSS_ANGLE_MODEL = WORKSPACE_MACD_CROSS_ANGLE_MODEL_ABC
NEW_WORKSPACE_MACD_CROSS_MIN_ABC_ANGLE = 2.25


def resolve_new_workspace_macd_extremum_min_prominence(symbol: str) -> float:
    """Повернути symbol-aware prominence нового WSP у raw price units."""
    try:
        pip_size = resolve_forex_pip_size(symbol)
    except ValueError:
        return NEW_WORKSPACE_MACD_EXTREMUM_MIN_PROMINENCE
    return NEW_WORKSPACE_MACD_EXTREMUM_MIN_PROMINENCE_PIPS * pip_size


def resolve_new_workspace_macd_extremum_to_cross_min_distance(
    symbol: str,
) -> float:
    """Повернути symbol-aware extremum distance нового WSP у raw units."""
    try:
        pip_size = resolve_forex_pip_size(symbol)
    except ValueError:
        return NEW_WORKSPACE_MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE
    return NEW_WORKSPACE_MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE_PIPS * pip_size


# Storage key і початковий стан незалежного фільтра Alligator.
WORKSPACE_ALLIGATOR_FILTER_ENABLED_KEY = "alligator_filter_enabled"
DEFAULT_WORKSPACE_ALLIGATOR_FILTER_ENABLED = True

# Варіанти підтвердження сигналу індикатором Alligator.
WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME = "SAME_TIMEFRAME"
WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_1 = "HIGHER_1"
WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_2 = "HIGHER_2"
# HIGHER_2 реалізований лише як експериментальний Replay-фільтр.
WORKSPACE_ALLIGATOR_HIGHER_2_EXPERIMENTAL = True
WORKSPACE_ALLIGATOR_CONFIRMATION_DISABLED = "DISABLED"
WORKSPACE_ALLIGATOR_CONFIRMATION_UI_CHOICES = (
    WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
    WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_1,
    WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_2,
)
WORKSPACE_ALLIGATOR_CONFIRMATIONS = (
    *WORKSPACE_ALLIGATOR_CONFIRMATION_UI_CHOICES,
    WORKSPACE_ALLIGATOR_CONFIRMATION_DISABLED,
)

# Канонічні переходи RoadMap96. Таблиці задаються явно: runtime не має
# права обчислювати "наступний" timeframe за позицією у загальному списку.
# None означає, що режим для базового timeframe недоступний без fallback.
WORKSPACE_ALLIGATOR_HIGHER_1_TIMEFRAME_BY_BASE = {
    "M1": "M5",
    "M5": "M15",
    "M15": "H1",
    "M30": "H1",
    "H1": "H4",
    "H4": "D1",
    "D1": None,
}

# HIGHER_2 є експериментальним і не default. Таблиця задає лише явно
# погоджені переходи; недоступні пари блокуються без fallback.
WORKSPACE_ALLIGATOR_HIGHER_2_TIMEFRAME_BY_BASE = {
    "M1": "M15",
    "M5": "H1",
    "M15": "H4",
    "M30": "H4",
    "H1": "D1",
    "H4": None,
    "D1": None,
}

# Початкові algorithm і runtime guard параметри нового WSP.
DEFAULT_WORKSPACE_MACD_SIGNAL_MODE = WORKSPACE_MACD_SIGNAL_MODE_LINEAR
DEFAULT_WORKSPACE_ALLIGATOR_CONFIRMATION = (
    WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME
)
DEFAULT_WORKSPACE_SPREAD_LIMIT = 0.00020
DEFAULT_WORKSPACE_WARMUP_BARS = 3
DEFAULT_WORKSPACE_PROFIT_DRAWDOWN_CLOSE_PERCENT = 30.0


# =============================================================================
# Runtime scheduler, watch loops і reconnect policy
# =============================================================================

# Загальний cooldown перед повторною runtime reconnect-спробою.
RUNTIME_RECONNECT_COOLDOWN_SECONDS = 15.0

# Параметри короткого runtime watch loop.
RUNTIME_WATCH_SLEEP_SECONDS = 5.0
RUNTIME_WATCH_ITERATIONS = 31

# Інтервали broker reconnect watchers.
IB_RECONNECT_WATCH_INTERVAL_SECONDS = 5.0
CTRADER_RECONNECT_WATCH_INTERVAL_SECONDS = 30.0

# Завершення scheduler thread і періодичні runtime tasks.
RUNTIME_SCHEDULER_THREAD_JOIN_TIMEOUT_SECONDS = 5.0
RUNTIME_SCHEDULER_STOP_WAIT_SECONDS = 0.5
RUNTIME_RECONNECT_TASK_INTERVAL_SECONDS = 5.0
RUNTIME_ACCOUNT_REFRESH_INTERVAL_SECONDS = 30.0

# Broker-specific cooldown після disconnect/reconnect cycle.
CTRADER_RECONNECT_COOLDOWN_SECONDS = 60.0
CTRADER_RECONNECT_FAILURE_BACKOFF_SECONDS = (60.0, 120.0, 300.0)
IB_RECONNECT_COOLDOWN_SECONDS = 60.0


# =============================================================================
# cTrader runtime: connection, requests і session lifecycle
# =============================================================================

# Network reachability та authorization timeouts.
CTRADER_HOST_CHECK_TIMEOUT_SECONDS = 3.0
CTRADER_STARTUP_READINESS_GRACE_SECONDS = 5.0
CTRADER_STARTUP_READINESS_PROBE_TIMEOUT_SECONDS = 0.5
CTRADER_STARTUP_READINESS_POLL_INTERVAL_SECONDS = 0.25
CTRADER_AUTH_TIMEOUT_SECONDS = 30.0
CTRADER_LATE_CONNECT_TIMEOUT_SECONDS = 30.0
CTRADER_REACTOR_JOIN_TIMEOUT_SECONDS = 5.0

# Runtime request timeouts.
CTRADER_WAIT_TIMEOUT_SECONDS = 20.0
CTRADER_POSITIONS_TIMEOUT_SECONDS = 10.0
CTRADER_SPOT_TIMEOUT_SECONDS = 3.0

# Максимальний bounded wait для підтвердження закриття старої cTrader session.
CTRADER_OLD_SESSION_CLOSE_TIMEOUT_SECONDS = 2.0


# =============================================================================
# Interactive Brokers runtime: connection, snapshots і operations
# =============================================================================

# Connection і worker thread lifecycle.
IB_CONNECT_TIMEOUT_SECONDS = 10.0
IB_THREAD_JOIN_TIMEOUT_SECONDS = 3.0

# Account, order, position і market-data snapshot timeouts.
IB_ACCOUNT_SUMMARY_TIMEOUT_SECONDS = 10.0
IB_COMPLETED_ORDERS_TIMEOUT_SECONDS = 10.0
IB_POSITIONS_TIMEOUT_SECONDS = 10.0
IB_PORTFOLIO_TIMEOUT_SECONDS = 10.0
IB_PNL_TIMEOUT_SECONDS = 5.0
IB_MARKET_DATA_TIMEOUT_SECONDS = 3.0
IB_OPEN_ORDERS_TIMEOUT_SECONDS = 10.0
IB_EXECUTIONS_TIMEOUT_SECONDS = 10.0
IB_ORDER_TIMEOUT_SECONDS = 20.0

# Quantity та protective coverage tolerances.
IB_SL_TP_COVERAGE_REL_TOLERANCE = 1e-9
IB_POSITION_QUANTITY_ABS_TOLERANCE = 1e-9
IB_SL_TP_COVERAGE_ABS_TOLERANCE = 0.01

# SL/TP modification orchestration.
IB_SL_TP_OPERATION_TIMEOUT_SECONDS = 20.0
IB_SL_TP_REPLACEMENT_STAGE_SETTLE_SECONDS = 1.0
IB_SL_TP_OCA_TYPE_CANCEL_WITH_BLOCK = 1
IB_SL_TP_ORDER_REF = "LGE_SL_TP_MODIFY"
IB_SL_TP_OCA_GROUP_PREFIX = "LGE_SLTP"

# Post-modify reconciliation retries for virtual legs.
IB_VIRTUAL_LEG_POST_MODIFY_RECONCILIATION_ATTEMPTS = 4
IB_VIRTUAL_LEG_POST_MODIFY_RECONCILIATION_DELAY_SECONDS = 0.5

# Recovery після timeout під час закриття virtual leg.
IB_VIRTUAL_LEG_CLOSE_TIMEOUT_RECOVERY_ATTEMPTS = 3
IB_VIRTUAL_LEG_CLOSE_TIMEOUT_RECOVERY_DELAY_SECONDS = 0.75

# Recovery після timeout під час manual open.
IB_MANUAL_OPEN_TIMEOUT_RECOVERY_ATTEMPTS = 5
IB_MANUAL_OPEN_TIMEOUT_RECOVERY_DELAY_SECONDS = 2.5

# Локальні execution statuses для операцій, що очікують підтвердження.
IB_MANUAL_OPEN_EXECUTION_STATUS_PENDING = "PENDING_CONFIRMATION"
IB_LEG_CLOSE_EXECUTION_STATUS_PENDING = "PENDING_CONFIRMATION"


# =============================================================================
# cTrader Open API numeric enums, використані runtime adapter
# =============================================================================

# ProtoOAOrderType.MARKET.
CTRADER_ORDER_TYPE_MARKET = 1

# ProtoOATradeSide.BUY / SELL.
CTRADER_TRADE_SIDE_BUY = 1
CTRADER_TRADE_SIDE_SELL = 2

# ProtoOAExecutionType order lifecycle values.
CTRADER_EXECUTION_TYPE_ORDER_ACCEPTED = 2
CTRADER_EXECUTION_TYPE_ORDER_FILLED = 3
CTRADER_EXECUTION_TYPE_ORDER_REJECTED = 7


# =============================================================================
# IB SL/TP operation statuses
# =============================================================================

# Стани, у яких protective order вважається прийнятим брокером.
IB_SL_TP_OPERATION_ACCEPTED_STATUSES = frozenset(
    {
        "PRESUBMITTED",
        "SUBMITTED",
    }
)

# Стани, що підтверджують скасування protective order.
IB_SL_TP_OPERATION_CANCELLED_STATUSES = frozenset(
    {
        "CANCELLED",
        "APICANCELLED",
    }
)

# Стани, що завершують SL/TP operation як невдалу.
IB_SL_TP_OPERATION_FAILURE_STATUSES = frozenset(
    {
        "INACTIVE",
        "FILLED",
    }
)

# Terminal broker statuses must never be treated as current open-order evidence.
IB_OPEN_ORDER_TERMINAL_STATUSES = frozenset(
    {
        "APICANCELLED",
        "CANCELLED",
        "FILLED",
        "INACTIVE",
    }
)


# =============================================================================
# IB virtual position legs: lifecycle, protection і reconciliation
# =============================================================================

# Lifecycle стан virtual position leg.
IB_LEG_STATUS_OPEN = "OPEN"
IB_LEG_STATUS_PARTIALLY_CLOSED = "PARTIALLY_CLOSED"
IB_LEG_STATUS_CLOSED = "CLOSED"

# Стан protective coverage virtual leg.
IB_PROTECTION_STATUS_NONE = "NONE"
IB_PROTECTION_STATUS_PARTIAL = "PARTIAL"
IB_PROTECTION_STATUS_COMPLETE = "COMPLETE"
IB_PROTECTION_STATUS_BLOCKED = "BLOCKED"

# Результат reconciliation virtual legs із broker snapshot/executions.
IB_RECONCILIATION_STATUS_RECONCILED = "RECONCILED"
IB_RECONCILIATION_STATUS_RECONCILED_MANUAL = "RECONCILED_MANUAL"
IB_RECONCILIATION_STATUS_UNRECONCILED = "UNRECONCILED"
IB_RECONCILIATION_STATUS_BLOCKED = "BLOCKED"
IB_RECONCILIATION_STATUS_CLOSE_EVIDENCE_MISSING = "CLOSE_EVIDENCE_MISSING"

# Стан persistence/reconciliation під час створення virtual leg.
IB_LEG_PERSISTENCE_STATUS_NOT_CREATED = "NOT_CREATED"
IB_LEG_PERSISTENCE_STATUS_RECONCILED = "RECONCILED"
IB_LEG_PERSISTENCE_STATUS_ERROR = "ERROR"


# =============================================================================
# IB position groups і broker position classification
# =============================================================================

# Режим представлення broker net position в OrdersPage.
IB_POSITION_GROUP_MODE_LGE_VIRTUAL_LEGS = "LGE_VIRTUAL_LEGS"
IB_POSITION_GROUP_MODE_NET_ONLY = "NET_ONLY"

# Тип broker position row.
IB_BROKER_POSITION_KIND_NET = "NET"
IB_BROKER_POSITION_KIND_VIRTUAL_FX = "VIRTUAL_FX"


# =============================================================================
# IB virtual leg order roles і protective order types
# =============================================================================

# Ролі broker orders, пов'язаних з однією virtual leg.
IB_LEG_ORDER_ROLE_PARENT = "PARENT"
IB_LEG_ORDER_ROLE_STOP_LOSS = "STOP_LOSS"
IB_LEG_ORDER_ROLE_TAKE_PROFIT = "TAKE_PROFIT"
IB_LEG_ORDER_ROLE_CLOSE = "CLOSE"
IB_LEG_ORDER_ROLES = frozenset(
    {
        IB_LEG_ORDER_ROLE_PARENT,
        IB_LEG_ORDER_ROLE_STOP_LOSS,
        IB_LEG_ORDER_ROLE_TAKE_PROFIT,
        IB_LEG_ORDER_ROLE_CLOSE,
    }
)

# Broker order types, що розпізнаються як SL/TP protection.
IB_STOP_ORDER_TYPES = frozenset({"STP", "STP LMT"})
IB_TAKE_PROFIT_ORDER_TYPES = frozenset({"LMT"})
IB_PROTECTIVE_ORDER_TYPES = IB_STOP_ORDER_TYPES | IB_TAKE_PROFIT_ORDER_TYPES
