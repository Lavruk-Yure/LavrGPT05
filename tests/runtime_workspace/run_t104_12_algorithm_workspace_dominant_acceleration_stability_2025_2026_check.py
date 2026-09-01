# -*- coding: utf-8 -*-
"""RoadMap104 / T104-12 / 8C.13: dominant acceleration stability.

TEST_ONLY runner не змінює production Candidate F, GREEN 8C.1 entry,
T104-08 Donchian pullback/re-breakout re-entry або T104-11 discriminator.
Базою є фактичні T104-11 candidates, відібрані тільки незмінним structural
predicate DOMINANT_ACCELERATION: directional signal histogram delta більший
за absolute directional signal histogram цього ж completed M15 signal bar.

Мета T104-12 — не додати новий filter, а перевірити концентрацію малого
selected sample: chronology, BUY/SELL, календарні місяці/дні, outcome/PnL та
чутливість net до вилучення одного winner. Це post-selection diagnostic;
outcome ніколи не використовується для causal permission другого leg.
Performance та concentration metrics не є PASS-критеріями.
"""

from __future__ import annotations

import importlib.util
import sys
from collections import Counter, defaultdict
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

BASE_SCRIPT_NAME = (
    "run_t104_11_algorithm_workspace_macd_relative_restart_discriminator_"
    "2025_2026_check.py"
)
TEST_ID = "T104-12"
ROADMAP_BLOCK = "8C.13"


def _load_base_module() -> ModuleType:
    """Завантажити T104-11 як read-only dependency."""
    file_path = Path(__file__).with_name(BASE_SCRIPT_NAME)
    assert file_path.is_file(), file_path
    module_name = "rm104_t104_12_dominant_acceleration_base"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


BASE = _load_base_module()
WINDOWS = getattr(BASE, "WINDOWS")
_run_base_window: Callable[..., Any] = getattr(BASE, "_run_window")
_dominant_acceleration: Callable[..., bool] = getattr(
    BASE,
    "_dominant_acceleration",
)
REENTRY_BASE = getattr(BASE, "REENTRY_BASE")
_summary: Callable[..., Any] = getattr(REENTRY_BASE, "_summary")


def _selected_rows(window: Any) -> list[tuple[Any, Any]]:
    """Повернути T104-11 dominant-acceleration rows без зміни predicate."""
    data = _run_base_window(window)
    rows = [
        (anatomy, trade)
        for anatomy, trade in data["rows"]
        if _dominant_acceleration(anatomy)
    ]
    assert len(rows) == data["dominant_acceleration"]["selected"]
    return rows


def _bucket_text(counter: Counter[str]) -> str:
    if not counter:
        return "NONE"
    return "|".join(f"{key}:{counter[key]}" for key in sorted(counter))


def _net_text(values: dict[str, float]) -> str:
    if not values:
        return "NONE"
    return "|".join(f"{key}:{values[key]:+.2f}" for key in sorted(values))


def _trade_timestamp(trade: Any) -> Any:
    timestamp = getattr(trade, "entry_timestamp", None)
    if timestamp is not None:
        return timestamp
    return getattr(trade, "start_timestamp")


def _trade_line(index: int, trade: Any) -> str:
    timestamp = _trade_timestamp(trade)
    return (
        f"n:{index},time:{timestamp.isoformat()},direction:{trade.direction},"
        f"outcome:{trade.close_reason},pnl:{float(trade.pnl):+.2f},"
        f"hold:{int(trade.holding_bars)}"
    )


def _diagnostic(rows: list[tuple[Any, Any]]) -> dict[str, Any]:
    trades = [trade for _, trade in rows]
    summary = _summary(tuple(trades))
    side_count: Counter[str] = Counter()
    side_net: defaultdict[str, float] = defaultdict(float)
    month_count: Counter[str] = Counter()
    month_net: defaultdict[str, float] = defaultdict(float)
    day_count: Counter[str] = Counter()
    day_net: defaultdict[str, float] = defaultdict(float)
    outcome_count: Counter[str] = Counter()

    for trade in trades:
        timestamp = _trade_timestamp(trade)
        side = str(trade.direction)
        month = timestamp.strftime("%Y-%m")
        day = timestamp.strftime("%Y-%m-%d")
        pnl = float(trade.pnl)
        side_count[side] += 1
        side_net[side] += pnl
        month_count[month] += 1
        month_net[month] += pnl
        day_count[day] += 1
        day_net[day] += pnl
        outcome_count[str(trade.close_reason)] += 1

    winners = [float(trade.pnl) for trade in trades if float(trade.pnl) > 0]
    losses = [float(trade.pnl) for trade in trades if float(trade.pnl) < 0]
    leave_one_winner_out = [summary.net - pnl for pnl in winners]
    leave_one_loss_out = [summary.net - pnl for pnl in losses]

    return {
        "trades": trades,
        "summary": summary,
        "side_count": side_count,
        "side_net": dict(side_net),
        "month_count": month_count,
        "month_net": dict(month_net),
        "day_count": day_count,
        "day_net": dict(day_net),
        "outcome_count": outcome_count,
        "unique_months": len(month_count),
        "unique_days": len(day_count),
        "max_same_month": max(month_count.values(), default=0),
        "max_same_day": max(day_count.values(), default=0),
        "min_leave_one_winner_out_net": min(leave_one_winner_out, default=None),
        "max_leave_one_loss_out_net": max(leave_one_loss_out, default=None),
        "positive_months": sum(value > 0 for value in month_net.values()),
        "negative_months": sum(value < 0 for value in month_net.values()),
        "flat_months": sum(value == 0 for value in month_net.values()),
    }


def _optional_money(value: float | None) -> str:
    return "NONE" if value is None else f"{value:+.2f}"


def _optional_pf(value: float | None) -> str:
    return "NONE" if value is None else f"{value:.4f}"


def main() -> int:
    results: dict[str, dict[str, Any]] = {}
    for window in WINDOWS:
        results[window.label] = _diagnostic(_selected_rows(window))

    print("T104-12 Dominant Acceleration Stability result")
    print(f"  test_id={TEST_ID}")
    print(f"  roadmap_block={ROADMAP_BLOCK}")
    print("  mode=RM104_T104_12_8C13_DOMINANT_ACCELERATION_STABILITY_" "TEST_ONLY")
    print("  base_test_id=T104-11")
    print("  production_candidate_f_logic_changed=False")
    print("  production_entry_logic_changed=False")
    print("  production_exit_logic_changed=False")
    print("  green_8c1_entry_frozen=True")
    print("  t104_08_reentry_logic_changed=False")
    print("  t104_11_discriminator_changed=False")
    print(
        "  selected_rule=SIGNAL_HIST_DELTA_GT_ABS_SIGNAL_HIST_"
        "AND_SIGNAL_MOMENTUM_FAVORABLE"
    )
    print("  new_filter_added=False")
    print("  new_numeric_tuning=False")
    print("  outcome_used_for_permission=False")
    print("  diagnostic_scope=CHRONOLOGY_SIDE_CALENDAR_CONCENTRATION_LEAVE_ONE_OUT")

    all_trades: list[Any] = []
    for window in WINDOWS:
        data = results[window.label]
        summary = data["summary"]
        all_trades.extend(data["trades"])
        print(
            f"  {window.label}/SUMMARY="
            f"selected:{len(data['trades'])},"
            f"outcomes:{_bucket_text(data['outcome_count'])},"
            f"net:{summary.net:+.2f},pf:{_optional_pf(summary.profit_factor)},"
            f"dd:{summary.maximum_drawdown:.2f},"
            f"unique_months:{data['unique_months']},"
            f"unique_days:{data['unique_days']},"
            f"max_same_month:{data['max_same_month']},"
            f"max_same_day:{data['max_same_day']}"
        )
        print(
            f"  {window.label}/SIDE="
            f"counts:{_bucket_text(data['side_count'])},"
            f"net:{_net_text(data['side_net'])}"
        )
        print(
            f"  {window.label}/MONTH="
            f"counts:{_bucket_text(data['month_count'])},"
            f"net:{_net_text(data['month_net'])},"
            f"positive:{data['positive_months']},"
            f"negative:{data['negative_months']},"
            f"flat:{data['flat_months']}"
        )
        print(
            f"  {window.label}/LEAVE_ONE_OUT="
            "min_net_after_removing_one_winner:"
            f"{_optional_money(data['min_leave_one_winner_out_net'])},"
            "max_net_after_removing_one_loss:"
            f"{_optional_money(data['max_leave_one_loss_out_net'])}"
        )
        for index, trade in enumerate(data["trades"], start=1):
            print(f"  {window.label}/TRADE={_trade_line(index, trade)}")

    combined = _summary(tuple(all_trades))
    print(
        "  COMBINED="
        f"selected:{len(all_trades)},net:{combined.net:+.2f},"
        f"pf:{_optional_pf(combined.profit_factor)},"
        f"dd:{combined.maximum_drawdown:.2f}"
    )
    print("  performance_is_diagnostic_not_pass_criterion=True")
    print("  concentration_is_diagnostic_not_pass_criterion=True")
    print("  causal_selection_unchanged_from_t104_11=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("T104_12_ALGORITHM_WORKSPACE_DOMINANT_ACCELERATION_STABILITY_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
