# LGE Runtime 02 — Runtime Orchestration Foundation

## Призначення

Документ фіксує стан RoadMap68 після переходу від broker connection foundation до runtime orchestration layer.

Цей документ є продовженням `LGE_Runtime_01.md` і описує вже побудовані runtime-шари:

- unified positions foundation;
- RuntimeScheduler;
- RuntimeHeartbeat;
- RuntimeMarketStateTask;
- IB thread shutdown lifecycle;
- cTrader reconcile positions mapping;
- поточні правила runtime orchestration.

Документ не є історичним журналом усіх спроб. Він фіксує канонічний стан, до якого прийшли після перевірок.

---

# 1. Поточна runtime architecture

Канонічна схема лишається такою:

```text
RuntimeEngine
    ->
RuntimeScheduler
    ->
BrokerInterface
    ->
BrokerAdapter
    ->
Broker API
```

Scheduler не замінює RuntimeEngine. Scheduler є окремим orchestration layer, який періодично запускає runtime tasks.

---

# 2. Unified positions foundation

Створено canonical model:

```text
engine/broker_position.py
```

Основна модель:

```text
BrokerPosition
```

Вона є broker-independent і використовується для IB та cTrader.

Підтверджені поля:

- broker;
- account_id;
- account_mode;
- position_id;
- symbol_name;
- side;
- volume;
- entry_price;
- current_price;
- stop_loss;
- take_profit;
- unrealized_pnl;
- currency;
- opened_utc;
- raw_payload.

---

# 3. BrokerInterface positions contract

У `BrokerInterface` додано canonical method:

```python
get_positions() -> list[BrokerPosition]
```

Це означає, що RuntimeEngine не має знати, який broker використовується. Він отримує список `BrokerPosition` через єдиний contract.

---

# 4. IB positions

Для IB реалізовано:

```text
IBAdapter.get_positions()
```

Технічна основа:

- `reqPositions()`;
- `position(...)` callback;
- `positionEnd()`;
- `cancelPositions()`;
- перетворення в `BrokerPosition`.

Поточний перевірений результат:

```text
IB positions_count=0
IB get_positions=OK
```

Нуль позицій — нормальний стан, якщо у TWS/IB Gateway немає відкритих позицій.

---

# 5. IB shutdown lifecycle

Під час тестів виявлено проблему:

```text
Exception in thread IBApiThread
TypeError: '>=' not supported between instances of 'NoneType' and 'int'
```

Причина:

```text
IB socket уже відключений, але IBApiThread ще виконує ibapi.client.run()
і після disconnect отримує serverVersion() = None.
```

Рішення:

- додано `_stopping`;
- `EClient.run()` обгорнуто в `_run_client_loop()`;
- `disconnect()` тепер робить керований shutdown thread;
- `TypeError` під час штатного disconnect не вважається runtime failure.

Поточний стан:

```text
IBApiThread shutdown TypeError = fixed
```

---

# 6. IB status messages

IB API надсилає status messages через `error(...)` callback.

Коди:

```text
2104 — Market data farm connection is OK
2106 — HMDS data farm connection is OK
2158 — Sec-def data farm connection is OK
```

Це не runtime errors.

Рішення:

- 2104 / 2106 / 2158 логуються як `INFO`;
- інші IB error codes поки лишаються `ERROR`.

Поточний стан:

```text
IB status codes 2104 / 2106 / 2158 = INFO
```

---

# 7. cTrader positions

Для cTrader реалізовано:

```text
CTraderAdapter.get_positions()
```

Технічна основа:

```text
ProtoOAReconcileReq
ProtoOAReconcileRes
```

Поточний перевірений результат:

```text
CTRADER positions_count=3
CTRADER_POSITIONS_CHECK=OK
```

---

# 8. cTrader reconcile mapping

Під час діагностики виявлено важливу структуру protobuf payload:

```text
ProtoOAReconcileRes.position
```

Має частину ключових торгових полів не напряму в `position`, а всередині:

```text
position.tradeData
```

Канонічне джерело mapping:

```text
position.positionId
position.price
position.stopLoss
position.takeProfit

position.tradeData.symbolId
position.tradeData.volume
position.tradeData.tradeSide
position.tradeData.openTimestamp
position.tradeData.label
position.tradeData.comment
```

Висновок:

- `position.positionId` читається напряму;
- `position.price`, `position.stopLoss`, `position.takeProfit` читаються напряму;
- `symbolId`, `volume`, `tradeSide`, `openTimestamp`, `label`, `comment` треба брати з `position.tradeData`;
- diagnostic `POSITION RAW` був тимчасовим і після мапінгу має бути прибраний або залишений тільки за debug mode.

---

# 9. cTrader symbolId

Зараз `symbol_name` для cTrader тимчасово містить `symbolId` як рядок:

```text
1
2
```

Це прийнятно для поточного foundation layer.

Наступний чистий крок:

```text
symbolId -> symbolName
```

через окрему canonical таблицю мапінгу broker symbol IDs:

```text
1 -> EURUSD
2 -> GBPUSD
```

Мапінг має бути централізованим, а не розкиданим по adapters.

---

# 10. Unified positions contract check

Створено diagnostic:

```text
tests/runtime/run_unified_positions_contract_check.py
```

Перевірено:

- IB adapter через `get_positions()`;
- cTrader adapter через `get_positions()`;
- обидва повертають `list[BrokerPosition]`;
- unified contract працює.

Поточний результат:

```text
UNIFIED_POSITIONS_CONTRACT_CHECK=OK
```

---

# 11. RuntimeScheduler

Створено:

```text
engine/runtime_scheduler.py
```

Рішення:

- не використовувати Qt timers;
- не використовувати asyncio;
- не використовувати APScheduler;
- використовувати `threading.Thread`, `threading.Event`, `time.monotonic()`.

Причина:

Runtime layer має бути незалежним від UI та стабільним для ATS.

Scheduler підтримує:

- startup tasks;
- periodic tasks;
- safe stop;
- exception isolation per task.

Поточний результат:

```text
RUNTIME_SCHEDULER_CHECK=OK
```

---

# 12. RuntimeHeartbeat

Створено:

```text
engine/runtime_heartbeat.py
```

Призначення:

- показати, що runtime живий;
- дати простий task для scheduler integration;
- підготувати основу для runtime monitoring.

Поточний результат:

```text
RUNTIME_HEARTBEAT_CHECK=OK
```

---

# 13. RuntimeMarketStateTask

Створено:

```text
engine/runtime_market_state_task.py
```

Призначення:

- періодично перевіряти market state;
- використовувати broker-independent `detect_market_state()`;
- готувати foundation для runtime protections.

Поточний результат:

```text
RUNTIME_MARKET_STATE_CHECK=OK
```

Поточне правило:

```text
MARKET_CLOSED:
    market orders blocked
    pending orders allowed
```

---

# 14. Runtime scheduler tasks

Поточні task foundations:

```text
RuntimeHeartbeat.heartbeat()
RuntimeMarketStateTask.refresh_market_state()
```

Наступні tasks:

```text
RuntimeReconnectTask
RuntimeAccountsSyncTask
RuntimePositionsSyncTask
RuntimeOrdersSyncTask
```

---

# 15. Поточний RoadMap68 стан

Закрито:

```text
BrokerPosition model
BrokerInterface.get_positions()
IBAdapter.get_positions()
CTraderAdapter.get_positions()
Unified positions contract
IB thread shutdown cleanup
IB status messages cleanup
RuntimeScheduler
RuntimeHeartbeat
RuntimeMarketStateTask
```

Наступний етап:

```text
runtime_reconnect_task.py
```

але тільки після cleanup стилю runtime layer.

---

# 16. Canonical style decision

Для LGE runtime layer фіксується стиль:

- перший рядок файла — `# filename.py`;
- docstrings — українською;
- коментарі — українською;
- runtime log messages — українською або технічно-змішані, але не випадковий English prototype style;
- API/library names не перекладаються;
- broker protocol terms можуть лишатися англійськими;
- diagnostic dumps не лишати в production path без debug gate.

---

# 17. Найближчі кроки

1. Cleanup runtime files:
   - `runtime_scheduler.py`;
   - `runtime_heartbeat.py`;
   - `runtime_market_state_task.py`.

2. Перевірити, що після cleanup проходять:
   - `run_runtime_scheduler_check.py`;
   - `run_runtime_heartbeat_scheduler_check.py`;
   - `run_runtime_market_state_scheduler_check.py`;
   - `run_unified_positions_contract_check.py`.

3. Після цього переходити до:

```text
runtime_reconnect_task.py
```
