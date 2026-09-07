"""run_t108_18_roadmap108_evidence_synthesis_check.py — T108-18.

TEST_ONLY runnable збирає прийняті evidence contracts T108-06…T108-17 в
один контрольний RoadMap108 branch ledger. Він перевіряє наявність усіх
runner-джерел, їхні causal/safety marker-и, exact MS_BUY P3/P4 hypothesis,
factual baseline constants та поля, на яких ґрунтуються qualitative branch
decisions. Числа, що існували лише у виконаних output, не вигадуються і не
перераховуються: замість нового Replay перевіряються canonical invariants
runner-ів та вже прийняті result semantics.

Результат формально відділяє rejected current implementations від ширшої
невирішеної multi-signal architecture і залишає один наступний стан:
RESEARCH_DESIGN_REQUIRED. Модуль не читає market data, не створює trades,
не вибирає weights, persistence чи thresholds, не змінює production або MD7
і не створює нової trading logic.
"""

from __future__ import annotations

import ast
import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

TEST_ID = "T108-18"
MODE = "RM108_T108_18_ROADMAP108_EVIDENCE_SYNTHESIS_TEST_ONLY"
SOURCE_IDS = tuple(f"T108-{number:02d}" for number in range(6, 18))
EXPECTED_BASELINE = {
    "2025": (42, 30, 11, 1, 4.03, 1.5424, 3.58),
    "2026": (18, 15, 2, 1, 3.68, 3.7669, 1.20),
}

SOURCE_FILES = {
    "T108-06": "run_t108_06_production_reject_anatomy_strong_trend_segments_check.py",
    "T108-07": (
        "run_t108_07_macd_weak_prominence_missed_strong_segments_anatomy_check.py"
    ),
    "T108-08": "run_t108_08_macd_weak_reject_residual_segment_move_anatomy_check.py",
    "T108-09": "run_t108_09_research_evidence_md7_coverage_audit_check.py",
    "T108-10": "run_t108_10_directional_signal_persistence_anatomy_check.py",
    "T108-11": "run_t108_11_unweighted_family_vote_anatomy_check.py",
    "T108-12": "run_t108_12_signed_family_combination_anatomy_check.py",
    "T108-13": "run_t108_13_exact_family_composition_position_state_anatomy_check.py",
    "T108-14": "run_t108_14_intra_trade_m1_opposite_evidence_timing_anatomy_check.py",
    "T108-15": "run_t108_15_opportunity_normalized_opposite_evidence_anatomy_check.py",
    "T108-16": "run_t108_16_ms_buy_flat_counterfactual_entry_replay_check.py",
    "T108-17": "run_t108_17_ms_buy_counterfactual_excursion_payoff_anatomy_check.py",
}

SOURCE_CONTRACTS = {
    "T108-06": (
        "strong_segment_trade_coverage_percent",
        "dominant_missed_reject_reason=",
        "filter_reason_code",
        "T108_06_PRODUCTION_REJECT_ANATOMY_STRONG_TREND_SEGMENTS=OK",
    ),
    "T108-07": (
        "PRODUCTION_MACD_EXTREMUM_TOO_WEAK_REJECT_EVENTS",
        "threshold_sweep_performed=False",
        "production_threshold_changed=False",
        "T108_07_MACD_WEAK_PROMINENCE_MISSED_STRONG_SEGMENTS_ANATOMY=OK",
    ),
    "T108-08": (
        "residual_2r_events",
        "counterfactual_trades_simulated=False",
        "T108_08_MACD_WEAK_REJECT_RESIDUAL_SEGMENT_MOVE_ANATOMY=OK",
    ),
    "T108-09": (
        "coverage_percent=17.99",
        "coverage_percent=17.50",
        "dominant_missed_reject_reason=MACD_EXTREMUM_TOO_WEAK",
        "T108_09_RESEARCH_EVIDENCE_MD7_COVERAGE_AUDIT=OK",
    ),
    "T108-10": (
        "STOCHASTIC_KD_CROSS_14_1_3",
        "SUPERTREND_DIRECTION_SWITCH_10_3",
        "T108_10_DIRECTIONAL_SIGNAL_PERSISTENCE_ANATOMY=OK",
    ),
    "T108-11": (
        "ABS_SCORE_ANATOMY",
        "MONOTONICITY_CHECK",
        "SUPERTREND_CONTROL_COMPARISON",
        "T108_11_UNWEIGHTED_FAMILY_VOTE_ANATOMY=OK",
    ),
    "T108-12": (
        '"MS_BUY"',
        '"MAS_SELL"',
        "CONFLICT_COMBINATIONS",
        "max_one_vote_per_family=True",
        "T108_12_SIGNED_FAMILY_COMBINATION_ANATOMY=OK",
    ),
    "T108-13": (
        'POSITION_STATES = ("FLAT", "LONG", "SHORT")',
        'FOCUS_CLASSES = ("MS_BUY", "MAS_SELL")',
        "OPPOSITE_SIGNAL_BEFORE_PRODUCTION_EXIT",
        "T108_13_EXACT_FAMILY_COMPOSITION_POSITION_STATE_ANATOMY=OK",
    ),
    "T108-14": (
        "FAMILY_OPPOSITE_EVIDENCE",
        "state_lifetime=CURRENT_COMPLETED_M15_ONLY",
        "supertrend_included=False",
        "T108_14_INTRA_TRADE_M1_OPPOSITE_EVIDENCE_TIMING_ANATOMY=OK",
    ),
    "T108-15": (
        "stochastic_loss_enrichment_among_eligible_trades",
        "macd_cross_period_stable_loss_pattern",
        "alligator_remains_zero_opposite",
        "T108_15_OPPORTUNITY_NORMALIZED_OPPOSITE_EVIDENCE_ANATOMY=OK",
    ),
    "T108-16": (
        "MS_BUY_STATE = (1, 0, 1)",
        "VARIANTS = (3, 4)",
        "profit_factor=",
        "canonical_exit_stack_preserved=True",
        "T108_16_MS_BUY_FLAT_COUNTERFACTUAL_ENTRY_REPLAY=OK",
    ),
    "T108-17": (
        "LOSS_EXCURSION_ANATOMY",
        "WIN_PAYOFF_ANATOMY",
        'return "mostly_small"',
        "cross_period_pattern_stable=",
        "T108_17_MS_BUY_COUNTERFACTUAL_EXCURSION_PAYOFF_ANATOMY=OK",
    ),
}


@dataclass(frozen=True, slots=True)
class EvidenceSource:
    """Один перевірений RoadMap108 runner та його immutable source facts."""

    test_id: str
    path: Path
    text: str
    sha256: str


@dataclass(frozen=True, slots=True)
class BranchDecision:
    """Формальний status, evidence summary та заборонене трактування гілки."""

    code: str
    status: str
    evidence: str
    restriction: str


BRANCHES = (
    BranchDecision(
        "STRICT_PRODUCTION_ENTRY_COVERAGE",
        "RESEARCH_PROBLEM_CONFIRMED",
        "CROSS_PERIOD_COVERAGE_NEAR_18_PERCENT|DOMINANT_REJECT_EXTREMUM_TOO_WEAK|"
        "WEAK_REJECT_NOT_NEAR_THRESHOLD_CONCENTRATED|SUBSTANTIAL_RESIDUAL_MOVE_EXISTS",
        "DOES_NOT_IMPLY_LOWERING_MACD_THRESHOLD",
    ),
    BranchDecision(
        "SIMPLE_MACD_THRESHOLD_LOWERING",
        "REJECTED_AS_UNSUPPORTED",
        "MISSED_WEAK_POPULATION_NOT_PREDOMINANTLY_NEAR_THRESHOLD",
        "NO_THRESHOLD_SWEEP",
    ),
    BranchDecision(
        "GENERIC_UNWEIGHTED_3_FAMILY_SCORE",
        "REJECTED_IN_CURRENT_SIMPLE_FORM",
        "STOCHASTIC_DUTY_CYCLE_DOMINATES|ABS_SCORE_NOT_MONOTONIC|"
        "EXACT_COMPOSITION_MATTERS|CONFLICTS_NOT_SOLVED_BY_SIMPLE_MAJORITY",
        "NO_SCORE_THRESHOLD",
    ),
    BranchDecision(
        "SUPERTREND_DIRECT_DIRECTION_VOTE",
        "REJECTED_AS_STANDALONE_DIRECTIONAL_VOTE",
        "DIRECT_TERNARY_VOTE_DID_NOT_ADD_STABLE_DIRECTIONAL_VALUE",
        "DOES_NOT_MEAN_SUPERTREND_USELESS",
    ),
    BranchDecision(
        "CURRENT_MAS_EXIT_REVERSE_BRANCH",
        "CLOSED_FOR_CURRENT_SEMANTICS",
        "POSITION_SAMPLE_SPARSE|OPPOSITE_EVIDENCE_RARE|STOCHASTIC_NOT_STABLE_"
        "AFTER_OPPORTUNITY_NORMALIZATION|MACD_UNSTABLE|ALLIGATOR_OPPOSITE_ZERO",
        "NO_REVERSE_LOGIC",
    ),
    BranchDecision(
        "EXACT_MS_BUY_FLAT_P3_P4_ADDED_ENTRY",
        "REJECTED_AS_ADDED_ENTRY_HYPOTHESIS",
        "NEXT_M15_ANATOMY_SOMETIMES_POSITIVE|ALL_FOUR_REPLAY_POPULATIONS_NET_"
        "NEGATIVE_AND_PF_LT_1|IMPULSE_MOSTLY_SMALL|LOSSES_RARELY_REACHED_0_25R|"
        "NO_LOSS_REACHED_0_50R|CROSS_PERIOD_PATTERN_STABLE",
        "NO_POST_HOC_FILTER_OR_EXIT_CHANGE",
    ),
    BranchDecision(
        "MAS_SELL",
        "RESEARCH_ONLY_SMALL_SAMPLE",
        "SMALL_EXACT_STATE_SAMPLES|LONG_EXIT_OVERLAP_ZERO|FLAT_PERSISTENCE_UNSTABLE",
        "NO_REPLAY_IN_T108_18",
    ),
    BranchDecision(
        "MULTI_SIGNAL_SCORE_ENGINE_AS_ARCHITECTURE",
        "ARCHITECTURE_UNRESOLVED",
        "ONLY_UNWEIGHTED_DIRECT_TERNARY_PERSISTENCE_MAJORITY_FORM_REJECTED",
        "NEW_CAUSAL_EVIDENCE_DESIGN_REQUIRED_BEFORE_PRODUCTION",
    ),
)

FINAL_DECISIONS = (
    ("strict_entry_coverage_problem", "CONFIRMED"),
    ("simple_macd_threshold_lowering", "REJECTED"),
    ("generic_unweighted_mas_score", "REJECTED_CURRENT_FORM"),
    ("supertrend_direct_vote", "REJECTED_STANDALONE"),
    ("current_mas_exit_reverse", "CLOSED_CURRENT_SEMANTICS"),
    ("ms_buy_flat_p3_p4_added_entry", "REJECTED"),
    ("mas_sell", "RESEARCH_ONLY_SMALL_SAMPLE"),
    ("multi_signal_score_engine_architecture", "UNRESOLVED"),
)


def _source(test_id: str) -> EvidenceSource:
    """Прочитати один source runner і перевірити всі required fragments."""

    path = TEST_ROOT / SOURCE_FILES[test_id]
    assert path.is_file(), path
    text = path.read_text(encoding="utf-8-sig")
    for fragment in SOURCE_CONTRACTS[test_id]:
        assert fragment in text, (test_id, fragment)
    return EvidenceSource(
        test_id=test_id,
        path=path,
        text=text,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )


def _literal_assignment(source: EvidenceSource, name: str) -> Any:
    """Без імпорту runner прочитати literal top-level assignment із AST."""

    tree = ast.parse(source.text, filename=str(source.path))
    source_lines = source.text.splitlines()
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and target.id == name:
            value = node.value
            assert value.end_lineno is not None
            assert value.end_col_offset is not None
            selected = source_lines[value.lineno - 1 : value.end_lineno]  # noqa: E203
            assert selected
            selected[0] = selected[0][value.col_offset :]  # noqa: E203
            selected[-1] = selected[-1][: value.end_col_offset]
            return ast.literal_eval("\n".join(selected))
    raise AssertionError((source.test_id, name))


def _assert_canonical_invariants(sources: dict[str, EvidenceSource]) -> None:
    """Підтвердити baseline, exact hypothesis, variants і descriptive R bins."""

    t108_16 = sources["T108-16"]
    t108_17 = sources["T108-17"]
    assert _literal_assignment(t108_16, "EXPECTED_BASELINE") == EXPECTED_BASELINE
    assert _literal_assignment(t108_16, "VARIANTS") == (3, 4)
    assert _literal_assignment(t108_16, "MS_BUY_STATE") == (1, 0, 1)
    assert _literal_assignment(t108_17, "R_LEVELS") == (0.25, 0.50, 1.0, 2.0)
    assert "future_bars_after_factual_exit_used=False" in t108_17.text
    assert "alternative_exit_simulated=False" in t108_17.text


def _print_source_audit(sources: dict[str, EvidenceSource]) -> None:
    """Надрукувати deterministic inventory перевірених evidence runners."""

    print("EVIDENCE_SOURCE_AUDIT")
    for test_id in SOURCE_IDS:
        source = sources[test_id]
        print(
            f"test_id={test_id}|file={source.path.name}|"
            f"source_contract_verified=True|sha256={source.sha256}"
        )
    print("evidence_source_count=12")
    print("canonical_baseline_2025=42|30|11|1|4.03|1.5424|3.58")
    print("canonical_baseline_2026=18|15|2|1|3.68|3.7669|1.20")
    print("exact_ms_buy_state=1|0|1")
    print("counterfactual_variants=P3_P4")


def _print_branch_evidence() -> None:
    """Надрукувати status кожної гілки з обмеженням її трактування."""

    print("BRANCH_EVIDENCE")
    for branch in BRANCHES:
        print(
            f"branch={branch.code}|decision={branch.status}|"
            f"evidence={branch.evidence}|restriction={branch.restriction}"
        )


def main() -> int:
    """Виконати статичний T108-18 synthesis без Replay або market data."""

    sources = {test_id: _source(test_id) for test_id in SOURCE_IDS}
    assert tuple(sources) == SOURCE_IDS
    _assert_canonical_invariants(sources)

    print("T108_18_ROADMAP108_EVIDENCE_SYNTHESIS")
    _print_source_audit(sources)
    _print_branch_evidence()
    print("ROADMAP108_BRANCH_DECISIONS")
    for key, value in FINAL_DECISIONS:
        print(f"{key}={value}")
    print("NEXT_RECOMMENDED_BRANCH")
    print("NEXT_STEP=RESEARCH_DESIGN_REQUIRED")
    print(
        "reason=SIMPLE_SIGNAL_ADDITION_PERSISTENCE_AND_MAJORITY_VOTE_"
        "FAILED_NEW_CAUSAL_EVIDENCE_DESIGN_REQUIRED"
    )

    print("SAFETY")
    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    print("new_market_replay=False")
    print("new_counterfactual_trades=False")
    print("new_entry_logic=False")
    print("new_exit_logic=False")
    print("reverse_logic_created=False")
    print("score_threshold_selected=False")
    print("weights_selected=False")
    print("persistence_selected=False")
    print("threshold_sweep_performed=False")
    print("optimization_performed=False")
    print("production_logic_changed=False")
    print("production_threshold_changed=False")
    print("md7_changed=False")
    print("broker_requests=0")
    print("broker_execution_attempted=False")
    print("T108_18_ROADMAP108_EVIDENCE_SYNTHESIS=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
