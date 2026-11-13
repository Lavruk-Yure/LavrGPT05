# -*- coding: utf-8 -*-
"""RoadMap115 / T115-75: production Candidate F signal/reject census.

TEST_ONLY / DATA_ONLY.

Повторює незмінний canonical Candidate F WorkspaceRuntime Replay на
EURUSD M15 у періодах 2025 і 2026 через GREEN harness T105-18.

Рахує всі збережені signal records: accepted, component rejects,
runtime/risk rejects, причини відхилення та deferred lifecycle.
Немає hindsight strong-segment selection або counterfactual trading.

Увага: кількість reject records не дорівнює кількості незалежних
пропущених угод. Тести RoadMap108 вже аналізували strong segments.
Production, Replay, MD7 та lang/strings.json не змінюються.
"""

from __future__ import annotations

import sys
from collections import Counter
from importlib import import_module
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = ROOT / "tests" / "runtime_workspace"

for import_path in (ROOT, TEST_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))


# Динамічний імпорт потрібний для окремого runnable-тесту.
# Штатні harness-модулі розташовані в tests/runtime_workspace.
source_t105_15 = import_module("run_t105_15_stochastic_entry_anatomy_check")

source_t105_18 = import_module(
    "run_t105_18_stochastic_current_bar_production_regression_check"
)

source_alligator = import_module("core.workspace_alligator")

source_signal = import_module("core.workspace_signal")


_production_hashes = getattr(
    source_t105_15,
    "_production_hashes",
)

BASELINE_POPULATION = getattr(
    source_t105_18,
    "BASELINE_POPULATION",
)

EXPECTED_REJECTS = getattr(
    source_t105_18,
    "EXPECTED_REJECTS",
)

PERIODS = getattr(
    source_t105_18,
    "PERIODS",
)

_broker_execution_attempted = getattr(
    source_t105_18,
    "_broker_execution_attempted",
)

_run_period = getattr(
    source_t105_18,
    "_run_period",
)

_summary_line = getattr(
    source_t105_18,
    "_summary_line",
)

ALLIGATOR_REASON_STOCHASTIC_CURRENT_BAR_CROSS = getattr(
    source_alligator,
    "ALLIGATOR_REASON_STOCHASTIC_CURRENT_BAR_CROSS",
)

WorkspaceMacdAlligatorReplayAlgorithm = getattr(
    source_alligator,
    "WorkspaceMacdAlligatorReplayAlgorithm",
)

WORKSPACE_SIGNAL_FILTER_REJECT = getattr(
    source_signal,
    "WORKSPACE_SIGNAL_FILTER_REJECT",
)


STAGES = (
    "ACCEPTED",
    "COMPONENT_REJECT",
    "RISK_REJECT",
    "RUNTIME_OR_OTHER_REJECT",
)


def _stage(record: Any) -> str:
    """Класифікувати збережене рішення без повторної торгівлі."""
    if record.accepted:
        return "ACCEPTED"

    if record.filter_decision == WORKSPACE_SIGNAL_FILTER_REJECT:
        return "COMPONENT_REJECT"

    if record.risk_decision is not None:
        return "RISK_REJECT"

    return "RUNTIME_OR_OTHER_REJECT"


def _census(
    spec: Any,
) -> tuple[Counter[str], Counter[str]]:
    """Виконати canonical Replay і звірити журнали сигналів."""
    runtime, stochastic_rejects, broker_requests = _run_period(spec)

    session = runtime.replay_session
    execution = runtime.replay_execution
    algorithm = runtime.algorithm

    assert session is not None and session.completed
    assert execution is not None

    assert type(algorithm) is WorkspaceMacdAlligatorReplayAlgorithm
    assert broker_requests == 0
    assert not _broker_execution_attempted(runtime)

    records = runtime.signal_records_for_ui()

    assert all(record.timeframe == "M15" for record in records)

    assert all(not record.risk_execution_attempted for record in records)

    stages = Counter(_stage(record) for record in records)

    assert sum(stages.values()) == len(records)
    assert all(stage in STAGES for stage in stages)

    filter_reasons = Counter(
        record.filter_reason_code or "UNSPECIFIED"
        for record in records
        if _stage(record) == "COMPONENT_REJECT"
    )

    risk_reasons = Counter(
        record.risk_reason_code or "UNSPECIFIED"
        for record in records
        if _stage(record) == "RISK_REJECT"
    )

    runtime_reasons = Counter(
        record.reason
        for record in records
        if _stage(record) == "RUNTIME_OR_OTHER_REJECT"
    )

    source_reasons = Counter(
        record.source_reason_code or "UNSPECIFIED"
        for record in records
        if not record.accepted
    )

    lifecycle = Counter(
        (
            record.candidate_f_lifecycle_action or "NONE",
            record.candidate_f_lifecycle_reason or "NONE",
        )
        for record in records
        if record.candidate_f_lifecycle_action is not None
    )

    assert sum(filter_reasons.values()) == stages["COMPONENT_REJECT"]
    assert sum(risk_reasons.values()) == stages["RISK_REJECT"]

    assert sum(runtime_reasons.values()) == (stages["RUNTIME_OR_OTHER_REJECT"])

    assert sum(source_reasons.values()) == (len(records) - stages["ACCEPTED"])

    # Звірка фактичних CURRENT_BAR rejects з T105-18.
    assert (
        filter_reasons[ALLIGATOR_REASON_STOCHASTIC_CURRENT_BAR_CROSS]
        == stochastic_rejects
    )

    assert stochastic_rejects == EXPECTED_REJECTS[spec.code]

    diagnostics = execution.trade_diagnostics()

    executed_uids = {trade.signal_uid for trade in diagnostics}

    accepted_uids = {record.signal_uid for record in records if record.accepted}

    assert executed_uids <= accepted_uids

    summary = runtime.historical_summary

    assert summary is not None
    assert len(diagnostics) == summary.opened_trades

    assert summary.opened_trades + stochastic_rejects == BASELINE_POPULATION[spec.code]

    # Lifecycle має стосуватися раніше створеного ARMED.
    for record in records:
        if record.candidate_f_lifecycle_action is not None:
            assert record.filter_reason_code == "ALLIGATOR_DEFERRED_ARMED"
            assert record.candidate_f_lifecycle_timestamp is not None

            assert record.candidate_f_lifecycle_timestamp >= record.timestamp

    print(f"BASELINE|PERIOD={spec.code}|" f"{_summary_line(runtime)}")

    print(
        f"PRODUCTION_SIGNAL_FUNNEL|PERIOD={spec.code}|"
        f"SIGNAL_RECORDS={len(records)}|"
        f"ACCEPTED={stages['ACCEPTED']}|"
        f"COMPONENT_REJECT={stages['COMPONENT_REJECT']}|"
        f"RISK_REJECT={stages['RISK_REJECT']}|"
        f"RUNTIME_OR_OTHER_REJECT={stages['RUNTIME_OR_OTHER_REJECT']}|"
        f"EXECUTED_TRADE_UIDS={len(executed_uids)}|"
        f"ACCEPTED_NOT_EXECUTED_UIDS={len(accepted_uids - executed_uids)}"
    )

    for reason, count in sorted(filter_reasons.items()):
        print(f"FILTER_REJECT|PERIOD={spec.code}|" f"REASON={reason}|COUNT={count}")

    for reason, count in sorted(risk_reasons.items()):
        print(f"RISK_REJECT|PERIOD={spec.code}|" f"REASON={reason}|COUNT={count}")

    for reason, count in sorted(runtime_reasons.items()):
        print(f"RUNTIME_REJECT|PERIOD={spec.code}|" f"REASON={reason}|COUNT={count}")

    for reason, count in sorted(source_reasons.items()):
        print(f"SOURCE_REASON|PERIOD={spec.code}|" f"REASON={reason}|COUNT={count}")

    for (action, reason), count in sorted(lifecycle.items()):
        print(
            f"CANDIDATE_F_LIFECYCLE|PERIOD={spec.code}|"
            f"ACTION={action}|REASON={reason}|COUNT={count}"
        )

    print(
        f"CANONICAL_STOCHASTIC|PERIOD={spec.code}|"
        f"CURRENT_BAR_REJECTS={stochastic_rejects}|"
        f"CANONICAL_POPULATION={BASELINE_POPULATION[spec.code]}|"
        f"BROKER_REQUESTS={broker_requests}"
    )

    print(f"PRODUCTION_CENSUS_RECONCILIATION={spec.code}:OK")

    return stages, filter_reasons


def main() -> None:
    """Провести factual census без підбору нових правил."""
    guarded_before = _production_hashes()

    md7 = ROOT / "doc" / "LGE_Runtime_07.md"

    assert md7.is_file()

    md7_before = md7.read_bytes()

    print("T115-75|TEST_ONLY|" "PRODUCTION_CANDIDATE_F_SIGNAL_REJECT_CENSUS")

    print("PATH=ACTUAL_REGISTERED_PRODUCTION_WORKSPACE_RUNTIME")
    print("PERIODS=2025,2026|TIMEFRAME=M15")
    print("NO_HINDSIGHT_SEGMENT_SELECTION=True")
    print("REJECT_RECORD_IS_NOT_MISSED_TRADE=True")
    print("NO_NEW_ENTRY_EXIT_REENTRY_RULE=True")

    pooled_stages: Counter[str] = Counter()
    pooled_reasons: Counter[str] = Counter()

    assert tuple(spec.code for spec in PERIODS) == ("2025", "2026")

    for spec in PERIODS:
        stages, reasons = _census(spec)

        pooled_stages.update(stages)
        pooled_reasons.update(reasons)

    print(
        "POOLED_PRODUCTION_SIGNAL_FUNNEL|"
        + "|".join(f"{stage}={pooled_stages[stage]}" for stage in STAGES)
        + f"|TOTAL={sum(pooled_stages.values())}"
    )

    for reason, count in sorted(pooled_reasons.items()):
        print(f"POOLED_FILTER_REJECT|" f"REASON={reason}|COUNT={count}")

    assert _production_hashes() == guarded_before
    assert md7.read_bytes() == md7_before

    print("PRODUCTION_BASELINES_2025_2026=OK")
    print("PRODUCTION_SIGNAL_RECORD_ACCOUNTING=OK")
    print("SOURCE_FILES_SHA_UNCHANGED=OK")
    print("NO_GATE_COUNTERFACTUAL_EXECUTED=True")
    print("NO_HINDSIGHT_ENTRY_LABELS=True")
    print("broker_requests=0|TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_75_PRODUCTION_CANDIDATE_F_SIGNAL_REJECT_CENSUS=OK")


if __name__ == "__main__":
    main()
