# Runtime Test Catalog

Functional runtime test packages after controlled cleanup.

| Package | Python files | Purpose |
|---|---:|---|
| `tests/runtime_core` | 21 | Broker-neutral runtime, scheduler and tooling checks |
| `tests/runtime_repository` | 2 | SQLite schema and repository checks |
| `tests/runtime_translation` | 3 | Translation and fallback checks |
| `tests/runtime_workspace` | 48 | WSP and algorithm checks |
| `tests/runtime_ib` | 57 | IB synthetic regression checks |
| `tests/runtime_ctrader` | 5 | cTrader synthetic regression checks |
| `tests/runtime_orders` | 21 | OrdersPage and position-group checks |
| `tests/runtime_manual` | 34 | Manual/live and destructive diagnostics |

No Python test was deleted during Phases 1-4.
