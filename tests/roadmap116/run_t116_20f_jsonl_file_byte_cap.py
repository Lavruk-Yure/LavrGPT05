"""T116-20F TEST_ONLY — жорсткий ліміт розміру JSONL у байтах UTF-8.

Перевіряє лише RawSpotRecorder на тимчасових файлах, без брокера та LGE.
"""

from __future__ import annotations

import json
import runpy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


TELEMETRY_FILE = (
    Path(__file__).resolve().parent / "run_t116_19_ctrader_raw_spot_telemetry.py"
)


def add_spot(recorder: Any, *, symbol: str = "EURUSD") -> None:
    """Подати сталу синтетичну котировку до записувача."""
    stamp = datetime(2026, 11, 24, 9, 0, tzinfo=UTC)
    recorder.observe(
        symbol_id=55,
        symbol=symbol,
        event_timestamp=int(stamp.timestamp() * 1000),
        received_at=stamp,
        raw_bid=109370,
        raw_ask=109372,
        cached_bid=1.09370,
        cached_ask=1.09372,
    )


def test_t116_20f_jsonl_file_byte_cap(tmp_path: Path) -> None:
    """Не допустити жодного запису, який перевищить задану межу."""
    namespace = runpy.run_path(str(TELEMETRY_FILE), run_name="t116_20f_test_only")
    recorder_type = namespace["RawSpotRecorder"]
    max_live_bytes = namespace["MAX_LIVE_JSONL_BYTES"]
    assert max_live_bytes == 2 * 1024 * 1024

    probe = recorder_type(max_events=3)
    add_spot(probe, symbol="ЄВРО-EURUSD")
    encoded_row = (
        json.dumps(probe.records[0], ensure_ascii=False, sort_keys=True) + "\n"
    ).encode("utf-8")
    assert b"\xd0\x84" in encoded_row
    assert len(encoded_row) > 100

    # Запис рівно до межі дозволений, наступний — заблокований.
    exact_path = tmp_path / "exact.jsonl"
    exact = recorder_type(path=exact_path, max_events=5,
                          max_file_bytes=len(encoded_row))
    add_spot(exact, symbol="ЄВРО-EURUSD")
    assert exact_path.read_bytes() == encoded_row
    assert exact_path.stat().st_size == len(encoded_row)
    add_spot(exact, symbol="ЄВРО-EURUSD")
    assert exact_path.read_bytes() == encoded_row
    assert exact.seen == 2 and len(exact.records) == 1
    assert exact.byte_limit_reached and exact.byte_limit_hits == 1

    # Один великий рядок не записується навіть частково.
    oversized_path = tmp_path / "oversized.jsonl"
    oversized = recorder_type(path=oversized_path, max_file_bytes=1024)
    add_spot(oversized, symbol="Є" * 4096)
    assert not oversized_path.exists()
    assert oversized.seen == 1 and not oversized.records
    assert oversized.byte_limit_reached and oversized.byte_limit_hits == 1

    # Існуючий файл не скорочується та не переповнюється.
    existing_path = tmp_path / "existing.jsonl"
    existing_path.write_bytes(encoded_row)
    existing = recorder_type(path=existing_path,
                             max_file_bytes=len(encoded_row))
    add_spot(existing, symbol="ЄВРО-EURUSD")
    assert existing_path.read_bytes() == encoded_row
    assert existing.byte_limit_reached and existing.byte_limit_hits == 1

    # Кількісний ліміт 3000 зберігає чинну незалежну семантику.
    count_path = tmp_path / "count.jsonl"
    count_only = recorder_type(path=count_path, max_events=1,
                               max_file_bytes=4096)
    add_spot(count_only)
    add_spot(count_only)
    assert count_only.seen == 2 and len(count_only.records) == 1
    assert len(count_path.read_bytes().splitlines()) == 1
    assert not count_only.byte_limit_reached
    assert count_only.file_errors == 0

    # Довести фактичне досягнення стандартної межі 2 МіБ до 3000 подій.
    default_path = tmp_path / "default_cap.jsonl"
    default_recorder = recorder_type(path=default_path)
    for _ in range(1500):
        add_spot(default_recorder, symbol="EURUSD" + "Є" * 1500)
        if default_recorder.byte_limit_reached:
            break
    assert default_recorder.byte_limit_reached
    assert default_recorder.byte_limit_hits == 1
    assert default_recorder.seen < 1500
    assert default_path.stat().st_size <= max_live_bytes
    assert default_path.read_bytes().endswith(b"\n")
    assert default_recorder.file_errors == 0

    print("T116-20F TEST_ONLY | bounded UTF-8 JSONL file size")
    print(f"default_jsonl_byte_cap={max_live_bytes}")
    print("utf8_multibyte_length=VERIFIED")
    print("exact_byte_boundary=ALLOWED")
    print("next_row_after_cap=BLOCKED")
    print("oversized_single_record=BLOCKED_WITHOUT_PARTIAL_WRITE")
    print("existing_file_not_truncated=VERIFIED")
    print("event_count_cap=UNCHANGED")
    print("default_2mib_file_cap=VERIFIED_BEFORE_EVENT_COUNT_LIMIT")
    print("actual_broker_stream=NOT_STARTED")
    print("real_broker_requests=0")
    print("real_config_disk_writes=0")
    print("production_changes=0")
    print("T116-20F=GREEN_OFFLINE_JSONL_FILE_BYTE_CAP")
