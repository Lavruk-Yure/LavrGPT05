"""T111-50 — IB production warm-up/live boundary regression — TEST_ONLY.

Виконує оригінальний метод маршрутизації runtime на локальних заглушках.
Читає production-код, не запускає брокерів і не змінює файли.
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
                    namespace = {"WORKSPACE_DATA_MODE_BROKER": "BROKER"}
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
            data_mode="BROKER",
            broker="IB",
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
        self._ib_warmup_last_timestamp = None
        self._ib_live_boundary_pending = False
        self.replay_execution = None
        self.last_algorithm_stamp = None

    @property
    def warmup_last_timestamp(self):
        """Останній timestamp warm-up для тестових перевірок."""
        return self._ib_warmup_last_timestamp

    @property
    def live_boundary_pending(self):
        """Чи активний перехід warm-up до першого нового live-бару."""
        return self._ib_live_boundary_pending

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


def _feed(runtime, stamps):
    for stamp in stamps:
        runtime.accept(_event(stamp), "BROKER_WARMUP", warmup_only=True)


def _snapshot(runtime):
    return (
        len(runtime.chart),
        len(runtime.dispatched),
        runtime.context.market_event_count,
        len(runtime.journal),
        runtime.replay_advances,
        runtime.last_algorithm_stamp,
    )


def main():
    original = _original_runtime_method()
    _source_assertions()
    stamps = _load_timestamps()
    last = stamps[-1]
    fresh = last + timedelta(minutes=15)

    ib = RuntimeHarness(original)
    _feed(ib, stamps)
    assert ib.warmup_last_timestamp == last
    assert ib.live_boundary_pending
    before = _snapshot(ib)
    ib.accept(_event(last), "LIVE_READ_ONLY")
    ib.accept(_event(stamps[-2]), "LIVE_READ_ONLY")
    assert _snapshot(ib) == before
    assert ib.live_boundary_pending

    ib.accept(_event(fresh), "LIVE_READ_ONLY")
    assert ib.dispatched[-1] == fresh
    assert not ib.live_boundary_pending
    assert ib.context.market_event_count == len(stamps) + 1
    assert ib.context.event_processing is False

    later_duplicate_errors = False
    try:
        ib.accept(_event(fresh), "LIVE_READ_ONLY")
    except ValueError as exc:
        later_duplicate_errors = str(exc) == ERROR
    assert later_duplicate_errors

    history = RuntimeHarness(original)
    _feed(history, stamps[:2])
    invalid_history_errors = False
    try:
        history.accept(_event(stamps[1]), "BROKER_WARMUP", warmup_only=True)
    except ValueError as exc:
        invalid_history_errors = str(exc) == ERROR
    assert invalid_history_errors

    ctrader = RuntimeHarness(original)
    ctrader.context.broker = "CTRADER"
    _feed(ctrader, stamps[:2])
    ctrader_not_guarded = False
    try:
        ctrader.accept(_event(stamps[1]), "LIVE_READ_ONLY")
    except ValueError as exc:
        ctrader_not_guarded = str(exc) == ERROR
    assert ctrader_not_guarded

    replay = RuntimeHarness(original)
    replay.context.data_mode = "REPLAY"
    replay.accept(_event(stamps[0]), "REPLAY")
    assert replay.dispatched == [stamps[0]]
    assert replay.replay_advances == 1
    assert not replay.live_boundary_pending

    source = RUNTIME.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    methods = {
        node.name: ast.unparse(node)
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "WorkspaceRuntime"
        for node in cls.body
        if isinstance(node, ast.FunctionDef)
    }
    assert "self._ib_warmup_last_timestamp = None" in methods["begin_start"]
    assert (
        "self._ib_warmup_last_timestamp = None"
        in methods["_resume_after_broker_reconnect"]
    )

    print("T111-50 TEST_ONLY")
    print("verdict=IB_PRODUCTION_BOUNDARY_GUARD_REGRESSION_GREEN")
    print(f"csv_rows={len(stamps)}")
    print("ib_boundary_duplicate_skipped=True")
    print("ib_boundary_older_skipped=True")
    print("skip_has_zero_runtime_side_effects=True")
    print("first_new_live_accepted=True")
    print("post_boundary_duplicate_still_errors=True")
    print("invalid_warmup_still_errors=True")
    print("ctrader_route_unchanged=True")
    print("replay_route_unchanged=True")
    print("start_and_reconnect_reset_guard=True")
    print("observed_server_root_cause=UNRESOLVED")
    print("TEST_ONLY=True")
    print("broker_requests=0")
    print("broker_execution_attempted=False")
    print("production_logic_changed=True")


if __name__ == "__main__":
    main()
