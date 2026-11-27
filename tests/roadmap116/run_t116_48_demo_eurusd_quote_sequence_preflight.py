"""T116-48 TEST_ONLY — офлайн контракт послідовності EURUSD SpotEvent."""

from __future__ import annotations

import os
import subprocess
from contextlib import redirect_stderr
from datetime import UTC, datetime, timedelta
from io import StringIO
from typing import Any
from unittest.mock import patch

import pytest

from tests.roadmap116.run_t116_25_demo_network_safety_preflight import FakeClock
from tests.roadmap116.run_t116_32_demo_network_readonly_discovery_preflight import (
    FakeScheduler,
    FakeSdkClient,
)
from tests.roadmap116.run_t116_47_first_demo_eurusd_quotes_preflight import (
    CREDENTIALS,
    envelope,
    new_message,
    synthetic_sdk,
)
from tests.roadmap116.t116_26_process_watchdog import SupervisedResult
from tests.roadmap116.t116_30_offline_symbol_preparation import external_tcp_denied
from tests.roadmap116.t116_47_first_demo_eurusd_quotes_network import (
    ORDERS_CONFIRMATION,
    WSP_CONFIRMATION,
)
from tests.roadmap116.t116_48_demo_eurusd_quote_sequence import (
    APPROVAL_VALUE,
    APPROVAL_VARIABLE,
    CAPTURE_SECONDS,
    CHILD_MODULE,
    CLI_CONFIRMATION,
    OFFLINE_SUCCESS,
    PARENT_SUCCESS,
    QuoteSequenceController,
    approved,
    main,
    metric_lines,
    prepare_child_environment,
    safe_failure,
    supervise_child,
    verify_child,
)

NOW = datetime(2026, 11, 27, 12, 15, 30, tzinfo=UTC)


def make_session() -> tuple[
    QuoteSequenceController,
    FakeSdkClient,
    FakeScheduler,
    FakeClock,
    Any,
    Any,
    list[bool],
]:
    """Справжнього SDK-клієнта не створювати."""
    messages, common = synthetic_sdk()
    client = FakeSdkClient()
    scheduler = FakeScheduler()
    fake_clock = FakeClock()
    done: list[bool] = []
    controller = QuoteSequenceController(
        client=client,
        messages=messages,
        common=common,
        clock=fake_clock,
        schedule=scheduler.schedule,
        now=lambda: NOW,
        credentials=CREDENTIALS,
        on_finished=lambda: done.append(True),
    )
    controller.start()
    client.dispatch_connected()
    return controller, client, scheduler, fake_clock, messages, common, done


def feed(
    client: FakeSdkClient,
    messages: Any,
    common: Any,
    name: str,
    **fields: Any,
) -> None:
    client.dispatch_message(envelope(common, new_message(messages, name, **fields)))


def authorize(client: FakeSdkClient, messages: Any, common: Any) -> None:
    feed(client, messages, common, "ProtoOAApplicationAuthRes")
    feed(
        client, messages, common, "ProtoOAAccountAuthRes", ctidTraderAccountId=46368962
    )


def spot(
    client: FakeSdkClient,
    messages: Any,
    common: Any,
    *,
    bid: int = 0,
    ask: int = 0,
    timestamp: int = 0,
    account_id: int = 46368962,
    symbol_id: int = 1,
) -> None:
    fields: dict[str, int] = {
        "ctidTraderAccountId": account_id,
        "symbolId": symbol_id,
    }
    if bid:
        fields["bid"] = bid
    if ask:
        fields["ask"] = ask
    if timestamp:
        fields["timestamp"] = timestamp
    feed(client, messages, common, "ProtoOASpotEvent", **fields)


def advance_and_finish(
    controller: QuoteSequenceController,
    scheduler: FakeScheduler,
    fake_clock: FakeClock,
) -> None:
    fake_clock.seconds += CAPTURE_SECONDS + 0.1
    scheduler.tick()
    assert controller.quote is not None or controller.error_code is not None


def test_t116_48_demo_eurusd_quote_sequence_preflight(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Відокремити знімок від прогресу, перевірити supervised fail-closed."""
    denied = 0
    with external_tcp_denied():
        # 1. Ранній SpotEvent: після ACK продовжуємо спостереження 20 секунд.
        controller, client, scheduler, fake_clock, messages, common, done = (
            make_session()
        )
        authorize(client, messages, common)
        spot(client, messages, common, bid=109860, timestamp=1795781730000)
        spot(client, messages, common, ask=109860, timestamp=1795781730000)
        assert controller.metrics.spot_events == 2
        assert controller.metrics.pre_ack_events == 2
        assert controller.quote is None
        feed(
            client,
            messages,
            common,
            "ProtoOASubscribeSpotsRes",
            ctidTraderAccountId=46368962,
        )
        assert controller.phase == "SUBSCRIBED"
        assert not done
        later = int((NOW + timedelta(seconds=2)).timestamp() * 1000)
        spot(client, messages, common, bid=109861, timestamp=later)
        spot(client, messages, common, ask=109864, timestamp=later)
        assert controller.metrics.post_ack_events == 2
        assert controller.metrics.post_ack_timestamp_advances == 1
        assert controller.metrics.post_ack_changed_quotes >= 1
        assert controller.metrics.post_ack_positive_spread_quotes >= 1
        assert controller.metrics.classification(now=NOW + timedelta(seconds=3)) == (
            "PROGRESS_WITH_RECENT_TIMESTAMP"
        )
        assert client.stop_calls == 0
        advance_and_finish(controller, scheduler, fake_clock)
        assert done == [True]
        assert controller.error_code is None
        assert controller.quote is not None
        assert client.stop_calls == 1
        rendered = metric_lines(controller.metrics, now=NOW + timedelta(seconds=3))
        stdout = "\n".join(rendered) + "\n"
        success = SupervisedResult(0, False, True, stdout, "")
        assert verify_child(success) is not None

        # 2. Один snapshot і відсутність подальших оновлень — не live.
        single, fake, ticks, tick_clock, m2, c2, single_done = make_session()
        authorize(fake, m2, c2)
        feed(fake, m2, c2, "ProtoOASubscribeSpotsRes", ctidTraderAccountId=46368962)
        spot(fake, m2, c2, bid=109860, ask=109860, timestamp=later)
        assert single.metrics.classification(now=NOW) == "INITIAL_SNAPSHOT_ONLY"
        advance_and_finish(single, ticks, tick_clock)
        assert single_done and single.quote is not None
        assert single.metrics.zero_spread_quotes == 1
        denied += 1

        # 3. Кілька однакових пакетів — теж не доказ ринкового руху.
        unchanged, fake, ticks, tick_clock, m3, c3, _ = make_session()
        authorize(fake, m3, c3)
        feed(fake, m3, c3, "ProtoOASubscribeSpotsRes", ctidTraderAccountId=46368962)
        for _index in range(3):
            spot(fake, m3, c3, bid=109860, ask=109862, timestamp=later)
        assert unchanged.metrics.classification(now=NOW) == "UNCHANGED_QUOTES"
        advance_and_finish(unchanged, ticks, tick_clock)
        denied += 1

        # 4. Рух ціни без прогресу брокерського часу не є доказом live.
        no_time, fake, ticks, tick_clock, m4, c4, _ = make_session()
        authorize(fake, m4, c4)
        feed(fake, m4, c4, "ProtoOASubscribeSpotsRes", ctidTraderAccountId=46368962)
        spot(fake, m4, c4, bid=109860, ask=109862, timestamp=later)
        spot(fake, m4, c4, bid=109861, ask=109863, timestamp=later)
        assert no_time.metrics.classification(now=NOW) == "NO_TIMESTAMP_PROGRESS"
        advance_and_finish(no_time, ticks, tick_clock)
        denied += 1

        # 5. Позитивний спред / timestamps не перекреслюють несвіжий час.
        stale, fake, ticks, tick_clock, m5, c5, _ = make_session()
        authorize(fake, m5, c5)
        feed(fake, m5, c5, "ProtoOASubscribeSpotsRes", ctidTraderAccountId=46368962)
        spot(fake, m5, c5, bid=109860, ask=109863, timestamp=1795600000000)
        spot(fake, m5, c5, bid=109861, ask=109864, timestamp=1795600001000)
        assert stale.metrics.classification(now=NOW) == "TIMESTAMP_NOT_RECENT"
        advance_and_finish(stale, ticks, tick_clock)
        denied += 1

        # 6. Неправильний рахунок і символ — fail-closed.
        for account, symbol in ((999, 1), (46368962, 2)):
            rejected, fake, _, _, m6, c6, _ = make_session()
            authorize(fake, m6, c6)
            feed(fake, m6, c6, "ProtoOASubscribeSpotsRes", ctidTraderAccountId=46368962)
            spot(
                fake,
                m6,
                c6,
                bid=109860,
                ask=109863,
                account_id=account,
                symbol_id=symbol,
            )
            assert rejected.error_code == "INVALID_RESPONSE"
            denied += 1

        # 7. Без ACK — жодного успіху; без повного Bid/Ask — FAILED.
        no_ack, fake, ticks, tick_clock, m7, c7, _ = make_session()
        authorize(fake, m7, c7)
        spot(fake, m7, c7, bid=109860, ask=109862)
        tick_clock.seconds += 61
        ticks.tick()
        assert no_ack.error_code == "QUOTE_SESSION_TIMEOUT"
        denied += 1
        no_quote, fake, ticks, tick_clock, m8, c8, _ = make_session()
        authorize(fake, m8, c8)
        feed(fake, m8, c8, "ProtoOASubscribeSpotsRes", ctidTraderAccountId=46368962)
        spot(fake, m8, c8, bid=109860)
        advance_and_finish(no_quote, ticks, tick_clock)
        assert no_quote.error_code == "NO_COMPLETE_QUOTE"
        denied += 1

        # 8. Строгий розбір stdout child.
        for tampered in (
            success.stdout + "secret\n",
            success.stdout.replace("symbol_id=1", "symbol_id=2"),
            success.stdout.replace("last_ask=1.09864", "last_ask=1.00000"),
            success.stdout.replace("spot_events=4", "spot_events=999999"),
            success.stdout.replace("post_ack_events=2", "post_ack_events=9"),
            success.stdout.replace(
                "quote_sequence=PROGRESS_WITH_RECENT_TIMESTAMP", "quote_sequence=WRONG"
            ),
        ):
            assert verify_child(SupervisedResult(0, False, True, tampered, "")) is None
            denied += 1
        for malformed in (
            SupervisedResult(1, False, True, stdout, ""),
            SupervisedResult(0, True, True, stdout, ""),
            SupervisedResult(0, False, False, stdout, ""),
            SupervisedResult(0, False, True, stdout, "SECRET"),
        ):
            assert verify_child(malformed) is None
            denied += 1

        # 9. Дозволи лише через окремий env, без усіх старих one-shot режимів.
        env = {
            key: os.environ[key]
            for key in ("SystemRoot", "WINDIR", "PATH", "TEMP", "TMP")
            if key in os.environ
        }
        env[APPROVAL_VARIABLE] = APPROVAL_VALUE
        assert approved(confirmation=CLI_CONFIRMATION, environment=env)
        assert not approved(confirmation="WRONG", environment=env)
        denied += 1
        assert not approved(confirmation=CLI_CONFIRMATION, environment={})
        denied += 1
        with pytest.raises(PermissionError):
            prepare_child_environment(
                CREDENTIALS,
                environment=env,
                orders="WRONG",
                wsp=WSP_CONFIRMATION,
            )
        denied += 1
        child_env = prepare_child_environment(
            CREDENTIALS,
            environment=env,
            orders=ORDERS_CONFIRMATION,
            wsp=WSP_CONFIRMATION,
        )
        assert approved(
            confirmation=CLI_CONFIRMATION, environment=child_env, child=True
        )
        assert not approved(confirmation=CLI_CONFIRMATION, environment=env, child=True)
        denied += 1

        # 10. Ніякого SDK Client у звичайному pytest / offline-preflight.
        with patch(
            "tests.roadmap116.t116_48_demo_eurusd_quote_sequence.run_network_child",
            side_effect=AssertionError("мережа заборонена"),
        ) as network:
            assert (
                main(
                    ["--offline-preflight"],
                    sdk_check=lambda: "VERIFIED_NO_EXTERNAL_NETWORK",
                )
                == 0
            )
            assert network.call_count == 0
            with pytest.raises(PermissionError):
                main(["--demo-network", "--confirm", CLI_CONFIRMATION], environment=env)
            denied += 1
            for args in (
                [],
                ["--live"],
                ["--offline-preflight", "--confirm", CLI_CONFIRMATION],
            ):
                with redirect_stderr(StringIO()):
                    with pytest.raises(SystemExit):
                        main(args)
                denied += 1
        assert OFFLINE_SUCCESS in capsys.readouterr().out

        # 11. Контроль supervisor і заборона витоку секретів.
        class FakeProcess:
            def __init__(self) -> None:
                self.killed = False

            def communicate(self, timeout: float) -> tuple[str, str]:
                assert timeout == 75 and not self.killed
                return success.stdout, ""

            def wait(self) -> int:
                return 124 if self.killed else 0

            def poll(self) -> int:
                return 124 if self.killed else 0

            def kill(self) -> None:
                self.killed = True

        def fake_popen(argv: list[str], **kwargs: Any) -> FakeProcess:
            assert argv[1:3] == ["-m", CHILD_MODULE]
            assert kwargs["env"] == child_env
            assert kwargs["shell"] is False
            assert kwargs["stdin"] == subprocess.DEVNULL
            return FakeProcess()

        supervised = supervise_child(child_env, popen=fake_popen)
        assert verify_child(supervised) is not None
        with patch.dict(os.environ, env, clear=False):
            assert (
                main(
                    ["--demo-network", "--confirm", CLI_CONFIRMATION],
                    ask=lambda prompt: (
                        ORDERS_CONFIRMATION if "Orders" in prompt else WSP_CONFIRMATION
                    ),
                    ask_password=lambda _: "TEST_ONLY_PASSWORD",
                    credential_reader=lambda _: CREDENTIALS,
                    runner=lambda _: supervised,
                    sdk_check=lambda: "VERIFIED_NO_EXTERNAL_NETWORK",
                )
                == 0
            )
        output = capsys.readouterr().out
        assert PARENT_SUCCESS in output
        assert CREDENTIALS.access_token not in output
        assert CREDENTIALS.client_secret not in output
        denied += 1
        assert safe_failure(SupervisedResult(124, True, True, "SECRET", "")) == (
            "HARD_PROCESS_TIMEOUT"
        )
        denied += 1
        missing_quote = SupervisedResult(
            1, False, True, "failure_code=NO_COMPLETE_QUOTE\n", ""
        )
        assert safe_failure(missing_quote) == "NO_COMPLETE_QUOTE"
        denied += 1
        unknown_error = SupervisedResult(1, False, True, "SECRET=TOKEN\n", "")
        assert safe_failure(unknown_error) == "SDK_CHILD_FAILED"
        denied += 1

    print("T116-48 TEST_ONLY | DEMO EURUSD SpotEvent sequence OFFLINE")
    print(f"negative_scenarios_denied={denied}")
    print("account_id=46368962")
    print("symbol_id=1")
    print("early_spot_before_ack=HANDLED_ACK_REQUIRED")
    print("partial_bid_ask_updates=VERIFIED_SYNTHETIC")
    print("classification=SNAPSHOT_VS_PRICE_PROGRESS_VS_TIMESTAMP_RECENCY")
    print("outbound_guard=T116-47_EXACT_READONLY_THREE_LEVELS")
    print("child_process=NOT_STARTED_NETWORK")
    print("sdk_client_constructor=NOT_CALLED")
    print("external_tcp=BLOCKED")
    print("real_broker_requests=0")
    print("production_changes=0")
    print("network_launch_authorized=NO")
    print(OFFLINE_SUCCESS)
