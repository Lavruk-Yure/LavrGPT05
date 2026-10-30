"""T114-04A — persisted cTrader MACD EXTENDED проти raw cross.

TEST_ONLY / DATA_ONLY. Жодних broker requests чи production-змін.
"""

from __future__ import annotations

import importlib
import json
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ANOMALY = datetime(2025, 4, 16, 21, 45, tzinfo=UTC)


def module(name):
    """Імпортувати LGE і T112-30 без залежності від IDE source roots."""
    for path in (ROOT, ROOT / "tests" / "roadmap112"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    return importlib.import_module(name)


def main():
    """На тих самих completed M15 порівняти raw і EXTENDED."""
    t112 = module("run_t112_30_ib_ctrader_eurusd_2025_macd_signal_parity_check")
    repo_class = module("core.session_repository").SessionRepository
    runtime_class = module("core.workspace_runtime").WorkspaceRuntimeContext
    macd_class = module("core.workspace_macd").WorkspaceMacdSignalSource
    event_class = module("core.workspace_market_event").WorkspaceMarketEvent

    session = ROOT / "Session"
    manifest = json.loads((session / "session.json").read_text(encoding="utf-8-sig"))
    repo = repo_class(session_dir=session)
    candidates = []
    for uid in manifest["workspace_order"]:
        workspace = repo.load_workspace(uid)
        if (workspace.broker, workspace.symbol, workspace.timeframe) == (
            "CTRADER",
            "EURUSD",
            "M15",
        ):
            candidates.append(workspace)
    assert len(candidates) == 1, f"CTRADER_EURUSD_M15_WSP_COUNT={len(candidates)}"
    workspace = candidates[0]
    assert workspace.data_mode == "REPLAY"
    context = runtime_class.from_workspace(workspace)
    extended = macd_class.from_runtime_context(context, workspace.parameters)
    profile = extended.runtime_profile
    assert extended.enabled and extended.mode == "EXTENDED"
    assert (profile.fast_period, profile.slow_period, profile.signal_period) == (
        8,
        17,
        5,
    )
    assert (
        profile.source,
        profile.oscillator_ma_type,
        profile.signal_ma_type,
        profile.shift,
    ) == ("CLOSE", "EXPONENTIAL", "EXPONENTIAL", 0)
    raw = macd_class(enabled=True, mode="LINEAR", runtime_profile=profile)

    path = t112.HISTORY / "CTRADER" / "EURUSD" / "M1" / t112.CT_CSV
    m1_count, bars = getattr(t112, "_read_complete_m15")(path)
    assert (m1_count, len(bars)) == (370481, 23753)

    results = Counter()
    reasons = Counter()
    anomaly = None
    for timestamp in sorted(bars):
        bar = bars[timestamp]
        event = event_class(
            timestamp=timestamp,
            broker="CTRADER",
            symbol="EURUSD",
            timeframe="M15",
            bid=bar.close,
            ask=bar.close,
            spread=0.0,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=0.0,
            source_mode="REPLAY",
        )
        original = raw.on_market_event(event)
        filtered = extended.on_market_event(event)
        assert (original is None) == (filtered is None)
        if original is None:
            continue
        assert original.direction == filtered.direction
        assert original.source_profile_uid == filtered.source_profile_uid
        results["raw"] += 1
        assert filtered.filter_decision in {"ALLOW", "REJECT"}
        results[filtered.filter_decision] += 1
        if filtered.filter_decision == "REJECT":
            reasons[filtered.filter_reason_code] += 1
        if timestamp == ANOMALY:
            anomaly = (
                original.direction,
                filtered.direction,
                filtered.filter_decision,
                filtered.filter_reason_code,
            )

    assert raw.observations == extended.observations
    assert len(extended.quality_diagnostics) == results["raw"]
    assert results == Counter({"raw": 3040, "ALLOW": 414, "REJECT": 2626})
    assert anomaly == ("BUY", "BUY", "REJECT", "MACD_EXTREMUM_TOO_WEAK")

    print("T114-04A|OFFLINE_CTRADER_EXTENDED_GATE_ISOLATION")
    print(f"workspace_uid={workspace.workspace_uid}|mode={workspace.data_mode}")
    print(f"profile={profile.profile_uid}|revision={profile.profile_revision}")
    print(
        f"completed_m15={len(bars)}|raw={results['raw']}|"
        f"allow={results['ALLOW']}|reject={results['REJECT']}"
    )
    print(f"reject_reasons={dict(sorted(reasons.items()))}")
    print(
        f"anomaly_utc={ANOMALY.isoformat()}|"
        f"available_not_before="
        f"{(ANOMALY + timedelta(minutes=15)).isoformat()}"
    )
    print(
        f"anomaly=raw:{anomaly[0]}|extended:{anomaly[1]}|"
        f"filter:{anomaly[2]}|reason:{anomaly[3]}"
    )
    print("raw_vs_extended_observations=IDENTICAL|directions=IDENTICAL")
    print("ib_profile=NOT_VERIFIED|alligator_and_other_gates=NOT_TESTED")
    print("completed_bars_only=True|look_ahead=False|broker_requests=0")
    print("production_changed=False|md7_changed=False")
    print("T114_04A_OFFLINE_EXTENDED_GATE_ISOLATION=OK")


if __name__ == "__main__":
    main()
