# LGE Runtime 01 — Консолідований Runtime Snapshot

## Призначення

Документ фіксує:
- підтверджений runtime-стан LGE після завершення RoadMap67;
- актуальну multi-broker архітектуру;
- перевірені runtime-компоненти;
- canonical runtime foundation.

Документ НЕ містить:
- історичного сміття;
- старих dead sections;
- застарілих test-only схем;
- попередніх експериментальних архітектур.

---

# 1. Канонічна Runtime Architecture

```text
RuntimeEngine
    ->
BrokerInterface
    ->
BrokerAdapter
    ->
Broker API
```

---

# 2. Runtime Foundation

Підтверджено:

- RuntimeEngine
- runtime lifecycle
- runtime states
- runtime context
- runtime events
- runtime DB bootstrap
- runtime broker lifecycle

---

# 3. Runtime States

Канонічні runtime states:

```text
OFF
STARTING
RUNNING
STOPPING
ERROR
```

---

# 4. Runtime Databases

Канонічна DB architecture:

```text
data/demo.db
data/live.db
data/test.db
```

Правила:
- demo/live мають однакову або майже однакову schema;
- test.db використовується для:
  - runtime tests;
  - historical tests;
  - backtests;
  - temporary broker history cache;
- permanent history.db не використовується.

---

# 5. Broker Architecture

## BrokerInterface

Канонічний broker contract:

- connect()
- disconnect()
- is_connected()
- get_account_info()
- detect_market_state()

RoadMap68:
- add get_positions()

---

# 6. cTrader Runtime

Підтверджено:

- TCP connect
- application auth
- account auth
- runtime lifecycle
- market-state detection
- MARKET_CLOSED fallback

Підтверджено runtime adapter:

```text
engine/ctrader_adapter.py
```

---

# 7. IB Runtime

Підтверджено:

- TWS connection
- startApi
- nextValidId
- reqAccountSummary
- real BrokerAccount runtime object

Підтверджено runtime adapter:

```text
engine/ib_adapter.py
```

---

# 8. Уніфікований Market Layer

Канонічні market states:

```text
MARKET_OPEN
MARKET_CLOSED
```

Канонічна runtime-поведінка:

- ринкові ордери:
  - дозволені лише при MARKET_OPEN;
- відкладені ордери:
  - можуть бути дозволені під час MARKET_CLOSED;
- runtime має лишатися broker-independent.

Канонічна unified-функція:

```python
detect_market_state()
```

---

# 9. Runtime Events

Поточні runtime events:

- runtime startup
- runtime shutdown
- broker selected
- account mode changed
- execution mode changed
- runtime errors
- broker connection events

---

# 10. Runtime Scheduler (RoadMap68)

Планується:

- startup checks
- periodic market checks
- reconnect checks
- runtime health checks

---

# 11. Runtime Protections (RoadMap68)

Планується:

- MARKET_CLOSED blocking
- pending-order exceptions
- emergency runtime states
- reconnect protection
- broker disconnect handling

---

# 12. Unified Runtime Sync (RoadMap68)

Планована unified-синхронізація:

- accounts
- positions
- orders

Мета:
- єдиний runtime state незалежно від брокера.

---

# 13. Runtime Positions Foundation (RoadMap68)

Наступний canonical layer:

```text
Broker API
    ->
BrokerAdapter.get_positions()
    ->
Unified Position Model
    ->
RuntimeEngine
```

Планується:
- IB positions
- cTrader positions
- unified broker-independent position model

---

# 14. Головне досягнення RoadMap67

RoadMap67 створив:

```text
real unified multi-broker runtime foundation
```

замість:
- isolated test scripts;
- disconnected broker experiments;
- UI-driven broker logic.

Це перша реальна canonical runtime architecture LGE.
