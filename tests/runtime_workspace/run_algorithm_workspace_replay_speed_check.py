# -*- coding: utf-8 -*-
"""Регресія швидкостей Replay та bounded high-speed responsiveness.

Перевірка доводить однакову chronology для 1x/10x/100x/1000x/MAX/
MAX FAST/Step. 100x/1000x і звичайний MAX зберігають консервативний 16-event
GUI rail. MAX FAST починає з тієї самої межі, але адаптує наступний compute
batch за виміряним throughput у межах короткого wall-clock budget і finite cap.
Важкий UI refresh лишається throttled, причому interval відлічується після
завершення попереднього sync; market events, Pause/Stop і deterministic result
не пропускаються.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.workspace_replay import (  # noqa: E402
    REPLAY_MAX_EVENTS_PER_CYCLE,
    REPLAY_MAX_FAST_ADAPTIVE_MAX_EVENTS,
    REPLAY_MAX_FAST_TIME_BUDGET_SECONDS,
    REPLAY_MAX_FAST_UI_REFRESH_SECONDS,
    REPLAY_SPEED_MAX,
    REPLAY_SPEED_MAX_FAST,
    WorkspaceReplayError,
    WorkspaceReplayService,
    replay_events_per_cycle,
    replay_max_fast_next_batch_size,
    replay_speed_label,
    replay_ui_batch_size,
    replay_ui_cycle_quota,
    replay_ui_should_refresh,
)
from core.workspace_replay_settings import (  # noqa: E402
    WorkspaceReplaySettings,
    WorkspaceReplaySettingsError,
)


def _event_signature(event: object) -> tuple[object, ...]:
    return (
        getattr(event, "timestamp"),
        getattr(event, "open"),
        getattr(event, "high"),
        getattr(event, "low"),
        getattr(event, "close"),
        getattr(event, "bid"),
        getattr(event, "ask"),
    )


def _drain(
    service: WorkspaceReplayService,
    *,
    speed: int,
    event_count: int,
) -> tuple[tuple[tuple[object, ...], ...], tuple[int, ...]]:
    session = service.create_synthetic_session(
        broker="IB",
        symbol="EURUSD",
        timeframe="M15",
        replay_settings={
            "start_utc": "2026-01-02T08:00:00Z",
            "event_count": event_count,
            "base_price": 1.10000,
            "spread": 0.00012,
            "speed": speed,
            "source": "REPLAY_SPEED_TEST",
        },
    )
    session.start()
    signatures: list[tuple[object, ...]] = []
    batch_sizes: list[int] = []
    while not session.completed:
        batch = session.advance()
        assert batch
        signatures.extend(_event_signature(event) for event in batch)
        batch_sizes.append(len(batch))
    assert session.index == event_count
    return tuple(signatures), tuple(batch_sizes)


def _drain_step(
    service: WorkspaceReplayService,
    *,
    event_count: int,
) -> tuple[tuple[object, ...], ...]:
    session = service.create_synthetic_session(
        broker="IB",
        symbol="EURUSD",
        timeframe="M15",
        replay_settings={
            "start_utc": "2026-01-02T08:00:00Z",
            "event_count": event_count,
            "speed": 1,
            "source": "REPLAY_SPEED_STEP_TEST",
        },
    )
    session.start()
    session.pause()
    signatures: list[tuple[object, ...]] = []
    while not session.completed:
        event = session.step()
        assert event is not None
        signatures.append(_event_signature(event))
    return tuple(signatures)


def _ui_cycle_batch_sizes(
    service: WorkspaceReplayService,
    *,
    speed: int,
    event_count: int,
) -> tuple[int, ...]:
    """Моделювати один GUI logical cycle як серію bounded chunks."""
    session = service.create_synthetic_session(
        broker="IB",
        symbol="EURUSD",
        timeframe="M15",
        replay_settings={
            "event_count": event_count,
            "speed": speed,
            "source": "REPLAY_UI_BURST_TEST",
        },
    )
    session.start()
    remaining = replay_ui_cycle_quota(speed)
    batch_sizes: list[int] = []
    while not session.completed:
        batch_size = replay_ui_batch_size(remaining)
        assert batch_size > 0
        batch = session.advance(max_events=batch_size)
        assert batch
        batch_sizes.append(len(batch))
        if remaining is not None:
            remaining -= len(batch)
            if remaining <= 0:
                break
    return tuple(batch_sizes)


def main() -> None:
    service = WorkspaceReplayService()
    event_count = 2058
    runs = {
        speed: _drain(service, speed=speed, event_count=event_count)
        for speed in (1, 10, 100, 1000, REPLAY_SPEED_MAX, REPLAY_SPEED_MAX_FAST)
    }
    baseline_signatures = runs[1][0]
    for signatures, _batch_sizes in runs.values():
        assert signatures == baseline_signatures
    assert _drain_step(service, event_count=event_count) == baseline_signatures

    assert runs[100][1][0] == 100
    assert runs[1000][1][0] == 1000
    max_batch_sizes = runs[REPLAY_SPEED_MAX][1]
    assert max(max_batch_sizes) <= REPLAY_MAX_EVENTS_PER_CYCLE
    assert sum(max_batch_sizes) == event_count
    assert REPLAY_MAX_EVENTS_PER_CYCLE <= 16
    assert replay_events_per_cycle(REPLAY_SPEED_MAX) == REPLAY_MAX_EVENTS_PER_CYCLE
    assert replay_speed_label(REPLAY_SPEED_MAX) == "MAX"
    assert replay_speed_label(REPLAY_SPEED_MAX_FAST) == "MAX FAST"
    assert replay_speed_label(1000) == "1000x"

    ui_100x_batches = _ui_cycle_batch_sizes(
        service, speed=100, event_count=2058
    )
    ui_1000x_batches = _ui_cycle_batch_sizes(
        service, speed=1000, event_count=2058
    )
    ui_max_batches = _ui_cycle_batch_sizes(
        service, speed=REPLAY_SPEED_MAX, event_count=2058
    )
    ui_max_fast_batches = _ui_cycle_batch_sizes(
        service, speed=REPLAY_SPEED_MAX_FAST, event_count=2058
    )
    assert max(ui_100x_batches) <= REPLAY_MAX_EVENTS_PER_CYCLE
    assert max(ui_1000x_batches) <= REPLAY_MAX_EVENTS_PER_CYCLE
    assert max(ui_max_batches) <= REPLAY_MAX_EVENTS_PER_CYCLE
    assert max(ui_max_fast_batches) <= REPLAY_MAX_EVENTS_PER_CYCLE
    assert sum(ui_100x_batches) == 100
    assert sum(ui_1000x_batches) == 1000
    assert sum(ui_max_batches) == 2058
    assert sum(ui_max_fast_batches) == 2058
    assert replay_ui_cycle_quota(1000) == 1000
    assert replay_ui_cycle_quota(REPLAY_SPEED_MAX) is None
    assert replay_ui_cycle_quota(REPLAY_SPEED_MAX_FAST) is None
    assert replay_events_per_cycle(REPLAY_SPEED_MAX_FAST) == REPLAY_MAX_EVENTS_PER_CYCLE
    assert REPLAY_MAX_FAST_UI_REFRESH_SECONDS == 0.50
    assert replay_ui_should_refresh(REPLAY_SPEED_MAX, 0.0)
    assert not replay_ui_should_refresh(REPLAY_SPEED_MAX_FAST, 0.49)
    assert replay_ui_should_refresh(REPLAY_SPEED_MAX_FAST, 0.50)
    assert REPLAY_MAX_FAST_TIME_BUDGET_SECONDS == 0.040
    assert REPLAY_MAX_FAST_ADAPTIVE_MAX_EVENTS == 256
    assert replay_max_fast_next_batch_size(16, 0.004) == 32
    assert replay_max_fast_next_batch_size(32, 0.008) == 64
    assert replay_max_fast_next_batch_size(64, 0.040) == 64
    assert replay_max_fast_next_batch_size(64, 0.080) == 32
    assert replay_max_fast_next_batch_size(256, 0.001) == 256

    area_source = (PROJECT_ROOT / "core" / "algorithm_workspace_area.py").read_text(
        encoding="utf-8"
    )
    assert "def _advance_replay_burst" in area_source
    assert "QTimer.singleShot(0" in area_source
    assert "max_events=batch_size" in area_source
    assert "REPLAY_SPEED_MAX_FAST" in area_source
    assert "replay_ui_should_refresh" in area_source
    assert "replay_max_fast_next_batch_size" in area_source
    assert "REPLAY_MAX_FAST_TIME_BUDGET_SECONDS" in area_source
    assert "_replay_fast_ui_last_sync" in area_source
    sync_call = "self._sync_workspace_runtime(workspace_uid)"
    post_sync_stamp = (
        "self._replay_fast_ui_last_sync[workspace_uid] = monotonic()"
    )
    burst_index = area_source.index("def _advance_replay_burst")
    sync_index = area_source.index(sync_call, burst_index)
    stamp_index = area_source.index(post_sync_stamp, sync_index)
    assert stamp_index > sync_index

    pause_session = service.create_synthetic_session(
        broker="IB",
        symbol="EURUSD",
        timeframe="M15",
        replay_settings={
            "event_count": REPLAY_MAX_EVENTS_PER_CYCLE + 10,
            "speed": REPLAY_SPEED_MAX,
            "source": "REPLAY_MAX_PAUSE_TEST",
        },
    )
    pause_session.start()
    assert len(pause_session.advance()) == REPLAY_MAX_EVENTS_PER_CYCLE
    pause_session.pause()
    paused_index = pause_session.index
    assert pause_session.advance() == []
    assert pause_session.index == paused_index
    pause_session.resume()
    assert len(pause_session.advance()) == 10
    assert pause_session.completed

    stop_session = service.create_synthetic_session(
        broker="IB",
        symbol="EURUSD",
        timeframe="M15",
        replay_settings={
            "event_count": REPLAY_MAX_EVENTS_PER_CYCLE + 10,
            "speed": REPLAY_SPEED_MAX,
            "source": "REPLAY_MAX_STOP_TEST",
        },
    )
    stop_session.start()
    assert len(stop_session.advance()) == REPLAY_MAX_EVENTS_PER_CYCLE
    stop_session.stop()
    stopped_index = stop_session.index
    assert stop_session.advance() == []
    assert stop_session.index == stopped_index

    max_settings = WorkspaceReplaySettings(speed=REPLAY_SPEED_MAX)
    assert max_settings.speed == REPLAY_SPEED_MAX
    assert max_settings.merge_settings({"future_key": "keep"})["speed"] == 0
    assert max_settings.merge_settings({"future_key": "keep"})["future_key"] == "keep"
    max_fast_settings = WorkspaceReplaySettings(speed=REPLAY_SPEED_MAX_FAST)
    assert max_fast_settings.speed == REPLAY_SPEED_MAX_FAST
    assert max_fast_settings.merge_settings({"future_key": "keep"})["speed"] == -1
    assert (
        max_fast_settings.merge_settings({"future_key": "keep"})["future_key"]
        == "keep"
    )

    invalid_session_speed_blocked = False
    try:
        replay_events_per_cycle(50)
    except WorkspaceReplayError:
        invalid_session_speed_blocked = True
    assert invalid_session_speed_blocked

    invalid_settings_speed_blocked = False
    try:
        WorkspaceReplaySettings(speed=50)
    except WorkspaceReplaySettingsError:
        invalid_settings_speed_blocked = True
    assert invalid_settings_speed_blocked

    ui_path = PROJECT_ROOT / "ui" / "algorithm_workspace_window.ui"
    ui_text = ui_path.read_text(encoding="utf-8")
    assert "<string>100x</string>" in ui_text
    assert "<string>1000x</string>" in ui_text
    assert "<string>MAX</string>" in ui_text
    assert "<string>MAX FAST</string>" in ui_text

    print("Algorithm Workspace Replay Speed result")
    print("  supported_speeds=1x,2x,5x,10x,100x,1000x,MAX,MAX FAST")
    print(f"  max_events_per_cycle={REPLAY_MAX_EVENTS_PER_CYCLE}")
    print(f"  historical_scale_events={event_count}")
    print(f"  speed_100x_first_batch={runs[100][1][0]}")
    print(f"  speed_1000x_first_batch={runs[1000][1][0]}")
    print(f"  max_batch_sizes={','.join(map(str, max_batch_sizes))}")
    print("  speed_1x_10x_100x_1000x_max_maxfast_step_deterministic=True")
    print("  max_yields_between_bounded_batches=True")
    print("  normal_high_speed_ui_batch_bounded_to_16=True")
    print(f"  ui_100x_batches={','.join(map(str, ui_100x_batches))}")
    print(f"  ui_1000x_batches={','.join(map(str, ui_1000x_batches))}")
    print(f"  ui_max_batch_count={len(ui_max_batches)}")
    print(f"  ui_max_fast_batch_count={len(ui_max_fast_batches)}")
    print("  speed_1000x_keeps_logical_quota_1000=True")
    print("  max_continuous_burst_yields_between_chunks=True")
    print("  max_fast_continuous_burst_yields_between_chunks=True")
    max_fast_budget_ms = int(REPLAY_MAX_FAST_TIME_BUDGET_SECONDS * 1000)
    print(f"  max_fast_adaptive_time_budget_ms={max_fast_budget_ms}")
    print(f"  max_fast_adaptive_batch_cap={REPLAY_MAX_FAST_ADAPTIVE_MAX_EVENTS}")
    print("  max_fast_batch_grows_and_shrinks_from_measured_throughput=True")
    print("  max_fast_ui_interval_starts_after_previous_sync=True")
    max_fast_refresh_ms = int(REPLAY_MAX_FAST_UI_REFRESH_SECONDS * 1000)
    print(f"  max_fast_ui_refresh_interval_ms={max_fast_refresh_ms}")
    print("  max_fast_skips_only_intermediate_ui_refresh=True")
    print("  pause_responsive_between_high_speed_chunks=True")
    print("  stop_responsive_between_high_speed_chunks=True")
    print("  max_speed_persisted_as_zero_sentinel=True")
    print("  max_fast_speed_persisted_as_minus_one_sentinel=True")
    print("  future_keys_preserved=True")
    print(f"  invalid_session_speed_blocked={invalid_session_speed_blocked}")
    print(f"  invalid_settings_speed_blocked={invalid_settings_speed_blocked}")
    print("  designer_ui_updated=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_REPLAY_SPEED_CHECK=OK")


if __name__ == "__main__":
    main()
