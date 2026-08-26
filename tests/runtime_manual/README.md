# Manual and Live Runtime Checks

This directory is intentionally separate from automated runtime tests.

## Rules

1. Do not run the whole directory as a regression suite.
2. Read the file header before every run.
3. Confirm the intended broker account and mode.
4. `DESTRUCTIVE_*` checks may open, modify, or close positions/orders.
5. `READ_ONLY_LIVE` checks still require a real broker connection.
6. Keep TWS/Gateway or cTrader credentials outside Git.

## Files

| File | Risk class |
|---|---|
| `run_runtime_ctrader_manual_buy_close_check.py` | `DESTRUCTIVE_DEMO` |
| `run_ib_virtual_leg_close_live_check.py` | `DESTRUCTIVE_PAPER` |
| `run_ib_virtual_leg_close_recovery_live_check.py` | `DESTRUCTIVE_PAPER` |
| `run_ib_virtual_leg_modify_live_check.py` | `DESTRUCTIVE_PAPER` |
| `run_ib_virtual_leg_open_live_check.py` | `DESTRUCTIVE_PAPER` |
| `run_ib_virtual_leg_live_persistence_sync.py` | `MANUAL_APPLY_OPTION` |
| `run_runtime_ctrader_service_real_reconnect_check.py` | `MANUAL_LIVE` |
| `run_runtime_ctrader_session_manager_check.py` | `MANUAL_LIVE` |
| `run_runtime_ib_reconnect_task_watch.py` | `MANUAL_LIVE` |
| `run_runtime_ib_tws_loss_watch.py` | `MANUAL_LIVE` |
| `run_runtime_ib_sl_tp_modify_plan.py` | `MANUAL_PLAN_ONLY` |
| `run_ib_overnight_protective_fill_evidence_check.py` | `READ_ONLY_LIVE` |
| `run_ib_position_groups_live_readonly_check.py` | `READ_ONLY_LIVE` |
| `run_ib_virtual_leg_live_readonly_check.py` | `READ_ONLY_LIVE` |
| `run_runtime_ctrader_connection.py` | `READ_ONLY_LIVE` |
| `run_runtime_ctrader_positions.py` | `READ_ONLY_LIVE` |
| `run_runtime_ctrader_refresh_broker_health_check.py` | `READ_ONLY_LIVE` |
| `run_runtime_engine_ctrader_production_path_check.py` | `READ_ONLY_LIVE` |
| `run_runtime_engine_ib_production_path_check.py` | `READ_ONLY_LIVE` |
| `run_runtime_ib_connection.py` | `READ_ONLY_LIVE` |
| `run_runtime_ib_positions.py` | `READ_ONLY_LIVE` |
| `run_runtime_ib_runtime_service_check.py` | `READ_ONLY_LIVE` |
| `run_runtime_ib_session_manager_check.py` | `READ_ONLY_LIVE` |
| `ib_virtual_leg_close_live_check_impl.py` | `SUPPORT_DESTRUCTIVE_PAPER` |
| `ib_virtual_leg_close_recovery_live_check_impl.py` | `SUPPORT_DESTRUCTIVE_PAPER` |
| `ib_virtual_leg_modify_live_check_impl.py` | `SUPPORT_DESTRUCTIVE_PAPER` |
| `ib_virtual_leg_open_live_check_impl.py` | `SUPPORT_DESTRUCTIVE_PAPER` |
| `ib_virtual_leg_live_persistence_sync_impl.py` | `SUPPORT_MANUAL_APPLY` |
