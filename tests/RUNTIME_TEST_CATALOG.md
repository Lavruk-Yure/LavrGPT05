# Runtime Test Catalog

Functional runtime test packages after controlled cleanup.

| Package | Python files | Purpose |
|---|---:|---|
| `tests/runtime_core` | 21 | Broker-neutral runtime, scheduler and tooling checks |
| `tests/runtime_repository` | 2 | SQLite schema and repository checks |
| `tests/runtime_translation` | 3 | Translation and fallback checks |
| `tests/runtime_workspace` | 144 | Retained canonical WSP and algorithm checks |
| `tests/runtime_temp` | 114 | Temporary Work research and diagnostic runners |
| `tests/runtime_ib` | 57 | IB synthetic regression checks |
| `tests/runtime_ctrader` | 5 | cTrader synthetic regression checks |
| `tests/runtime_orders` | 21 | OrdersPage and position-group checks |
| `tests/runtime_manual` | 34 | Manual/live and destructive diagnostics |

No Python test was deleted during Phases 1-4.

`runtime_workspace` is retained-only. `runtime_temp` may be cleaned after an
import scan confirms that retained tests do not depend on its modules.
