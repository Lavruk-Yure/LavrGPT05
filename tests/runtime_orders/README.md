# Automated OrdersPage Runtime Checks

Synthetic OrdersPage regression checks and their shared support fixtures.

UI checks may require PySide6 and an offscreen Qt platform. These checks must
not place Paper or Live orders.

## External IB FX exposure

- `run_orders_page_ib_external_only_exposure_check.py` verifies the explicit
  operation-disabled but selectable diagnostic row, the `Зовнішні у брокері`
  filter, exact foreign SL/TP and TWS identifiers, and the recovery route that
  refreshes exactly once and selects the matching external row.
- `run_main_external_exposure_popup_auto_refresh_check.py` verifies that the
  main warning dialog performs setup before display and exactly one OrdersPage
  refresh after the user closes the dialog, without any broker execution.
- `run_orders_page_ib_stale_external_exposure_check.py` verifies persisted
  stale exposure with broker confirmation required and no enabled operations.
