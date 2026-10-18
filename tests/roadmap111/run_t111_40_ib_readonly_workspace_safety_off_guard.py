# -*- coding: utf-8 -*-
"""T111-40 v2 — IB Read-Only Workspace Safety OFF Guard — TEST_ONLY."""

from __future__ import annotations

from dataclasses import dataclass

from core.workspace_broker_market import (
    RuntimeEngineWorkspaceMarketProvider,
    WorkspaceBrokerBinding,
)

TEST_ONLY = True
BROKER_REQUESTS = 0
BROKER_EXECUTION_ATTEMPTED = False
PRODUCTION_LOGIC_CHANGED = True


@dataclass
class _Context:
    execution_mode: str = "OFF"


@dataclass
class _Decision:
    allowed: bool = True
    reason_code: str = "ALLOWED"
    reason_text: str = "guard evaluated"
    matching_exposure: object | None = None


class _RuntimeEngineStub:
    def __init__(self) -> None:
        self.context = _Context()
        self.guard_calls: list[tuple[str, str, str]] = []

    def refresh_ib_fx_external_exposure_guard(
        self,
        *,
        account_id: str,
        symbol_name: str,
        runtime_mode: str,
    ) -> _Decision:
        self.guard_calls.append((account_id, symbol_name, runtime_mode))
        return _Decision()


class _ProviderHarness(RuntimeEngineWorkspaceMarketProvider):
    def bind_for_test(self, binding: WorkspaceBrokerBinding) -> None:
        """Додати binding без broker start/request для TEST_ONLY."""
        self._bindings[binding.workspace_uid] = binding

    def has_checked_at(self, workspace_uid: str) -> bool:
        """Перевірити internal cache через контрольований test harness."""
        return workspace_uid in self._execution_safety_checked_at


def _require(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)


def main() -> int:
    runtime_engine = _RuntimeEngineStub()
    provider = _ProviderHarness(runtime_engine)
    workspace_uid = "t111-40-ib"

    provider.bind_for_test(
        WorkspaceBrokerBinding(
            workspace_uid=workspace_uid,
            broker="IB",
            account_id="DU_TEST",
            symbol="EURUSD",
            timeframe="M15",
        )
    )

    off_snapshot = provider.get_workspace_execution_safety(
        workspace_uid,
        runtime_mode="PAPER",
        force=True,
    )

    off_guard_skipped = len(runtime_engine.guard_calls) == 0
    off_snapshot_allowed = off_snapshot.allowed
    off_reason_present = "orders are OFF" in off_snapshot.message
    off_does_not_cache_checked_at = not provider.has_checked_at(workspace_uid)

    runtime_engine.context.execution_mode = "SEMI"

    semi_snapshot = provider.get_workspace_execution_safety(
        workspace_uid,
        runtime_mode="PAPER",
        force=False,
    )

    semi_guard_called_once = len(runtime_engine.guard_calls) == 1
    semi_call_arguments_correct = runtime_engine.guard_calls == [
        ("DU_TEST", "EURUSD", "PAPER")
    ]
    semi_snapshot_allowed = semi_snapshot.allowed
    semi_check_cached_at = provider.has_checked_at(workspace_uid)

    _require(
        off_guard_skipped,
        "OFF must skip IB external-exposure refresh",
    )
    _require(
        off_snapshot_allowed,
        "OFF snapshot must be allowed",
    )
    _require(
        off_reason_present,
        "OFF snapshot reason",
    )
    _require(
        off_does_not_cache_checked_at,
        "OFF must not create stale cache",
    )
    _require(
        semi_guard_called_once,
        "OFF -> SEMI must execute guard immediately",
    )
    _require(
        semi_call_arguments_correct,
        "SEMI guard arguments",
    )
    _require(
        semi_snapshot_allowed,
        "SEMI guard result must be applied",
    )
    _require(
        semi_check_cached_at,
        "SEMI guard check must be cached",
    )

    print("T111-40 TEST_ONLY")
    print("verdict=IB_WORKSPACE_SAFETY_ORDERS_OFF_GUARDED")
    print(f"off_guard_skipped={off_guard_skipped}")
    print(f"off_snapshot_allowed={off_snapshot_allowed}")
    print(f"off_reason_present={off_reason_present}")
    print("off_does_not_cache_checked_at=" f"{off_does_not_cache_checked_at}")
    print(f"semi_guard_called_once={semi_guard_called_once}")
    print("semi_call_arguments_correct=" f"{semi_call_arguments_correct}")
    print(f"semi_snapshot_allowed={semi_snapshot_allowed}")
    print(f"semi_check_cached_at={semi_check_cached_at}")
    print(f"TEST_ONLY={TEST_ONLY}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print("broker_execution_attempted=" f"{BROKER_EXECUTION_ATTEMPTED}")
    print("production_logic_changed=" f"{PRODUCTION_LOGIC_CHANGED}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
