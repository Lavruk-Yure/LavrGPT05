"""run_t108_24_roadmap108_final_evidence_closure_check.py

TEST_ONLY runner статично закриває evidence ledger RoadMap108 T108-06…T108-23.
Він читає лише Python-джерела попередніх runner-ів, перевіряє їхні фактичні
constants, assertions, output fields, final marker-и та causal/safety
contracts,
після чого друкує прийняті branch conclusions і фінальні рішення RoadMap108.

Точні підсумки T108-23 зафіксовані як прийнятий GREEN execution result і
додатково узгоджуються із source-level population/threshold contracts T108-23.
Модуль не імпортує попередні runner-и, не читає market data та не запускає
Replay,
не симулює trades, не створює гіпотез чи cutoff-ів і не змінює production або
MD7. Його єдиний результат — deterministic static closure report із safety
marker-ами та наступним станом ROADMAP108_CLOSE_RESEARCH_ONLY.
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path
from typing import Any

TEST_ROOT = Path(__file__).resolve().parent
TEST_ID = "T108-24"
MODE = "RM108_T108_24_FINAL_EVIDENCE_CLOSURE_TEST_ONLY"
SOURCE_IDS = tuple(f"T108-{number:02d}" for number in range(6, 24))

SOURCE_FILES = {
    "T108-06": (
        "run_t108_06_production_reject_anatomy_strong_trend_segments_check.py"
    ),
    "T108-07": (
        "run_t108_07_macd_weak_prominence_missed_strong_segments_"
        "anatomy_check.py"
    ),
    "T108-08": (
        "run_t108_08_macd_weak_reject_residual_segment_move_anatomy_check.py"
    ),
    "T108-09": "run_t108_09_research_evidence_md7_coverage_audit_check.py",
    "T108-10": "run_t108_10_directional_signal_persistence_anatomy_check.py",
    "T108-11": "run_t108_11_unweighted_family_vote_anatomy_check.py",
    "T108-12": "run_t108_12_signed_family_combination_anatomy_check.py",
    "T108-13": (
        "run_t108_13_exact_family_composition_position_state_anatomy_check.py"
    ),
    "T108-14": (
        "run_t108_14_intra_trade_m1_opposite_evidence_timing_anatomy_check.py"
    ),
    "T108-15": (
        "run_t108_15_opportunity_normalized_opposite_evidence_anatomy_check.py"
    ),
    "T108-16": "run_t108_16_ms_buy_flat_counterfactual_entry_replay_check.py",
    "T108-17": (
        "run_t108_17_ms_buy_counterfactual_excursion_payoff_anatomy_check.py"
    ),
    "T108-18": "run_t108_18_roadmap108_evidence_synthesis_check.py",
    "T108-19": (
        "run_t108_19_dominant_reject_conditional_evidence_anatomy_check.py"
    ),
    "T108-20": (
        "run_t108_20_macd_weak_reject_internal_temporal_geometry_"
        "anatomy_check.py"
    ),
    "T108-21": (
        "run_t108_21_first_weak_reject_counterfactual_entry_replay_check.py"
    ),
    "T108-22": (
        "run_t108_22_causal_weak_reject_population_rebuild_anatomy_check.py"
    ),
    "T108-23": (
        "run_t108_23_weak_prominence_existing_distance_gate_"
        "counterfactual_entry_check.py"
    ),
}

SOURCE_CONTRACTS = {
    "T108-06": (
        "strong_segment_trade_coverage_percent",
        "dominant_missed_reject_reason=",
        "T108_06_PRODUCTION_REJECT_ANATOMY_STRONG_TREND_SEGMENTS=OK",
    ),
    "T108-07": (
        "PRODUCTION_MACD_EXTREMUM_TOO_WEAK_REJECT_EVENTS",
        "threshold_sweep_performed=False",
        "T108_07_MACD_WEAK_PROMINENCE_MISSED_STRONG_SEGMENTS_ANATOMY=OK",
    ),
    "T108-08": (
        "residual_2r_events",
        "counterfactual_trades_simulated=False",
        "T108_08_MACD_WEAK_REJECT_RESIDUAL_SEGMENT_MOVE_ANATOMY=OK",
    ),
    "T108-09": (
        "139 strong;25 traded;114 missed;coverage=17.99pct",
        "80 strong;14 traded;66 missed;coverage=17.50pct",
        "simple_prominence_threshold_lowering_supported=False",
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
        "T108_11_UNWEIGHTED_FAMILY_VOTE_ANATOMY=OK",
    ),
    "T108-12": (
        "CONFLICT_COMBINATIONS",
        "max_one_vote_per_family=True",
        "T108_12_SIGNED_FAMILY_COMBINATION_ANATOMY=OK",
    ),
    "T108-13": (
        'POSITION_STATES = ("FLAT", "LONG", "SHORT")',
        "OPPOSITE_SIGNAL_BEFORE_PRODUCTION_EXIT",
        "T108_13_EXACT_FAMILY_COMPOSITION_POSITION_STATE_ANATOMY=OK",
    ),
    "T108-14": (
        "FAMILY_OPPOSITE_EVIDENCE",
        "supertrend_included=False",
        "T108_14_INTRA_TRADE_M1_OPPOSITE_EVIDENCE_TIMING_ANATOMY=OK",
    ),
    "T108-15": (
        "alligator_remains_zero_opposite",
        "T108_15_OPPORTUNITY_NORMALIZED_OPPOSITE_EVIDENCE_ANATOMY=OK",
    ),
    "T108-16": (
        "MS_BUY_STATE = (1, 0, 1)",
        "canonical_exit_stack_preserved=True",
        "T108_16_MS_BUY_FLAT_COUNTERFACTUAL_ENTRY_REPLAY=OK",
    ),
    "T108-17": (
        "LOSS_EXCURSION_ANATOMY",
        "alternative_exit_simulated=False",
        "T108_17_MS_BUY_COUNTERFACTUAL_EXCURSION_PAYOFF_ANATOMY=OK",
    ),
    "T108-18": (
        '"simple_macd_threshold_lowering", "REJECTED"',
        '"multi_signal_score_engine_architecture", "UNRESOLVED"',
        "T108_18_ROADMAP108_EVIDENCE_SYNTHESIS=OK",
    ),
    "T108-19": (
        "NO_CONDITIONAL_RESCUE_EVIDENCE",
        "future_movement_role=OUTCOME_LABEL_ONLY",
        "T108_19_DOMINANT_REJECT_CONDITIONAL_EVIDENCE_ANATOMY=OK",
    ),
    "T108-20": (
        'EXPECTED_COUNTS = {"2025": 136, "2026": 96}',
        '"prominence_geometry": _combined_decision(',
        "NO_STABLE_SEPARATION",
        "T108_20_MACD_WEAK_REJECT_INTERNAL_TEMPORAL_GEOMETRY_ANATOMY=OK",
    ),
    "T108-21": (
        "CAUSAL_ENTRY_HYPOTHESIS_NOT_EXECUTABLE=True",
        "future_segment_information_detected_in_population=True",
        "T108_21_FIRST_WEAK_REJECT_COUNTERFACTUAL_ENTRY_REPLAY=OK",
    ),
    "T108-22": (
        "population=all_factual_weak_reject_events",
        "future_segment_information_used=False",
        "T108_22_CAUSAL_WEAK_REJECT_POPULATION_REBUILD_ANATOMY=OK",
    ),
    "T108-23": (
        'EXPECTED_POPULATIONS = {"2025": 1679, "2026": 1209}',
        "threshold_source=ACTUAL_CONFIGURED_PRODUCTION_SOURCE",
        "normalized_distance_role=RECONCILIATION_ONLY",
        'marker = "T108_23_WEAK_PROMINENCE_EXISTING_DISTANCE_GATE"',
        'print(f"{marker}_COUNTERFACTUAL_ENTRY=OK")',
    ),
}

ACCEPTED_T108_23_RESULTS = {
    "2025": (1679, 751, 747, -84.65, 0.5346, -0.0930),
    "2026": (1209, 483, 472, -39.85, 0.6087, -0.0618),
}

BRANCH_CONCLUSIONS = (
    ("strict_entry_coverage_problem", "CONFIRMED"),
    ("global_macd_prominence_threshold_lowering", "REJECTED"),
    ("weak_reject_population_has_future_move", "CONFIRMED_DESCRIPTIVE_ONLY"),
    ("simple_unweighted_multi_family_score", "REJECTED_CURRENT_FORM"),
    ("supertrend_direct_directional_vote", "REJECTED_STANDALONE"),
    ("current_mas_exit_reverse_branch", "CLOSED_CURRENT_SEMANTICS"),
    ("ms_buy_added_entry", "REJECTED"),
    ("known_external_confirmation_rescue", "NOT_SUPPORTED"),
    ("t10820_hindsight_selected_first_reject_advantage", "INVALID_FOR_ENTRY"),
    ("causal_weak_reject_population_rebuild", "CONFIRMED"),
    ("first_reject_causal_advantage", "REJECTED"),
    ("distance_geometry_descriptive_separation", "CONFIRMED"),
    ("existing_production_distance_gate_added_entry", "REJECTED"),
    (
        "angle_cutoff_hypothesis",
        "NOT_TESTED_NO_PREDECLARED_PRODUCTION_THRESHOLD",
    ),
    ("steepness_hypothesis", "NOT_ADVANCED_CROSS_PERIOD_INSTABILITY"),
    ("strict_entry_rescue_branch", "EXHAUSTED_CURRENT_EVIDENCE"),
)

FINAL_DECISIONS = (
    ("strict_entry_coverage_problem", "CONFIRMED"),
    ("global_macd_threshold_lowering", "REJECTED"),
    ("simple_unweighted_multi_signal_score", "REJECTED_CURRENT_FORM"),
    ("supertrend_direct_vote", "REJECTED_STANDALONE"),
    ("current_mas_exit_reverse", "CLOSED_CURRENT_SEMANTICS"),
    ("ms_buy_added_entry", "REJECTED"),
    ("known_confirmation_rescue", "NOT_SUPPORTED"),
    ("first_weak_reject_entry", "REJECTED_AFTER_CAUSAL_REBUILD"),
    ("existing_distance_gate_entry", "REJECTED"),
    ("angle_threshold", "NOT_TESTED_NO_PREDECLARED_THRESHOLD"),
    ("steepness_threshold", "NOT_ADVANCED"),
    ("multi_signal_score_engine_architecture", "UNRESOLVED"),
    ("strict_entry_rescue_branch", "EXHAUSTED_CURRENT_EVIDENCE"),
    ("production_change_required", False),
)


def _read_sources() -> dict[str, tuple[Path, str, str]]:
    """Прочитати всі runner-и та перевірити required source fragments."""

    sources: dict[str, tuple[Path, str, str]] = {}
    for test_id in SOURCE_IDS:
        path = TEST_ROOT / SOURCE_FILES[test_id]
        assert path.is_file(), path
        text = path.read_text(encoding="utf-8-sig")
        for fragment in SOURCE_CONTRACTS[test_id]:
            assert fragment in text, (test_id, fragment)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        sources[test_id] = path, text, digest
    return sources


def _literal_assignment(text: str, path: Path, name: str) -> Any:
    """Без імпорту runner прочитати його literal top-level assignment."""

    tree = ast.parse(text, filename=str(path))
    source_lines = text.splitlines()
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id != name:
            continue
        value = node.value
        assert value.end_lineno is not None
        assert value.end_col_offset is not None
        selected = source_lines[
            value.lineno - 1 : value.end_lineno  # noqa: E203
        ]
        selected[0] = selected[0][value.col_offset :]  # noqa: E203
        selected[-1] = selected[-1][: value.end_col_offset]
        return ast.literal_eval("\n".join(selected))
    raise AssertionError((path.name, name))


def _assert_cross_source_facts(
    sources: dict[str, tuple[Path, str, str]],
) -> None:
    """Звірити literal population, threshold і causal gate між джерелами."""

    path_20, text_20, _ = sources["T108-20"]
    path_21, text_21, _ = sources["T108-21"]
    path_23, text_23, _ = sources["T108-23"]
    assert _literal_assignment(text_20, path_20, "EXPECTED_COUNTS") == {
        "2025": 136,
        "2026": 96,
    }
    assert _literal_assignment(text_21, path_21, "EXPECTED_FIRST_COUNTS") == {
        "2025": 74,
        "2026": 50,
    }
    expected_populations = _literal_assignment(
        text_23,
        path_23,
        "EXPECTED_POPULATIONS",
    )
    expected_threshold = _literal_assignment(
        text_23,
        path_23,
        "EXPECTED_THRESHOLD",
    )
    assert expected_populations == {"2025": 1679, "2026": 1209}
    assert expected_threshold == 0.00005
    for period, result in ACCEPTED_T108_23_RESULTS.items():
        population, gate_pass, trades, net, profit_factor, mean_r = result
        assert population == expected_populations[period]
        assert 0 < trades <= gate_pass <= population
        assert net < 0.0 and profit_factor < 1.0 and mean_r < 0.0


def _print_source_audit(
    sources: dict[str, tuple[Path, str, str]],
) -> None:
    """Надрукувати deterministic inventory перевірених source runner-ів."""

    print("SOURCE_CONTRACT_AUDIT")
    for test_id in SOURCE_IDS:
        path, _, digest = sources[test_id]
        print(
            f"test_id={test_id}|file={path.name}|"
            f"source_contract_verified=True|sha256={digest}"
        )
    print("verified_source_contracts=T108-06...T108-23")
    print("evidence_source_count=18")


def _print_t108_23_results() -> None:
    """Надрукувати точний прийнятий GREEN result останньої entry-перевірки."""

    print("T108_23_ACCEPTED_GREEN_RESULT")
    print("result_provenance=VERIFIED_LOCAL_T108_23_EXECUTION_OUTPUT")
    print("production_minimum_distance=0.0000500000")
    print("threshold_source=ACTUAL_CONFIGURED_PRODUCTION_SOURCE")
    print("new_cutoff=False")
    for period in ("2025", "2026"):
        population, gate_pass, trades, net, profit_factor, mean_r = (
            ACCEPTED_T108_23_RESULTS[period]
        )
        print(
            f"period={period}|all_weak={population}|gate_pass={gate_pass}|"
            f"completed_trades={trades}|net={net:.2f}|"
            f"profit_factor={profit_factor:.4f}|mean_r={mean_r:.4f}"
        )


def main() -> int:
    """Виконати фінальне статичне закриття RoadMap108 без Replay."""

    sources = _read_sources()
    assert tuple(sources) == SOURCE_IDS
    _assert_cross_source_facts(sources)

    print("T108_24_ROADMAP108_FINAL_EVIDENCE_CLOSURE")
    _print_source_audit(sources)
    print("BRANCH_CONCLUSIONS")
    for key, value in BRANCH_CONCLUSIONS:
        print(f"{key}={value}")
    print("normalized_distance_role=SAME_GEOMETRY_NOT_INDEPENDENT_SIGNAL")
    print(
        "supertrend_interpretation="
        "NOT_USELESS_ONLY_REJECTED_STANDALONE_VOTE"
    )
    _print_t108_23_results()

    print("ROADMAP108_FINAL_DECISIONS")
    for key, value in FINAL_DECISIONS:
        print(f"{key}={value}")
    print("NEXT_STEP=ROADMAP108_CLOSE_RESEARCH_ONLY")

    print("SAFETY")
    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    print("new_replay_run=False")
    print("new_trade_simulation=False")
    print("new_hypothesis_created=False")
    print("threshold_sweep_performed=False")
    print("optimization_performed=False")
    print("classifier_created=False")
    print("weights_used=False")
    print("production_logic_changed=False")
    print("production_threshold_changed=False")
    print("md7_changed=False")
    print("broker_requests=0")
    print("broker_execution_attempted=False")
    print("T108_24_ROADMAP108_FINAL_EVIDENCE_CLOSURE=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
