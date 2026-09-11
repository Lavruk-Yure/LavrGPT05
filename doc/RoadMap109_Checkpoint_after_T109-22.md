# RoadMap109 — Checkpoint after T109-22

Дата checkpoint: 2026-09-11

## 1. Мета RoadMap109

Довести production BROKER path LGE05:

completed BROKER bar
→ production algorithm
→ Candidate F
→ WorkspaceTradeIntent
→ risk
→ execution identity
→ execution/order plan
→ broker adapter
→ broker-confirmed position lifecycle.

Основний принцип:
одна причинна межа за раз, без look-ahead і без змішування кількох неперевірених production-змін.

---

## 2. Канонічний trading baseline

Entry:
- Candidate F
- MACD production quality
- Alligator SAME_TIMEFRAME
- Stochastic 14/1/3 CURRENT_BAR reject

Exit:
- SL = max(signal_bar_range, spread * 10)
- TP = 2R
- Profit Drawdown = 35%
- negative-PD recovery unchanged

Canonical Replay:

2025:
- trades: 42
- W/L/BE: 30/11/1
- net: +4.03
- PF: 1.5424
- DD: 3.58

2026:
- trades: 18
- W/L/BE: 15/2/1
- net: +3.68
- PF: 3.7669
- DD: 1.20

Усі T109 anatomy/contract tests до T109-22 зберегли цей baseline.

---

## 3. Що вже встановлено

### 3.1 Completed BROKER data → Candidate F

Шлях completed BROKER bars до production algorithm працює.

AUTO і SEMI отримують causal completed bars.
Partial current bucket не використовується алгоритмом.

Перший початковий defect RoadMap109 був не в market data і не в Candidate F.

---

### 3.2 Signal → WorkspaceTradeIntent

T109-01/T109-02 встановили:

accepted Candidate F signal створювався,
але `WorkspaceTradeIntent` не створювався.

Через це `_record_signal()` не входив у risk path.

T109-03 виконав мінімальний production repair у:

`core/workspace_runtime.py`

Для accepted BROKER Candidate F AUTO/SEMI створюється `WorkspaceTradeIntent`.

Після цього signal входить у production risk pipeline.

Trading algorithm не змінювався.

---

## 4. Volume contract

T109-10..T109-13 встановили broker-neutral contract для FX position size.

Production contract:

`BASE_UNITS`

Scope:

`FX_POSITION_SIZE_ONLY`

Production declaration знаходиться в:

`engine/risk/constants.py`

Canonical fields:
- maximum_position_volume
- requested_volume
- approved_volume

1 BASE_UNIT = одна одиниця base currency FX symbol.

Поточні значення 1000/3000 зберігають числову семантику.

Broker-native conversion має виконуватися пізніше на execution boundary.

---

## 5. Risk account snapshot

Після T109-03 наступною межею став BROKER risk snapshot.

Встановлено:

- equity доступний через `RuntimeAccountState`;
- account currency доступна через `RuntimeAccountState.currency`;
- BROKER risk snapshot спочатку не мав повного production route;
- daily realized PnL та open positions count залишалися unresolved.

T109-15 підтвердив route account currency до Workspace risk snapshot.

BROKER account currency може бути отримана з cached RuntimeAccountState без нового broker request.

Replay currency source окремо не визначений.

---

## 6. Daily realized PnL blocker

Risk contract потребує:

`daily_realized_pnl`

Цільова семантика досліджувалась як:

- ACCOUNT_WIDE
- REALIZED_NET_COSTS
- ACCOUNT_CURRENCY
- BROKER_ACCOUNT_TRADING_DAY

Але production-neutral authoritative source не визначений.

### IB

Є `reqPnL()` / `pnl` та position-level PnL data.

Проблеми:
- broker reset schedule конфігурований;
- callback не дає authoritative period identity;
- period start/end/timezone/reset identity відсутні;
- net-cost completeness не доведена.

### cTrader

Deal history потенційно дозволяє агрегувати:
- gross profit
- swap
- commission
- pnlConversionFee

Але authoritative broker account trading-day identity відсутній.

### Висновок

Production daily-PnL fallback НЕ додавати.

Safe behavior:

`missing/unknown/stale daily PnL → BLOCK_RISK_EXECUTION`

T109-19 TEST_ONLY surrogate `daily_realized_pnl=0` використовувався тільки для переходу до наступної risk boundary.

Production fallback = NONE.

---

## 7. Open positions contract

T109-20 визначив цільовий contract:

- ownership scope = WORKSPACE_ONLY
- position scope = OPEN_EXPOSURE_ONLY
- lifecycle = BROKER_CONFIRMED
- partial fill = OPEN
- partial close = OPEN until zero
- close requested = OPEN until confirmed flat

Це сумісно з reverse invariant:

opposite position
→ request exact owned close
→ wait broker-confirmed flat
→ only then opposite open.

Сам count поки не можна production-вирахувати, бо broker positions не мають causal Workspace ownership.

---

## 8. Execution identity

T109-21 встановив:

поточний manual Runtime execution path не зберігає:

- workspace_uid
- signal_uid

через trade/order/position lifecycle.

Broker-native identity недостатня як єдине джерело.

Recommended architecture:

`broker-native hint + local persisted causal mapping`

Broker-native hint не є authoritative ownership source.

IB candidate:
`orderRef`

cTrader candidates:
`clientOrderId / label / comment`

Authoritative identity повинна зберігатися локально.

---

## 9. T109-22 canonical persisted identity decision

T109-22 встановив:

**Нова workspace_execution entity не потрібна.**

Existing:

`trade_uid`

може бути canonical Workspace execution root.

Причини:
- створюється до broker submission;
- persisted;
- restart-stable;
- один trade підтримує one-to-many orders;
- broker orders/positions можуть бути дочірніми.

Candidate pre-submission identity:

- trade_uid
- workspace_uid
- signal_uid
- execution_origin
- control_mode
- execution_state
- broker
- account_id
- symbol
- side
- created_utc

Idempotency candidate:

`UNIQUE(workspace_uid, signal_uid)`

До будь-якого broker submission:

risk ALLOW
→ atomic create-or-reuse Workspace-owned trade
→ тільки потім broker execution.

AUTO state:

`READY_FOR_SUBMISSION`

SEMI state:

`PENDING_CONFIRMATION`

SEMI broker submission заборонений до confirmation.

Manual GUI trades повинні залишатися окремими і не ставати Workspace-owned.

Recommended persistence strategy:

`EXTEND trades`

nullable Workspace causal fields + explicit execution origin/state.

---

## 10. Поточна unresolved boundary

Після T109-22:

`TRADE_ROW_WORKSPACE_IDENTITY_SCHEMA_AND_POST_RISK_PERSISTENCE_WIRING`

Boundary contract:

`RISK_ALLOW_MUST_ATOMICALLY_CREATE_OR_REUSE_ONE_WORKSPACE_OWNED_TRADE_BY_WORKSPACE_UID_SIGNAL_UID_BEFORE_ANY_BROKER_SUBMISSION`

Production schema migration ще НЕ виконувалась.

Post-risk Workspace persistence wiring ще НЕ виконувалось.

Broker execution wiring ще НЕ виконувалось.

---

## 11. Що production вже змінено в RoadMap109

Прийняті production зміни:

### T109-03
`core/workspace_runtime.py`

Accepted BROKER Candidate F AUTO/SEMI signal
→ WorkspaceTradeIntent
→ existing risk pipeline.

### T109-13
`engine/risk/constants.py`

Declared:
- BASE_UNITS
- FX_POSITION_SIZE_ONLY

### T109-15
Account currency route до Workspace risk snapshot присутній у поточному production tree.

Перед наступними production edits фактичний current tree перевірити з актуального ZIP.

---

## 12. Що НЕ реалізовано

На checkpoint T109-22 НЕ реалізовано:

- authoritative production daily realized PnL;
- authoritative broker-day contract;
- production open_positions_count;
- Workspace execution persistence after risk ALLOW;
- UNIQUE(workspace_uid, signal_uid) DB constraint;
- Workspace execution/order plan;
- broker-native identity hint;
- Workspace → RuntimeEngine execution wiring;
- broker order submission з Workspace;
- Workspace broker-position reconciliation;
- confirmed-flat reverse state machine;
- SEMI confirmation execution;
- FX quote→account currency normalization;
- повний broker execution lifecycle.

---

## 13. Наступний крок

T109-23.

Не робити одразу migration.

Спочатку на фактичному current tree перевірити мінімальну schema feasibility для розширення `trades`:

- workspace_uid
- signal_uid
- execution_origin
- control_mode
- execution_state

та:

`UNIQUE(workspace_uid, signal_uid)`

Не змінювати production, поки feasibility окремо не доведена.

---

# 14. Нова модель роботи — Classic

Починаючи після цього checkpoint основний workflow змінюється.

## ChatGPT / Еон

Еон є технічним керівником і основним розробником.

Він працює безпосередньо з актуальним ZIP/кодом LGE.

Перед кожним кроком коротко формулює:

1. ЩО зараз не працює.
2. ЩО саме будемо змінювати або перевіряти.
3. ЯК доведемо результат.

Один крок = одна перевірювана зміна або один runnable test.

Production logic змінюється тільки після окремого підтвердження.

Після зміни:
- малий overlay ZIP;
- точна команда тесту;
- очікуваний результат.

Користувач запускає тест локально і повертає фактичний output.

---

## Work / Codex

Work/Codex більше НЕ є обов'язковим посередником кожного T109.

Використовувати лише коли це дає реальну користь:

- великий незалежний codebase review;
- складний багатофайловий аналіз;
- друга незалежна перевірка ризикової production-зміни;
- задача, яку недоцільно виконувати локально в основному workflow.

Користувач не повинен бути постійним «поштарем»
між RoadMap109 та Work.

---

## Контроль користувача

Кожна production-зміна повинна бути зрозуміла до її застосування.

Формат:

`ПРОБЛЕМА → ЗМІНА → ТЕСТ → РЕЗУЛЬТАТ`

Не переходити до наступної production boundary,
поки попередня не має factual GREEN.

---

## 15. Статус checkpoint

RoadMap109 збережений після T109-22.

Наступний ID:

`T109-23`

Основний workflow:

`CLASSIC`

Work/Codex:

`ON_DEMAND_ONLY`

MD7:

`UNCHANGED`