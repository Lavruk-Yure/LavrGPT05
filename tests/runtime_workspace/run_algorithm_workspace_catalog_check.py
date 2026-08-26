"""Synthetic account/symbol catalog check for RoadMap92."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (
    WORKSPACE_ACCOUNT_MODE_DEMO,
    WORKSPACE_ACCOUNT_MODE_LIVE,
    WORKSPACE_ACCOUNT_MODE_PAPER,
)
from core.algorithm_workspace_catalog import AlgorithmWorkspaceCatalog
from engine.runtime_account_state import RuntimeAccountState


class FakeIbService:
    @staticmethod
    def get_managed_accounts() -> list[str]:
        return ["DUM513747", "U1234567"]

    @staticmethod
    def get_account_state() -> RuntimeAccountState:
        return RuntimeAccountState(
            account_id="DUM513747",
            broker_name="IB",
            currency="USD",
            balance=125000.50,
        )


class FakeCtraderService:
    @staticmethod
    def get_account_state() -> RuntimeAccountState:
        return RuntimeAccountState(
            account_id="111",
            broker_name="CTRADER",
            currency="USD",
            balance=2500.75,
        )

    @staticmethod
    def get_account_list() -> list[dict]:
        return [
            {
                "account_id": "111",
                "trader_login": "demo-login",
                "account_mode": "DEMO",
            },
            {
                "account_id": "222",
                "trader_login": "live-login",
                "account_mode": "LIVE",
            },
        ]


def main() -> None:
    runtime_engine = SimpleNamespace(
        ib_runtime_service=FakeIbService(),
        ctrader_runtime_service=FakeCtraderService(),
    )
    catalog = AlgorithmWorkspaceCatalog(runtime_engine)

    ib_accounts = catalog.list_accounts("IB")
    ib_modes = {item.account_id: item.account_mode for item in ib_accounts}
    assert ib_modes["DUM513747"] == WORKSPACE_ACCOUNT_MODE_PAPER
    assert ib_modes["U1234567"] == WORKSPACE_ACCOUNT_MODE_LIVE
    ib_paper = catalog.find_account("IB", "DUM513747")
    assert ib_paper is not None
    assert ib_paper.balance == 125000.50
    assert ib_paper.currency == "USD"

    ctrader_accounts = catalog.list_accounts("CTRADER")
    ctrader_modes = {
        item.account_id: item.account_mode for item in ctrader_accounts
    }
    assert ctrader_modes["111"] == WORKSPACE_ACCOUNT_MODE_DEMO
    assert ctrader_modes["222"] == WORKSPACE_ACCOUNT_MODE_LIVE
    ctrader_demo = catalog.find_account("CTRADER", "111")
    assert ctrader_demo is not None
    assert ctrader_demo.balance == 2500.75
    assert ctrader_demo.currency == "USD"

    symbols = catalog.list_symbols("IB", "DUM513747")
    assert "EURUSD" in symbols
    assert "GBPUSD" in symbols

    print("Algorithm Workspace Catalog result")
    print(f"  ib_accounts={len(ib_accounts)}")
    print(f"  ctrader_accounts={len(ctrader_accounts)}")
    print(f"  ib_balance={ib_paper.balance} {ib_paper.currency}")
    print(
        f"  ctrader_balance={ctrader_demo.balance} "
        f"{ctrader_demo.currency}"
    )
    print(f"  symbols={len(symbols)}")
    print("ALGORITHM_WORKSPACE_CATALOG_CHECK=OK")


if __name__ == "__main__":
    main()
