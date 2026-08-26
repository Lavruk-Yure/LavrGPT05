# -*- coding: utf-8 -*-
"""Локалізоване read-only представлення WSP signal records.

Модуль формує таблицю/tooltip без зміни immutable evidence. RoadMap101 додає
видимий Alligator regime разом із causal фазою STARTING/ACTIVE/ENDING та
diagnostic метрики. Для SAME_TIMEFRAME STARTING/ENDING можуть бути причиною
REJECT phase-gate. Той самий localized detail використовується для Signals
tooltip і читабельного SIGNAL block у Journal. RoadMap102 додає
MACD Quality result, explicit phase/active_age, causal t-2/t-1/t та
Candidate F terminal lifecycle без зміни immutable trade evidence. RoadMap102/3B
додає короткий виділений summary перед повною технічною діагностикою. RoadMap102/3D
залишає у Signals tooltip лише коротке повідомлення, а повний detail з raw evidence
зберігає для Journal. RoadMap102/3E розбиває довгу причину tooltip по реченнях,
щоб hover-підказка читалась без горизонтально довгого рядка. RoadMap102/3G
розділяє RELEASE-підтвердження Alligator, structural guard і фінальне рішення,
щоб RELEASE не сприймався як остаточний ALLOW угоди.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from core.workspace_signal import WorkspaceSignalRecord

TranslationCallback = Callable[[str, str], str]

_ALLIGATOR_REGIME_LABELS: dict[str, tuple[str, str]] = {
    "ALLIGATOR_REGIME_FLAT": (
        "AlgorithmWorkspaceAlligatorRegime.flat",
        "Flat",
    ),
    "ALLIGATOR_REGIME_TREND_UP": (
        "AlgorithmWorkspaceAlligatorRegime.trendUp",
        "Trend up",
    ),
    "ALLIGATOR_REGIME_TREND_DOWN": (
        "AlgorithmWorkspaceAlligatorRegime.trendDown",
        "Trend down",
    ),
    "ALLIGATOR_REGIME_WARMUP": (
        "AlgorithmWorkspaceAlligatorRegime.warmup",
        "Warm-up",
    ),
    "ALLIGATOR_REGIME_DISABLED": (
        "AlgorithmWorkspaceAlligatorRegime.disabled",
        "Disabled",
    ),
}

_ALLIGATOR_REGIME_PHASE_LABELS: dict[
    tuple[str, str], tuple[str, str]
] = {
    (
        "ALLIGATOR_REGIME_TREND_UP",
        "ALLIGATOR_REGIME_PHASE_STARTING",
    ): (
        "AlgorithmWorkspaceAlligatorRegime.trendUpStarting",
        "Trend up starting",
    ),
    (
        "ALLIGATOR_REGIME_TREND_UP",
        "ALLIGATOR_REGIME_PHASE_ENDING",
    ): (
        "AlgorithmWorkspaceAlligatorRegime.trendUpEnding",
        "Trend up ending",
    ),
    (
        "ALLIGATOR_REGIME_TREND_DOWN",
        "ALLIGATOR_REGIME_PHASE_STARTING",
    ): (
        "AlgorithmWorkspaceAlligatorRegime.trendDownStarting",
        "Trend down starting",
    ),
    (
        "ALLIGATOR_REGIME_TREND_DOWN",
        "ALLIGATOR_REGIME_PHASE_ENDING",
    ): (
        "AlgorithmWorkspaceAlligatorRegime.trendDownEnding",
        "Trend down ending",
    ),
}

_ALLIGATOR_PHASE_LABELS: dict[str, tuple[str, str]] = {
    "ALLIGATOR_REGIME_PHASE_STARTING": (
        "AlgorithmWorkspaceAlligatorPhase.starting",
        "Starting",
    ),
    "ALLIGATOR_REGIME_PHASE_ACTIVE": (
        "AlgorithmWorkspaceAlligatorPhase.active",
        "Active",
    ),
    "ALLIGATOR_REGIME_PHASE_ENDING": (
        "AlgorithmWorkspaceAlligatorPhase.ending",
        "Ending",
    ),
}

_CANDIDATE_F_LIFECYCLE_ACTION_LABELS: dict[str, tuple[str, str]] = {
    "ARMED": ("AlgorithmWorkspaceCandidateFLifecycle.armed", "ARMED"),
    "RELEASE": ("AlgorithmWorkspaceCandidateFLifecycle.release", "RELEASE"),
    "CANCEL": ("AlgorithmWorkspaceCandidateFLifecycle.cancel", "CANCEL"),
    "EXPIRE": ("AlgorithmWorkspaceCandidateFLifecycle.expire", "EXPIRE"),
}

_CANDIDATE_F_LIFECYCLE_REASON_LABELS: dict[str, tuple[str, str]] = {
    "OPPOSITE_MACD": (
        "AlgorithmWorkspaceCandidateFLifecycle.oppositeMacd",
        "Opposite MACD signal cancelled the armed candidate.",
    ),
    "MACD_INVALID": (
        "AlgorithmWorkspaceCandidateFLifecycle.macdInvalid",
        "MACD relation became invalid before release.",
    ),
    "OPPOSITE_ACTIVE_ALLIGATOR": (
        "AlgorithmWorkspaceCandidateFLifecycle.oppositeActiveAlligator",
        "Opposite ACTIVE Alligator cancelled the armed candidate.",
    ),
    "TTL_EXPIRED": (
        "AlgorithmWorkspaceCandidateFLifecycle.ttlExpired",
        "ARMED TTL expired before confirmation.",
    ),
    "ALLIGATOR_DEFERRED_RELEASE": (
        "AlgorithmWorkspaceCandidateFLifecycle.releasedByAlligator",
        "Alligator confirmation released the armed candidate.",
    ),
}

_MACD_QUALITY_PASS_CODES = {"MACD_CROSS_ACCEPTED"}
_MACD_QUALITY_REJECT_CODES = {
    "MACD_EXTREMUM_NOT_FOUND",
    "MACD_EXTREMUM_TOO_WEAK",
    "MACD_EXTREMUM_DISTANCE_TOO_SMALL",
    "MACD_CROSS_TOO_FLAT",
}

_STRUCTURAL_GUARD_CODES: dict[str, str] = {
    "ALLIGATOR_OPENING_COLLAPSE_REJECT": "OPENING_COLLAPSE",
    "ALLIGATOR_WEAK_OPENING_REJECT": "WEAK_OPENING",
    "ALLIGATOR_VOLATILITY_SPIKE_DETERIORATION_REJECT": (
        "VOLATILITY_SPIKE_WITH_DETERIORATION"
    ),
    "ALLIGATOR_OVEREXTENDED_TREND_REJECT": "OVEREXTENDED_TREND",
}

_SOURCE_REASON_LABELS: dict[str, tuple[str, str]] = {
    "MACD_CLASSIC_CROSS": (
        "AlgorithmWorkspaceSignalReason.macdClassicCross",
        "MACD classic crossover.",
    ),
    "MACD_CLASSIC_CROSS_EXTENDED_BASELINE": (
        "AlgorithmWorkspaceSignalReason.macdExtendedCross",
        "MACD crossover with extended baseline mode.",
    ),
    "MACD_CROSS_ACCEPTED": (
        "AlgorithmWorkspaceSignalReason.macdQualityAccepted",
        "MACD crossover passed the quality criteria.",
    ),
    "MACD_EXTREMUM_NOT_FOUND": (
        "AlgorithmWorkspaceSignalReason.macdExtremumNotFound",
        "MACD crossover has no suitable previous histogram extremum.",
    ),
    "MACD_EXTREMUM_TOO_WEAK": (
        "AlgorithmWorkspaceSignalReason.macdExtremumTooWeak",
        "Previous MACD histogram extremum is too weak.",
    ),
    "MACD_EXTREMUM_DISTANCE_TOO_SMALL": (
        "AlgorithmWorkspaceSignalReason.macdExtremumDistanceTooSmall",
        "MACD extremum-to-crossover distance is too small.",
    ),
    "MACD_CROSS_TOO_FLAT": (
        "AlgorithmWorkspaceSignalReason.macdCrossTooFlat",
        "MACD and Signal cross at too small an angle.",
    ),
    "MACD_DEFERRED_RELEASE": (
        "AlgorithmWorkspaceSignalReason.macdDeferredRelease",
        "Previously armed MACD signal was released after Alligator confirmation.",
    ),
}

_FILTER_REASON_LABELS: dict[str, tuple[str, str]] = {
    "ALLIGATOR_DISABLED_BYPASS": (
        "AlgorithmWorkspaceSignalReason.alligatorDisabled",
        "Alligator filter is disabled.",
    ),
    "ALLIGATOR_SAME_TIMEFRAME_BUY_ALLOW": (
        "AlgorithmWorkspaceSignalReason.alligatorSameBuyAllow",
        "Alligator on the signal timeframe confirms BUY.",
    ),
    "ALLIGATOR_SAME_TIMEFRAME_SELL_ALLOW": (
        "AlgorithmWorkspaceSignalReason.alligatorSameSellAllow",
        "Alligator on the signal timeframe confirms SELL.",
    ),
    "ALLIGATOR_SAME_TIMEFRAME_BUY_REJECT": (
        "AlgorithmWorkspaceSignalReason.alligatorSameBuyReject",
        "Alligator on the signal timeframe does not confirm BUY.",
    ),
    "ALLIGATOR_SAME_TIMEFRAME_SELL_REJECT": (
        "AlgorithmWorkspaceSignalReason.alligatorSameSellReject",
        "Alligator on the signal timeframe does not confirm SELL.",
    ),
    "ALLIGATOR_SAME_TIMEFRAME_NOT_READY": (
        "AlgorithmWorkspaceSignalReason.alligatorSameNotReady",
        "Alligator warm-up is incomplete.",
    ),
    "ALLIGATOR_SAME_TIMEFRAME_BUY_STARTING_REJECT": (
        "AlgorithmWorkspaceSignalReason.alligatorSameBuyStartingReject",
        "Alligator trend is still starting and rejects BUY.",
    ),
    "ALLIGATOR_SAME_TIMEFRAME_SELL_STARTING_REJECT": (
        "AlgorithmWorkspaceSignalReason.alligatorSameSellStartingReject",
        "Alligator trend is still starting and rejects SELL.",
    ),
    "ALLIGATOR_SAME_TIMEFRAME_BUY_ENDING_REJECT": (
        "AlgorithmWorkspaceSignalReason.alligatorSameBuyEndingReject",
        "Alligator trend is ending and rejects BUY.",
    ),
    "ALLIGATOR_SAME_TIMEFRAME_SELL_ENDING_REJECT": (
        "AlgorithmWorkspaceSignalReason.alligatorSameSellEndingReject",
        "Alligator trend is ending and rejects SELL.",
    ),
    "ALLIGATOR_HIGHER_1_BUY_ALLOW": (
        "AlgorithmWorkspaceSignalReason.alligatorHigher1BuyAllow",
        "Alligator HIGHER_1 confirms BUY.",
    ),
    "ALLIGATOR_HIGHER_1_SELL_ALLOW": (
        "AlgorithmWorkspaceSignalReason.alligatorHigher1SellAllow",
        "Alligator HIGHER_1 confirms SELL.",
    ),
    "ALLIGATOR_HIGHER_1_BUY_REJECT": (
        "AlgorithmWorkspaceSignalReason.alligatorHigher1BuyReject",
        "Alligator HIGHER_1 does not confirm BUY.",
    ),
    "ALLIGATOR_HIGHER_1_SELL_REJECT": (
        "AlgorithmWorkspaceSignalReason.alligatorHigher1SellReject",
        "Alligator HIGHER_1 does not confirm SELL.",
    ),
    "ALLIGATOR_HIGHER_1_NOT_READY": (
        "AlgorithmWorkspaceSignalReason.alligatorHigher1NotReady",
        "Alligator HIGHER_1 warm-up is incomplete.",
    ),
    "ALLIGATOR_HIGHER_2_BUY_ALLOW": (
        "AlgorithmWorkspaceSignalReason.alligatorHigher2BuyAllow",
        "Alligator HIGHER_2 confirms BUY.",
    ),
    "ALLIGATOR_HIGHER_2_SELL_ALLOW": (
        "AlgorithmWorkspaceSignalReason.alligatorHigher2SellAllow",
        "Alligator HIGHER_2 confirms SELL.",
    ),
    "ALLIGATOR_HIGHER_2_BUY_REJECT": (
        "AlgorithmWorkspaceSignalReason.alligatorHigher2BuyReject",
        "Alligator HIGHER_2 does not confirm BUY.",
    ),
    "ALLIGATOR_HIGHER_2_SELL_REJECT": (
        "AlgorithmWorkspaceSignalReason.alligatorHigher2SellReject",
        "Alligator HIGHER_2 does not confirm SELL.",
    ),
    "ALLIGATOR_HIGHER_2_NOT_READY": (
        "AlgorithmWorkspaceSignalReason.alligatorHigher2NotReady",
        "Alligator HIGHER_2 warm-up is incomplete.",
    ),
    "ALLIGATOR_DEFERRED_ARMED": (
        "AlgorithmWorkspaceSignalReason.alligatorDeferredArmed",
        "MACD signal is armed while the matching Alligator trend is starting.",
    ),
    "ALLIGATOR_DEFERRED_RELEASE": (
        "AlgorithmWorkspaceSignalReason.alligatorDeferredRelease",
        "Alligator became ACTIVE and released the armed MACD signal.",
    ),
    "ALLIGATOR_OPENING_COLLAPSE_REJECT": (
        "AlgorithmWorkspaceSignalReason.alligatorOpeningCollapseReject",
        "Alligator opening is collapsing too quickly; signal rejected.",
    ),
    "ALLIGATOR_WEAK_OPENING_REJECT": (
        "AlgorithmWorkspaceSignalReason.alligatorWeakOpeningReject",
        "Alligator is ACTIVE too early with insufficient opening; signal rejected.",
    ),
    "ALLIGATOR_VOLATILITY_SPIKE_DETERIORATION_REJECT": (
        "AlgorithmWorkspaceSignalReason.alligatorVolatilitySpikeReject",
        "Volatility spike coincides with Alligator deterioration; signal rejected.",
    ),
    "ALLIGATOR_OVEREXTENDED_TREND_REJECT": (
        "AlgorithmWorkspaceSignalReason.alligatorOverextendedReject",
        "Alligator trend is overextended; signal rejected.",
    ),
}

_RUNTIME_REASON_LABELS: dict[str, tuple[str, str]] = {
    "runtime is stopped": (
        "AlgorithmWorkspaceSignalReason.runtimeStopped",
        "Runtime is stopped.",
    ),
    "market data is not loaded": (
        "AlgorithmWorkspaceSignalReason.marketDataNotLoaded",
        "Market data is not loaded.",
    ),
    "waiting for acceptable spread": (
        "AlgorithmWorkspaceSignalReason.waitingAcceptableSpread",
        "Waiting for an acceptable spread.",
    ),
    "warmup incomplete": (
        "AlgorithmWorkspaceSignalReason.warmupIncomplete",
        "Warm-up is incomplete.",
    ),
    "waiting for live spread": (
        "AlgorithmWorkspaceSignalReason.waitingLiveSpread",
        "Waiting for the first live spread.",
    ),
    "waiting for fresh live spread": (
        "AlgorithmWorkspaceSignalReason.waitingFreshSpread",
        "Waiting for a fresh live spread.",
    ),
    "waiting for broker reconnect": (
        "AlgorithmWorkspaceSignalReason.waitingBrokerReconnect",
        "Waiting for broker reconnection.",
    ),
    "runtime error": (
        "AlgorithmWorkspaceSignalReason.runtimeError",
        "Runtime error.",
    ),
    "startup guard is not ready": (
        "AlgorithmWorkspaceSignalReason.startupGuardNotReady",
        "Startup guard is not ready.",
    ),
    "external ib fx exposure safety hold": (
        "AlgorithmWorkspaceSignalReason.externalExposureSafetyHold",
        "Signals are paused by the external IB FX exposure safety hold.",
    ),
    "spread too wide": (
        "AlgorithmWorkspaceSignalReason.spreadTooWide",
        "Spread is too wide.",
    ),
    "accepted for signal display only": (
        "AlgorithmWorkspaceSignalReason.manualDisplayOnly",
        "Signal accepted for display only in MANUAL control.",
    ),
    "accepted; user confirmation is required": (
        "AlgorithmWorkspaceSignalReason.semiConfirmationRequired",
        "Signal accepted; user confirmation is required in SEMI control.",
    ),
    "accepted; automatic execution is disabled in roadmap95": (
        "AlgorithmWorkspaceSignalReason.autoAccepted",
        "Signal accepted by AUTO control.",
    ),
    "signal was rejected before risk evaluation": (
        "AlgorithmWorkspaceSignalReason.rejectedBeforeRisk",
        "Signal was rejected before risk evaluation.",
    ),
}

_TOOLTIP_ENTRIES: dict[str, str] = {
    "AlgorithmWorkspaceSignalTooltip.reason": "Reason",
    "AlgorithmWorkspaceSignalTooltip.signalTime": "Signal time",
    "AlgorithmWorkspaceSignalTooltip.macdReason": "MACD reason",
    "AlgorithmWorkspaceSignalTooltip.macdState": "MACD state",
    "AlgorithmWorkspaceSignalTooltip.macdProfile": "MACD profile",
    "AlgorithmWorkspaceSignalTooltip.macdQualityResult": "MACD Quality result",
    "AlgorithmWorkspaceSignalTooltip.alligatorReason": "Alligator reason",
    "AlgorithmWorkspaceSignalTooltip.alligatorState": "Alligator state",
    "AlgorithmWorkspaceSignalTooltip.alligatorObservationState": (
        "Alligator observation state"
    ),
    "AlgorithmWorkspaceSignalTooltip.alligatorRegime": "Alligator regime",
    "AlgorithmWorkspaceSignalTooltip.alligatorPhase": "Alligator phase",
    "AlgorithmWorkspaceSignalTooltip.alligatorActiveAge": "Alligator active age",
    "AlgorithmWorkspaceSignalTooltip.alligatorNormalizedSlope": (
        "Normalized Alligator slope"
    ),
    "AlgorithmWorkspaceSignalTooltip.alligatorNormalizedOpening": (
        "Normalized Alligator opening"
    ),
    "AlgorithmWorkspaceSignalTooltip.alligatorMode": "Alligator mode",
    "AlgorithmWorkspaceSignalTooltip.alligatorTimeframe": "Alligator timeframe",
    "AlgorithmWorkspaceSignalTooltip.alligatorProfile": "Alligator profile",
    "AlgorithmWorkspaceSignalTooltip.observationTime": "Observation time",
    "AlgorithmWorkspaceSignalTooltip.availableAt": "Available at",
    "AlgorithmWorkspaceSignalTooltip.alligatorT2": "Alligator t-2",
    "AlgorithmWorkspaceSignalTooltip.alligatorT1": "Alligator t-1",
    "AlgorithmWorkspaceSignalTooltip.alligatorT": "Alligator t",
    "AlgorithmWorkspaceSignalTooltip.alligatorDecision": "Alligator decision",
    "AlgorithmWorkspaceSignalTooltip.finalDecision": "Final decision",
    "AlgorithmWorkspaceSignalTooltip.candidateFLifecycle": "Candidate F lifecycle",
    "AlgorithmWorkspaceSignalTooltip.lifecycleReason": "Lifecycle reason",
    "AlgorithmWorkspaceSignalTooltip.lifecycleTime": "Lifecycle time",
    "AlgorithmWorkspaceSignalTooltip.lifecycleDelayBars": "Lifecycle delay, bars",
    "AlgorithmWorkspaceSignalTooltip.lifecycleSnapshot": "Lifecycle snapshot",
    "AlgorithmWorkspaceSignalTooltip.technicalCodes": "Technical reason codes",
    "AlgorithmWorkspaceSignalTooltip.diagnosticReason": "Diagnostic reason",
    "AlgorithmWorkspaceSignalTooltip.profileRevision": "revision",
    "AlgorithmWorkspaceSignalSummary.header": (
        "************************************ DECISION SUMMARY "
        "************************************"
    ),
    "AlgorithmWorkspaceSignalSummary.footer": (
        "************************************ END OF SUMMARY "
        "************************************"
    ),
    "AlgorithmWorkspaceSignalSummary.signal": "Signal",
    "AlgorithmWorkspaceSignalSummary.macdQuality": "MACD Quality",
    "AlgorithmWorkspaceSignalSummary.alligator": "Alligator",
    "AlgorithmWorkspaceSignalSummary.alligatorStrength": "Alligator strength",
    "AlgorithmWorkspaceSignalSummary.lifecycle": "Candidate F",
    "AlgorithmWorkspaceSignalSummary.lifecycleSnapshot": "Lifecycle state",
    "AlgorithmWorkspaceSignalSummary.lifecycleReason": "Lifecycle reason",
    "AlgorithmWorkspaceSignalSummary.alligatorConfirmation": (
        "Alligator confirmation"
    ),
    "AlgorithmWorkspaceSignalSummary.confirmationPassedRelease": (
        "PASSED → RELEASE"
    ),
    "AlgorithmWorkspaceSignalSummary.structuralGuard": "Structural guard",
    "AlgorithmWorkspaceSignalSummary.filter": "Filter / guard",
    "AlgorithmWorkspaceSignalSummary.finalDecision": "Final decision",
    "AlgorithmWorkspaceSignalSummary.decision": "Decision",
    "AlgorithmWorkspaceSignalSummary.technicalHeader": (
        "*** TECHNICAL DIAGNOSTICS ***"
    ),
    "AlgorithmWorkspaceSignalReason.riskRejected": (
        "Signal was rejected by risk limits."
    ),
}


@dataclass(frozen=True, slots=True)
class WorkspaceSignalPresentation:
    """Локалізовані reason, короткий tooltip і повний diagnostic detail."""

    reason_text: str
    tooltip_text: str
    detail_text: str


def workspace_signal_i18n_entries() -> dict[str, str]:
    """Return all translation keys used by signal presentation."""
    entries = dict(_TOOLTIP_ENTRIES)
    for mapping in (
        _SOURCE_REASON_LABELS,
        _FILTER_REASON_LABELS,
        _RUNTIME_REASON_LABELS,
        _ALLIGATOR_REGIME_LABELS,
        _ALLIGATOR_REGIME_PHASE_LABELS,
        _ALLIGATOR_PHASE_LABELS,
        _CANDIDATE_F_LIFECYCLE_ACTION_LABELS,
        _CANDIDATE_F_LIFECYCLE_REASON_LABELS,
    ):
        for key, fallback in mapping.values():
            entries[key] = fallback
    return entries


def workspace_signal_reason_code_text(
    code: str | None,
    tr: TranslationCallback,
) -> str:
    """Return localized source/filter reason text for one technical code."""
    normalized = str(code or "").strip().upper()
    if not normalized:
        return "—"
    for labels in (_SOURCE_REASON_LABELS, _FILTER_REASON_LABELS):
        translated = _translated_code(normalized, labels, tr)
        if translated is not None:
            return translated
    return normalized


def workspace_signal_alligator_regime_text(
    record: WorkspaceSignalRecord,
    tr: TranslationCallback,
) -> str:
    """Return localized causal Alligator regime/phase for one signal."""
    context = record.filter_context
    if context is None or context.regime is None:
        return "—"

    phase_key = (
        context.regime,
        context.regime_phase or "",
    )
    phase_label = _ALLIGATOR_REGIME_PHASE_LABELS.get(phase_key)
    if phase_label is not None:
        key, fallback = phase_label
        return tr(key, fallback)

    translated = _translated_code(
        context.regime,
        _ALLIGATOR_REGIME_LABELS,
        tr,
    )
    return translated or context.regime


def workspace_signal_alligator_phase_text(
    record: WorkspaceSignalRecord,
    tr: TranslationCallback,
) -> str:
    """Повернути локалізовану явну фазу Alligator для діагностики."""
    context = record.filter_context
    if context is None or context.regime_phase is None:
        return "—"
    translated = _translated_code(
        context.regime_phase,
        _ALLIGATOR_PHASE_LABELS,
        tr,
    )
    return translated or context.regime_phase


def workspace_signal_macd_quality_result_text(
    record: WorkspaceSignalRecord,
) -> str:
    """Повернути PASS/REJECT лише для reason codes MACD Quality."""
    code = str(record.source_reason_code or "").strip().upper()
    if code in _MACD_QUALITY_PASS_CODES or code == "MACD_DEFERRED_RELEASE":
        return "PASS"
    if code in _MACD_QUALITY_REJECT_CODES:
        return "REJECT"
    return "—"


def workspace_signal_timeframe_mode_text(record: WorkspaceSignalRecord) -> str:
    """Return compact signal/filter timeframe evidence for the table."""
    context = record.filter_context
    if context is None:
        return record.timeframe
    if context.timeframe == record.timeframe:
        return f"{record.timeframe} | {context.mode}"
    return f"{record.timeframe} | {context.mode} -> {context.timeframe}"


def workspace_signal_profile_revision_text(record: WorkspaceSignalRecord) -> str:
    """Return compact source/filter profile revisions without hiding identity."""
    parts: list[str] = []
    if record.source_profile_revision is not None:
        parts.append(f"MACD r{record.source_profile_revision}")
    if record.filter_context is not None:
        parts.append(f"Alligator r{record.filter_context.profile_revision}")
    return " / ".join(parts) or "—"


def build_workspace_signal_presentation(
    record: WorkspaceSignalRecord,
    tr: TranslationCallback,
) -> WorkspaceSignalPresentation:
    """Build localized user text without altering immutable signal evidence."""
    runtime_reason = _translated_runtime_reason(record.reason, tr)
    source_reason = _translated_code(
        record.source_reason_code,
        _SOURCE_REASON_LABELS,
        tr,
    )
    filter_reason = _translated_code(
        record.filter_reason_code,
        _FILTER_REASON_LABELS,
        tr,
    )

    if runtime_reason is not None:
        reason_text = runtime_reason
    elif record.risk_reason_code:
        reason_text = tr(
            "AlgorithmWorkspaceSignalReason.riskRejected",
            "Signal was rejected by risk limits.",
        )
    else:
        user_parts = [part for part in (source_reason, filter_reason) if part]
        reason_text = " ".join(user_parts) or record.reason

    lifecycle_suffix = _candidate_f_lifecycle_reason_suffix(record, tr)
    if lifecycle_suffix:
        reason_text = f"{reason_text} {lifecycle_suffix}"

    summary_lines = _build_compact_summary_lines(
        record,
        tr,
        filter_reason=filter_reason,
    )
    tooltip_lines = _build_short_tooltip_lines(
        record,
        tr,
        reason_text=reason_text,
    )

    revision_label = tr(
        "AlgorithmWorkspaceSignalTooltip.profileRevision",
        "revision",
    )
    lines = [
        *summary_lines,
        "",
        tr(
            "AlgorithmWorkspaceSignalSummary.technicalHeader",
            "*** TECHNICAL DIAGNOSTICS ***",
        ),
        _tooltip_line(tr, "reason", "Reason", reason_text),
        _tooltip_line(
            tr,
            "signalTime",
            "Signal time",
            record.timestamp.isoformat(),
        ),
    ]

    if source_reason:
        lines.append(_tooltip_line(tr, "macdReason", "MACD reason", source_reason))
    lines.append(_tooltip_line(tr, "macdState", "MACD state", record.macd_state))
    lines.append(
        _tooltip_line(
            tr,
            "macdQualityResult",
            "MACD Quality result",
            workspace_signal_macd_quality_result_text(record),
        )
    )
    if record.source_profile_uid is not None:
        lines.append(
            _tooltip_line(
                tr,
                "macdProfile",
                "MACD profile",
                (
                    f"{record.source_profile_uid} "
                    f"({revision_label} {record.source_profile_revision})"
                ),
            )
        )

    if filter_reason:
        lines.append(
            _tooltip_line(
                tr,
                "alligatorReason",
                "Alligator reason",
                filter_reason,
            )
        )
    lines.append(
        _tooltip_line(
            tr,
            "alligatorState",
            "Alligator state",
            record.alligator_confirmation,
        )
    )

    context = record.filter_context
    if context is not None and context.regime is not None:
        if context.diagnostic_observations:
            lines.append(
                _tooltip_line(
                    tr,
                    "alligatorObservationState",
                    "Alligator observation state",
                    context.diagnostic_observations[-1].state,
                )
            )
        lines.append(
            _tooltip_line(
                tr,
                "alligatorRegime",
                "Alligator regime",
                workspace_signal_alligator_regime_text(record, tr),
            )
        )
        lines.append(
            _tooltip_line(
                tr,
                "alligatorPhase",
                "Alligator phase",
                workspace_signal_alligator_phase_text(record, tr),
            )
        )
        if context.active_age is not None:
            lines.append(
                _tooltip_line(
                    tr,
                    "alligatorActiveAge",
                    "Alligator active age",
                    context.active_age,
                )
            )
        if context.normalized_slope is not None:
            lines.append(
                _tooltip_line(
                    tr,
                    "alligatorNormalizedSlope",
                    "Normalized Alligator slope",
                    f"{context.normalized_slope:.6f}",
                )
            )
        if context.normalized_opening is not None:
            lines.append(
                _tooltip_line(
                    tr,
                    "alligatorNormalizedOpening",
                    "Normalized Alligator opening",
                    f"{context.normalized_opening:.6f}",
                )
            )

    if context is not None:
        lines.extend(
            (
                _tooltip_line(
                    tr,
                    "alligatorMode",
                    "Alligator mode",
                    context.mode,
                ),
                _tooltip_line(
                    tr,
                    "alligatorTimeframe",
                    "Alligator timeframe",
                    context.timeframe,
                ),
                _tooltip_line(
                    tr,
                    "alligatorProfile",
                    "Alligator profile",
                    (
                        f"{context.profile_uid} "
                        f"({revision_label} {context.profile_revision})"
                    ),
                ),
            )
        )
        if context.observation_timestamp is not None:
            lines.append(
                _tooltip_line(
                    tr,
                    "observationTime",
                    "Observation time",
                    context.observation_timestamp.isoformat(),
                )
            )
        if context.available_at is not None:
            lines.append(
                _tooltip_line(
                    tr,
                    "availableAt",
                    "Available at",
                    context.available_at.isoformat(),
                )
            )

    if context is not None and context.diagnostic_observations:
        labels = ("alligatorT2", "alligatorT1", "alligatorT")
        fallbacks = ("Alligator t-2", "Alligator t-1", "Alligator t")
        observations = context.diagnostic_observations[-3:]
        offset = 3 - len(observations)
        for index, observation in enumerate(observations, start=offset):
            lines.append(
                _tooltip_line(
                    tr,
                    labels[index],
                    fallbacks[index],
                    _filter_observation_text(observation, tr),
                )
            )

    lines.append(
        _tooltip_line(
            tr,
            "alligatorDecision",
            "Alligator decision",
            record.filter_decision,
        )
    )
    lines.append(
        _tooltip_line(
            tr,
            "finalDecision",
            "Final decision",
            "ALLOW" if record.accepted else "REJECT",
        )
    )
    _append_candidate_f_lifecycle_lines(lines, record, tr)

    technical_codes = ", ".join(
        dict.fromkeys(
            code
            for code in (
                record.source_reason_code,
                record.filter_reason_code,
                record.risk_reason_code,
            )
            if code
        )
    )
    if technical_codes:
        lines.append(
            _tooltip_line(
                tr,
                "technicalCodes",
                "Technical reason codes",
                technical_codes,
            )
        )
    lines.append(
        _tooltip_line(
            tr,
            "diagnosticReason",
            "Diagnostic reason",
            record.reason,
        )
    )
    return WorkspaceSignalPresentation(
        reason_text=reason_text,
        tooltip_text="\n".join(tooltip_lines),
        detail_text="\n".join(lines),
    )


def build_workspace_signal_journal_text(
    record: WorkspaceSignalRecord,
    tr: TranslationCallback,
    *,
    journal_timestamp: datetime,
    event: str,
) -> str:
    """Побудувати повний Journal block; Signals tooltip лишається коротким."""
    presentation = build_workspace_signal_presentation(record, tr)
    runtime_time = journal_timestamp
    if runtime_time.tzinfo is None:
        runtime_time = runtime_time.replace(tzinfo=UTC)
    signal_time = record.timestamp
    if signal_time.tzinfo is None:
        signal_time = signal_time.replace(tzinfo=UTC)
    header = (
        f"{runtime_time.astimezone(UTC).isoformat(timespec='milliseconds')} "
        f"[SIGNAL] {str(event or '').strip().upper()} @ "
        f"{signal_time.astimezone(UTC).isoformat(timespec='seconds')}"
    )
    return f"{header}\n\n{presentation.detail_text}"


def _build_short_tooltip_lines(
    record: WorkspaceSignalRecord,
    tr: TranslationCallback,
    *,
    reason_text: str,
) -> list[str]:
    """Побудувати короткий hover-text без raw technical diagnostics."""
    lines = [
        _summary_line(
            tr,
            "signal",
            "Signal",
            f"{_compact_utc(record.timestamp)} | {record.direction}",
        ),
        _summary_line(
            tr,
            "macdQuality",
            "MACD Quality",
            workspace_signal_macd_quality_result_text(record),
        ),
    ]
    context = record.filter_context
    if context is not None:
        alligator_parts = [record.alligator_confirmation]
        regime_text = workspace_signal_alligator_regime_text(record, tr)
        phase_text = workspace_signal_alligator_phase_text(record, tr)
        if regime_text != "—":
            alligator_parts.append(regime_text)
        if phase_text != "—":
            alligator_parts.append(phase_text)
        lines.append(
            _summary_line(
                tr,
                "alligator",
                "Alligator",
                " | ".join(alligator_parts),
            )
        )
    lifecycle_text = _candidate_f_lifecycle_summary_text(record, tr)
    if lifecycle_text:
        lines.append(
            _summary_line(
                tr,
                "lifecycle",
                "Candidate F",
                lifecycle_text,
            )
        )
    if _candidate_f_release_visible(record):
        lines.append(
            _summary_line(
                tr,
                "alligatorConfirmation",
                "Alligator confirmation",
                tr(
                    "AlgorithmWorkspaceSignalSummary.confirmationPassedRelease",
                    "PASSED → RELEASE",
                ),
            )
        )
    structural_guard = _structural_guard_code(record.filter_reason_code)
    if structural_guard:
        lines.append(
            _summary_line(
                tr,
                "structuralGuard",
                "Structural guard",
                structural_guard,
            )
        )
    lines.extend(_tooltip_reason_lines(tr, reason_text))
    lines.append(
        _summary_line(
            tr,
            "finalDecision",
            "Final decision",
            "ALLOW" if record.accepted else "REJECT",
        )
    )
    return lines


def _tooltip_reason_lines(
    tr: TranslationCallback,
    reason_text: str,
) -> list[str]:
    """Розбити коротку причину tooltip на читабельні речення."""
    normalized = " ".join(str(reason_text or "").split())
    if not normalized:
        return [_tooltip_line(tr, "reason", "Reason", "—")]

    raw_parts = normalized.split(". ")
    sentences: list[str] = []
    for index, raw_part in enumerate(raw_parts):
        sentence = raw_part.strip()
        if not sentence:
            continue
        if index < len(raw_parts) - 1 and not sentence.endswith((".", "!", "?")):
            sentence = f"{sentence}."
        sentences.append(sentence)

    if not sentences:
        return [_tooltip_line(tr, "reason", "Reason", normalized)]

    label = tr("AlgorithmWorkspaceSignalTooltip.reason", "Reason")
    return [f"{label}: {sentences[0]}", *sentences[1:]]


def _build_compact_summary_lines(
    record: WorkspaceSignalRecord,
    tr: TranslationCallback,
    *,
    filter_reason: str | None,
) -> list[str]:
    """Побудувати короткий виділений summary перед повним technical detail."""
    header = tr(
        "AlgorithmWorkspaceSignalSummary.header",
        "************************************ DECISION SUMMARY "
        "************************************",
    )
    footer = tr(
        "AlgorithmWorkspaceSignalSummary.footer",
        "************************************ END OF SUMMARY "
        "************************************",
    )
    lines = [
        header,
        _summary_line(
            tr,
            "signal",
            "Signal",
            f"{_compact_utc(record.timestamp)} | {record.direction}",
        ),
        _summary_line(
            tr,
            "macdQuality",
            "MACD Quality",
            workspace_signal_macd_quality_result_text(record),
        ),
    ]

    context = record.filter_context
    if context is not None:
        alligator_parts = [record.alligator_confirmation]
        regime_text = workspace_signal_alligator_regime_text(record, tr)
        phase_text = workspace_signal_alligator_phase_text(record, tr)
        if regime_text != "—":
            alligator_parts.append(regime_text)
        if phase_text != "—":
            alligator_parts.append(phase_text)
        lines.append(
            _summary_line(
                tr,
                "alligator",
                "Alligator",
                " | ".join(alligator_parts),
            )
        )
        strength_parts: list[str] = []
        if context.normalized_slope is not None:
            strength_parts.append(f"slope={context.normalized_slope:.6f}")
        if context.normalized_opening is not None:
            strength_parts.append(f"opening={context.normalized_opening:.6f}")
        if context.active_age is not None:
            strength_parts.append(f"active_age={context.active_age}")
        if strength_parts:
            lines.append(
                _summary_line(
                    tr,
                    "alligatorStrength",
                    "Alligator strength",
                    " | ".join(strength_parts),
                )
            )

    lifecycle_text = _candidate_f_lifecycle_summary_text(record, tr)
    if lifecycle_text:
        lines.append(
            _summary_line(
                tr,
                "lifecycle",
                "Candidate F",
                lifecycle_text,
            )
        )
    lifecycle_context = record.candidate_f_lifecycle_context
    if lifecycle_context is not None:
        snapshot = _candidate_f_lifecycle_snapshot_text(lifecycle_context, tr)
        if snapshot:
            lines.append(
                _summary_line(
                    tr,
                    "lifecycleSnapshot",
                    "Lifecycle state",
                    snapshot,
                )
            )
    lifecycle_reason_code = str(
        record.candidate_f_lifecycle_reason or ""
    ).strip().upper()
    if lifecycle_reason_code and lifecycle_reason_code != "ALLIGATOR_DEFERRED_RELEASE":
        lifecycle_reason = _translated_code(
            lifecycle_reason_code,
            _CANDIDATE_F_LIFECYCLE_REASON_LABELS,
            tr,
        ) or lifecycle_reason_code
        lines.append(
            _summary_line(
                tr,
                "lifecycleReason",
                "Lifecycle reason",
                lifecycle_reason,
            )
        )

    if _candidate_f_release_visible(record):
        lines.append(
            _summary_line(
                tr,
                "alligatorConfirmation",
                "Alligator confirmation",
                tr(
                    "AlgorithmWorkspaceSignalSummary.confirmationPassedRelease",
                    "PASSED → RELEASE",
                ),
            )
        )

    structural_guard = _structural_guard_code(record.filter_reason_code)
    if structural_guard:
        lines.append(
            _summary_line(
                tr,
                "structuralGuard",
                "Structural guard",
                structural_guard,
            )
        )
    elif filter_reason:
        lines.append(
            _summary_line(
                tr,
                "filter",
                "Filter / guard",
                filter_reason,
            )
        )
    lines.append(
        _summary_line(
            tr,
            "finalDecision",
            "Final decision",
            "ALLOW" if record.accepted else "REJECT",
        )
    )
    lines.append(footer)
    return lines


def _candidate_f_release_visible(record: WorkspaceSignalRecord) -> bool:
    """Чи містить signal evidence підтверджений Candidate F RELEASE."""
    action = str(record.candidate_f_lifecycle_action or "").strip().upper()
    return (
        action == "RELEASE"
        or record.source_reason_code == "MACD_DEFERRED_RELEASE"
        or record.filter_reason_code == "ALLIGATOR_DEFERRED_RELEASE"
    )


def _structural_guard_code(reason_code: str | None) -> str:
    """Повернути короткий код structural guard для compact presentation."""
    normalized = str(reason_code or "").strip().upper()
    return _STRUCTURAL_GUARD_CODES.get(normalized, "")


def _candidate_f_lifecycle_summary_text(
    record: WorkspaceSignalRecord,
    tr: TranslationCallback,
) -> str:
    """Повернути compact ARMED/RELEASE/CANCEL/EXPIRE evidence."""
    action = str(record.candidate_f_lifecycle_action or "").strip().upper()
    if not action:
        if record.filter_reason_code == "ALLIGATOR_DEFERRED_ARMED":
            action = "ARMED"
        elif (
            record.filter_reason_code == "ALLIGATOR_DEFERRED_RELEASE"
            or record.source_reason_code == "MACD_DEFERRED_RELEASE"
        ):
            action = "RELEASE"
    if not action:
        return ""
    action_text = _translated_code(
        action,
        _CANDIDATE_F_LIFECYCLE_ACTION_LABELS,
        tr,
    ) or action
    if record.filter_reason_code == "ALLIGATOR_DEFERRED_ARMED" and action != "ARMED":
        armed_text = _translated_code(
            "ARMED",
            _CANDIDATE_F_LIFECYCLE_ACTION_LABELS,
            tr,
        ) or "ARMED"
        return f"{armed_text} → {action_text}"
    return action_text


def _candidate_f_lifecycle_snapshot_text(
    context: object,
    tr: TranslationCallback,
) -> str:
    """Повернути короткий terminal Alligator snapshot Candidate F."""
    regime = str(getattr(context, "regime", "") or "").strip().upper()
    phase = str(getattr(context, "regime_phase", "") or "").strip().upper()
    parts = [
        _translated_code(regime, _ALLIGATOR_REGIME_LABELS, tr) or regime or "—",
        _translated_code(phase, _ALLIGATOR_PHASE_LABELS, tr) or phase or "—",
    ]
    active_age = getattr(context, "active_age", None)
    slope = getattr(context, "normalized_slope", None)
    opening = getattr(context, "normalized_opening", None)
    if active_age is not None:
        parts.append(f"active_age={int(active_age)}")
    if slope is not None:
        parts.append(f"slope={float(slope):.6f}")
    if opening is not None:
        parts.append(f"opening={float(opening):.6f}")
    return " | ".join(parts)


def _summary_line(
    tr: TranslationCallback,
    suffix: str,
    fallback_label: str,
    value: object,
) -> str:
    label = tr(f"AlgorithmWorkspaceSignalSummary.{suffix}", fallback_label)
    return f"{label}: {value}"


def _compact_utc(value: datetime) -> str:
    """Повернути короткий UTC timestamp для summary без зайвого ISO шуму."""
    normalized = value
    if normalized.tzinfo is None:
        normalized = normalized.replace(tzinfo=UTC)
    return normalized.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def _candidate_f_lifecycle_reason_suffix(
    record: WorkspaceSignalRecord,
    tr: TranslationCallback,
) -> str:
    if record.filter_reason_code != "ALLIGATOR_DEFERRED_ARMED":
        return ""
    action = str(record.candidate_f_lifecycle_action or "").strip().upper()
    if not action or action == "ARMED":
        return ""
    action_text = _translated_code(
        action,
        _CANDIDATE_F_LIFECYCLE_ACTION_LABELS,
        tr,
    ) or action
    reason_code = str(record.candidate_f_lifecycle_reason or "").strip().upper()
    reason_text = _translated_code(
        reason_code,
        _CANDIDATE_F_LIFECYCLE_REASON_LABELS,
        tr,
    ) if reason_code else None
    if reason_text:
        return f"→ {action_text}: {reason_text}"
    return f"→ {action_text}."


def _append_candidate_f_lifecycle_lines(
    lines: list[str],
    record: WorkspaceSignalRecord,
    tr: TranslationCallback,
) -> None:
    action = str(record.candidate_f_lifecycle_action or "").strip().upper()
    if not action:
        if record.filter_reason_code == "ALLIGATOR_DEFERRED_ARMED":
            action = "ARMED"
        elif record.filter_reason_code == "ALLIGATOR_DEFERRED_RELEASE":
            action = "RELEASE"
    if not action:
        return

    action_text = _translated_code(
        action,
        _CANDIDATE_F_LIFECYCLE_ACTION_LABELS,
        tr,
    ) or action
    if (
        record.filter_reason_code == "ALLIGATOR_DEFERRED_ARMED"
        and action != "ARMED"
    ):
        armed_text = _translated_code(
            "ARMED",
            _CANDIDATE_F_LIFECYCLE_ACTION_LABELS,
            tr,
        ) or "ARMED"
        action_text = f"{armed_text} → {action_text}"
    lines.append(
        _tooltip_line(
            tr,
            "candidateFLifecycle",
            "Candidate F lifecycle",
            action_text,
        )
    )
    reason_code = str(record.candidate_f_lifecycle_reason or "").strip().upper()
    if reason_code:
        reason_text = _translated_code(
            reason_code,
            _CANDIDATE_F_LIFECYCLE_REASON_LABELS,
            tr,
        ) or reason_code
        lines.append(
            _tooltip_line(
                tr,
                "lifecycleReason",
                "Lifecycle reason",
                reason_text,
            )
        )
    if record.candidate_f_lifecycle_timestamp is not None:
        lines.append(
            _tooltip_line(
                tr,
                "lifecycleTime",
                "Lifecycle time",
                record.candidate_f_lifecycle_timestamp.isoformat(),
            )
        )
    if record.candidate_f_lifecycle_delay_bars is not None:
        lines.append(
            _tooltip_line(
                tr,
                "lifecycleDelayBars",
                "Lifecycle delay, bars",
                record.candidate_f_lifecycle_delay_bars,
            )
        )
    lifecycle_context = record.candidate_f_lifecycle_context
    if lifecycle_context is not None:
        lifecycle_regime = str(lifecycle_context.regime or "").strip().upper()
        lifecycle_phase = str(
            lifecycle_context.regime_phase or ""
        ).strip().upper()
        snapshot_parts = [
            _translated_code(
                lifecycle_regime,
                _ALLIGATOR_REGIME_LABELS,
                tr,
            )
            or lifecycle_regime
            or "—",
            _translated_code(
                lifecycle_phase,
                _ALLIGATOR_PHASE_LABELS,
                tr,
            )
            or lifecycle_phase
            or "—",
        ]
        if lifecycle_context.active_age is not None:
            snapshot_parts.append(f"active_age={lifecycle_context.active_age}")
        if lifecycle_context.normalized_slope is not None:
            snapshot_parts.append(
                f"slope={lifecycle_context.normalized_slope:.6f}"
            )
        if lifecycle_context.normalized_opening is not None:
            snapshot_parts.append(
                f"opening={lifecycle_context.normalized_opening:.6f}"
            )
        lines.append(
            _tooltip_line(
                tr,
                "lifecycleSnapshot",
                "Lifecycle snapshot",
                " | ".join(snapshot_parts),
            )
        )


def _filter_observation_text(observation: object, tr: TranslationCallback) -> str:
    regime = str(getattr(observation, "regime", "") or "").strip().upper()
    phase = str(
        getattr(observation, "regime_phase", "") or ""
    ).strip().upper()
    regime_text = _translated_code(regime, _ALLIGATOR_REGIME_LABELS, tr) or regime
    phase_text = _translated_code(phase, _ALLIGATOR_PHASE_LABELS, tr) or phase
    timestamp = getattr(observation, "timestamp", None)
    state = str(getattr(observation, "state", "") or "—")
    slope = getattr(observation, "normalized_slope", None)
    opening = getattr(observation, "normalized_opening", None)
    parts = [str(timestamp.isoformat() if timestamp is not None else "—")]
    parts.extend((state, regime_text, phase_text))
    if slope is not None:
        parts.append(f"slope={float(slope):.6f}")
    if opening is not None:
        parts.append(f"opening={float(opening):.6f}")
    return " | ".join(parts)


def _translated_runtime_reason(
    reason: str,
    tr: TranslationCallback,
) -> str | None:
    key_fallback = _RUNTIME_REASON_LABELS.get(str(reason or "").strip().lower())
    if key_fallback is None:
        return None
    key, fallback = key_fallback
    return tr(key, fallback)


def _translated_code(
    code: str | None,
    labels: dict[str, tuple[str, str]],
    tr: TranslationCallback,
) -> str | None:
    normalized_code = str(code or "").strip().upper()
    key_fallback = labels.get(normalized_code)
    if key_fallback is None:
        return None
    key, fallback = key_fallback
    return tr(key, fallback)


def _tooltip_line(
    tr: TranslationCallback,
    suffix: str,
    fallback_label: str,
    value: object,
) -> str:
    label = tr(f"AlgorithmWorkspaceSignalTooltip.{suffix}", fallback_label)
    return f"{label}: {value}"
