# -*- coding: utf-8 -*-
"""
Канонічна модель робочого простору алгоритму LGE.

RoadMap92:
- workspace_uid є незмінним технічним ідентифікатором;
- display_name є користувацькою назвою;
- data_mode і control_mode належать конкретному WSP;
- account_mode описує вибраний broker account (LIVE/DEMO/PAPER);
- runtime_state не зберігається як істина в Session;
- після відновлення runtime_state завжди RESTORED;
- автоматичний запуск алгоритму після рестарту заборонений.

RoadMap101 матеріалізує нові MACD reference-defaults лише під час створення
нового WSP. Persisted WSP і legacy fallback не переписуються приховано: їхні
параметри та indicator snapshot лишаються джерелом істини для Replay.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from core.timeframes import get_timeframe
from core.workspace_indicator_profile import (
    default_workspace_indicator_profile_bindings,
    new_workspace_indicator_profile_bindings,
    normalize_workspace_indicator_profile_bindings,
)
from engine.runtime_constants import (
    NEW_WORKSPACE_MACD_CROSS_ANGLE_MODEL,
    NEW_WORKSPACE_MACD_CROSS_MIN_ABC_ANGLE,
    NEW_WORKSPACE_MACD_SIGNAL_MODE,
    WORKSPACE_MACD_EXTREMUM_MIN_PROMINENCE_KEY,
    WORKSPACE_MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE_KEY,
    resolve_new_workspace_macd_extremum_min_prominence,
    resolve_new_workspace_macd_extremum_to_cross_min_distance,
)

WORKSPACE_SCHEMA_VERSION = 5
SUPPORTED_WORKSPACE_SCHEMA_VERSIONS = {1, 2, 3, 4, WORKSPACE_SCHEMA_VERSION}

WORKSPACE_DATA_MODE_BROKER = "BROKER"
WORKSPACE_DATA_MODE_REPLAY = "REPLAY"
WORKSPACE_DATA_MODE_BACKTEST = "BACKTEST"
WORKSPACE_DATA_MODES = (
    WORKSPACE_DATA_MODE_BROKER,
    WORKSPACE_DATA_MODE_REPLAY,
    WORKSPACE_DATA_MODE_BACKTEST,
)

WORKSPACE_ACCOUNT_MODE_LIVE = "LIVE"
WORKSPACE_ACCOUNT_MODE_DEMO = "DEMO"
WORKSPACE_ACCOUNT_MODE_PAPER = "PAPER"
WORKSPACE_ACCOUNT_MODES = (
    WORKSPACE_ACCOUNT_MODE_LIVE,
    WORKSPACE_ACCOUNT_MODE_DEMO,
    WORKSPACE_ACCOUNT_MODE_PAPER,
)

WORKSPACE_CONTROL_MODE_MANUAL = "MANUAL"
WORKSPACE_CONTROL_MODE_SEMI = "SEMI"
WORKSPACE_CONTROL_MODE_AUTO = "AUTO"
WORKSPACE_CONTROL_MODES = (
    WORKSPACE_CONTROL_MODE_MANUAL,
    WORKSPACE_CONTROL_MODE_SEMI,
    WORKSPACE_CONTROL_MODE_AUTO,
)

WORKSPACE_STATE_STOPPED = "STOPPED"
WORKSPACE_STATE_RESTORED = "RESTORED"
WORKSPACE_STATE_STARTING = "STARTING"
WORKSPACE_STATE_RUNNING = "RUNNING"
WORKSPACE_STATE_STOPPING = "STOPPING"
WORKSPACE_STATE_ERROR = "ERROR"
WORKSPACE_RUNTIME_STATES = (
    WORKSPACE_STATE_STOPPED,
    WORKSPACE_STATE_RESTORED,
    WORKSPACE_STATE_STARTING,
    WORKSPACE_STATE_RUNNING,
    WORKSPACE_STATE_STOPPING,
    WORKSPACE_STATE_ERROR,
)

WORKSPACE_PANEL_ORDERS = "ORDERS"
WORKSPACE_PANEL_CHART = "CHART"
WORKSPACE_PANEL_POSITION = "POSITION"
WORKSPACE_PANEL_SIGNALS = "SIGNALS"
WORKSPACE_PANEL_LOG = "LOG"
WORKSPACE_PANELS = (
    WORKSPACE_PANEL_CHART,
    WORKSPACE_PANEL_POSITION,
    WORKSPACE_PANEL_SIGNALS,
    WORKSPACE_PANEL_ORDERS,
    WORKSPACE_PANEL_LOG,
)

DEFAULT_PROFIT_PROTECTION = {
    "enabled": True,
    "activation_mode": "AFTER_SPREAD",
    "max_profit_drawdown_percent": 30.0,
    "minimum_profit": 0.0,
}

NEW_WORKSPACE_MACD_STATIC_PARAMETERS = {
    "macd_signal_mode": NEW_WORKSPACE_MACD_SIGNAL_MODE,
    "macd_cross_angle_model": NEW_WORKSPACE_MACD_CROSS_ANGLE_MODEL,
    "macd_cross_min_abc_angle": NEW_WORKSPACE_MACD_CROSS_MIN_ABC_ANGLE,
}


def new_workspace_macd_parameters(symbol: str) -> dict[str, Any]:
    """Матеріалізувати symbol-aware MACD reference-defaults нового WSP."""
    parameters = dict(NEW_WORKSPACE_MACD_STATIC_PARAMETERS)
    parameters[WORKSPACE_MACD_EXTREMUM_MIN_PROMINENCE_KEY] = (
        resolve_new_workspace_macd_extremum_min_prominence(symbol)
    )
    parameters[WORKSPACE_MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE_KEY] = (
        resolve_new_workspace_macd_extremum_to_cross_min_distance(symbol)
    )
    return parameters


class AlgorithmWorkspaceError(ValueError):
    """Помилка валідації workspace."""


def utc_now_iso() -> str:
    """Повернути поточний UTC timestamp у ISO-форматі."""
    return datetime.now(UTC).isoformat()


def normalize_workspace_uid(value: str) -> str:
    """Перевірити й нормалізувати workspace UUID."""
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise AlgorithmWorkspaceError("Invalid workspace_uid") from exc


def build_default_workspace_name(
    *,
    broker: str,
    symbol: str,
    timeframe: str,
    algorithm: str,
) -> str:
    """Побудувати початкову читабельну назву workspace."""
    return f"{broker} {symbol} {timeframe} — {algorithm}"


def default_workspace_ui_state() -> dict[str, Any]:
    """Повернути безпечний UI-стан нового WSP."""
    return {
        "geometry": None,
        "window_state": "NORMAL",
        "active_panel": WORKSPACE_PANEL_CHART,
    }


def infer_account_mode(broker: str, account_id: str | None) -> str | None:
    """Безпечний fallback типу рахунку за broker/account_id."""
    normalized_broker = str(broker or "").strip().upper()
    normalized_account = str(account_id or "").strip().upper()
    if not normalized_account:
        return None
    if normalized_broker == "IB":
        return (
            WORKSPACE_ACCOUNT_MODE_PAPER
            if normalized_account.startswith("D")
            else WORKSPACE_ACCOUNT_MODE_LIVE
        )
    return None


def normalize_legacy_data_mode(value: object) -> str:
    """Перетворити legacy LIVE/PAPER у canonical BROKER."""
    normalized = str(value or "").strip().upper()
    if normalized in {"LIVE", "PAPER"}:
        return WORKSPACE_DATA_MODE_BROKER
    return normalized or WORKSPACE_DATA_MODE_BROKER


@dataclass(slots=True)
class AlgorithmWorkspace:
    """Конфігурація одного algorithm workspace."""

    workspace_uid: str
    display_name: str
    broker: str
    account_id: str | None
    symbol: str
    timeframe: str
    algorithm: str
    data_mode: str = WORKSPACE_DATA_MODE_BROKER
    account_mode: str | None = None
    control_mode: str = WORKSPACE_CONTROL_MODE_SEMI
    parameters: dict[str, Any] = field(default_factory=dict)
    risk_settings: dict[str, Any] = field(default_factory=dict)
    profit_protection: dict[str, Any] = field(
        default_factory=lambda: dict(DEFAULT_PROFIT_PROTECTION)
    )
    replay_settings: dict[str, Any] = field(default_factory=dict)
    history_download_settings: dict[str, Any] = field(default_factory=dict)
    indicator_profile_bindings: dict[str, Any] = field(
        default_factory=default_workspace_indicator_profile_bindings
    )
    ui_state: dict[str, Any] = field(default_factory=default_workspace_ui_state)
    has_started_once: bool = False
    created_utc: str = field(default_factory=utc_now_iso)
    updated_utc: str = field(default_factory=utc_now_iso)
    runtime_state: str = WORKSPACE_STATE_STOPPED

    def __post_init__(self) -> None:
        self.workspace_uid = normalize_workspace_uid(self.workspace_uid)
        self.display_name = self._required_text(self.display_name, "display_name")
        self.broker = self._required_text(self.broker, "broker").upper()
        self.account_id = self._optional_text(self.account_id)
        self.account_mode = self._normalize_account_mode(
            self.account_mode,
            broker=self.broker,
            account_id=self.account_id,
        )
        self.symbol = self._required_text(self.symbol, "symbol").upper()
        self.timeframe = self._required_text(self.timeframe, "timeframe").upper()
        get_timeframe(self.timeframe)
        self.algorithm = self._required_text(self.algorithm, "algorithm")
        self.data_mode = self._normalized_choice(
            normalize_legacy_data_mode(self.data_mode),
            "data_mode",
            WORKSPACE_DATA_MODES,
        )
        self.control_mode = self._normalized_choice(
            self.control_mode,
            "control_mode",
            WORKSPACE_CONTROL_MODES,
        )

        self.parameters = self._dict_copy(self.parameters, "parameters")
        # RoadMap98: одноразовий Strength-експеримент MACD відхилено.
        # Невідомі future keys зберігаємо, але цей конкретний retired key
        # більше не повинен жити в конфігурації WSP.
        self.parameters.pop("macd_minimum_crossover_strength", None)
        self.risk_settings = self._dict_copy(
            self.risk_settings,
            "risk_settings",
        )
        self.profit_protection = self._normalize_profit_protection(
            self.profit_protection
        )
        self.replay_settings = self._dict_copy(
            self.replay_settings,
            "replay_settings",
        )
        self.history_download_settings = self._dict_copy(
            self.history_download_settings,
            "history_download_settings",
        )
        self.indicator_profile_bindings = (
            normalize_workspace_indicator_profile_bindings(
                self.indicator_profile_bindings
            )
        )
        self.ui_state = self._normalize_ui_state(self.ui_state)

        if self.runtime_state not in WORKSPACE_RUNTIME_STATES:
            raise AlgorithmWorkspaceError("Invalid workspace runtime_state")

    @classmethod
    def create(
        cls,
        *,
        broker: str,
        account_id: str | None,
        symbol: str,
        timeframe: str,
        algorithm: str,
        display_name: str | None = None,
        data_mode: str = WORKSPACE_DATA_MODE_BROKER,
        account_mode: str | None = None,
        control_mode: str = WORKSPACE_CONTROL_MODE_SEMI,
        parameters: dict[str, Any] | None = None,
        risk_settings: dict[str, Any] | None = None,
        profit_protection: dict[str, Any] | None = None,
        replay_settings: dict[str, Any] | None = None,
        history_download_settings: dict[str, Any] | None = None,
        indicator_profile_bindings: dict[str, Any] | None = None,
        ui_state: dict[str, Any] | None = None,
    ) -> AlgorithmWorkspace:
        """Створити новий workspace з автоматичним UUID."""
        normalized_broker = cls._required_text(broker, "broker").upper()
        normalized_symbol = cls._required_text(symbol, "symbol").upper()
        normalized_timeframe = cls._required_text(
            timeframe,
            "timeframe",
        ).upper()
        normalized_algorithm = cls._required_text(algorithm, "algorithm")

        initial_name = display_name
        if initial_name is None or not initial_name.strip():
            initial_name = build_default_workspace_name(
                broker=normalized_broker,
                symbol=normalized_symbol,
                timeframe=normalized_timeframe,
                algorithm=normalized_algorithm,
            )

        return cls(
            workspace_uid=str(uuid4()),
            display_name=initial_name,
            broker=normalized_broker,
            account_id=account_id,
            account_mode=account_mode,
            symbol=normalized_symbol,
            timeframe=normalized_timeframe,
            algorithm=normalized_algorithm,
            data_mode=data_mode,
            control_mode=control_mode,
            parameters=(
                new_workspace_macd_parameters(normalized_symbol)
                if parameters is None
                else dict(parameters)
            ),
            risk_settings=dict(risk_settings or {}),
            profit_protection=dict(
                profit_protection or DEFAULT_PROFIT_PROTECTION
            ),
            replay_settings=dict(replay_settings or {}),
            history_download_settings=dict(history_download_settings or {}),
            indicator_profile_bindings=(
                dict(indicator_profile_bindings)
                if indicator_profile_bindings is not None
                else new_workspace_indicator_profile_bindings()
            ),
            ui_state=dict(ui_state or default_workspace_ui_state()),
            runtime_state=WORKSPACE_STATE_STOPPED,
        )

    @classmethod
    def from_storage_dict(cls, data: dict[str, Any]) -> AlgorithmWorkspace:
        """Відновити workspace з JSON у стані RESTORED."""
        if not isinstance(data, dict):
            raise AlgorithmWorkspaceError("Workspace payload must be a dict")

        schema_version = int(data.get("schema_version", 0))
        if schema_version not in SUPPORTED_WORKSPACE_SCHEMA_VERSIONS:
            raise AlgorithmWorkspaceError(
                f"Unsupported workspace schema_version: {schema_version}"
            )

        broker = str(data.get("broker") or "")
        account_id = data.get("account_id")
        account_mode = data.get("account_mode")
        if account_mode is None:
            account_mode = infer_account_mode(broker, account_id)

        replay_settings = dict(data.get("replay_settings") or {})
        history_download_settings = dict(
            data.get("history_download_settings") or {}
        )
        if not history_download_settings:
            legacy_start = replay_settings.get("download_start_date")
            legacy_end = replay_settings.get("download_end_date")
            legacy_timezone = replay_settings.get("download_timezone")
            if legacy_start is not None or legacy_end is not None:
                history_download_settings = {
                    "broker": broker,
                    "account_id": account_id,
                    "symbol": str(data.get("symbol") or ""),
                    "timeframe": str(data.get("timeframe") or ""),
                    "start_date": legacy_start,
                    "end_date": legacy_end,
                    "timezone": legacy_timezone or "UTC",
                }
        for legacy_key in (
            "download_start_date",
            "download_end_date",
            "download_timezone",
        ):
            replay_settings.pop(legacy_key, None)

        return cls(
            workspace_uid=str(data.get("workspace_uid") or ""),
            display_name=str(data.get("display_name") or ""),
            broker=broker,
            account_id=account_id,
            account_mode=account_mode,
            symbol=str(data.get("symbol") or ""),
            timeframe=str(data.get("timeframe") or ""),
            algorithm=str(data.get("algorithm") or ""),
            data_mode=normalize_legacy_data_mode(data.get("data_mode")),
            control_mode=str(
                data.get("control_mode") or WORKSPACE_CONTROL_MODE_SEMI
            ),
            parameters=dict(data.get("parameters") or {}),
            risk_settings=dict(data.get("risk_settings") or {}),
            profit_protection=dict(
                data.get("profit_protection") or DEFAULT_PROFIT_PROTECTION
            ),
            replay_settings=replay_settings,
            history_download_settings=history_download_settings,
            indicator_profile_bindings=dict(
                data.get("indicator_profile_bindings")
                or default_workspace_indicator_profile_bindings()
            ),
            ui_state=dict(data.get("ui_state") or default_workspace_ui_state()),
            has_started_once=bool(data.get("has_started_once", False)),
            created_utc=str(data.get("created_utc") or utc_now_iso()),
            updated_utc=str(data.get("updated_utc") or utc_now_iso()),
            runtime_state=WORKSPACE_STATE_RESTORED,
        )

    def to_storage_dict(self) -> dict[str, Any]:
        """Повернути JSON без runtime-істини брокера й алгоритму."""
        return {
            "schema_version": WORKSPACE_SCHEMA_VERSION,
            "workspace_uid": self.workspace_uid,
            "display_name": self.display_name,
            "broker": self.broker,
            "account_id": self.account_id,
            "account_mode": self.account_mode,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "algorithm": self.algorithm,
            "data_mode": self.data_mode,
            "control_mode": self.control_mode,
            "parameters": dict(self.parameters),
            "risk_settings": dict(self.risk_settings),
            "profit_protection": dict(self.profit_protection),
            "replay_settings": dict(self.replay_settings),
            "history_download_settings": dict(
                self.history_download_settings
            ),
            "indicator_profile_bindings": dict(
                self.indicator_profile_bindings
            ),
            "ui_state": dict(self.ui_state),
            "has_started_once": self.has_started_once,
            "created_utc": self.created_utc,
            "updated_utc": self.updated_utc,
        }

    def set_display_name(self, display_name: str) -> None:
        """Змінити назву до першого запуску workspace."""
        if self.has_started_once:
            raise AlgorithmWorkspaceError(
                "Workspace display_name is locked after first start"
            )
        self.display_name = self._required_text(display_name, "display_name")
        self.updated_utc = utc_now_iso()

    def set_modes(self, *, data_mode: str, control_mode: str) -> None:
        """Змінити джерело даних і режим керування WSP."""
        self.data_mode = self._normalized_choice(
            normalize_legacy_data_mode(data_mode),
            "data_mode",
            WORKSPACE_DATA_MODES,
        )
        self.control_mode = self._normalized_choice(
            control_mode,
            "control_mode",
            WORKSPACE_CONTROL_MODES,
        )
        self.updated_utc = utc_now_iso()

    def set_algorithm_configuration(
        self,
        *,
        parameters: dict[str, Any],
        risk_settings: dict[str, Any],
        profit_protection: dict[str, Any],
    ) -> None:
        """Update validated per-WSP algorithm and risk configuration."""
        self.parameters = self._dict_copy(parameters, "parameters")
        self.risk_settings = self._dict_copy(
            risk_settings,
            "risk_settings",
        )
        self.profit_protection = self._normalize_profit_protection(
            profit_protection
        )
        self.updated_utc = utc_now_iso()

    def set_indicator_profile_bindings(
        self,
        indicator_profile_bindings: dict[str, Any],
    ) -> None:
        """Оновити відтворювані bindings профілів MACD та Alligator."""
        self.indicator_profile_bindings = (
            normalize_workspace_indicator_profile_bindings(
                indicator_profile_bindings
            )
        )
        self.updated_utc = utc_now_iso()

    def set_replay_settings(self, replay_settings: dict[str, Any]) -> None:
        """Update persisted Replay source and period settings."""
        self.replay_settings = self._dict_copy(
            replay_settings,
            "replay_settings",
        )
        self.updated_utc = utc_now_iso()

    def set_history_download_settings(
        self,
        history_download_settings: dict[str, Any],
    ) -> None:
        """Update persisted broker-history download settings."""
        self.history_download_settings = self._dict_copy(
            history_download_settings,
            "history_download_settings",
        )
        self.updated_utc = utc_now_iso()

    def set_ui_state(self, ui_state: dict[str, Any]) -> None:
        """Оновити лише безпечний UI-стан WSP."""
        self.ui_state = self._normalize_ui_state(ui_state)
        self.updated_utc = utc_now_iso()

    def set_runtime_state(self, runtime_state: str) -> None:
        """Змінити тимчасовий runtime-стан без збереження як істини."""
        if runtime_state not in WORKSPACE_RUNTIME_STATES:
            raise AlgorithmWorkspaceError("Invalid workspace runtime_state")
        self.runtime_state = runtime_state

    def mark_started_once(self) -> None:
        """Зафіксувати перший запуск і заблокувати перейменування."""
        self.has_started_once = True
        self.runtime_state = WORKSPACE_STATE_STOPPED
        self.updated_utc = utc_now_iso()

    @staticmethod
    def _required_text(value: object, field_name: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise AlgorithmWorkspaceError(f"{field_name} is required")
        return text

    @staticmethod
    def _optional_text(value: object) -> str | None:
        text = str(value or "").strip()
        return text or None

    @staticmethod
    def _dict_copy(value: object, field_name: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise AlgorithmWorkspaceError(f"{field_name} must be a dict")
        return dict(value)

    @classmethod
    def _normalized_choice(
        cls,
        value: object,
        field_name: str,
        allowed: tuple[str, ...],
    ) -> str:
        normalized = cls._required_text(value, field_name).upper()
        if normalized not in allowed:
            raise AlgorithmWorkspaceError(f"Invalid {field_name}: {normalized}")
        return normalized

    @classmethod
    def _normalize_account_mode(
        cls,
        value: object,
        *,
        broker: str,
        account_id: str | None,
    ) -> str | None:
        text = cls._optional_text(value)
        if text is None:
            return infer_account_mode(broker, account_id)
        normalized = text.upper()
        if normalized not in WORKSPACE_ACCOUNT_MODES:
            raise AlgorithmWorkspaceError(
                f"Invalid account_mode: {normalized}"
            )
        return normalized

    @classmethod
    def _normalize_profit_protection(
        cls,
        value: object,
    ) -> dict[str, Any]:
        data = dict(DEFAULT_PROFIT_PROTECTION)
        data.update(cls._dict_copy(value, "profit_protection"))

        drawdown = float(data["max_profit_drawdown_percent"])
        if not 0.0 < drawdown < 100.0:
            raise AlgorithmWorkspaceError(
                "max_profit_drawdown_percent must be between 0 and 100"
            )
        data["max_profit_drawdown_percent"] = drawdown
        minimum_profit = float(data.get("minimum_profit", 0.0))
        if minimum_profit < 0.0:
            raise AlgorithmWorkspaceError(
                "profit_protection.minimum_profit cannot be negative"
            )
        data["minimum_profit"] = minimum_profit
        data["enabled"] = bool(data.get("enabled", True))
        data["activation_mode"] = cls._required_text(
            data.get("activation_mode"),
            "profit_protection.activation_mode",
        ).upper()
        return data

    @classmethod
    def _normalize_ui_state(cls, value: object) -> dict[str, Any]:
        data = default_workspace_ui_state()
        data.update(cls._dict_copy(value, "ui_state"))

        active_panel = cls._required_text(
            data.get("active_panel"),
            "ui_state.active_panel",
        ).upper()
        if active_panel not in WORKSPACE_PANELS:
            active_panel = WORKSPACE_PANEL_CHART
        data["active_panel"] = active_panel

        window_state = cls._required_text(
            data.get("window_state"),
            "ui_state.window_state",
        ).upper()
        if window_state not in ("NORMAL", "MINIMIZED", "MAXIMIZED"):
            window_state = "NORMAL"
        data["window_state"] = window_state

        geometry = data.get("geometry")
        if geometry is not None:
            if not isinstance(geometry, dict):
                raise AlgorithmWorkspaceError(
                    "ui_state.geometry must be a dict or None"
                )
            required_geometry_keys = ("x", "y", "width", "height")
            data["geometry"] = {
                key: int(geometry[key]) for key in required_geometry_keys
            }
        return data
