"""run_t108_09_research_evidence_md7_coverage_audit_check.py

T108-09 виконує AUDIT ONLY / TEST_ONLY inventory directional signal,
indicator, structural і protection sources, фактично досліджених до T108-08.
Runner читає наявні runnable-модулі та MD7 як immutable evidence, перевіряє
ключові source markers і друкує компактні канонічні records з однаковою
схемою для 2025/2026, research status та MD7 coverage.

Audit не запускає Replay, не відновлює відсутні результати з назв файлів і не
створює trading hypothesis. Future outcomes T108 залишаються factual labels.
До і після читання звіряються hashes усіх production Python files і MD7;
production logic, thresholds, MD7, score/vote/weight models, broker execution
та наступний RoadMap item не змінюються.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MD7_PATH = PROJECT_ROOT / "doc" / "LGE_Runtime_07.md"
TEST_ID = "T108-09"
MODE = "RM108_T108_09_RESEARCH_EVIDENCE_MD7_COVERAGE_AUDIT_TEST_ONLY"

RESEARCH_STATUSES = (
    "PRODUCTION_ACCEPTED",
    "CROSS_PERIOD_POSITIVE_RESEARCH",
    "ONE_PERIOD_POSITIVE_ONLY",
    "NEUTRAL_OR_NEGATIVE_CONTROL",
    "UNRESOLVED",
    "MANUAL_SCREENING_ONLY",
)
MD7_STATUSES = (
    "MD7_PRESENT",
    "MD7_PARTIAL",
    "MD7_MISSING",
    "MD7_OUTDATED",
)


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    """Один factual source/event record із фіксованою audit schema."""

    family: str
    signal_or_event: str
    role: str
    source_test_ids: str
    causal_status: str
    completed_bars_only: str
    lookahead_status: str
    factual_2025: str
    factual_2026: str
    sample_size_if_known: str
    production_status: str
    research_status: str
    positive_evidence_level: str
    cross_period_status: str
    md7_coverage: str
    notes: str

    def __post_init__(self) -> None:
        """Відхилити порожній або неканонічний audit record."""

        assert all(
            str(value).strip()
            for value in (
                self.family,
                self.signal_or_event,
                self.role,
                self.source_test_ids,
                self.causal_status,
                self.completed_bars_only,
                self.lookahead_status,
                self.factual_2025,
                self.factual_2026,
                self.sample_size_if_known,
                self.production_status,
                self.positive_evidence_level,
                self.cross_period_status,
                self.notes,
            )
        )
        assert self.research_status in RESEARCH_STATUSES
        assert self.md7_coverage in MD7_STATUSES


def _record(
    family: str,
    event: str,
    role: str,
    tests: str,
    result_2025: str,
    result_2026: str,
    sample: str,
    production: str,
    research: str,
    evidence: str,
    cross_period: str,
    md7: str,
    notes: str,
    *,
    causal: str = "VALIDATED_CAUSAL",
    completed: str = "TRUE",
    lookahead: str = "NO_LOOKAHEAD",
) -> EvidenceRecord:
    """Створити record зі спільними causal defaults без inference."""

    return EvidenceRecord(
        family=family,
        signal_or_event=event,
        role=role,
        source_test_ids=tests,
        causal_status=causal,
        completed_bars_only=completed,
        lookahead_status=lookahead,
        factual_2025=result_2025,
        factual_2026=result_2026,
        sample_size_if_known=sample,
        production_status=production,
        research_status=research,
        positive_evidence_level=evidence,
        cross_period_status=cross_period,
        md7_coverage=md7,
        notes=notes,
    )


def _inventory() -> tuple[EvidenceRecord, ...]:
    """Повернути factual inventory, підтверджений runners та MD7."""

    return (
        _record(
            "MACD",
            "CROSS_EXTENDED_QUALITY",
            "ENTRY",
            "RM101_MACD_CHECKS,T105-18",
            "42T_30W_11L_1BE_NET+4.03",
            "18T_15W_2L_1BE_NET+3.68",
            "42/18 production trades",
            "ACTIVE",
            "PRODUCTION_ACCEPTED",
            "PRODUCTION_REGRESSION",
            "VALIDATED_2025_2026",
            "MD7_PRESENT",
            "real cross remains signal basis",
        ),
        _record(
            "MACD",
            "EXTREMUM_PROMINENCE_DISTANCE_ABC_ANGLE",
            "ENTRY",
            "RM101_QUALITY_CHECKS,T108-06,T108-07,T108-08",
            "weak_all=1679;missed_weak=136;median_ratio=.453853",
            "weak_all=1209;missed_weak=96;median_ratio=.433212",
            "1679/1209 weak rejects",
            "ACTIVE_THRESHOLDS",
            "PRODUCTION_ACCEPTED",
            "PRODUCTION_PLUS_UNRESOLVED_ANATOMY",
            "LOWERING_NOT_SUPPORTED",
            "MD7_PRESENT",
            "quality is accepted; lowering prominence is not",
        ),
        _record(
            "MACD",
            "EARLY_CONTRACTION_OR_SLOPE_REVERSAL",
            "EXIT",
            "T104-01,T104-02,T104-03",
            "events too frequent; direct exit degraded baseline",
            "opposite cross exit net=-17.70",
            "reported by T104 anatomy",
            "NOT_IN_PRODUCTION",
            "NEUTRAL_OR_NEGATIVE_CONTROL",
            "NEGATIVE_EXIT_EVIDENCE",
            "NO_STABLE_DISCRIMINATOR",
            "MD7_PRESENT",
            "Alligator state did not isolate structural failure",
        ),
        _record(
            "MACD",
            "RELATIVE_RESTART_DOMINANT_ACCELERATION",
            "ENTRY",
            "T104-10,T104-11,T104-12",
            "positive incremental result",
            "positive incremental result",
            "small sample",
            "NOT_IN_PRODUCTION",
            "CROSS_PERIOD_POSITIVE_RESEARCH",
            "LIMITED_SMALL_SAMPLE",
            "POSITIVE_BOTH_PERIODS",
            "MD7_PRESENT",
            "identity normalization required before policy",
        ),
        _record(
            "ALLIGATOR",
            "DIRECTION_REGIME_PHASE_STARTING_ACTIVE_ENDING",
            "CONTEXT",
            "RM101_REGIME_CHECKS,T105-18",
            "production context validated",
            "production context validated",
            "42/18 production trades",
            "ACTIVE",
            "PRODUCTION_ACCEPTED",
            "PRODUCTION_REGRESSION",
            "VALIDATED_2025_2026",
            "MD7_PRESENT",
            "ACTIVE plus same direction permits downstream checks",
        ),
        _record(
            "ALLIGATOR",
            "CANDIDATE_F_GUARDS_AND_DEFERRED_RELEASE",
            "ENTRY",
            "RM101_CANDIDATE_F_CHECKS,T105-18",
            "42T_30W_11L_1BE",
            "18T_15W_2L_1BE",
            "42/18 production trades",
            "ACTIVE",
            "PRODUCTION_ACCEPTED",
            "PRODUCTION_REGRESSION",
            "VALIDATED_2025_2026",
            "MD7_PRESENT",
            "collapse weak spike and overextension guards active",
        ),
        _record(
            "ALLIGATOR",
            "FIRST_OPENING_EXPANSION_FROM_COMPRESSION",
            "ENTRY",
            "RM104_8C1_OPENING_EXPANSION",
            "122T_NET+8.40_PF1.0886",
            "90T_NET+26.67_PF1.4293",
            "122/90 test-only trades",
            "NOT_IN_PRODUCTION",
            "CROSS_PERIOD_POSITIVE_RESEARCH",
            "CROSS_PERIOD_POSITIVE",
            "POSITIVE_BOTH_PERIODS",
            "MD7_PRESENT",
            "test-only early opening baseline",
        ),
        _record(
            "ALLIGATOR",
            "FORWARD_SHIFT_H1_PROJECTION",
            "CONTEXT",
            "T104-14,T105-04",
            "precision=.8765;coverage=.8320",
            "precision=.8766;coverage=.8420",
            "full H1 candidate inventory",
            "DIAGNOSTIC_ONLY",
            "CROSS_PERIOD_POSITIVE_RESEARCH",
            "STRONG_DESCRIPTIVE",
            "STABLE_BOTH_PERIODS",
            "MD7_PRESENT",
            "display geometry is not price forecast",
        ),
        _record(
            "STOCHASTIC",
            "CURRENT_BAR_KD_CROSS_14_1_3",
            "ENTRY",
            "T104-19,T105-15,T105-16,T105-17,T105-18",
            "17 rejects;42T_NET+4.03_PF1.5424",
            "11 rejects;18T_NET+3.68_PF3.7669",
            "59/29 factual proposals",
            "ACTIVE",
            "PRODUCTION_ACCEPTED",
            "PRODUCTION_REGRESSION",
            "VALIDATED_2025_2026",
            "MD7_PRESENT",
            "only current completed signal-bar cross rejects",
        ),
        _record(
            "DONCHIAN",
            "ADVERSE_MIDLINE_BREAK",
            "EXIT",
            "T104-04,T104-05,T105-24",
            "direct exit unstable",
            "direct exit unstable",
            "paired factual trades",
            "NOT_IN_PRODUCTION",
            "NEUTRAL_OR_NEGATIVE_CONTROL",
            "NO_STABLE_GAIN",
            "NOT_BETTER_BOTH_PERIODS",
            "MD7_PRESENT",
            "previous completed N20 reference",
        ),
        _record(
            "DONCHIAN",
            "OPPOSITE_BOUNDARY_BREAK",
            "EXIT",
            "T104-04,T105-25",
            "better structural event but no baseline superiority",
            "no frozen baseline superiority",
            "paired factual trades",
            "NOT_IN_PRODUCTION",
            "NEUTRAL_OR_NEGATIVE_CONTROL",
            "CONTROL_ONLY",
            "NOT_BETTER_BOTH_PERIODS",
            "MD7_PRESENT",
            "not a production exit",
        ),
        _record(
            "DONCHIAN",
            "FAVORABLE_BREAKOUT_TP_RELEASE",
            "EXIT",
            "T104-05,T104-06",
            "improved versus frozen reference",
            "strong degradation",
            "paired factual trades",
            "NOT_IN_PRODUCTION",
            "ONE_PERIOD_POSITIVE_ONLY",
            "ONE_PERIOD_ONLY",
            "CONTRADICTORY",
            "MD7_PRESENT",
            "universal TP release rejected",
        ),
        _record(
            "DONCHIAN",
            "POST_TP_REENTRY_AND_PULLBACK_REBREAKOUT",
            "ENTRY",
            "T104-07,T104-08,T104-09,T104-10",
            "second-leg evidence not stable",
            "second-leg evidence not stable",
            "test-only reentry candidates",
            "NOT_IN_PRODUCTION",
            "NEUTRAL_OR_NEGATIVE_CONTROL",
            "NO_STABLE_GAIN",
            "UNSTABLE",
            "MD7_PRESENT",
            "additional momentum did not become policy",
        ),
        _record(
            "DONCHIAN",
            "ENTRY_BREAKOUT_GATE_AND_REJECTED_POPULATION",
            "ENTRY",
            "T105-11,T105-12,T105-13,T105-14,T105-20..T105-23",
            "incremental and rejected anatomy; no accepted gate",
            "cross-period guard damaged winners",
            "59/29 proposal baseline",
            "DISABLED",
            "NEUTRAL_OR_NEGATIVE_CONTROL",
            "NO_PRODUCTION_SUPPORT",
            "NOT_PRODUCTION_READY",
            "MD7_PARTIAL",
            "production Donchian gate remains False",
        ),
        _record(
            "SUPERTREND",
            "DIRECTION_SWITCH_PROTECTED_EXIT_10_3",
            "EXIT",
            "T104-24..T104-29,T105-01",
            "standalone exit effect under current stack=0",
            "standalone exit effect under current stack=0",
            "actual exits=0 across both periods",
            "NOT_IN_PRODUCTION",
            "NEUTRAL_OR_NEGATIVE_CONTROL",
            "CAUSAL_VALID_ZERO_INCREMENT",
            "ZERO_EFFECT_BOTH_PERIODS",
            "MD7_PRESENT",
            "directional value not disproved; PD/SL preempted exits",
        ),
        _record(
            "STRUCTURAL_SR",
            "CAUSAL_SUPPORT_RESISTANCE_ZONES",
            "CONTEXT",
            "RM103_7O..7V",
            "causal zones quantified; policy unresolved",
            "frozen cross-period check; no accepted gate",
            "production-entry paired inventories",
            "NOT_IN_PRODUCTION",
            "UNRESOLVED",
            "DESCRIPTIVE_ONLY",
            "NO_ACCEPTED_CROSS_PERIOD_POLICY",
            "MD7_PRESENT",
            "zones use confirmed completed pivots",
        ),
        _record(
            "STRUCTURAL_SR",
            "BOUNDED_STRUCTURAL_SL_TP",
            "PROTECTION",
            "RM103_8A_FINAL_STRUCTURAL_SL_TP",
            "promising paired geometry; not production",
            "cross-period diagnostic; not production",
            "59/29 frozen baseline entries",
            "NOT_IN_PRODUCTION",
            "UNRESOLVED",
            "PROMISING_NOT_FINAL",
            "NO_ACCEPTED_POLICY",
            "MD7_PRESENT",
            "12..24 pip bounded research reference only",
        ),
        _record(
            "BBW",
            "COMPRESSION_TO_FIRST_EXPANSION",
            "CONTEXT",
            "T104-17",
            "quantitative anatomy; no selection verdict persisted",
            "quantitative anatomy; no selection verdict persisted",
            "runner reports matched openings",
            "NOT_IN_PRODUCTION",
            "UNRESOLVED",
            "DESCRIPTIVE_ONLY",
            "NOT_QUANTIFIED_AS_POLICY",
            "MD7_PARTIAL",
            "MD7 has candidate role but not quantitative conclusion",
        ),
        _record(
            "AC",
            "ACCELERATION_DECELERATION",
            "CONTEXT",
            "T104-18",
            "quantitative anatomy; no selection verdict persisted",
            "quantitative anatomy; no selection verdict persisted",
            "runner reports matched openings",
            "NOT_IN_PRODUCTION",
            "UNRESOLVED",
            "DESCRIPTIVE_ONLY",
            "NOT_QUANTIFIED_AS_POLICY",
            "MD7_PARTIAL",
            "price-incremental anatomy only",
        ),
        _record(
            "DMI_ADX",
            "TREND_STRENGTH_DIRECTION_GUARD",
            "CONTEXT",
            "NONE",
            "manual screening only",
            "manual screening only",
            "NONE",
            "NOT_IN_PRODUCTION",
            "MANUAL_SCREENING_ONLY",
            "MANUAL_ONLY",
            "NOT_QUANTITATIVELY_TESTED",
            "MD7_PRESENT",
            "14/14 reference; not a quantitative result",
            causal="NOT_QUANTITATIVELY_IMPLEMENTED",
            completed="NOT_APPLICABLE",
            lookahead="NOT_TESTED_MANUAL",
        ),
        _record(
            "AROON",
            "DIRECTIONAL_RECENCY_14",
            "CONTEXT",
            "NONE",
            "manual screening: noisy M15",
            "manual screening only",
            "NONE",
            "NOT_IN_PRODUCTION",
            "MANUAL_SCREENING_ONLY",
            "MANUAL_ONLY",
            "NOT_QUANTITATIVELY_TESTED",
            "MD7_PRESENT",
            "not priority; not a quantitative rejection",
            causal="NOT_QUANTITATIVELY_IMPLEMENTED",
            completed="NOT_APPLICABLE",
            lookahead="NOT_TESTED_MANUAL",
        ),
        _record(
            "ICHIMOKU",
            "REGIME_AND_SUPPORT_RESISTANCE_9_26_52_26",
            "CONTEXT",
            "NONE",
            "manual screening only",
            "manual screening only",
            "NONE",
            "NOT_IN_PRODUCTION",
            "MANUAL_SCREENING_ONLY",
            "MANUAL_ONLY",
            "NOT_QUANTITATIVELY_TESTED",
            "MD7_PRESENT",
            "not current priority; no quantitative verdict",
            causal="NOT_QUANTITATIVELY_IMPLEMENTED",
            completed="NOT_APPLICABLE",
            lookahead="NOT_TESTED_MANUAL",
        ),
        _record(
            "CHOP",
            "CHOPPINESS_INDEX_14_REGIME_GUARD",
            "CONTEXT",
            "NONE",
            "manual screening only",
            "manual screening only",
            "NONE",
            "NOT_IN_PRODUCTION",
            "MANUAL_SCREENING_ONLY",
            "MANUAL_ONLY",
            "NOT_QUANTITATIVELY_TESTED",
            "MD7_PRESENT",
            "raw T108-05 choppiness is not CHOP indicator validation",
            causal="NOT_QUANTITATIVELY_IMPLEMENTED",
            completed="NOT_APPLICABLE",
            lookahead="NOT_TESTED_MANUAL",
        ),
        _record(
            "ZIG_ZAG",
            "STRUCTURAL_SWING_REFERENCE",
            "CONTEXT",
            "NONE",
            "manual screening only; repaint risk identified",
            "manual screening only",
            "NONE",
            "NOT_IN_PRODUCTION",
            "MANUAL_SCREENING_ONLY",
            "MANUAL_ONLY",
            "NOT_QUANTITATIVELY_TESTED",
            "MD7_PRESENT",
            "requires separate confirmed-pivot causal semantics",
            causal="NOT_QUANTITATIVELY_IMPLEMENTED",
            completed="NOT_APPLICABLE",
            lookahead="REPAINT_RISK_NOT_VALIDATED",
        ),
        _record(
            "VOLUME_PROFILE",
            "FEED_SESSION_DEPENDENT_STRUCTURE",
            "CONTEXT",
            "NONE",
            "manual candidate deferred",
            "manual candidate deferred",
            "NONE",
            "NOT_IN_PRODUCTION",
            "MANUAL_SCREENING_ONLY",
            "MANUAL_ONLY",
            "NOT_QUANTITATIVELY_TESTED",
            "MD7_PRESENT",
            "deferred because feed and session semantics are unresolved",
            causal="NOT_QUANTITATIVELY_IMPLEMENTED",
            completed="NOT_APPLICABLE",
            lookahead="NOT_TESTED_MANUAL",
        ),
        _record(
            "ATR",
            "STRUCTURAL_SL_DISTANCE_RMA14",
            "PROTECTION",
            "T104-23",
            "causal distance anatomy; no multiplier policy",
            "causal distance anatomy; no multiplier policy",
            "59/29 first-leg reference",
            "NOT_IN_PRODUCTION",
            "UNRESOLVED",
            "DESCRIPTIVE_ONLY",
            "NO_STABILITY_THRESHOLD",
            "MD7_PARTIAL",
            "entry source is prior completed M15",
        ),
        _record(
            "PIVOT",
            "TRADITIONAL_DAILY_STRUCTURAL_TP",
            "PROTECTION",
            "T104-21,T104-22",
            "anatomy and paired cap diagnostic; no policy",
            "anatomy and paired cap diagnostic; no policy",
            "59/29 first-leg reference",
            "NOT_IN_PRODUCTION",
            "UNRESOLVED",
            "DESCRIPTIVE_ONLY",
            "NO_ACCEPTED_POLICY",
            "MD7_PARTIAL",
            "previous completed observed trading day only",
        ),
        _record(
            "FRACTAL",
            "CONFIRMED_SWING_STRUCTURAL_SL",
            "PROTECTION",
            "T104-20",
            "causal anatomy; no accepted SL policy",
            "causal anatomy; no accepted SL policy",
            "59/29 first-leg reference",
            "NOT_IN_PRODUCTION",
            "UNRESOLVED",
            "DESCRIPTIVE_ONLY",
            "NO_ACCEPTED_POLICY",
            "MD7_PARTIAL",
            "confirmed after two right completed M15 bars",
        ),
        _record(
            "PROFIT_DRAWDOWN",
            "NEGATIVE_RECOVERY_AND_35_PERCENT_CLOSE",
            "PROTECTION",
            "T105-05..T105-10,T105-18",
            "35 percent improved cross-period reference",
            "35 percent improved cross-period reference",
            "59/29 pre-Stochastic baseline",
            "ACTIVE",
            "PRODUCTION_ACCEPTED",
            "CROSS_PERIOD_PRODUCTION",
            "POSITIVE_BOTH_PERIODS",
            "MD7_PRESENT",
            "recovery state machine unchanged",
        ),
        _record(
            "RAW_PRICE_ACTION",
            "POST_ENTRY_LOSS_PATH_AND_EARLY_FAILURE",
            "CONTEXT",
            "T108-01,T108-02",
            "outcome anatomy; no production rule",
            "outcome anatomy; no production rule",
            "42/18 trades;13 total losses",
            "NOT_IN_PRODUCTION",
            "UNRESOLVED",
            "OUTCOME_ANATOMY_ONLY",
            "NO_CAUSAL_ENTRY_RULE",
            "MD7_MISSING",
            "post-entry data cannot be an entry feature",
        ),
        _record(
            "RAW_PRICE_ACTION",
            "SIGNAL_BAR_TERMINAL_M1_MOMENTUM",
            "CONTEXT",
            "T108-03",
            "causal anatomy runner; verdict not persisted in MD7",
            "causal anatomy runner; verdict not persisted in MD7",
            "42/18 trades;13 total losses",
            "NOT_IN_PRODUCTION",
            "UNRESOLVED",
            "ANATOMY_ONLY",
            "NO_ACCEPTED_RULE",
            "MD7_MISSING",
            "15 completed constituent M1 bars only",
        ),
        _record(
            "RAW_PRICE_ACTION",
            "PRE_ENTRY_EXTENSION_EXHAUSTION",
            "CONTEXT",
            "T108-04",
            "causal anatomy runner; no accepted pattern",
            "causal anatomy runner; no accepted pattern",
            "42/18 trades;13 total losses",
            "NOT_IN_PRODUCTION",
            "UNRESOLVED",
            "ANATOMY_ONLY",
            "NO_ACCEPTED_RULE",
            "MD7_MISSING",
            "fixed 1/2/3/5 completed M15 windows",
        ),
        _record(
            "RAW_PRICE_ACTION",
            "PRE_ENTRY_VOLATILITY_CHOPPINESS",
            "CONTEXT",
            "T108-05",
            "causal anatomy runner; no accepted pattern",
            "causal anatomy runner; no accepted pattern",
            "42/18 trades;13 total losses",
            "NOT_IN_PRODUCTION",
            "UNRESOLVED",
            "ANATOMY_ONLY",
            "NO_ACCEPTED_RULE",
            "MD7_MISSING",
            "raw price features; not ATR ADX or CHOP indicator",
        ),
        _record(
            "ALLIGATOR_MACD",
            "STRONG_ACTIVE_SEGMENT_PRODUCTION_COVERAGE",
            "CONTEXT",
            "T108-06",
            "139 strong;25 traded;114 missed;coverage=17.99pct",
            "80 strong;14 traded;66 missed;coverage=17.50pct",
            "139/80 strong segments",
            "DIAGNOSTIC_ONLY",
            "UNRESOLVED",
            "FACTUAL_COVERAGE",
            "LOW_COVERAGE_BOTH_PERIODS",
            "MD7_MISSING",
            "dominant missed reject is MACD_EXTREMUM_TOO_WEAK",
        ),
        _record(
            "MACD",
            "WEAK_REJECT_RESIDUAL_STRONG_SEGMENT_MOVE",
            "ENTRY",
            "T108-07,T108-08",
            "136 events;median=1.7375R;59 residual2R;41/114 segments",
            "96 events;median=2.2672R;51 residual2R;33/66 segments",
            "136/96 missed-segment weak rejects",
            "DIAGNOSTIC_ONLY",
            "UNRESOLVED",
            "OUTCOME_LABEL_ONLY",
            "35.96pct_VS_50.00pct_SEGMENT_COVERAGE",
            "MD7_MISSING",
            "residual 2R is not a simulated profitable trade",
        ),
    )


REQUIRED_EVIDENCE = (
    (
        "tests/runtime_workspace/"
        "run_algorithm_workspace_macd_production_comparison_runner_check.py",
        "ALGORITHM_WORKSPACE_MACD_PRODUCTION_COMPARISON_RUNNER_CHECK=OK",
    ),
    (
        "tests/runtime_workspace/"
        "run_algorithm_workspace_alligator_candidate_f_production_check.py",
        "ALGORITHM_WORKSPACE_ALLIGATOR_CANDIDATE_F_PRODUCTION_CHECK=OK",
    ),
    (
        "tests/runtime_temp/"
        "run_t104_12_algorithm_workspace_dominant_acceleration_stability_"
        "2025_2026_check.py",
        "T104_12_ALGORITHM_WORKSPACE_DOMINANT_ACCELERATION_STABILITY_CHECK=OK",
    ),
    (
        "tests/runtime_temp/"
        "run_t104_17_algorithm_workspace_bbw_compression_expansion_anatomy_"
        "2025_2026_check.py",
        "T104_17_ALGORITHM_WORKSPACE_BBW_COMPRESSION_EXPANSION_",
    ),
    (
        "tests/runtime_temp/"
        "run_t104_18_algorithm_workspace_ac_acceleration_anatomy_"
        "2025_2026_check.py",
        "T104_18_ALGORITHM_WORKSPACE_AC_ACCELERATION_ANATOMY_CHECK=OK",
    ),
    (
        "tests/runtime_temp/"
        "run_t104_20_algorithm_workspace_fractal_structural_sl_anatomy_"
        "2025_2026_check.py",
        "T104_20_FRACTAL_STRUCTURAL_SL_ANATOMY_CHECK=OK",
    ),
    (
        "tests/runtime_temp/"
        "run_t104_22_algorithm_workspace_causal_pivot_tp_policy_diagnostic_"
        "2025_2026_check.py",
        "T104_22_CAUSAL_PIVOT_TP_POLICY_DIAGNOSTIC_CHECK=OK",
    ),
    (
        "tests/runtime_temp/"
        "run_t104_23_algorithm_workspace_atr_structural_sl_distance_anatomy_"
        "2025_2026_check.py",
        "T104_23_ATR_STRUCTURAL_SL_DISTANCE_ANATOMY_CHECK=OK",
    ),
    (
        "tests/runtime_temp/"
        "run_t104_29_algorithm_workspace_causal_m1_m15_supertrend_ordering_"
        "prototype_2025_2026_check.py",
        "SUPERTREND_NO_EFFECT_UNDER_CURRENT_PRODUCTION_EXIT_STACK",
    ),
    (
        "tests/runtime_workspace/"
        "run_t105_18_stochastic_current_bar_production_regression_check.py",
        "T105_18_STOCHASTIC_CURRENT_BAR_PRODUCTION_REGRESSION=OK",
    ),
    (
        "tests/runtime_workspace/"
        "run_t106_04_no_change_production_truth_regression_check.py",
        "T106_04_NO_CHANGE_PRODUCTION_TRUTH_REGRESSION=OK",
    ),
    (
        "tests/runtime_workspace/"
        "run_t108_06_production_reject_anatomy_strong_trend_segments_check.py",
        "T108_06_PRODUCTION_REJECT_ANATOMY_STRONG_TREND_SEGMENTS=OK",
    ),
    (
        "tests/runtime_workspace/"
        "run_t108_07_macd_weak_prominence_missed_strong_segments_"
        "anatomy_check.py",
        "T108_07_MACD_WEAK_PROMINENCE_MISSED_STRONG_SEGMENTS_ANATOMY=OK",
    ),
    (
        "tests/runtime_workspace/"
        "run_t108_08_macd_weak_reject_residual_segment_move_anatomy_check.py",
        "T108_08_MACD_WEAK_REJECT_RESIDUAL_SEGMENT_MOVE_ANATOMY=OK",
    ),
)


def _tree_hash() -> str:
    """Порахувати deterministic hash production Python files і MD7."""

    paths = sorted((PROJECT_ROOT / "core").rglob("*.py")) + [MD7_PATH]
    digest = hashlib.sha256()
    for path in paths:
        relative_path = path.relative_to(PROJECT_ROOT).as_posix()
        digest.update(relative_path.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _assert_evidence(md7: str) -> None:
    """Підтвердити існування source runners і канонічних markers."""

    for relative_path, marker in REQUIRED_EVIDENCE:
        path = PROJECT_ROOT / relative_path
        assert path.is_file(), path
        assert marker in path.read_text(encoding="utf-8"), path

    required_md7 = (
        "# LGE Runtime 07 — RoadMap101–106",
        "SUPERTREND_NO_EFFECT_UNDER_CURRENT_PRODUCTION_EXIT_STACK",
        "Profit Drawdown threshold = 35%",
        "T105_18_STOCHASTIC_CURRENT_BAR_PRODUCTION_REGRESSION=OK",
        "roadmap106_decision=VARIANT_C_NO_CHANGE",
        "| CHOP       | 14",
        "`Zig Zag` не використовувати",
        "Volume Profile відкласти",
    )
    assert all(item in md7 for item in required_md7)
    assert "RoadMap107" not in md7
    assert "T108-06" not in md7
    assert "T108-07" not in md7
    assert "T108-08" not in md7


def _print_record(record: EvidenceRecord) -> None:
    """Надрукувати один компактний factual record у стабільній схемі."""

    print(
        f"family={record.family}|signal_or_event={record.signal_or_event}|"
        f"role={record.role}|source_test_ids={record.source_test_ids}|"
        f"causal_status={record.causal_status}|"
        f"completed_bars_only={record.completed_bars_only}|"
        f"lookahead_status={record.lookahead_status}|"
        f"2025_factual_result={record.factual_2025}|"
        f"2026_factual_result={record.factual_2026}|"
        f"sample_size_if_known={record.sample_size_if_known}|"
        f"production_status={record.production_status}|"
        f"research_status={record.research_status}|"
        f"positive_evidence_level={record.positive_evidence_level}|"
        f"cross_period_status={record.cross_period_status}|"
        f"md7_coverage={record.md7_coverage}|notes={record.notes}"
    )


def _print_counts(
    title: str,
    names: tuple[str, ...],
    counts: Counter[str],
) -> None:
    """Надрукувати повний набір status counts, включно з нулями."""

    print(title)
    for name in names:
        print(f"{name}={counts[name]}")


def _print_md7_gaps() -> None:
    """Надрукувати лише підтверджені missing/partial MD7 conclusions."""

    print("MD7_GAPS")
    print(
        "ROADMAP107_HIGH_LEVEL_CLOSURE|MD7_MISSING|"
        "review_before_canonical_transfer=True"
    )
    print(
        "BBW_AC_FRACTAL_PIVOT_ATR_QUANTITATIVE_CONCLUSIONS|MD7_PARTIAL|"
        "candidate_roles_present_but_quantitative_verdicts_absent=True"
    )
    print(
        "DONCHIAN_T105_INCREMENTAL_AND_REJECTED_ANATOMY|MD7_PARTIAL|"
        "production_gate_false_is_present=True"
    )
    print(
        "T108_01_TO_T108_05_ANATOMY|MD7_MISSING|"
        "research_detail_not_automatically_canonical=True"
    )
    print(
        "T108_06_STRONG_SEGMENT_COVERAGE_AND_DOMINANT_REJECT|MD7_MISSING|"
        "high_level_candidate_for_later_review=True"
    )
    print(
        "T108_07_PROMINENCE_ANATOMY|MD7_MISSING|"
        "simple_threshold_lowering_not_supported=True"
    )
    print(
        "T108_08_RESIDUAL_MOVE_LABELS|MD7_MISSING|"
        "not_simulated_trade_and_requires_later_review=True"
    )


def _print_supertrend_verdict() -> None:
    """Відокремити causal validity від нульового exit contribution."""

    print("SUPERTREND_VERDICT")
    print("causal_implementation_valid=True")
    print("directional_reversal_information_observed=True")
    print("standalone_exit_contribution_tested=True")
    print("standalone_exit_effect_under_current_stack=0")
    print("preempted_by=PROFIT_DRAWDOWN_OR_STOP_LOSS")
    print("actual_supertrend_exits=0")
    print("directional_value=UNRESOLVED_NOT_ZERO")
    print("indicator_rejected=False")
    print("production_wiring=False")
    print("verdict=SUPERTREND_NO_EFFECT_UNDER_CURRENT_PRODUCTION_EXIT_STACK")


def _print_roadmap108() -> None:
    """Надрукувати обов'язкові factual T108-06/07/08 results."""

    print("ROADMAP108_NEW_EVIDENCE")
    print(
        "T108-06|2025|strong_segments=139|traded=25|missed=114|"
        "coverage_percent=17.99"
    )
    print(
        "T108-06|2026|strong_segments=80|traded=14|missed=66|" "coverage_percent=17.50"
    )
    print("T108-06|dominant_missed_reject_reason=MACD_EXTREMUM_TOO_WEAK")
    print(
        "T108-07|2025|weak_events=136|all_median_ratio=.432371|"
        "missed_strong_median_ratio=.453853"
    )
    print(
        "T108-07|2026|weak_events=96|all_median_ratio=.401358|"
        "missed_strong_median_ratio=.433212"
    )
    print("T108-07|simple_prominence_threshold_lowering_supported=False")
    print(
        "T108-08|2025|weak_events=136|residual_move_r_median=1.7375|"
        "residual_2r_events=59|segments=41/114|coverage_percent=35.96"
    )
    print(
        "T108-08|2026|weak_events=96|residual_move_r_median=2.2672|"
        "residual_2r_events=51|segments=33/66|coverage_percent=50.00"
    )
    print("T108-08|future_movement_role=OUTCOME_LABEL_ONLY")
    print("T108-08|residual_2r_is_simulated_profitable_trade=False")


def main() -> None:
    """Виконати read-only evidence/MD7 coverage audit T108-09."""

    before = _tree_hash()
    md7 = MD7_PATH.read_text(encoding="utf-8")
    _assert_evidence(md7)
    records = _inventory()
    assert len(records) == 35

    print("T108_09_RESEARCH_EVIDENCE_INVENTORY")
    for record in records:
        _print_record(record)

    status_counts = Counter(record.research_status for record in records)
    md7_counts = Counter(record.md7_coverage for record in records)
    _print_counts("STATUS_COUNTS", RESEARCH_STATUSES, status_counts)
    _print_counts("MD7_COVERAGE_COUNTS", MD7_STATUSES, md7_counts)
    _print_md7_gaps()
    _print_supertrend_verdict()
    _print_roadmap108()

    after = _tree_hash()
    assert before == after
    print("SAFETY")
    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    print("audit_only=True")
    print("production_logic_changed=False")
    print("production_threshold_changed=False")
    print("md7_changed=False")
    print("new_entry_rule_created=False")
    print("new_exit_rule_created=False")
    print("score_model_created=False")
    print("weights_created=False")
    print("optimization_performed=False")
    print("threshold_sweep_performed=False")
    print("counterfactual_trades_simulated=False")
    print("broker_requests=0")
    print("broker_execution_attempted=False")
    print("T108_09_RESEARCH_EVIDENCE_MD7_COVERAGE_AUDIT=OK")


if __name__ == "__main__":
    main()
