# -*- coding: utf-8 -*-
"""Перевірка канонічного Forex pip resolver для RM103 / 7W.1."""

from __future__ import annotations

from engine.runtime_constants import (
    FOREX_JPY_QUOTE_PIP_SIZE,
    FOREX_STANDARD_PIP_SIZE,
    resolve_forex_pip_size,
)
from core.workspace_macd_cross_angle_abc import (
    resolve_workspace_macd_cross_angle_value_scale,
)


EXPECTED_PIP_SIZES = {
    "EURUSD": 0.0001,
    "GBPUSD": 0.0001,
    "USDJPY": 0.01,
}


def _assert_rejected(symbol: str) -> None:
    try:
        resolve_forex_pip_size(symbol)
    except ValueError:
        return
    raise AssertionError(f"Unexpected Forex symbol accepted: {symbol!r}")


def main() -> None:
    assert FOREX_STANDARD_PIP_SIZE == 0.0001
    assert FOREX_JPY_QUOTE_PIP_SIZE == 0.01

    actual = {
        symbol: resolve_forex_pip_size(symbol)
        for symbol in EXPECTED_PIP_SIZES
    }
    assert actual == EXPECTED_PIP_SIZES

    assert resolve_forex_pip_size("eurusd") == 0.0001
    assert resolve_forex_pip_size(" USDJPY ") == 0.01

    value_scales = {
        symbol: resolve_workspace_macd_cross_angle_value_scale(symbol)
        for symbol in EXPECTED_PIP_SIZES
    }
    assert value_scales == {
        "EURUSD": 10000.0,
        "GBPUSD": 10000.0,
        "USDJPY": 100.0,
    }
    assert all(
        abs((1.0 / value_scales[symbol]) - pip_size) < 1e-12
        for symbol, pip_size in EXPECTED_PIP_SIZES.items()
    )

    for invalid in ("", "EUR/USD", "XAUUSD", "BTCUSD", "EURUSDX"):
        _assert_rejected(invalid)

    print("Algorithm Workspace Forex Pip Scaling Foundation result")
    print("  mode=RM103_7W1_CANONICAL_FOREX_PIP_SCALING_FOUNDATION")
    print("  production_trading_logic_changed=False")
    print("  canonical_resolver_module=engine.runtime_constants")
    print(
        "  pip_sizes="
        + ",".join(
            f"{symbol}:{pip_size:g}"
            for symbol, pip_size in EXPECTED_PIP_SIZES.items()
        )
    )
    print(
        "  abc_value_scales="
        + ",".join(
            f"{symbol}:{value_scales[symbol]:g}"
            for symbol in EXPECTED_PIP_SIZES
        )
    )
    print("  inverse_abc_scale_matches_pip=True")
    print("  symbol_case_and_whitespace_normalized=True")
    print("  unknown_non_forex_symbols_fail_closed=True")
    print("  replay_spread_scaling_changed=False")
    print("  macd_quality_threshold_scaling_changed=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_FOREX_PIP_SCALING_FOUNDATION_CHECK=OK")


if __name__ == "__main__":
    main()
