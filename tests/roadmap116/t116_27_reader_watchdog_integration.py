"""T116-27 TEST_ONLY — автономний читач і watchdog на підставному транспорті.

Модуль не створює SDK Client, мережеві з'єднання чи процес LGE.
Реальне підключення до брокера в цьому модулі навмисно відсутнє.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Event

from google.protobuf.message import Message

from tests.roadmap116.t116_22_standalone_demo_reader import (
    StandaloneDemoQuoteReader,
)
from tests.roadmap116.t116_25_demo_network_safety import (
    OfflineDemoSafetySession,
)
from tests.roadmap116.t116_26_process_watchdog import (
    CAPTURE_DEADLINE_SECONDS,
    CaptureDeadline,
)


@dataclass(frozen=True, slots=True)
class CaptureResult:
    """Підсумок роботи фактичного циклу читача на підставних подіях."""

    reason: str
    spot_events: int
    accepted_observations: int
    timer_fired: bool


def run_offline_reader_capture(
    *,
    reader: StandaloneDemoQuoteReader,
    session: OfflineDemoSafetySession,
    receive: Callable[[Event], Message | None],
    deadline_seconds: float = CAPTURE_DEADLINE_SECONDS,
    max_observations: int | None = None,
) -> CaptureResult:
    """Пов'язати реальний reader, TEST_ONLY transport і незалежний таймер.

    receive має прокидатися за stop_event. Якщо він зависне без відповіді,
    зовнішній supervisor T116-26 повинен завершити дочірній процес.
    """
    if reader.sender is not session:
        raise ValueError("T116-27: reader не прив'язаний до захищеної сесії")
    if not 0 < deadline_seconds <= CAPTURE_DEADLINE_SECONDS:
        raise ValueError("T116-27: недопустима тривалість збору")
    if max_observations is not None and max_observations <= 0:
        raise ValueError("T116-27: ліміт спостережень має бути додатним")

    stop_requested = Event()
    spot_events = 0
    accepted = 0
    reason = "SOFT_DEADLINE"

    with session:
        with CaptureDeadline(
            stop_requested.set, seconds=deadline_seconds
        ) as timer:
            while not stop_requested.is_set():
                event = receive(stop_requested)
                if stop_requested.is_set():
                    break
                if event is None:
                    continue
                spot_events += 1
                if reader.on_spot_event(event) is None:
                    continue
                accepted += 1
                if (
                    max_observations is not None
                    and accepted >= max_observations
                ):
                    reason = "OBSERVATION_LIMIT"
                    break
            return CaptureResult(
                reason=reason,
                spot_events=spot_events,
                accepted_observations=accepted,
                timer_fired=timer.expired.is_set(),
            )
