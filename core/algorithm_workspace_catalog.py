# -*- coding: utf-8 -*-
"""Read-only broker/account/symbol catalog for RoadMap92 WSP creation."""

from __future__ import annotations

from dataclasses import dataclass

from core.algorithm_workspace import (
    WORKSPACE_ACCOUNT_MODE_DEMO,
    WORKSPACE_ACCOUNT_MODE_LIVE,
    infer_account_mode,
)
from core.ctrader_symbols import list_enabled_symbols


@dataclass(frozen=True, slots=True)
class WorkspaceAccountOption:
    """One selectable broker account for a WSP."""

    account_id: str
    account_mode: str
    display_name: str
    balance: float | None = None
    currency: str = ""


def format_workspace_balance(
    balance: float | None,
    currency: str = "",
) -> str:
    """Format a read-only broker balance for compact WSP display."""
    if balance is None:
        return "—"
    try:
        text = f"{float(balance):,.2f}".replace(",", " ")
    except (TypeError, ValueError):
        return "—"
    normalized_currency = str(currency or "").strip().upper()
    return f"{text} {normalized_currency}" if normalized_currency else text


class AlgorithmWorkspaceCatalog:
    """
    Build WSP account/symbol lists without changing broker state.

    Runtime services are read only. When a broker is disconnected, the
    last selected account from LGE.conf is used as a safe fallback.
    """

    def __init__(self, runtime_engine: object | None = None) -> None:
        self._runtime_engine = runtime_engine

    def set_runtime_engine(self, runtime_engine: object | None) -> None:
        """Attach the shared RuntimeEngine after MainAppWindow creates it."""
        self._runtime_engine = runtime_engine

    def list_accounts(self, broker: str) -> list[WorkspaceAccountOption]:
        """Return deduplicated accounts for IB or cTrader."""
        normalized_broker = str(broker or "").strip().upper()
        if normalized_broker == "IB":
            options = self._ib_runtime_accounts()
            saved = self._saved_ib_account()
        elif normalized_broker == "CTRADER":
            options = self._ctrader_runtime_accounts()
            saved = self._saved_ctrader_account()
        else:
            return []

        if saved is not None:
            options.append(saved)

        deduplicated: dict[str, WorkspaceAccountOption] = {}
        for option in options:
            current = deduplicated.get(option.account_id)
            if current is None:
                deduplicated[option.account_id] = option
                continue
            if current.balance is None and option.balance is not None:
                deduplicated[option.account_id] = option
                continue
            if current.balance is not None and option.balance is None:
                continue
            if (
                current.display_name == current.account_id
                and option.display_name != option.account_id
            ):
                deduplicated[option.account_id] = option

        return sorted(
            deduplicated.values(),
            key=lambda item: (item.account_mode, item.display_name.casefold()),
        )

    def find_account(
        self,
        broker: str,
        account_id: str | None,
    ) -> WorkspaceAccountOption | None:
        """Return one current read-only account option by broker/account ID."""
        normalized_account_id = str(account_id or "").strip()
        if not normalized_account_id:
            return None
        for option in self.list_accounts(broker):
            if option.account_id == normalized_account_id:
                return option
        return None

    @staticmethod
    def list_symbols(
        broker: str,
        account_id: str | None = None,
    ) -> list[str]:
        """
        Return the current canonical Forex symbol catalog.

        cTrader symbols originate from the verified account table. IB uses
        the same Forex names at this UI stage; RuntimeEngine reconciliation
        will validate the real contract before Start.
        """
        normalized_broker = str(broker or "").strip().upper()
        if normalized_broker not in {"IB", "CTRADER"}:
            return []

        if account_id is not None and not str(account_id).strip():
            return []

        return list_enabled_symbols()

    def _ib_runtime_accounts(self) -> list[WorkspaceAccountOption]:
        runtime_engine = self._runtime_engine
        if runtime_engine is None:
            return []

        service = getattr(runtime_engine, "ib_runtime_service", None)
        if service is None:
            return []

        try:
            accounts = list(service.get_managed_accounts())
        except Exception:  # noqa
            accounts = []

        try:
            account_state = service.get_account_state()
        except Exception:  # noqa
            account_state = None

        result: list[WorkspaceAccountOption] = []
        for raw_account_id in accounts:
            account_id = str(raw_account_id or "").strip()
            if not account_id:
                continue
            mode = infer_account_mode("IB", account_id) or WORKSPACE_ACCOUNT_MODE_LIVE
            balance, currency = self._matching_account_balance(
                account_state,
                account_id,
            )
            result.append(
                WorkspaceAccountOption(
                    account_id=account_id,
                    account_mode=mode,
                    display_name=account_id,
                    balance=balance,
                    currency=currency,
                )
            )
        return result

    def _ctrader_runtime_accounts(self) -> list[WorkspaceAccountOption]:
        runtime_engine = self._runtime_engine
        if runtime_engine is None:
            return []

        service = getattr(runtime_engine, "ctrader_runtime_service", None)
        if service is None:
            return []

        try:
            accounts = list(service.get_account_list())
        except Exception:  # noqa
            accounts = []

        try:
            account_state = service.get_account_state()
        except Exception:  # noqa
            account_state = None

        result: list[WorkspaceAccountOption] = []
        for account in accounts:
            if not isinstance(account, dict):
                continue
            account_id = str(account.get("account_id") or "").strip()
            if not account_id:
                continue
            account_mode = str(account.get("account_mode") or "DEMO").strip().upper()
            if account_mode not in {
                WORKSPACE_ACCOUNT_MODE_LIVE,
                WORKSPACE_ACCOUNT_MODE_DEMO,
            }:
                account_mode = WORKSPACE_ACCOUNT_MODE_DEMO
            login = str(
                account.get("trader_login")
                or account.get("account_number")
                or account_id
            ).strip()

            balance = self._optional_float(account.get("balance"))
            currency = str(account.get("currency") or "").strip().upper()
            state_balance, state_currency = self._matching_account_balance(
                account_state,
                account_id,
            )
            if state_balance is not None:
                balance = state_balance
            if state_currency:
                currency = state_currency

            result.append(
                WorkspaceAccountOption(
                    account_id=account_id,
                    account_mode=account_mode,
                    display_name=login or account_id,
                    balance=balance,
                    currency=currency,
                )
            )
        return result

    @staticmethod
    def _matching_account_balance(
        account_state: object | None,
        account_id: str,
    ) -> tuple[float | None, str]:
        if account_state is None:
            return None, ""
        state_account_id = str(getattr(account_state, "account_id", "") or "").strip()
        if state_account_id != account_id:
            return None, ""
        balance = AlgorithmWorkspaceCatalog._optional_float(
            getattr(account_state, "balance", None)
        )
        currency = str(getattr(account_state, "currency", "") or "").strip().upper()
        return balance, currency

    @staticmethod
    def _optional_float(value: object) -> float | None:
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            try:
                return float(text)
            except ValueError:
                return None
        return None

    @staticmethod
    def _saved_ib_account() -> WorkspaceAccountOption | None:
        try:
            from core import session_state
        except Exception:  # noqa
            return None

        config = session_state.CURRENT_CONFIG
        if config is None:
            return None

        engine_ib = config.get("engine", "ib", {}) or {}
        if not isinstance(engine_ib, dict):
            return None
        account_id = str(engine_ib.get("account_id") or "").strip()
        if not account_id:
            return None
        mode = infer_account_mode("IB", account_id) or WORKSPACE_ACCOUNT_MODE_LIVE
        return WorkspaceAccountOption(account_id, mode, account_id)

    @staticmethod
    def _saved_ctrader_account() -> WorkspaceAccountOption | None:
        try:
            from core import session_state
        except Exception:  # noqa
            return None

        config = session_state.CURRENT_CONFIG
        if config is None:
            return None

        account_id = str(config.get("ctrader", "account_id", "") or "").strip()
        if not account_id:
            return None
        account_mode = (
            str(
                config.get("ctrader", "account_mode", WORKSPACE_ACCOUNT_MODE_DEMO)
                or WORKSPACE_ACCOUNT_MODE_DEMO
            )
            .strip()
            .upper()
        )
        if account_mode not in {
            WORKSPACE_ACCOUNT_MODE_LIVE,
            WORKSPACE_ACCOUNT_MODE_DEMO,
        }:
            account_mode = WORKSPACE_ACCOUNT_MODE_DEMO
        return WorkspaceAccountOption(account_id, account_mode, account_id)
