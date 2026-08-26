# Automated IB Runtime Checks

Offline and synthetic IB regression checks, including virtual legs, protective
orders, reconciliation, RuntimeEngine integration, and repository persistence.

These checks must not connect to or trade through a real IB session unless a
file header explicitly says otherwise. Real/manual checks remain in
`tests/runtime_manual`.

## LGE EXCLUSIVE external FX exposure

- `run_ib_fx_external_exposure_ledger_check.py` verifies the persistent
  CONFIRMED/STALE/CLEARED ledger, durable transition events, and that MANUAL,
  SEMI, and AUTO same-symbol IB opens are rejected before `Trade` persistence
  and before any broker execution request.
- `run_ib_fx_external_exposure_display_snapshot_check.py` verifies current and
  protective-order-derived external exposure display facts, including exact
  foreign-client `permId`, `parentId`, `clientId`, OCA, prices, and preserved
  `orderId=0` evidence.
- `run_ib_fx_virtual_observation_external_execution_check.py` verifies that
  an exact non-LGE execution determines external-exposure direction;
  the IB Virtual FX observation is never subtracted from managed LGE legs to
  invent the opposite residual side.
