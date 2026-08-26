"""Shared synthetic fixtures for RoadMap91 OrdersPage checks."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from core.lang_manager import LangManager
from engine.ib_position_group import IBPositionGroup, IBPositionGroupSnapshot
from engine.ib_virtual_position_leg import IBVirtualPositionLeg
from engine.runtime_constants import (
    IB_BROKER_POSITION_KIND_NET,
    IB_BROKER_POSITION_KIND_VIRTUAL_FX,
    IB_LEG_STATUS_OPEN,
    IB_POSITION_GROUP_MODE_LGE_VIRTUAL_LEGS,
    IB_POSITION_GROUP_MODE_NET_ONLY,
    IB_PROTECTION_STATUS_COMPLETE,
    IB_PROTECTION_STATUS_NONE,
    IB_RECONCILIATION_STATUS_BLOCKED,
    IB_RECONCILIATION_STATUS_RECONCILED,
    IB_RECONCILIATION_STATUS_UNRECONCILED,
)


class DummyLangManager(LangManager):
    """Minimal fallback-only language manager."""

    def __init__(self) -> None:
        super().__init__()
        self._current_lang = "en"

    @property
    def current_language(self) -> str:
        return self._current_lang

    def tr(
        self,
        _key: str,
        fallback: str,
        localized_fallbacks: Mapping[str, str] | None = None,
    ) -> str:
        _ = localized_fallbacks
        return fallback

    def resolve(
        self,
        _key: str,
        fallback: str = "",
    ) -> str | None:
        return fallback or None


def build_leg(
    *,
    position_uid: str,
    trade_uid: str,
    side: str,
    volume: float,
    entry_price: float,
    stop_loss: float | None,
    take_profit: float | None,
    reconciliation_status: str = IB_RECONCILIATION_STATUS_RECONCILED,
) -> IBVirtualPositionLeg:
    """Build one synthetic active IB virtual leg."""
    return IBVirtualPositionLeg(
        position_uid=position_uid,
        trade_uid=trade_uid,
        broker_position_id="IB:DUM513747:EURUSD",
        account_id="DUM513747",
        symbol_name="EURUSD",
        side=side,
        volume=volume,
        entry_price=entry_price,
        opened_utc="2026-07-20T12:00:00+00:00",
        source="LGE_MANUAL",
        parent_order_id=100,
        stop_loss_order_id=101 if stop_loss is not None else None,
        take_profit_order_id=102 if take_profit is not None else None,
        stop_loss=stop_loss,
        take_profit=take_profit,
        oca_group="LGE-TEST-OCA",
        leg_status=IB_LEG_STATUS_OPEN,
        protection_status=(
            IB_PROTECTION_STATUS_COMPLETE
            if stop_loss is not None and take_profit is not None
            else IB_PROTECTION_STATUS_NONE
        ),
        reconciliation_status=reconciliation_status,
        reconciliation_messages=(
            ()
            if reconciliation_status == IB_RECONCILIATION_STATUS_RECONCILED
            else ("Synthetic leg reconciliation warning",)
        ),
    )


def build_reconciled_snapshot(
    *,
    include_second_leg: bool = True,
    broker_position_present: bool = True,
) -> IBPositionGroupSnapshot:
    """Build one reconciled Virtual FX group with one or two OPEN legs."""
    legs = [
        build_leg(
            position_uid="11111111-1111-1111-1111-111111111111",
            trade_uid="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            side="BUY",
            volume=1000.0,
            entry_price=1.145,
            stop_loss=1.140,
            take_profit=1.155,
        )
    ]

    if include_second_leg:
        legs.append(
            build_leg(
                position_uid="22222222-2222-2222-2222-222222222222",
                trade_uid="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                side="BUY",
                volume=2000.0,
                entry_price=1.149,
                stop_loss=1.141,
                take_profit=1.158,
            )
        )

    broker_side = "BUY" if broker_position_present else "UNKNOWN"
    broker_volume = sum(leg.volume for leg in legs) if broker_position_present else 0.0
    broker_entry_price = 1.14766667 if broker_position_present else None

    group = IBPositionGroup(
        broker_position_id="IB:DUM513747:EURUSD",
        account_id="DUM513747",
        symbol_name="EURUSD",
        broker_position_present=broker_position_present,
        broker_side=broker_side,
        broker_volume=broker_volume,
        broker_signed_volume=broker_volume,
        broker_entry_price=broker_entry_price,
        broker_position_kind=IB_BROKER_POSITION_KIND_VIRTUAL_FX,
        currency="USD",
        current_price=1.151,
        unrealized_pnl=14.0,
        opened_utc="2026-07-20T12:00:00+00:00",
        group_mode=IB_POSITION_GROUP_MODE_LGE_VIRTUAL_LEGS,
        reconciliation_status=IB_RECONCILIATION_STATUS_RECONCILED,
        reconciliation_messages=(),
        legs=legs,
    )
    return IBPositionGroupSnapshot(
        captured_utc="2026-07-20T12:05:00+00:00",
        complete=True,
        groups=[group],
        unmapped_protective_order_ids=[],
    )


def build_blocked_snapshot() -> IBPositionGroupSnapshot:
    """Build one blocked LGE group and one normal NET_ONLY group."""
    blocked_leg = build_leg(
        position_uid="33333333-3333-3333-3333-333333333333",
        trade_uid="cccccccc-cccc-cccc-cccc-cccccccccccc",
        side="SELL",
        volume=1000.0,
        entry_price=1.152,
        stop_loss=1.160,
        take_profit=1.140,
        reconciliation_status=IB_RECONCILIATION_STATUS_BLOCKED,
    )
    blocked_group = IBPositionGroup(
        broker_position_id="IB:DUM513747:EURUSD",
        account_id="DUM513747",
        symbol_name="EURUSD",
        broker_position_present=True,
        broker_side="SELL",
        broker_volume=1000.0,
        broker_signed_volume=-1000.0,
        broker_entry_price=1.152,
        broker_position_kind=IB_BROKER_POSITION_KIND_VIRTUAL_FX,
        currency="USD",
        current_price=1.150,
        unrealized_pnl=2.0,
        group_mode=IB_POSITION_GROUP_MODE_LGE_VIRTUAL_LEGS,
        reconciliation_status=IB_RECONCILIATION_STATUS_BLOCKED,
        reconciliation_messages=("Synthetic group block",),
        legs=[blocked_leg],
    )
    net_group = IBPositionGroup(
        broker_position_id="IB:DUM513747:GBPUSD",
        account_id="DUM513747",
        symbol_name="GBPUSD",
        broker_position_present=True,
        broker_side="BUY",
        broker_volume=1000.0,
        broker_signed_volume=1000.0,
        broker_entry_price=1.350,
        broker_position_kind=IB_BROKER_POSITION_KIND_NET,
        currency="USD",
        current_price=1.352,
        unrealized_pnl=2.0,
        stop_loss=1.340,
        take_profit=1.370,
        opened_utc="2026-07-20T11:00:00+00:00",
        group_mode=IB_POSITION_GROUP_MODE_NET_ONLY,
        reconciliation_status=IB_RECONCILIATION_STATUS_UNRECONCILED,
        reconciliation_messages=("Broker net position has no LGE virtual legs",),
        legs=[],
    )
    return IBPositionGroupSnapshot(
        captured_utc="2026-07-20T12:05:00+00:00",
        complete=True,
        groups=[blocked_group, net_group],
        unmapped_protective_order_ids=[999],
    )


class TrackingGroupRuntimeEngine:
    """Synthetic RuntimeEngine with exact leg modify and close tracking."""

    def __init__(self, snapshot: IBPositionGroupSnapshot) -> None:
        self.snapshot = deepcopy(snapshot)
        self.group_calls = 0
        self.pending_open_recovery_calls = 0
        self.modify_calls: list[dict[str, Any]] = []
        self.close_calls: list[str] = []

    @staticmethod
    def get_active_broker() -> str:
        return "IB"

    def get_active_broker_position_groups(self) -> IBPositionGroupSnapshot:
        self.group_calls += 1
        return deepcopy(self.snapshot)

    def recover_pending_ib_manual_market_order_opens(self) -> dict[str, Any]:
        """Track pre-refresh delayed Open recovery integration."""
        self.pending_open_recovery_calls += 1
        return {
            "pending": 0,
            "adopted": [],
            "recovered": [],
            "unresolved": [],
        }

    def modify_runtime_position_leg_sl_tp(
        self,
        position_uid: str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> dict[str, Any]:
        self.modify_calls.append(
            {
                "position_uid": position_uid,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
            }
        )
        leg = self._find_leg(position_uid)
        leg.stop_loss = stop_loss
        leg.take_profit = take_profit
        return {
            "position_uid": position_uid,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "position_group_snapshot": deepcopy(self.snapshot),
            "post_modify_group_reconciliation_settled": True,
        }

    def close_runtime_position_leg(
        self,
        position_uid: str,
    ) -> dict[str, Any]:
        self.close_calls.append(position_uid)

        for group in self.snapshot.groups:
            for index, leg in enumerate(group.legs):
                if leg.position_uid != position_uid:
                    continue

                group.broker_volume -= leg.volume
                group.broker_signed_volume -= leg.signed_volume
                del group.legs[index]
                return {
                    "closed": True,
                    "position_uid": position_uid,
                }

        raise RuntimeError("Synthetic virtual leg was not found")

    @staticmethod
    def modify_active_broker_position_sl_tp(
        broker_position_id: str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> dict[str, Any]:
        return {
            "broker_position_id": broker_position_id,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
        }

    @staticmethod
    def close_active_broker_position(
        broker_position_id: str,
    ) -> dict[str, Any]:
        return {
            "closed": True,
            "broker_position_id": broker_position_id,
        }

    def _find_leg(self, position_uid: str) -> IBVirtualPositionLeg:
        for group in self.snapshot.groups:
            for leg in group.legs:
                if leg.position_uid == position_uid:
                    return leg

        raise RuntimeError("Synthetic virtual leg was not found")
