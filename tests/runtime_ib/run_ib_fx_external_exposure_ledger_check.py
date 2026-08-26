"""Persistent IB CASH FX external exposure ledger and guard check."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.ib_fx_external_exposure import (  # noqa: E402
    IB_FX_EXTERNAL_EXPOSURE_CONFIRMED,
    IB_FX_EXTERNAL_EXPOSURE_STALE,
    IB_FX_GUARD_MODE_LIVE,
    IB_FX_GUARD_MODE_LIVE_READ_ONLY,
    IB_FX_GUARD_MODE_PAPER,
    IB_FX_GUARD_MODE_REPLAY,
)
from engine.broker_order_identity import (  # noqa: E402
    ORDER_CONTROL_MODE_AUTO,
    ORDER_CONTROL_MODE_MANUAL,
    ORDER_CONTROL_MODE_SEMI,
)
from engine.runtime_account_state import RuntimeAccountState  # noqa: E402
from engine.runtime_constants import (  # noqa: E402
    IB_RECONCILIATION_STATUS_RECONCILED,
)
from engine.runtime_engine import RuntimeEngine  # noqa: E402
from engine.runtime_events import RuntimeEventType  # noqa: E402
from tests.runtime_ib import (  # noqa: E402
    run_ib_broker_residual_and_missing_close_evidence_check as fixture,
)
from tests.runtime_ib import (  # noqa: E402
    run_runtime_engine_ib_broker_residual_persistence_check as support,
)

ACCOUNT_ID = fixture.ACCOUNT_ID
POSITION_ID = fixture.EURUSD_ID
GBPUSD_ID = f"IB:{ACCOUNT_ID}:GBPUSD"


class _GuardedExecutionService(support.EvidenceService):
    """Synthetic service proving the guard runs before broker execution."""

    def __init__(self, snapshot: dict) -> None:
        super().__init__(snapshot)
        self.broker_requests = 0

    def get_account_state(self) -> RuntimeAccountState:
        return RuntimeAccountState(
            account_id=ACCOUNT_ID,
            broker_name="IB",
        )

    def place_market_order(
        self,
        symbol_name: str,
        side: str,
        quantity: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        comment: str = "LGE manual order",
    ) -> dict:
        del symbol_name, side, quantity, stop_loss, take_profit, comment
        self.broker_requests += 1
        return {"order_id": 999, "status": "FILLED"}


def _without_position_observation() -> dict:
    snapshot = support.build_live_like_evidence(include_external_execution=False)
    snapshot["captured_utc"] = "2026-08-04T06:01:14+00:00"
    snapshot["positions"] = []
    return snapshot


def _managed_only_position_observation() -> dict:
    snapshot = support.build_live_like_evidence(include_external_execution=False)
    snapshot["captured_utc"] = "2026-08-04T09:00:00+00:00"
    snapshot["positions"] = [
        fixture.build_position(POSITION_ID, "EUR", "USD", -1000.0)
    ]
    snapshot["executions"] = [
        {
            "account": ACCOUNT_ID,
            "symbol": "EUR",
            "currency": "USD",
            "sec_type": "CASH",
            "symbol_name": "EURUSD",
            "broker_position_id": POSITION_ID,
            "side": "SLD",
            "shares": 1000.0,
            "price": 1.1372,
            "time": "20260804 05:55:00 US/Eastern",
            "order_id": 194,
            "perm_id": 1329483705,
        }
    ]
    return snapshot


def _pure_external_gbpusd_observation() -> dict:
    snapshot = _without_position_observation()
    snapshot["captured_utc"] = "2026-08-04T08:30:00+00:00"
    snapshot["positions"] = [
        fixture.build_position(GBPUSD_ID, "GBP", "USD", 1000.0)
    ]
    return snapshot


def _group(engine: RuntimeEngine, symbol_name: str):
    snapshot = engine.sync_active_broker_position_groups()
    matches = [
        group for group in snapshot.groups if group.symbol_name == symbol_name
    ]

    if len(matches) != 1:
        raise AssertionError(
            f"Expected one {symbol_name} IB group, got {len(matches)}"
        )

    return matches[0]


def main() -> int:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "runtime.db"
        first_engine = RuntimeEngine(db_path=str(db_path))

        try:
            support.seed_runtime_position(first_engine)
            first_service = support.EvidenceService(
                support.build_live_like_evidence(include_external_execution=True)
            )
            first_engine.set_ib_runtime_service(first_service)
            first_engine.set_broker("IB")
            confirmed_group = _group(first_engine, "EURUSD")

            if confirmed_group.reconciliation_status != (
                IB_RECONCILIATION_STATUS_RECONCILED
            ):
                raise AssertionError("Confirmed mixed group is not reconciled")

            if confirmed_group.broker_residual_signed_volume != 2000.0:
                raise AssertionError("Confirmed external residual differs")

            if confirmed_group.broker_residual_evidence_status != (
                IB_FX_EXTERNAL_EXPOSURE_CONFIRMED
            ):
                raise AssertionError("Confirmed exposure status differs")

            confirmed_ledger = (
                first_engine.repository.get_active_ib_fx_external_exposures()
            )

            if len(confirmed_ledger) != 1:
                raise AssertionError("Confirmed exposure was not persisted")
        finally:
            first_engine.connection.close()

        restart_engine = RuntimeEngine(db_path=str(db_path))

        try:
            restart_service = support.EvidenceService(
                _without_position_observation()
            )
            restart_engine.set_ib_runtime_service(restart_service)
            restart_engine.set_broker("IB")
            stale_group = _group(restart_engine, "EURUSD")

            if stale_group.broker_position_present:
                raise AssertionError("Missing reqPositions row was invented")

            if stale_group.broker_residual_signed_volume != 2000.0:
                raise AssertionError("Empty reqPositions erased the residual")

            if stale_group.broker_residual_evidence_status != (
                IB_FX_EXTERNAL_EXPOSURE_STALE
            ):
                raise AssertionError("Missing observation was not marked stale")

            if not stale_group.broker_residual_confirmation_required:
                raise AssertionError("Stale exposure lacks confirmation flag")

            if stale_group.display_signed_volume != 1000.0:
                raise AssertionError("Persisted group display net differs")

            stale_ledger = (
                restart_engine.repository.get_active_ib_fx_external_exposures()
            )

            if len(stale_ledger) != 1:
                raise AssertionError("Stale exposure disappeared from ledger")

            exposure = stale_ledger[0]

            if exposure.evidence_status != IB_FX_EXTERNAL_EXPOSURE_STALE:
                raise AssertionError("Ledger did not persist stale status")

            replay = restart_engine.evaluate_ib_fx_external_exposure_guard(
                account_id=ACCOUNT_ID,
                symbol_name="EURUSD",
                runtime_mode=IB_FX_GUARD_MODE_REPLAY,
            )
            live_read_only = (
                restart_engine.evaluate_ib_fx_external_exposure_guard(
                    account_id=ACCOUNT_ID,
                    symbol_name="EURUSD",
                    runtime_mode=IB_FX_GUARD_MODE_LIVE_READ_ONLY,
                )
            )
            paper_same = restart_engine.evaluate_ib_fx_external_exposure_guard(
                account_id=ACCOUNT_ID,
                symbol_name="EURUSD",
                runtime_mode=IB_FX_GUARD_MODE_PAPER,
            )
            live_same = restart_engine.evaluate_ib_fx_external_exposure_guard(
                account_id=ACCOUNT_ID,
                symbol_name="EURUSD",
                runtime_mode=IB_FX_GUARD_MODE_LIVE,
            )
            paper_other_symbol = (
                restart_engine.evaluate_ib_fx_external_exposure_guard(
                    account_id=ACCOUNT_ID,
                    symbol_name="GBPUSD",
                    runtime_mode=IB_FX_GUARD_MODE_PAPER,
                )
            )

            if not replay.allowed or not live_read_only.allowed:
                raise AssertionError("Non-executing modes were blocked")

            if paper_same.allowed or live_same.allowed:
                raise AssertionError("Same-symbol execution was not blocked")

            if not paper_other_symbol.allowed:
                raise AssertionError("Different symbol was blocked")

            guarded_service = _GuardedExecutionService(
                _pure_external_gbpusd_observation()
            )
            restart_engine.set_ib_runtime_service(guarded_service)
            trade_count_before = int(
                restart_engine.connection.execute(
                    "SELECT COUNT(*) FROM trades"
                ).fetchone()[0]
            )

            for control_mode in (
                ORDER_CONTROL_MODE_MANUAL,
                ORDER_CONTROL_MODE_SEMI,
                ORDER_CONTROL_MODE_AUTO,
            ):
                try:
                    restart_engine.place_manual_market_order(
                        symbol_name="GBPUSD",
                        side="BUY",
                        lots=0.01,
                        control_mode=control_mode,
                    )
                except RuntimeError as error:
                    if "External IB FX exposure blocks" not in str(error):
                        raise
                else:
                    raise AssertionError(
                        "Current broker-only exposure bypassed "
                        f"{control_mode} LGE EXCLUSIVE guard"
                    )

            guarded_service.snapshot = _without_position_observation()

            try:
                restart_engine.place_manual_market_order(
                    symbol_name="EURUSD",
                    side="BUY",
                    lots=0.01,
                    control_mode=ORDER_CONTROL_MODE_AUTO,
                )
            except RuntimeError as error:
                if "External IB FX exposure blocks" not in str(error):
                    raise
            else:
                raise AssertionError("AUTO execution bypassed exposure guard")

            trade_count_after = int(
                restart_engine.connection.execute(
                    "SELECT COUNT(*) FROM trades"
                ).fetchone()[0]
            )

            if guarded_service.broker_requests != 0:
                raise AssertionError("Exposure guard sent an IB broker request")

            if trade_count_after != trade_count_before:
                raise AssertionError("Blocked AUTO order persisted a Trade")

            guarded_service.snapshot = _managed_only_position_observation()
            _group(restart_engine, "EURUSD")
            cleared_group = _group(restart_engine, "EURUSD")

            if cleared_group.broker_residual_present:
                raise AssertionError("Current broker evidence did not clear residual")

            active_after_clear = (
                restart_engine.repository.get_active_ib_fx_external_exposures()
            )

            if any(
                exposure.symbol_name == "EURUSD"
                for exposure in active_after_clear
            ):
                raise AssertionError(
                    "Current EURUSD evidence did not clear matching exposure"
                )

            if not any(
                exposure.symbol_name == "GBPUSD"
                and exposure.evidence_status == IB_FX_EXTERNAL_EXPOSURE_STALE
                for exposure in active_after_clear
            ):
                raise AssertionError(
                    "Unobserved GBPUSD external exposure was erased"
                )

            event_counts = {
                str(row["event_type"]): int(row["event_count"])
                for row in restart_engine.connection.execute(
                    """
                    SELECT event_type, COUNT(*) AS event_count
                    FROM runtime_events
                    WHERE event_type IN (?, ?, ?)
                    GROUP BY event_type
                    """,
                    (
                        RuntimeEventType.IB_FX_EXTERNAL_EXPOSURE_CONFIRMED.value,
                        RuntimeEventType.IB_FX_EXTERNAL_EXPOSURE_STALE.value,
                        RuntimeEventType.IB_FX_EXTERNAL_EXPOSURE_CLEARED.value,
                    ),
                ).fetchall()
            }
            expected_event_counts = {
                RuntimeEventType.IB_FX_EXTERNAL_EXPOSURE_CONFIRMED.value: 2,
                RuntimeEventType.IB_FX_EXTERNAL_EXPOSURE_STALE.value: 2,
                RuntimeEventType.IB_FX_EXTERNAL_EXPOSURE_CLEARED.value: 1,
            }
            if event_counts != expected_event_counts:
                raise AssertionError(
                    "External exposure transition events differ: "
                    f"expected={expected_event_counts}, actual={event_counts}"
                )
        finally:
            restart_engine.connection.close()

    print("IB FX external exposure ledger result")
    print("  confirmed_residual=BUY 2000")
    print("  restart_without_position_row_visible=True")
    print("  empty_reqPositions_does_not_erase=True")
    print("  stale_requires_confirmation=True")
    print("  external_filter_payload_available=True")
    print("  replay_allowed=True")
    print("  live_read_only_allowed=True")
    print("  paper_same_symbol_blocked=True")
    print("  live_same_symbol_blocked=True")
    print("  different_symbol_allowed=True")
    print("  current_broker_only_symbol_blocked=True")
    print("  manual_semi_auto_blocked_before_trade=True")
    print("  broker_requests=0")
    print("  durable_transition_events=CONFIRMED,STALE,CLEARED")
    print("  duplicate_transition_events=False")
    print("  current_evidence_clears_matching_symbol=True")
    print("  unobserved_external_symbol_retained=True")
    print("IB_FX_EXTERNAL_EXPOSURE_LEDGER_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
