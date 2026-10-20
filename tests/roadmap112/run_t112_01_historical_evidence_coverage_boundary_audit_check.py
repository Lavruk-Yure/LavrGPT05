"""T112-01 — Historical Evidence & Coverage Boundary Audit — TEST_ONLY.

Статично зіставити чинний production baseline, T108-06/T108-24 та два
раніші способи діагностики трендів із RoadMap102/103. Ніякого імпорту
runtime, Replay, модифікації порогів, дослідження нового entry чи запису у
проєкт. Історичні числа є evidence, а не результатом нового прогону.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ID = "T112-01"
MODE = "RM112_T112_01_HISTORICAL_EVIDENCE_COVERAGE_BOUNDARY_AUDIT_TEST_ONLY"

SOURCES = {
    "T105-18": "tests/runtime_workspace/"
    "run_t105_18_stochastic_current_bar_production_regression_check.py",
    "T108-06": "tests/runtime_workspace/"
    "run_t108_06_production_reject_anatomy_strong_trend_segments_check.py",
    "T108-09": "tests/runtime_workspace/"
    "run_t108_09_research_evidence_md7_coverage_audit_check.py",
    "T108-24": "tests/runtime_workspace/"
    "run_t108_24_roadmap108_final_evidence_closure_check.py",
    "RM102_PRICE_ONLY": "tests/runtime_temp/"
    "run_algorithm_workspace_candidate_f_trend_coverage_2025_check.py",
    "RM103_ACTIVE_INVENTORY": "tests/runtime_temp/"
    "run_algorithm_workspace_candidate_f_alligator_active_no_position_"
    "trend_inventory_2025_check.py",
    "MD7": "doc/LGE_Runtime_07.md",
}


def _read_sources() -> dict[str, str]:
    """Прочитати наявні sources без імпорту production і без записів."""
    result: dict[str, str] = {}
    for identifier, relative_path in SOURCES.items():
        path = PROJECT_ROOT / relative_path
        assert path.is_file(), path
        result[identifier] = path.read_text(encoding="utf-8-sig")
    return result


def _tree(text: str, identifier: str) -> ast.Module:
    """Перевірити синтаксис джерела і повернути його AST."""
    return ast.parse(text, filename=SOURCES[identifier])


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    """Взяти функцію з AST за її точним іменем."""
    matches = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    assert len(matches) == 1, name
    return matches[0]


def _code(text: str, node: ast.AST) -> str:
    """Отримати текст AST-функції для source-contract перевірок."""
    result = ast.get_source_segment(text, node)
    assert result is not None
    return result


def _literal(tree: ast.Module, name: str):
    """Отримати top-level literal константу без імпорту модуля."""
    matches: list[ast.expr] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and target.id == name:
            matches.append(node.value)
    assert len(matches) == 1, name
    return ast.literal_eval(matches[0])


def _audit_baseline(sources: dict[str, str]) -> None:
    """Перевірити канонічний baseline, але не стверджувати нового Replay."""
    baseline = sources["T105-18"]
    doc = sources["MD7"]
    assert '"2025": ProductionExpectation(42, 30, 11, 1, 4.03, 1.5424, 3.58' in baseline
    assert '"2026": ProductionExpectation(18, 15, 2, 1, 3.68, 3.7669, 1.20' in baseline
    for item in (
        "2025: 42 trades | 30W | 11L | 1 BE | net +4.03 | PF 1.5424 | DD 3.58",
        "2026: 18 trades | 15W | 2L  | 1 BE | net +3.68 | PF 3.7669 | DD 1.20",
        "SL = max(signal_bar_range, spread*10)",
        "TP = 2R",
        "Profit Drawdown = 35%",
        "negative-PD recovery = unchanged",
    ):
        assert item in doc, item
    assert "_assert_stochastic_path" in baseline
    assert "_assert_geometry" in baseline
    print("baseline_source=T105-18_AND_MD7|status=SOURCE_CONTRACT_VERIFIED")
    print("baseline_2025=42T_30W_11L_1BE_NET+4.03_PF1.5424_DD3.58")
    print("baseline_2026=18T_15W_2L_1BE_NET+3.68_PF3.7669_DD1.20")
    print("baseline_runtime_replay_executed=False")


def _audit_t108_population(sources: dict[str, str]) -> None:
    """Довести вузькість T108 denominator та інтерпретацію reject counts."""
    source = sources["T108-06"]
    tree = _tree(source, "T108-06")
    assert _literal(tree, "STRONG_MOVE_R") == 2.0

    direction = _code(source, _function(tree, "_observation_side"))
    assert "observation.regime_phase != ALLIGATOR_REGIME_PHASE_ACTIVE" in direction
    assert "ALLIGATOR_REGIME_TREND_UP" in direction
    assert "ALLIGATOR_REGIME_TREND_DOWN" in direction
    assert "ALLIGATOR_STATE_BULLISH" in direction
    assert "ALLIGATOR_STATE_BEARISH" in direction

    segmentation = _code(source, _function(tree, "_segments"))
    assert "_observation_side(observation)" in segmentation
    assert "side == current_side" in segmentation
    # У T108-06 contiguous означає сусідні observations, а не перевірений M15 gap.
    assert "timestamp" not in segmentation

    strong = _code(source, _function(tree, "_strong_move_r"))
    assert "segment.start_timestamp" in strong
    assert "first.high - first.low, first.spread * 10.0" in strong
    assert "item.high for item in segment_events" in strong
    assert "item.low for item in segment_events" in strong
    assert "first.close" in strong

    period = _code(source, _function(tree, "_run_period"))
    assert "for segment in _segments(observations)" in period
    assert "move_r + 1e-12 < STRONG_MOVE_R" in period
    assert "trade.signal_timestamp" in period
    assert "_assert_metrics(spec, runtime)" in period
    assert "_assert_stochastic_path(spec, runtime)" in period
    assert "_assert_geometry(runtime)" in period
    assert "broker_probe.requests == 0" in period

    rejects = _code(source, _function(tree, "_segment_reject_counts"))
    assert "for observation in segment.observations" in rejects
    assert "reasons[record.filter_reason_code] += 1" in rejects
    assert "NO_PRODUCTION_MACD_PROPOSAL" in rejects
    assert "ACCEPTED_SIGNAL_NO_FACTUAL_TRADE" in rejects

    audit = sources["T108-09"]
    rows = re.findall(
        r"(\d+) strong;(\d+) traded;(\d+) missed;coverage=(\d+\.\d+)pct",
        audit,
    )
    assert rows == [("139", "25", "114", "17.99"), ("80", "14", "66", "17.50")]
    for strong_count, traded, missed, coverage in rows:
        assert int(strong_count) == int(traded) + int(missed)
        assert round(100 * int(traded) / int(strong_count), 2) == float(coverage)
    doc = sources["MD7"]
    assert "2025 coverage = 17.99%" in doc
    assert "2026 coverage = 17.50%" in doc
    assert "dominant reject = MACD_EXTREMUM_TOO_WEAK" in doc

    print("t108_population=ALLIGATOR_ACTIVE_ALIGNED_CONTIGUOUS_OBSERVATIONS_ONLY")
    print("t108_label=EX_POST_FUTURE_SEGMENT_MFE_GE_2R")
    print("t108_coverage=HISTORICAL_REPLAY_EVIDENCE_NOT_RERUN")
    print("period=2025|strong=139|traded=25|missed=114|coverage_pct=17.99")
    print("period=2026|strong=80|traded=14|missed=66|coverage_pct=17.50")
    print("t108_reject_count_unit=REJECT_EVENTS_NOT_MISSED_TRENDS")
    print("t108_gap_validation=NOT_PRESENT_IN_SEGMENTATION_SOURCE")
    print("t108_non_active_trend_population=NOT_MEASURED")


def _audit_legacy_detectors(sources: dict[str, str]) -> None:
    """Зіставити незалежний price-only detector та ACTIVE inventory."""
    price_source = sources["RM102_PRICE_ONLY"]
    price_tree = _tree(price_source, "RM102_PRICE_ONLY")
    constants = {
        "TREND_WINDOW_BARS": 32,
        "TREND_SCAN_STEP_BARS": 4,
        "TREND_VOLATILITY_REFERENCE_BARS": 64,
        "TREND_MIN_NORMALIZED_MOVE": 8.0,
        "TREND_MIN_PATH_EFFICIENCY": 0.55,
    }
    for key, expected in constants.items():
        assert _literal(price_tree, key) == expected, key
    price_detector = _code(
        price_source, _function(price_tree, "price_only_trend_candidates")
    )
    assert "_window_is_contiguous(events, start_index, end_index)" in price_detector
    assert (
        "_true_range_reference(events[reference_start:start_index])" in price_detector
    )
    assert "records" not in price_detector and "trades" not in price_detector
    selection = _code(price_source, _function(price_tree, "strongest_non_overlapping"))
    assert "overlaps" in selection
    assert "item.score" in selection
    assert "records" not in selection and "trades" not in selection
    price_main_source = _code(price_source, _function(price_tree, "main"))
    assert "summary.period_start.year == 2025" in price_main_source
    assert "frozen_oos_workspace" in price_main_source

    active_source = sources["RM103_ACTIVE_INVENTORY"]
    active_tree = _tree(active_source, "RM103_ACTIVE_INVENTORY")
    split = _code(active_source, _function(active_tree, "_split_active_runs"))
    assert "observation.timestamp - previous_timestamp == M15" in split
    assert "_active_direction(observation)" in split
    assert (
        "EXPECTED_BASELINE = (59, 40, 18, 1, 9, -4.05, 0.7808, 5.80)" in active_source
    )

    print("rm102_price_detector=AVAILABLE|scope=HISTORICAL_2025_ONLY")
    print("rm102_detector=PRICE_ONLY_M15_32_BARS_STEP4_REF64_MOVE8TR_EFF0.55")
    print("rm102_detector_lookahead=ALLOWED_FOR_POST_HOC_LABEL_ONLY")
    print("rm102_gap_validation=PRESENT")
    print("rm102_thresholds=HISTORICAL_NOT_NEW_PRODUCTION_CONSTANTS")
    print("rm103_active_inventory=AVAILABLE|baseline=LEGACY_NOT_CURRENT")
    print("rm103_gap_validation=PRESENT")
    print("legacy_trading_metrics_comparable_to_current_baseline=False")


def _audit_roadmap108_closure(sources: dict[str, str]) -> None:
    """Підтвердити source contract закриття rescue-гілки RoadMap108."""
    closure = sources["T108-24"]
    doc = sources["MD7"]
    for fragment in (
        '("strict_entry_coverage_problem", "CONFIRMED")',
        '("first_reject_causal_advantage", "REJECTED")',
        '("existing_production_distance_gate_added_entry", "REJECTED")',
        '("strict_entry_rescue_branch", "EXHAUSTED_CURRENT_EVIDENCE")',
        '("production_change_required", False)',
        '"new_replay_run=False"',
    ):
        assert fragment in closure, fragment
    assert "strict_entry_rescue_branch=EXHAUSTED_CURRENT_EVIDENCE" in doc
    assert "production_change_required=False" in doc
    print("roadmap108_closure=SOURCE_CONTRACT_VERIFIED")
    print("strict_entry_rescue_branch=EXHAUSTED_CURRENT_EVIDENCE")
    print("t108_24_local_execution=USER_REPORTED_GREEN_NOT_RERUN")


def main() -> int:
    """Виконати одну статичну audit-перевірку без runtime execution."""
    sources = _read_sources()
    print("T112_01_HISTORICAL_EVIDENCE_COVERAGE_BOUNDARY_AUDIT")
    print("EVIDENCE_SOURCES")
    for identifier, path in SOURCES.items():
        print(f"source={identifier}|path={path}|verified=EXISTS_AND_READABLE")
    print("BASELINE_CONTRACT")
    _audit_baseline(sources)
    print("ROADMAP108_POPULATION_BOUNDARY")
    _audit_t108_population(sources)
    print("PRIOR_INDEPENDENT_DIAGNOSTICS")
    _audit_legacy_detectors(sources)
    print("ROADMAP108_CLOSURE")
    _audit_roadmap108_closure(sources)
    print("NEXT_RESEARCH_BOUNDARY")
    print("next_test=T112-02_PRICE_ONLY_VS_ACTIVE_POPULATION_OVERLAP")
    print(
        "t112_02_requirement="
        "REUSE_EXISTING_PRICE_ONLY_DETECTOR_ON_SAME_2025_2026_INPUT"
    )
    print("t112_02_requirement=REPLAY_CURRENT_REGISTERED_BASELINE_ON_BOTH_PERIODS")
    print("t112_02_requirement=PREDECLARE_OVERLAP_DEFINITION_AND_GAP_HANDLING")
    print("t112_02_requirement=NO_CAUSAL_ENTRY_FROM_EX_POST_TREND_LABELS")
    print("SAFETY")
    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    print("static_source_audit=True")
    print("new_replay_run=False")
    print("new_trade_simulation=False")
    print("new_entry_rule_created=False")
    print("threshold_sweep_performed=False")
    print("production_logic_changed=False")
    print("exit_logic_changed=False")
    print("md7_changed=False")
    print("broker_requests=0")
    print("T112_01_HISTORICAL_EVIDENCE_COVERAGE_BOUNDARY_AUDIT=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
