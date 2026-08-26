# LGE Runtime Architecture — Canonical Runtime Document

Version: 00
Status: IN_PROGRESS
Project: LavrGPT05 / LGE
RoadMap: RoadMap67

---

# Purpose

LGE Runtime є canonical runtime architecture document для ATS (Algorithmic Trading System).

Документ визначає:

- runtime architecture;
- broker integration architecture;
- database architecture;
- runtime states;
- broker connection lifecycle;
- market availability logic;
- event logging;
- runtime behavior rules;
- future implementation direction.

Цей документ є source of truth для runtime layer.

---

# Core Runtime Principles

1. Runtime layer НЕ залежить від UI.
2. Runtime layer НЕ залежить від Qt.
3. Runtime layer працює через broker adapters.
4. Runtime layer НЕ знає деталей broker APIs.
5. Runtime layer працює через canonical interfaces.
6. Runtime layer використовує SQLite runtime persistence.
7. Runtime layer повинен бути broker-independent.
8. Runtime layer повинен підтримувати DEMO/LIVE.
9. Runtime layer повинен підтримувати future backtesting.
10. Runtime layer не повинен покладатися на manual scripts.

---

# Runtime Architecture

```text
LGE UI
    ->
RuntimeEngine
    ->
BrokerInterface
    ->
BrokerAdapter
    ->
Broker API
```

---

# Runtime Engine

Current canonical module:

```text
engine/runtime_engine.py
```

RuntimeEngine відповідає за:

- runtime lifecycle;
- broker lifecycle;
- runtime states;
- broker states;
- event logging;
- periodic runtime checks;
- runtime coordination.

RuntimeEngine НЕ повинен:

- знати broker protocol details;
- містити UI logic;
- містити broker-specific code.

---

# Runtime State

Canonical runtime states:

```text
OFF
STARTING
RUNNING
STOPPING
ERROR
```

---

# Broker Connection State

Canonical broker connection states:

```text
DISCONNECTED
CONNECTING
CONNECTED
RECONNECTING
ERROR
```

Meaning:

- DISCONNECTED
  - broker connection inactive.

- CONNECTING
  - broker auth/connect sequence active.

- CONNECTED
  - broker authenticated and operational.

- RECONNECTING
  - broker reconnection in progress.

- ERROR
  - unrecoverable broker connection error.

---

# Broker Interface

Canonical broker abstraction:

```text
engine/broker_interface.py
```

Current canonical methods:

```python
connect()
disconnect()
is_connected()
get_account_info()
```

Future methods:

```python
get_positions()
get_orders()
place_market_order()
place_limit_order()
place_stop_order()
modify_position()
close_position()
```

---

# cTrader Adapter

Current canonical adapter:

```text
engine/ctrader_adapter.py
```

Current RoadMap67 implementation:

Implemented:

- TCP connect;
- application auth;
- account auth;
- runtime connection state;
- broker lifecycle logging;
- runtime DB events;
- account info foundation.

Not implemented yet:

- positions sync;
- order sync;
- SL/TP runtime layer;
- pending orders runtime layer;
- runtime execution engine.

---

# Current Runtime Flow

```text
RuntimeEngine
    ->
BrokerInterface
    ->
CTraderAdapter
    ->
cTrader Open API
```

---

# Runtime Events

Current canonical runtime events:

```text
STARTUP
SHUTDOWN
BROKER_SELECTED
BROKER_ADAPTER_SELECTED
BROKER_CONNECTING
BROKER_CONNECTED
BROKER_DISCONNECTED
BROKER_CONNECTION_ERROR
```

Runtime events must be written into:

```text
data/demo.db
data/live.db
```

Table:

```text
runtime_events
```

---

# Database Architecture

Canonical runtime databases:

```text
data/demo.db
data/live.db
data/test.db
```

Rules:

- only one active broker;
- only one active account mode;
- DEMO and LIVE schema should remain максимально однаковими;
- TEST DB використовується для diagnostics/backtests.

---

# Runtime Tables

Current/future runtime tables:

```text
sessions
runtime_events
broker_accounts
settings_runtime
orders
positions
signals
filters
rails
```

---

# Broker Accounts

Canonical runtime account information:

```python
broker
account_id
account_mode
currency
balance
equity
margin_used
margin_free
```

---

# Runtime Logging

Runtime logging rules:

- всі critical runtime events логуються;
- broker lifecycle логуються;
- runtime state transitions логуються;
- broker connection errors логуються;
- future order lifecycle теж логується.

---

# Market Availability State [IN_PROGRESS]

Market availability state є окремим від:

- RuntimeState
- BrokerConnectionState

Broker може бути:

```text
CONNECTED
```

але ринок може бути:

```text
MARKET_CLOSED
```

---

## Canonical market states

```text
MARKET_OPEN
MARKET_CLOSED
MARKET_PREOPEN
MARKET_HALTED
MARKET_UNKNOWN
```

---

## Значення станів

### MARKET_OPEN

- market orders дозволені
- pending orders дозволені

---

### MARKET_CLOSED

- market orders заборонені
- pending orders можуть бути дозволені broker

---

### MARKET_PREOPEN

- ринок ще не відкрився повністю
- broker може дозволяти тільки pending orders

---

### MARKET_HALTED

- trading halted broker/exchange
- нові ордери заборонені

---

### MARKET_UNKNOWN

- runtime не зміг надійно визначити стан ринку
- runtime повинен використовувати conservative mode

---

## Canonical behavior flags

```text
can_place_market_order
can_place_pending_order
```

---

## Canonical market state sources

```text
FOREX_WEEKEND_HEURISTIC
FOREX_WEEKDAY_HEURISTIC
BROKER_ERROR_MARKET_CLOSED
BROKER_SYMBOL_SESSION
IB_MARKET_RULES
CTRADER_SYMBOL_STATUS
UNKNOWN
```

---

## Current RoadMap67 implementation status

Реалізовано:

- MARKET_OPEN
- MARKET_CLOSED
- FOREX weekend heuristic
- broker error fallback
- runtime market availability function
- cTrader manual market-state diagnostic
- IB compatibility layer (heuristic only)

---

## Current canonical engine module

```text
engine/market_availability_state.py
```

---

## Current runtime test

```text
tests/runtime/run_market_availability_state_check.py
```

---

## Current cTrader diagnostic test

```text
tests/ctrader/manual/run_ctrader_04b_market_availability_check.py
```

---

## Current runtime behavior

Runtime може:

- перевіряти market state при startup;
- перевіряти market state щогодини;
- блокувати market orders;
- дозволяти pending orders;
- не покладатися тільки на broker order rejection.

---

## RoadMap67 verified scenarios

Підтверджено:

- weekend Forex closed;
- weekday Forex open;
- pending orders allowed while market closed;
- broker MARKET_CLOSED fallback;
- broker-independent engine function;
- cTrader integration preparation;
- IB integration preparation.

---

# cTrader Runtime Diagnostics

Current diagnostic scripts:

```text
tests/runtime/run_runtime_ctrader_connection.py
tests/runtime/run_runtime_events_check.py
tests/runtime/run_market_availability_state_check.py
```

Temporary manual diagnostics:

```text
tests/ctrader/manual/
```

Purpose:

- diagnostics;
- recovery;
- broker verification;
- protocol analysis.

These scripts are NOT canonical runtime architecture.

---

# Runtime Startup Sequence

Current startup flow:

```text
RuntimeEngine startup
    ->
Broker adapter selection
    ->
Broker connecting
    ->
Application auth
    ->
Account auth
    ->
Broker connected
    ->
Market availability check
```

Future:

```text
Account sync
    ->
Positions sync
    ->
Orders sync
```

---

# Runtime Constraints

Current RoadMap67 constraints:

- no UI dependency;
- no Qt dependency;
- no unnecessary abstractions;
- no framework-for-framework;
- runtime-first architecture;
- documentation alongside development;
- broker-independent runtime layer.

---

# IB Runtime Preparation

Current status:

- IB integration planned;
- IB heuristic compatibility prepared;
- IB market availability placeholders prepared.

Not implemented yet:

- IB adapter;
- IB runtime lifecycle;
- IB account sync;
- IB market rules;
- IB order runtime layer.

---

# Future Runtime Work

Planned next steps:

1. Account sync.
2. Broker account persistence.
3. Positions sync.
4. Orders sync.
5. Runtime periodic scheduler.
6. Runtime heartbeat.
7. Broker reconnect logic.
8. Runtime execution layer.
9. Runtime protections.
10. Strategy runtime integration.

---

# Runtime Decision Log

## 2026-05-06

- Removed external import architecture.
- Selected broker history + SQLite cache.
- Runtime before backtest.

---

## 2026-05-07

- LGE_Runtime.md declared canonical runtime source.
- Runtime architecture separated from UI.
- Runtime progress tracking became mandatory.

---

## 2026-05-08

- Canonical DB architecture:
  - demo.db
  - live.db
  - test.db
- Only one active broker.
- Only one active account mode.
- Historical data temporary/on-demand.

---

## 2026-05-15

RoadMap67:

- First production runtime cTrader connection lifecycle implemented.
- Runtime events integrated with SQLite.
- Broker lifecycle states introduced.
- Runtime broker diagnostics stabilized.
- Market availability architecture started.

---

## 2026-05-16

RoadMap67 market availability:

- MARKET_OPEN and MARKET_CLOSED implemented.
- Forex weekend heuristic implemented.
- Broker MARKET_CLOSED fallback implemented.
- Runtime market availability function introduced.
- Pending-order allowance while market closed verified.
- cTrader market diagnostics implemented.
- IB compatibility layer prepared.
- Canonical market state architecture documented.

