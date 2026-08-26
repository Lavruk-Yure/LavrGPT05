# Automated Workspace Runtime Checks

This directory contains offline/synthetic or controlled read-only regression
checks for Algorithm Workspace, Replay, indicators, risk, profiles, history,
market-data ownership, and WSP lifecycle.

## Rules

1. These checks must not place Paper or Live orders.
2. Run scripts directly by their full path.
3. `PROJECT_ROOT` remains stable because this directory is a sibling of
   `tests/runtime`, not a nested child directory.
4. UI checks may require PySide6 and an offscreen Qt platform.
5. Manual/live broker checks remain in `tests/runtime_manual`.

## Scope

- `run_algorithm_workspace_*`
- `run_workspace_*`
- `run_runtime_engine_workspace_market_data_check.py`

## External exposure safety hold

`run_algorithm_workspace_external_exposure_safety_hold_check.py` verifies that
an IB WSP enters recoverable `SAFETY_HOLD_EXTERNAL_EXPOSURE`, keeps read-only
market data and charts active, blocks signals/new execution, renders the
critical safety tooltip and journal lines in the active language, and resumes
only after current clear evidence plus a fresh spread.

`run_algorithm_workspace_external_exposure_alert_check.py` verifies that the
system warning sound and automatic Orders recovery signal fire exactly once on
entry into a safety hold, remain silent on repeated syncs and hold updates, and
are re-armed only after the hold has been cleared.

## Transient broker disconnect recovery

`run_algorithm_workspace_transient_broker_disconnect_recovery_check.py`
reproduces the race where the broker health snapshot is still `CONNECTED` but
the adapter disconnects before the quote request. The WSP must enter
`WAIT_BROKER`, preserve its chart and algorithm instance, avoid `ERROR` and
`STOPPED`, revalidate the binding after reconnect, require a fresh spread, and
return to `RUNNING` without duplicate subscriptions or broker execution.
