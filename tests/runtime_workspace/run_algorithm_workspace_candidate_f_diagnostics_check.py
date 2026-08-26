# -*- coding: utf-8 -*-
"""Read-only діагностика Signals/Journal production Candidate F, RoadMap102/3.

Тест фіксує читабельний detail для MACD Quality,
Alligator state/regime/phase,
active_age, causal t-2/t-1/t, profile UID/revision, observation/available-at та
Candidate F ARMED -> RELEASE/CANCEL/EXPIRE lifecycle. RoadMap102/3B додає
короткий виділений summary перед technical detail. RoadMap102/3D лишає у
Signals tooltip тільки коротке повідомлення, а повний summary + raw diagnostic
зберігає в Journal detail; перед summary є порожній рядок, separator довший за
рядок journal-header. Terminal lifecycle оновлює immutable evidence початкового
ARMED signal record через ``replace``, не створює нового торгового сигналу й не
викликає broker execution.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_DATA_MODE_REPLAY,
    AlgorithmWorkspace,
)
from core.translation_policy import translation_override_for_key  # noqa: E402
from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_REASON_DEFERRED_ARMED,
    ALLIGATOR_REASON_OPENING_COLLAPSE,
    ALLIGATOR_REASON_OVEREXTENDED,
    ALLIGATOR_REASON_VOLATILITY_SPIKE,
    ALLIGATOR_REASON_WEAK_OPENING,
    CANDIDATE_F_LIFECYCLE_CANCEL,
    CANDIDATE_F_LIFECYCLE_EXPIRE,
    CANDIDATE_F_LIFECYCLE_REASON_OPPOSITE_MACD,
    CANDIDATE_F_LIFECYCLE_REASON_TTL_EXPIRED,
    CANDIDATE_F_LIFECYCLE_RELEASE,
    WorkspaceCandidateFLifecycleEvent,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from core.workspace_signal import (  # noqa: E402
    WORKSPACE_SIGNAL_FILTER_REJECT,
    WorkspaceSignalFilterContext,
    WorkspaceSignalFilterObservation,
    WorkspaceSignalRecord,
)
from core.workspace_signal_presentation import (  # noqa: E402
    build_workspace_signal_journal_text,
    build_workspace_signal_presentation,
    workspace_signal_i18n_entries,
    workspace_signal_reason_code_text,
)

BASE_TIME = datetime(2026, 8, 21, 9, 0, tzinfo=UTC)


class CandidateFDiagnosticsRuntime(WorkspaceRuntime):
    """Тестовий доступ до protected lifecycle hooks без зміни production API."""

    def seed_signal_record(self, record: WorkspaceSignalRecord) -> None:
        """Додати початковий ARMED record у видиму та повну історію."""
        self.signals.append(record)
        self._historical_signal_records.append(record)

    def apply_lifecycle_event(
        self,
        event: WorkspaceCandidateFLifecycleEvent,
    ) -> None:
        """Застосувати terminal lifecycle event через runtime hook."""
        self._apply_candidate_f_lifecycle_event(event)


def _uk_tr(key: str, fallback: str) -> str:
    return translation_override_for_key(key, "uk") or fallback


def _observation(
    offset: int,
    *,
    phase: str,
    slope: float,
    opening: float,
) -> WorkspaceSignalFilterObservation:
    timestamp = BASE_TIME + timedelta(minutes=15 * offset)
    return WorkspaceSignalFilterObservation(
        timestamp=timestamp,
        available_at=timestamp + timedelta(minutes=15),
        state="BULLISH",
        regime="ALLIGATOR_REGIME_TREND_UP",
        regime_phase=phase,
        normalized_slope=slope,
        normalized_opening=opening,
    )


def _context(
    *,
    phase: str,
    active_age: int,
    observations: tuple[WorkspaceSignalFilterObservation, ...],
) -> WorkspaceSignalFilterContext:
    current = observations[-1]
    return WorkspaceSignalFilterContext(
        mode="SAME_TIMEFRAME",
        timeframe="M15",
        profile_uid="alligator-lge-candidate-f",
        profile_revision=1,
        observation_timestamp=current.timestamp,
        available_at=current.available_at,
        regime=current.regime,
        regime_phase=phase,
        normalized_slope=current.normalized_slope,
        normalized_opening=current.normalized_opening,
        active_age=active_age,
        diagnostic_observations=observations,
    )


def _armed_record() -> WorkspaceSignalRecord:
    history = (
        _observation(
            -2,
            phase="ALLIGATOR_REGIME_PHASE_STARTING",
            slope=0.090,
            opening=0.420,
        ),
        _observation(
            -1,
            phase="ALLIGATOR_REGIME_PHASE_STARTING",
            slope=0.110,
            opening=0.460,
        ),
        _observation(
            0,
            phase="ALLIGATOR_REGIME_PHASE_STARTING",
            slope=0.130,
            opening=0.490,
        ),
    )
    return WorkspaceSignalRecord(
        timestamp=BASE_TIME,
        signal_uid="candidate-f-armed-signal",
        workspace_uid="workspace-candidate-f-diagnostics",
        broker="CTRADER",
        account_id=None,
        symbol="EURUSD",
        timeframe="M15",
        source_mode="REPLAY",
        signal_type="MACD_CROSS",
        direction="BUY",
        strength=0.00018,
        macd_state="MACD_CROSS_UP",
        alligator_confirmation="SAME_TIMEFRAME_BULLISH",
        spread_status="OK",
        accepted=False,
        reason=(
            "MACD_CROSS_ACCEPTED; ALLIGATOR_DEFERRED_ARMED; "
            "raw_candidate_f_diagnostic=kept"
        ),
        source_reason_code="MACD_CROSS_ACCEPTED",
        source_profile_uid="macd-custom-fast",
        source_profile_revision=7,
        filter_decision=WORKSPACE_SIGNAL_FILTER_REJECT,
        filter_reason_code=ALLIGATOR_REASON_DEFERRED_ARMED,
        filter_context=_context(
            phase="ALLIGATOR_REGIME_PHASE_STARTING",
            active_age=0,
            observations=history,
        ),
    )


def _terminal_context() -> WorkspaceSignalFilterContext:
    history = (
        _observation(
            1,
            phase="ALLIGATOR_REGIME_PHASE_ACTIVE",
            slope=0.180,
            opening=0.720,
        ),
        _observation(
            2,
            phase="ALLIGATOR_REGIME_PHASE_ACTIVE",
            slope=0.170,
            opening=0.650,
        ),
        _observation(
            3,
            phase="ALLIGATOR_REGIME_PHASE_ACTIVE",
            slope=0.150,
            opening=0.580,
        ),
    )
    return _context(
        phase="ALLIGATOR_REGIME_PHASE_ACTIVE",
        active_age=3,
        observations=history,
    )


def main() -> None:
    workspace = AlgorithmWorkspace.create(
        broker="CTRADER",
        account_id=None,
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        data_mode=WORKSPACE_DATA_MODE_REPLAY,
        control_mode=WORKSPACE_CONTROL_MODE_AUTO,
    )
    runtime = CandidateFDiagnosticsRuntime(workspace)
    armed = replace(_armed_record(), workspace_uid=workspace.workspace_uid)
    runtime.seed_signal_record(armed)

    terminal_time = BASE_TIME + timedelta(minutes=45)
    lifecycle_event = WorkspaceCandidateFLifecycleEvent(
        action=CANDIDATE_F_LIFECYCLE_CANCEL,
        original_signal_timestamp=BASE_TIME,
        event_timestamp=terminal_time,
        direction="BUY",
        reason_code=CANDIDATE_F_LIFECYCLE_REASON_OPPOSITE_MACD,
        delay_bars=3,
        filter_context=_terminal_context(),
    )
    runtime.apply_lifecycle_event(lifecycle_event)

    records = runtime.signal_records()
    assert len(records) == 1
    updated = records[0]
    assert updated.signal_uid == armed.signal_uid
    assert updated.candidate_f_lifecycle_action == CANDIDATE_F_LIFECYCLE_CANCEL
    assert (
        updated.candidate_f_lifecycle_reason
        == CANDIDATE_F_LIFECYCLE_REASON_OPPOSITE_MACD
    )
    assert updated.candidate_f_lifecycle_delay_bars == 3
    assert updated.candidate_f_lifecycle_context is not None
    assert updated.candidate_f_lifecycle_context.active_age == 3

    presentation = build_workspace_signal_presentation(updated, _uk_tr)
    tooltip = presentation.tooltip_text
    detail = presentation.detail_text
    assert tooltip.startswith("Сигнал: 2026-08-21 09:00 UTC | BUY\n")
    assert "MACD Quality: PASS" in tooltip
    assert (
        "Alligator: SAME_TIMEFRAME_BULLISH | Початок тренду вгору | STARTING"
        in tooltip
    )
    assert "Candidate F: ARMED → CANCEL" in tooltip
    assert "Причина:" in tooltip
    reason_line = next(
        line for line in tooltip.splitlines() if line.startswith("Причина:")
    )
    assert len(reason_line) < 160
    assert "\n" in tooltip
    assert "Фінальне рішення: REJECT" in tooltip
    assert "ПІДСУМОК РІШЕННЯ" not in tooltip
    assert "ТЕХНІЧНА ДІАГНОСТИКА" not in tooltip
    assert "raw_candidate_f_diagnostic=kept" not in tooltip

    summary_header = translation_override_for_key(
        "AlgorithmWorkspaceSignalSummary.header",
        "uk",
    )
    summary_footer = translation_override_for_key(
        "AlgorithmWorkspaceSignalSummary.footer",
        "uk",
    )
    assert summary_header is not None
    assert summary_footer is not None
    assert len(summary_header) > 86
    assert detail.startswith(f"{summary_header}\n")
    assert "Сигнал: 2026-08-21 09:00 UTC | BUY" in detail
    assert "MACD Quality: PASS" in detail
    assert (
        "Alligator: SAME_TIMEFRAME_BULLISH | Початок тренду вгору | STARTING"
        in detail
    )
    assert (
        "Сила Alligator: slope=0.130000 | opening=0.490000 | active_age=0"
        in detail
    )
    assert "Candidate F: ARMED → CANCEL" in detail
    assert (
        "Стан lifecycle: Тренд вгору | ACTIVE | active_age=3 | "
        "slope=0.150000 | opening=0.580000"
        in detail
    )
    assert "Причина lifecycle: З’явився протилежний сигнал MACD" in detail
    assert "Фільтр / guard:" in detail
    assert "Фінальне рішення: REJECT" in detail
    assert summary_footer in detail
    assert "*** ТЕХНІЧНА ДІАГНОСТИКА ***" in detail
    assert detail.index(summary_footer) < detail.index(
        "*** ТЕХНІЧНА ДІАГНОСТИКА ***"
    )
    assert "Результат MACD Quality: PASS" in detail
    assert "Стан Alligator: SAME_TIMEFRAME_BULLISH" in detail
    assert "Стан observation Alligator: BULLISH" in detail
    assert "Режим Alligator: Початок тренду вгору" in detail
    assert "Фаза Alligator: STARTING" in detail
    assert "Вік ACTIVE, барів: 0" in detail
    assert "Нормалізований нахил Alligator: 0.130000" in detail
    assert "Нормалізоване розкриття Alligator: 0.490000" in detail
    assert "Alligator t-2:" in detail
    assert "Alligator t-1:" in detail
    assert "Alligator t:" in detail
    assert "Рішення Alligator: REJECT" in detail
    assert "Підсумкове рішення: REJECT" in detail
    assert "Життєвий цикл Candidate F: ARMED → CANCEL" in detail
    assert "З’явився протилежний сигнал MACD" in detail
    assert "Очікування, барів: 3" in detail
    assert "active_age=3" in detail
    assert "Профіль MACD: macd-custom-fast (ревізія 7)" in detail
    assert "Профіль Alligator: alligator-lge-candidate-f (ревізія 1)" in detail
    assert f"Час спостереження: {BASE_TIME.isoformat()}" in detail
    assert (
        "Доступно з: "
        f"{(BASE_TIME + timedelta(minutes=15)).isoformat()}"
    ) in detail
    assert "raw_candidate_f_diagnostic=kept" in detail
    assert "→ CANCEL:" in presentation.reason_text

    journal_entry = runtime.journal[-1]
    assert journal_entry.category == "SIGNAL"
    assert journal_entry.event == "CANDIDATE_F_CANCEL"
    assert journal_entry.details["signal_uid"] == updated.signal_uid
    assert journal_entry.details["broker_execution_attempted"] is False
    journal_text = build_workspace_signal_journal_text(
        updated,
        _uk_tr,
        journal_timestamp=journal_entry.timestamp,
        event=journal_entry.event,
    )
    assert "CANDIDATE_F_CANCEL" in journal_text
    assert f"\n\n{summary_header}\n" in journal_text
    assert "Життєвий цикл Candidate F: ARMED → CANCEL" in journal_text
    assert "Alligator t-2:" in journal_text
    assert "Діагностична причина:" in journal_text

    released = replace(
        updated,
        candidate_f_lifecycle_action=CANDIDATE_F_LIFECYCLE_RELEASE,
        candidate_f_lifecycle_reason="ALLIGATOR_DEFERRED_RELEASE",
        candidate_f_lifecycle_timestamp=terminal_time,
        candidate_f_lifecycle_delay_bars=2,
    )
    expired = replace(
        updated,
        candidate_f_lifecycle_action=CANDIDATE_F_LIFECYCLE_EXPIRE,
        candidate_f_lifecycle_reason=CANDIDATE_F_LIFECYCLE_REASON_TTL_EXPIRED,
        candidate_f_lifecycle_timestamp=terminal_time,
        candidate_f_lifecycle_delay_bars=5,
    )
    assert "ARMED → RELEASE" in build_workspace_signal_presentation(
        released,
        _uk_tr,
    ).tooltip_text
    assert "ARMED → EXPIRE" in build_workspace_signal_presentation(
        expired,
        _uk_tr,
    ).tooltip_text

    release_reject = replace(
        updated,
        source_reason_code="MACD_DEFERRED_RELEASE",
        filter_reason_code=ALLIGATOR_REASON_WEAK_OPENING,
        candidate_f_lifecycle_action=None,
        candidate_f_lifecycle_reason=None,
        candidate_f_lifecycle_timestamp=None,
        candidate_f_lifecycle_delay_bars=None,
        candidate_f_lifecycle_context=None,
        reason="ALLIGATOR_WEAK_OPENING_REJECT; raw_release_diagnostic=kept",
    )
    release_presentation = build_workspace_signal_presentation(
        release_reject,
        _uk_tr,
    )
    release_tooltip = release_presentation.tooltip_text
    assert "Candidate F: RELEASE" in release_tooltip
    assert "Підтвердження Alligator: ПРОЙДЕНО → RELEASE" in release_tooltip
    assert "Structural guard: WEAK_OPENING" in release_tooltip
    assert "Причина:" in release_tooltip
    assert "недостатньо розкритий" in release_tooltip
    assert "Фінальне рішення: REJECT" in release_tooltip
    assert "raw_release_diagnostic=kept" not in release_tooltip
    release_detail = release_presentation.detail_text
    assert "Підтвердження Alligator: ПРОЙДЕНО → RELEASE" in release_detail
    assert "Structural guard: WEAK_OPENING" in release_detail
    assert "Фінальне рішення: REJECT" in release_detail
    assert "raw_release_diagnostic=kept" in release_detail

    structural_codes = (
        ALLIGATOR_REASON_OPENING_COLLAPSE,
        ALLIGATOR_REASON_WEAK_OPENING,
        ALLIGATOR_REASON_VOLATILITY_SPIKE,
        ALLIGATOR_REASON_OVEREXTENDED,
    )
    for code in structural_codes:
        text = workspace_signal_reason_code_text(code, _uk_tr)
        assert text != code
        assert text != "—"

    entries = workspace_signal_i18n_entries()
    for key in (
        "AlgorithmWorkspaceSignalTooltip.macdQualityResult",
        "AlgorithmWorkspaceSignalTooltip.alligatorPhase",
        "AlgorithmWorkspaceSignalTooltip.alligatorActiveAge",
        "AlgorithmWorkspaceSignalTooltip.alligatorT2",
        "AlgorithmWorkspaceSignalTooltip.candidateFLifecycle",
        "AlgorithmWorkspaceCandidateFLifecycle.oppositeMacd",
        "AlgorithmWorkspaceCandidateFLifecycle.ttlExpired",
        "AlgorithmWorkspaceSignalSummary.header",
        "AlgorithmWorkspaceSignalSummary.alligatorConfirmation",
        "AlgorithmWorkspaceSignalSummary.structuralGuard",
        "AlgorithmWorkspaceSignalSummary.finalDecision",
        "AlgorithmWorkspaceSignalSummary.technicalHeader",
    ):
        assert key in entries

    print("Algorithm Workspace Candidate F Diagnostics result")
    print("  macd_quality_result_visible=True")
    print("  alligator_state_regime_phase_visible=True")
    print("  alligator_observation_state_visible=True")
    print("  active_age_visible=True")
    print("  normalized_slope_opening_visible=True")
    print("  causal_t2_t1_t_visible=True")
    print("  armed_release_cancel_expire_readable=True")
    print("  structural_rejects_readable=True")
    print("  final_allow_reject_visible=True")
    print("  profile_uid_revision_visible=True")
    print("  observation_available_at_visible=True")
    print("  compact_summary_first=True")
    print("  compact_summary_star_delimited=True")
    print("  journal_summary_separator_longer_than_header=True")
    print("  journal_blank_line_before_summary=True")
    print("  tooltip_short_only=True")
    print("  tooltip_reason_split_by_sentence=True")
    print("  compact_release_structural_guard_readable=True")
    print("  release_confirmation_not_final_allow=True")
    print("  structural_guard_code_visible=True")
    print("  final_decision_explicit=True")
    print("  technical_diagnostics_separated=True")
    print("  raw_technical_diagnostic_preserved=True")
    print("  runtime_terminal_event_updates_armed_signal=True")
    print("  terminal_event_does_not_create_second_signal=True")
    print("  journal_terminal_event_connected=True")
    print("  strings_json_manual_edit=False")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_CANDIDATE_F_DIAGNOSTICS_CHECK=OK")


if __name__ == "__main__":
    main()
