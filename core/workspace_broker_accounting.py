# -*- coding: utf-8 -*-
"""Broker request and subscription accounting for Algorithm Workspaces."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WorkspaceBrokerSubscriptionKey:
    """One broker-session/symbol streaming-subscription identity."""

    broker: str
    symbol: str

    def __post_init__(self) -> None:
        broker = str(self.broker or "").strip().upper()
        symbol = (
            str(self.symbol or "")
            .strip()
            .upper()
            .replace("/", "")
            .replace(".", "")
        )
        if broker not in {"CTRADER", "IB"}:
            raise ValueError("Unsupported workspace subscription broker")
        if len(symbol) != 6 or not symbol.isalpha():
            raise ValueError("Workspace subscription symbol is invalid")
        object.__setattr__(self, "broker", broker)
        object.__setattr__(self, "symbol", symbol)


@dataclass(frozen=True, slots=True)
class WorkspaceBrokerSubscriptionRelease:
    """Result of releasing one WSP ownership reference."""

    released: bool
    key: WorkspaceBrokerSubscriptionKey | None
    last_reference: bool


@dataclass(frozen=True, slots=True)
class WorkspaceBrokerAccountingSnapshot:
    """Immutable counters and current logical subscription ownership."""

    subscription_acquires: int
    subscription_deduplicated: int
    subscription_requests: int
    subscription_releases: int
    unsubscription_requests: int
    quote_snapshot_requests: int
    history_downloads: int
    history_broker_requests: int
    retry_requests: int
    failed_requests: int
    active_subscriptions: int
    active_references: int
    references_by_subscription: tuple[
        tuple[WorkspaceBrokerSubscriptionKey, int], ...
    ]


class WorkspaceBrokerRequestAccounting:
    """Track WSP request counts and reference-counted subscriptions."""

    def __init__(self) -> None:
        self._owners_by_key: dict[
            WorkspaceBrokerSubscriptionKey,
            set[str],
        ] = {}
        self._key_by_workspace: dict[
            str,
            WorkspaceBrokerSubscriptionKey,
        ] = {}
        self._subscription_acquires = 0
        self._subscription_deduplicated = 0
        self._subscription_requests = 0
        self._subscription_releases = 0
        self._unsubscription_requests = 0
        self._quote_snapshot_requests = 0
        self._history_downloads = 0
        self._history_broker_requests = 0
        self._retry_requests = 0
        self._failed_requests = 0

    def acquire_subscription(
        self,
        workspace_uid: str,
        key: WorkspaceBrokerSubscriptionKey,
    ) -> bool:
        """Acquire one owner reference and return whether subscribe is new."""
        uid = str(workspace_uid or "").strip()
        if not uid:
            raise ValueError("workspace_uid is required")
        existing = self._key_by_workspace.get(uid)
        if existing is not None:
            if existing != key:
                raise RuntimeError(
                    "Workspace subscription binding cannot change in place"
                )
            self._subscription_deduplicated += 1
            return False

        owners = self._owners_by_key.setdefault(key, set())
        first_reference = not owners
        owners.add(uid)
        self._key_by_workspace[uid] = key
        self._subscription_acquires += 1
        if first_reference:
            self._subscription_requests += 1
        else:
            self._subscription_deduplicated += 1
        return first_reference

    def release_subscription(
        self,
        workspace_uid: str,
    ) -> WorkspaceBrokerSubscriptionRelease:
        """Release one owner reference and identify final unsubscribe."""
        uid = str(workspace_uid or "").strip()
        key = self._key_by_workspace.pop(uid, None)
        if key is None:
            return WorkspaceBrokerSubscriptionRelease(False, None, False)

        owners = self._owners_by_key.get(key)
        if owners is None or uid not in owners:
            raise RuntimeError("Workspace subscription ownership is corrupted")
        owners.remove(uid)
        self._subscription_releases += 1
        last_reference = not owners
        if last_reference:
            self._owners_by_key.pop(key, None)
            self._unsubscription_requests += 1
        return WorkspaceBrokerSubscriptionRelease(
            released=True,
            key=key,
            last_reference=last_reference,
        )

    def record_quote_snapshot_request(self) -> None:
        """Count one broker quote snapshot/synchronization request."""
        self._quote_snapshot_requests += 1

    def record_history_download(self) -> None:
        """Count one logical WSP history download attempt."""
        self._history_downloads += 1

    def record_history_broker_requests(self, request_count: int) -> None:
        """Count physical broker history chunks reported by the adapter."""
        count = int(request_count)
        if count < 0:
            raise ValueError("history request_count cannot be negative")
        self._history_broker_requests += count

    def record_retry_request(self) -> None:
        """Count one reconnect-driven resubscription request."""
        self._retry_requests += 1

    def record_failed_request(self) -> None:
        """Count one failed quote, history or resubscription request."""
        self._failed_requests += 1

    def snapshot(self) -> WorkspaceBrokerAccountingSnapshot:
        """Return deterministic immutable accounting state."""
        references = tuple(
            sorted(
                (
                    (key, len(owners))
                    for key, owners in self._owners_by_key.items()
                ),
                key=lambda row: (
                    row[0].broker,
                    row[0].symbol,
                ),
            )
        )
        return WorkspaceBrokerAccountingSnapshot(
            subscription_acquires=self._subscription_acquires,
            subscription_deduplicated=self._subscription_deduplicated,
            subscription_requests=self._subscription_requests,
            subscription_releases=self._subscription_releases,
            unsubscription_requests=self._unsubscription_requests,
            quote_snapshot_requests=self._quote_snapshot_requests,
            history_downloads=self._history_downloads,
            history_broker_requests=self._history_broker_requests,
            retry_requests=self._retry_requests,
            failed_requests=self._failed_requests,
            active_subscriptions=len(self._owners_by_key),
            active_references=len(self._key_by_workspace),
            references_by_subscription=references,
        )
