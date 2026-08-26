# -*- coding: utf-8 -*-
"""Persistent read-only IB CASH Forex external exposure facts and guards."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from engine.broker_position import (
    POSITION_SIDE_BUY,
    POSITION_SIDE_SELL,
    POSITION_SIDE_UNKNOWN,
)
from engine.runtime_constants import IB_POSITION_QUANTITY_ABS_TOLERANCE

IB_FX_EXTERNAL_EXPOSURE_CONFIRMED = "CONFIRMED"
IB_FX_EXTERNAL_EXPOSURE_STALE = "STALE"
IB_FX_EXTERNAL_EXPOSURE_CLEARED = "CLEARED"
IB_FX_EXTERNAL_EXPOSURE_ACTIVE_STATUSES = {
    IB_FX_EXTERNAL_EXPOSURE_CONFIRMED,
    IB_FX_EXTERNAL_EXPOSURE_STALE,
}

IB_FX_GUARD_MODE_REPLAY = "REPLAY"
IB_FX_GUARD_MODE_LIVE_READ_ONLY = "LIVE_READ_ONLY"
IB_FX_GUARD_MODE_PAPER = "PAPER"
IB_FX_GUARD_MODE_LIVE = "LIVE"
IB_FX_GUARD_NON_EXECUTING_MODES = {
    IB_FX_GUARD_MODE_REPLAY,
    IB_FX_GUARD_MODE_LIVE_READ_ONLY,
}
IB_FX_GUARD_EXECUTING_MODES = {
    IB_FX_GUARD_MODE_PAPER,
    IB_FX_GUARD_MODE_LIVE,
}

IB_FX_EXECUTION_POLICY_LGE_EXCLUSIVE = "LGE_EXCLUSIVE"
IB_FX_GUARD_ALLOWED = "IB_FX_EXTERNAL_EXPOSURE_ALLOWED"
IB_FX_GUARD_BLOCKED = "IB_FX_EXTERNAL_EXPOSURE_BLOCKED"
IB_FX_GUARD_EVIDENCE_UNAVAILABLE = "IB_FX_EXTERNAL_EVIDENCE_UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class IBFxExternalExposure:
    """One persisted broker-only CASH Forex exposure observation."""

    broker_position_id: str
    account_id: str
    symbol_name: str
    signed_volume: float
    evidence_status: str
    last_confirmed_utc: str
    last_observed_utc: str
    updated_utc: str

    @property
    def is_active(self) -> bool:
        return bool(
            self.evidence_status in IB_FX_EXTERNAL_EXPOSURE_ACTIVE_STATUSES
            and abs(self.signed_volume)
            > IB_POSITION_QUANTITY_ABS_TOLERANCE
        )

    @property
    def confirmation_required(self) -> bool:
        return self.evidence_status == IB_FX_EXTERNAL_EXPOSURE_STALE

    @property
    def side(self) -> str:
        if self.signed_volume > 0.0:
            return POSITION_SIDE_BUY
        if self.signed_volume < 0.0:
            return POSITION_SIDE_SELL
        return POSITION_SIDE_UNKNOWN

    @property
    def volume(self) -> float:
        return abs(self.signed_volume)


@dataclass(frozen=True, slots=True)
class IBFxExternalExposureGuardDecision:
    """Pure symbol-scoped decision for future IB Paper/Live execution."""

    allowed: bool
    reason_code: str
    reason_text: str
    matching_exposure: IBFxExternalExposure | None = None


class IBFxExternalExposureExecutionBlockedError(RuntimeError):
    """Fail-closed LGE EXCLUSIVE rejection before Trade persistence."""

    def __init__(self, decision: IBFxExternalExposureGuardDecision) -> None:
        self.decision = decision
        self.reason_code = decision.reason_code
        self.matching_exposure = decision.matching_exposure
        super().__init__(decision.reason_text)


def evaluate_ib_fx_external_exposure_guard(
    exposures: Iterable[IBFxExternalExposure],
    *,
    account_id: str,
    symbol_name: str,
    runtime_mode: str,
) -> IBFxExternalExposureGuardDecision:
    """Apply LGE EXCLUSIVE to one exact IB account and Forex symbol."""
    account = str(account_id or "").strip()
    symbol = str(symbol_name or "").strip().upper()
    mode = str(runtime_mode or "").strip().upper()

    if mode in IB_FX_GUARD_NON_EXECUTING_MODES:
        return IBFxExternalExposureGuardDecision(
            allowed=True,
            reason_code=IB_FX_GUARD_ALLOWED,
            reason_text=(
                f"{mode} does not send broker orders; external IB FX "
                "exposure is monitoring-only"
            ),
        )

    matching = next(
        (
            exposure
            for exposure in exposures
            if exposure.is_active
            and exposure.account_id == account
            and exposure.symbol_name == symbol
        ),
        None,
    )

    if matching is None:
        return IBFxExternalExposureGuardDecision(
            allowed=True,
            reason_code=IB_FX_GUARD_ALLOWED,
            reason_text=(
                "No active external IB FX exposure exists for the exact "
                f"account and symbol: account={account}, symbol={symbol}"
            ),
        )

    if mode in IB_FX_GUARD_EXECUTING_MODES:
        status_suffix = (
            "; broker confirmation is required"
            if matching.confirmation_required
            else ""
        )
        return IBFxExternalExposureGuardDecision(
            allowed=False,
            reason_code=IB_FX_GUARD_BLOCKED,
            reason_text=(
                f"{IB_FX_EXECUTION_POLICY_LGE_EXCLUSIVE}: External IB FX "
                "exposure blocks LGE execution for the same account and "
                "symbol before Trade persistence and before the execution "
                "request: "
                f"account={account}, symbol={symbol}, "
                f"signed_volume={matching.signed_volume}, "
                f"evidence={matching.evidence_status}{status_suffix}"
            ),
            matching_exposure=matching,
        )

    return IBFxExternalExposureGuardDecision(
        allowed=False,
        reason_code=IB_FX_GUARD_BLOCKED,
        reason_text=f"Unsupported IB FX execution guard mode: {mode}",
        matching_exposure=matching,
    )
