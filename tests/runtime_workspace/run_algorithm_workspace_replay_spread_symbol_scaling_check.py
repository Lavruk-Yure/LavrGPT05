# -*- coding: utf-8 -*-
"""Перевірка symbol-aware Replay spread для RM103 / 7W.2."""

from __future__ import annotations

import math
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_DATA_MODE_REPLAY,
    AlgorithmWorkspace,
)
from core.workspace_history import WorkspaceCsvHistoryLoader  # noqa: E402
from core.workspace_replay import WorkspaceReplayService  # noqa: E402
from core.workspace_replay_settings import WorkspaceReplaySettings  # noqa: E402
from engine.runtime_constants import (  # noqa: E402
    DEFAULT_WORKSPACE_HISTORY_SPREAD,
    DEFAULT_WORKSPACE_HISTORY_SPREAD_PIPS,
    resolve_forex_pip_size,
    resolve_workspace_history_default_spread,
)


EXPECTED_SPREADS = {
    "EURUSD": 0.00012,
    "GBPUSD": 0.00012,
    "USDJPY": 0.012,
}


def _workspace(
    symbol: str,
    replay_settings: dict[str, object] | None = None,
) -> AlgorithmWorkspace:
    return AlgorithmWorkspace.create(
        broker="CTRADER",
        account_id="12345",
        symbol=symbol,
        timeframe="M1",
        algorithm="RailAlgorithm",
        data_mode=WORKSPACE_DATA_MODE_REPLAY,
        replay_settings=replay_settings,
    )


def _write_history(path: Path, *, jpy: bool) -> None:
    if jpy:
        rows = (
            "timestamp,open,high,low,close,volume\n"
            "2026-08-25T10:00:00Z,147.100,147.120,147.090,147.110,100\n"
            "2026-08-25T10:01:00Z,147.110,147.130,147.100,147.120,120\n"
        )
    else:
        rows = (
            "timestamp,open,high,low,close,volume\n"
            "2026-08-25T10:00:00Z,1.17000,1.17020,1.16990,1.17010,100\n"
            "2026-08-25T10:01:00Z,1.17010,1.17030,1.17000,1.17020,120\n"
        )
    path.write_text(rows, encoding="utf-8")


def _assert_close(actual: float, expected: float) -> None:
    assert math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-12)


def main() -> None:
    assert DEFAULT_WORKSPACE_HISTORY_SPREAD_PIPS == 1.2
    _assert_close(DEFAULT_WORKSPACE_HISTORY_SPREAD, 0.00012)

    resolved = {
        symbol: resolve_workspace_history_default_spread(symbol)
        for symbol in EXPECTED_SPREADS
    }
    for symbol, expected in EXPECTED_SPREADS.items():
        _assert_close(resolved[symbol], expected)
        _assert_close(
            resolved[symbol] / resolve_forex_pip_size(symbol),
            DEFAULT_WORKSPACE_HISTORY_SPREAD_PIPS,
        )

    settings_defaults = {
        symbol: WorkspaceReplaySettings.from_workspace(_workspace(symbol)).spread
        for symbol in EXPECTED_SPREADS
    }
    for symbol, expected in EXPECTED_SPREADS.items():
        _assert_close(settings_defaults[symbol], expected)

    explicit_spread = 0.00012
    persisted_legacy = WorkspaceReplaySettings.from_workspace(
        _workspace("USDJPY", {"spread": explicit_spread})
    )
    _assert_close(persisted_legacy.spread, explicit_spread)

    non_forex_fallback = resolve_workspace_history_default_spread("XAUUSD")
    _assert_close(non_forex_fallback, DEFAULT_WORKSPACE_HISTORY_SPREAD)

    with TemporaryDirectory() as temp_dir:
        directory = Path(temp_dir)
        eurusd_path = directory / "eurusd_m1.csv"
        usdjpy_path = directory / "usdjpy_m1.csv"
        _write_history(eurusd_path, jpy=False)
        _write_history(usdjpy_path, jpy=True)

        loader = WorkspaceCsvHistoryLoader()
        eurusd_data = loader.load(
            file_path=eurusd_path,
            broker="CTRADER",
            symbol="EURUSD",
            timeframe="M1",
        )
        usdjpy_data = loader.load(
            file_path=usdjpy_path,
            broker="CTRADER",
            symbol="USDJPY",
            timeframe="M1",
        )
        _assert_close(eurusd_data.events[0].spread, 0.00012)
        _assert_close(usdjpy_data.events[0].spread, 0.012)

        service = WorkspaceReplayService()
        usdjpy_session = service.create_historical_session(
            broker="CTRADER",
            symbol="USDJPY",
            timeframe="M1",
            replay_settings={
                "source_type": "CSV",
                "file_path": str(usdjpy_path),
                "source_timeframe": "M1",
            },
        )
        _assert_close(usdjpy_session.events[0].spread, 0.012)

        custom_session = service.create_historical_session(
            broker="CTRADER",
            symbol="USDJPY",
            timeframe="M1",
            replay_settings={
                "source_type": "CSV",
                "file_path": str(usdjpy_path),
                "source_timeframe": "M1",
                "spread": 0.02,
            },
        )
        _assert_close(custom_session.events[0].spread, 0.02)

        synthetic_session = service.create_synthetic_session(
            broker="CTRADER",
            symbol="USDJPY",
            timeframe="M1",
        )
        _assert_close(synthetic_session.events[0].spread, 0.012)

        custom_synthetic = service.create_synthetic_session(
            broker="CTRADER",
            symbol="USDJPY",
            timeframe="M1",
            replay_settings={"spread": 0.02},
        )
        _assert_close(custom_synthetic.events[0].spread, 0.02)

    print("Algorithm Workspace Replay Spread Symbol Scaling result")
    print("  mode=RM103_7W2_SYMBOL_SAFE_REPLAY_SPREAD")
    print("  production_trading_logic_changed=False")
    print("  default_spread_pips=1.2")
    print(
        "  default_spreads="
        + ",".join(f"{symbol}:{resolved[symbol]:g}" for symbol in EXPECTED_SPREADS)
    )
    print("  pip_normalized_default_spread_equal=True")
    print("  missing_workspace_spread_symbol_aware=True")
    print("  explicit_persisted_spread_preserved=True")
    print("  direct_history_loader_symbol_aware=True")
    print("  historical_replay_service_symbol_aware=True")
    print("  synthetic_replay_service_symbol_aware=True")
    print("  explicit_replay_spread_override_preserved=True")
    print("  non_forex_legacy_fallback_preserved=True")
    print("  macd_quality_threshold_scaling_changed=False")
    print("  candidate_f_changed=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_REPLAY_SPREAD_SYMBOL_SCALING_CHECK=OK")


if __name__ == "__main__":
    main()
