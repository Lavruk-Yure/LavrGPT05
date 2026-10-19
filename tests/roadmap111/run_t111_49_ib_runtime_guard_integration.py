"""T111-49 — IB runtime warm-up/live guard integration — TEST_ONLY.

Виконує оригінальний метод маршрутизації runtime на локальних заглушках.
Production, Replay, брокерські адаптери й CSV не змінює.
"""

from __future__ import annotations

import ast
import csv
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "core" / "workspace_runtime.py"
CSV_NAME = "2026-10-16_2026-10-19_IB_EURUSD_M15.csv"
ERROR = "Alligator bars must be strictly ordered and unique"


def _original_runtime_method():
    tree = ast.parse(RUNTIME.read_text(encoding="utf-8-sig"))
    for cls in tree.body:
        if not isinstance(cls, ast.ClassDef) or cls.name != "WorkspaceRuntime":
            continue
        for method in cls.body:
            if isinstance(method, ast.FunctionDef):
                if method.name == "_accept_market_event":
                    method.decorator_list = []
                    module = ast.fix_missing_locations(
                        ast.Module(body=[method], type_ignores=[])
                    )
                    namespace = {}
                    exec(compile(module, str(RUNTIME), "exec"), namespace)
                    return namespace[method.name]
    raise AssertionError("Production runtime route not found")


def _source_assertions() -> None:
    source = RUNTIME.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    methods = [
        node
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "WorkspaceRuntime"
        for node in cls.body
        if isinstance(node, ast.FunctionDef)
    ]
    names = {node.name: node for node in methods}
    warmup = ast.unparse(names["_complete_broker_start"])
    polling = ast.unparse(names["advance_broker_market"])
    replay = ast.unparse(names["_accept_replay_session_event"])
    assert "BROKER_WARMUP" in warmup
    assert "LIVE_READ_ONLY" in polling
    assert "_accept_market_event" in replay


def _load_timestamps() -> list[datetime]:
    locations = (
        Path(r"D:\LGE\data\history\IB\EURUSD\M15") / CSV_NAME,
        Path(r"D:\LGE\data\history\IB\EURUSDM15") / CSV_NAME,
        ROOT / "data/history/IB/EURUSD/M15" / CSV_NAME,
        ROOT / "data/history/IB/EURUSDM15" / CSV_NAME,
        ROOT / CSV_NAME,
        Path(__file__).parent / CSV_NAME,
    )
    csv_file = next((p for p in locations if p.is_file()), None)
    if csv_file is None:
        raise FileNotFoundError(CSV_NAME)
    with csv_file.open(encoding="utf-8-sig", newline="") as handle:
        records = list(csv.DictReader(handle))
    timestamps = [
        datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")).astimezone(UTC)
        for row in records
    ]
    assert len(timestamps) == 126
    assert all(a < b for a, b in zip(timestamps, timestamps[1:]))
    return timestamps


class RuntimeHarness:
    """Мінімальні залежності справжнього production runtime route."""

    def __init__(self, original_method):
        self.original_method = original_method
        self.context = SimpleNamespace(
            event_processing=False,
            current_market_event=None,
            market_event_count=0,
            signal_allowed=False,
        )
        self.chart_model = SimpleNamespace(append=self._append_chart)
        self.chart = []
        self.dispatched = []
        self.journal = []
        self.guard_calls = []
        self.replay_advances = 0
        self._live_quote_received = False
        self.replay_execution = None
        self.last_algorithm_stamp = None

    def _append_chart(self, event):
        self.chart.append(event.timestamp)

    def _update_market_guards(self, event, *, warmup_only):
        self.guard_calls.append((event.timestamp, warmup_only))

    def _advance_replay_execution(self, event):
        _ = event
        self.replay_advances += 1

    def evaluate_profit_protection(self):
        pass

    def _append_journal(self, category, name, text, **fields):
        _ = text
        self.journal.append((category, name, fields["timestamp"]))

    def _dispatch_market_event_to_algorithm(self, event):
        if (
            self.last_algorithm_stamp is not None
            and event.timestamp <= self.last_algorithm_stamp
        ):
            raise ValueError(ERROR)
        self.last_algorithm_stamp = event.timestamp
        self.dispatched.append(event.timestamp)

    def accept(self, event, origin, warmup_only=False):
        return self.original_method(self, event, origin=origin, warmup_only=warmup_only)


def _event(stamp):
    return SimpleNamespace(
        timestamp=stamp,
        symbol="EURUSD",
        timeframe="M15",
        close=1.123,
        spread=0.00003,
    )


class BoundaryCandidate:
    """Лише тимчасовий guard для першого новішого live-бару."""

    def __init__(self, harness):
        self.runtime = harness
        self.last_warmup = None
        self.pending_boundary = False
        self.skipped = 0

    def deliver(self, event, origin):
        if origin == "BROKER_WARMUP":
            # Жодного захисту історії: помилки мають бути видимі.
            self.runtime.accept(event, origin, warmup_only=True)
            self.last_warmup = event.timestamp
            self.pending_boundary = True
            return "ACCEPTED"
        if (
            origin == "LIVE_READ_ONLY"
            and self.pending_boundary
            and self.last_warmup is not None
        ):
            if event.timestamp <= self.last_warmup:
                self.skipped += 1
                return "SKIPPED_BOUNDARY"
            # Захист знімається після першого справді нового live-бару.
            self.runtime.accept(event, origin)
            self.pending_boundary = False
            return "ACCEPTED"
        self.runtime.accept(event, origin)
        return "ACCEPTED"


def _feed_warmup(candidate, stamps):
    for stamp in stamps:
        candidate.deliver(_event(stamp), "BROKER_WARMUP")


def main():
    original = _original_runtime_method()
    _source_assertions()
    stamps = _load_timestamps()
    last = stamps[-1]
    new = last + timedelta(minutes=15)

    baseline = RuntimeHarness(original)
    for stamp in stamps:
        baseline.accept(_event(stamp), "BROKER_WARMUP", warmup_only=True)
    baseline_error = False
    try:
        baseline.accept(_event(last), "LIVE_READ_ONLY")
    except ValueError as exc:
        baseline_error = str(exc) == ERROR
    assert baseline_error
    assert baseline.context.event_processing is False

    protected = RuntimeHarness(original)
    candidate = BoundaryCandidate(protected)
    _feed_warmup(candidate, stamps)
    before = (
        len(protected.chart),
        len(protected.dispatched),
        protected.context.market_event_count,
        len(protected.journal),
        protected.replay_advances,
    )
    assert candidate.deliver(_event(last), "LIVE_READ_ONLY") == "SKIPPED_BOUNDARY"
    older = _event(last - timedelta(minutes=15))
    assert candidate.deliver(older, "LIVE_READ_ONLY") == "SKIPPED_BOUNDARY"
    assert before == (
        len(protected.chart),
        len(protected.dispatched),
        protected.context.market_event_count,
        len(protected.journal),
        protected.replay_advances,
    )
    assert candidate.deliver(_event(new), "LIVE_READ_ONLY") == "ACCEPTED"
    assert protected.dispatched[-1] == new
    assert protected.context.event_processing is False
    assert len(protected.dispatched) == len(stamps) + 1
    assert candidate.skipped == 2

    # Після завершення межі новий дубль не можна приховати.
    post_boundary_error = False
    try:
        candidate.deliver(_event(new), "LIVE_READ_ONLY")
    except ValueError as exc:
        post_boundary_error = str(exc) == ERROR
    assert post_boundary_error

    # Порушення warm-up має залишитися помилкою.
    history = RuntimeHarness(original)
    history_guard = BoundaryCandidate(history)
    _feed_warmup(history_guard, stamps[:2])
    history_error = False
    try:
        history_guard.deliver(_event(stamps[1]), "BROKER_WARMUP")
    except ValueError as exc:
        history_error = str(exc) == ERROR
    assert history_error

    # Replay передається без поглинання й без gate.
    replay = RuntimeHarness(original)
    replay.accept(_event(stamps[0]), "REPLAY")
    assert replay.dispatched == [stamps[0]]
    assert replay.replay_advances == 1

    print("T111-49 TEST_ONLY")
    print("verdict=IB_RUNTIME_BOUNDARY_INTEGRATION_CANDIDATE_GREEN")
    print(f"csv_rows={len(stamps)}")
    print("actual_runtime_route_exercised=True")
    print("baseline_overlap_error=True")
    print("candidate_boundary_duplicate_skipped=True")
    print("candidate_boundary_older_skipped=True")
    print("skipped_events_do_not_mutate_runtime=True")
    print("candidate_first_new_live_accepted=True")
    print("post_boundary_live_duplicate_still_errors=True")
    print("invalid_warmup_still_errors=True")
    print("replay_route_unchanged=True")
    print("observed_server_root_cause=UNRESOLVED")
    print("TEST_ONLY=True")
    print("broker_requests=0")
    print("production_logic_changed=False")


if __name__ == "__main__":
    main()
