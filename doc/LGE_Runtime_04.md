# LGE_Runtime_04.md

# LGE Runtime Architecture — Part 04

# RoadMap71-74
# cTrader OAuth / Runtime Service Architecture
---

# 1. Призначення документа

Документ описує production-style архітектуру інтеграції cTrader у LGE після переходу від test-script підходу до runtime architecture.

Поточний фокус:

1. cTrader OAuth authorization flow.
2. Runtime-safe account loading.
3. Canonical token handling.
4. Twisted subprocess isolation.
5. Runtime broker integration.
6. Account persistence.
7. Runtime service architecture.
8. Runtime reconnect preparation.

Документ є canonical source of truth для 
cTrader Runtime Architecture (RoadMap71-74).

---

# 2. Загальна production-архітектура

LGE більше НЕ розглядається як набір тестових скриптів.

LGE тепер:

1. Runtime ATS application.
2. Long-running process.
3. Multi-broker architecture.
4. Stateful reconnect-capable runtime.
5. GUI + RuntimeEngine + broker services.

---

# 3. Canonical cTrader integration architecture

## 3.1 Архітектурні рівні

### Layer 1 — GUI

GUI відповідає тільки за:

1. dialogs
2. settings
3. account selection
4. runtime diagnostics
5. runtime state display

GUI НЕ володіє Twisted reactor.

---

### Layer 2 — Runtime Engine

RuntimeEngine відповідає за:

1. runtime lifecycle
2. runtime states
3. broker orchestration
4. reconnect scheduling
5. SAFE_DISCONNECTED policy

---

### Layer 3 — Broker Service Layer

Broker service layer:

1. broker runtime services
2. account services
3. runtime tasks
4. broker health checks
5. reconnect logic
6. broker adapter abstraction

---

### Layer 4 — SessionManager

SessionManager відповідає за:

1. reactor lifecycle
2. deferred cleanup
3. reconnect-safe sessions
4. stale callback cleanup
5. reconnect isolation

---

### Layer 5 — Open API Layer

Нижній рівень:

1. ctrader_open_api
2. protobuf payloads
3. Twisted networking
4. async callbacks

---

# 4. Canonical OAuth architecture

---

## 4.1 Production OAuth policy

LGE використовує:

1. external system browser
2. localhost callback server
3. authorization code flow
4. refresh token flow

LGE НЕ використовує:

1. Selenium
2. embedded browser
3. browser automation hacks
4. HTML scraping

---

## 4.2 Canonical OAuth flow

Production flow:

1. Користувач натискає:
   `Авторизація в cTrader`

2. LGE відкриває системний браузер.

3. Користувач проходить OAuth authorization.

4. cTrader redirect:
   `localhost callback`

5. Local callback server отримує:
   `authorization code`

6. LGE виконує:

```text id="h61a7l"
authorization_code
    ↓
access_token + refresh_token
```

7. `tokens/tokens.json` оновлюється автоматично.

---

## 4.3 Confirmed RoadMap71 state

Підтверджено working state:

1. browser OAuth працює
2. localhost callback працює
3. token exchange працює
4. refresh token persistence працює
5. automatic tokens.json update працює

---

# 5. Canonical token architecture

---

## 5.1 Critical bug discovered

Під час RoadMap71 знайдено критичну проблему:

Різні модулі читали різні `tokens.json`.

Було:

```text id="b4m9g5"
D:\LavrGPT\LavrGPT05\tokens.json
```

і:

```text id="ij2j71"
D:\LavrGPT\LavrGPT05\tokens\tokens.json
```

Це призводило до:

1. CH_ACCESS_TOKEN_INVALID
2. використання старих token
3. runtime inconsistency

---

## 5.2 Canonical rule

Єдиний canonical token source:

```text id="6fx1on"
tokens/tokens.json
```

Усі runtime modules MUST use:

```python id="4y0rbt"
PROJECT_ROOT / "tokens" / "tokens.json"
```

Root-level `tokens.json` вважається deprecated.

---

# 6. Runtime-safe account loading architecture

---

## 6.1 Головне production-рішення

GUI НЕ повинен напряму тримати Twisted runtime.

Замість цього використовується:

1. subprocess runner
2. isolated Twisted process
3. JSON stdout protocol
4. structured result exchange

---

## 6.2 Canonical account probe flow

Production architecture:

```text id="0q6yrj"
GUI
  ↓
ctrader_account_list_probe_runner.py
  ↓
ctrader_account_list_probe.py
  ↓
Twisted/OpenAPI
```

---

## 6.3 Confirmed production result

Підтверджено:

1. subprocess isolation працює
2. GUI не зависає
3. account loading працює
4. account combo заповнюється
5. runtime JSON exchange працює

---

# 7. Account persistence architecture

---

## 7.1 Confirmed working state

Підтверджено:

```json id="6vlp9v"
"ctrader": {
  "host": "demo.ctraderapi.com",
  "port": 5035,
  "client_id": "...",
  "client_secret": "...",
  "account_mode": "DEMO",
  "account_id": "46368962"
}
```

Selected account correctly persists to:

```text id="a4trvl"
LGE.conf
```

---

## 7.2 Confirmed persistence policy

У LGE.conf зберігаються тільки параметри ідентифікації:

1. host
2. port
3. client_id
4. client_secret
5. account_mode
6. account_id

Приклад:

"ctrader": {
    "host": "demo.ctraderapi.com",
    "port": 5035,
    "client_id": "...",
    "client_secret": "...",
    "account_mode": "DEMO",
    "account_id": "46368962"
}

НЕ зберігаються:

1. balance
2. equity
3. margin
4. free_margin
5. currency
6. leverage

Причина:

Ці значення належать до runtime state і повинні
отримуватися безпосередньо від брокера після підключення.

---

## 7.3 Runtime snapshot policy

Balance, currency та leverage НЕ є конфігурацією.

Вони:

1. завантажуються з брокера;
2. можуть змінюватися будь-якої миті;
3. не зберігаються в LGE.conf;
4. використовуються лише для runtime UI та runtime diagnostics.

Canonical source of truth:
broker runtime state.

---

# 8. Account combo architecture

---

## 8.1 Історичний формат (ранній етап RoadMap71)

Поточний формат:

```text id="5cvgk4"
46368962 | 9870599 | None
```

---

## 8.2 Поточний production-формат

Поточний формат:

9870599 • Demo • 869.75 USD • 1:500

або

Raw Trading Ltd • Demo • 9870599 • 869.75 USD • 1:500

## 8.3 Important architecture note

Balance/currency/leverage НЕ треба вигадувати.

Ці дані повинні приходити через:

1. separate account-info query
2. reconcile/account-state request
3. runtime broker state service

---

## 8.4 Підтверджена архітектура Account Snapshot

Під час RoadMap71 реалізовано окремий snapshot probe.

Production architecture:

GUI
↓
ctrader_account_snapshot_probe_runner.py
↓
ctrader_account_snapshot_probe.py
↓
ProtoOATrader
↓
Runtime Snapshot

Snapshot використовується для отримання:

1. balance
2. currency
3. leverage
4. broker_name
5. trader_login
6. runtime account metadata

Snapshot НЕ зберігається у LGE.conf.

Snapshot є runtime-only станом.

---

## 8.5 Підтверджені поля Runtime Snapshot

Підтверджено отримання:

1. account_id
2. trader_login
3. broker_name
4. currency
5. balance
6. leverage

Не підтверджено на поточному етапі:

1. equity
2. margin
3. free_margin

Для цих значень потрібен окремий runtime механізм або інший Open API request.

---

## 8.6 Підтверджене відображення ProtoOATrader

Підтверджено робочу структуру:

ProtoOATrader

1. ctidTraderAccountId
2. traderLogin
3. brokerName
4. leverageInCents
5. balance
6. moneyDigits
7. depositAssetId

Balance обчислюється як:

balance = raw_balance / (10 ** moneyDigits)

Підтверджений результат RoadMap71:

9870599 • Demo • 869.75 USD • 1:500

---

## 8.7 Канонічний формат відображення рахунку

Поточний формат:

"<login> • Demo • <balance> <currency> • <leverage>"

Приклад:

9870599 • Demo • 869.75 USD • 1:500

Runtime значення можуть змінюватися в будь-який момент.

Balance, currency та leverage є лише snapshot значеннями,
отриманими під час завантаження рахунків.

Вони не вважаються постійно синхронізованими runtime показниками.

# 9. Runtime reconnect preparation

---

## 9.1 Підтверджений напрямок архітектури

Runtime reconnect architecture вже визначена:

1. RuntimeReconnectTask
2. SessionManager
3. SAFE_DISCONNECTED
4. reconnect scheduler
5. broker health monitor

---

## 9.2 Важливе поточне обмеження

Auto-connect поки НЕ реалізовується.

Поточна policy:

1. remember configuration
2. manual connect
3. manual OAuth
4. runtime-safe startup

---

# 10. Runtime states

Canonical runtime states:

```text id="g7n9pt"
OFF
STARTING
RUNNING
SAFE_DISCONNECTED
STOPPING
ERROR
```

---

# 11. Відомі обмеження RoadMap71

Поточний стан RoadMap71:

Завершено:

1. OAuth authorization flow
2. Token refresh flow
3. Canonical token storage
4. Account list probe
5. Account snapshot probe
6. Account persistence
7. Runtime-safe subprocess architecture
8. Balance loading
9. Currency loading
10. Leverage loading

Залишилось:

1. Account auto restore UX
2. Runtime service layer
3. RuntimeReconnectTask
4. SessionManager integration
5. SAFE_DISCONNECTED finalization
6. Reconnect stabilization

---

# 12. Заборонені підходи

Production architecture забороняє:

1. Selenium OAuth automation
2. embedded browser OAuth
3. GUI-owned reactor
4. duplicated reactors
5. test-script reconnect logic
6. blocking GUI networking
7. random token file locations

---

# 13. Постійні правила розробки

Обов'язкові runtime rules:

1. Runtime-style architecture only.
2. GUI must not own Twisted reactor.
3. RuntimeEngine is the source of truth for runtime lifecycle
   and runtime context.
4. External browser only for OAuth.
5. Canonical token path: `tokens/tokens.json`
6. Reconnect must not require LGE restart.
7. Comments/docstrings — українською.
8. Numbered architecture sections mandatory.

---

# 14. Final target architecture

Цільова production architecture:

```text id="7g9mkr"
LGE GUI
↓
RuntimeEngine
↓
RuntimeScheduler
↓
Broker Runtime Service
↓
SessionManager
↓
Broker Adapter
↓
Twisted/OpenAPI
```

з:

1. stable reconnect
2. SAFE_DISCONNECTED
3. runtime-safe OAuth
4. broker abstraction
5. no GUI freeze
6. isolated Twisted runtime
7. multi-broker architecture

---

# 15. RoadMap72 Result Summary

---

## 15.1 Головне архітектурне рішення RoadMap72

Під час RoadMap72 виконано перехід від adapter-centric runtime до service-centric runtime.

Стара архітектура:

RuntimeEngine
↓
CTraderAdapter

Нова архітектура:

RuntimeEngine
↓
Broker Runtime Service
↓
SessionManager
↓
Broker Adapter

RuntimeEngine більше НЕ повинен працювати напряму з конкретним брокерним адаптером.

Уся взаємодія з брокером повинна проходити через Runtime Service Layer.

---

## 15.2 Реалізований CTrader Runtime Service

Під час RoadMap72 створено:

CTraderRuntimeService

Призначення:

1. runtime orchestration для cTrader;
2. робота через SessionManager;
3. інтеграція RuntimeAccountState;
4. інтеграція RuntimeBrokerHealth;
5. підготовка до RuntimeReconnectTask;
6. приховування деталей OpenAPI від RuntimeEngine.

RuntimeEngine більше не повинен знати внутрішню реалізацію cTrader adapter.

---

## 15.3 Runtime Service Protocol

Для ізоляції RuntimeEngine від конкретних брокерів введено:

CTraderRuntimeServiceProtocol

RuntimeEngine працює через protocol interface.

Це є першим кроком до multi-broker runtime architecture.

---

## 15.4 Runtime Account State

Під час RoadMap72 введено:

RuntimeAccountState

Призначення:

1. runtime snapshot account information;
2. account mode;
3. account id;
4. balance;
5. currency;
6. leverage;
7. broker metadata.

RuntimeAccountState є runtime-only структурою.

Вміст RuntimeAccountState не зберігається у LGE.conf.

---

## 15.5 Runtime Broker Health

Під час RoadMap72 введено:

RuntimeBrokerHealth

Призначення:

1. broker connection state;
2. runtime diagnostics;
3. reconnect readiness;
4. health monitoring;
5. SAFE_DISCONNECTED support.

RuntimeBrokerHealth є canonical runtime health model.

---

## 15.6 RuntimeEngine Integration

Під час RoadMap72 RuntimeEngine отримав:

set_ctrader_runtime_service()

та

connect_ctrader_demo()

connect_ctrader_demo() виконує підключення через Runtime Service Layer, а не напряму через Adapter.

---

## 15.7 Runtime Events

Під час RoadMap72 оновлено runtime events.

Було:

BROKER_ADAPTER_SELECTED

Стало:

BROKER_SERVICE_SELECTED

Причина:

RuntimeEngine більше працює із сервісом, а не з конкретним адаптером.

---

## 15.8 Підтверджені результати тестування

Успішно пройдено:

run_runtime_engine_ctrader_service_check.py

Підтверджено:

1. RuntimeEngine ↔ RuntimeService integration;
2. RuntimeContext updates;
3. RuntimeEvents generation;
4. RuntimeAccountState integration;
5. RuntimeBrokerHealth integration;
6. cTrader demo connection through service layer.

---

## 15.9 Поточна canonical runtime architecture

Поточна production architecture:

LGE GUI
↓
RuntimeEngine
↓
Broker Runtime Service
↓
SessionManager
↓
Broker Adapter
↓
OpenAPI

Ця архітектура є canonical результатом RoadMap72.

---

## 15.10 RoadMap72 Status

RoadMap72 завершено.

Підтверджено:

1. RuntimeEngine працює через Runtime Service.
2. RuntimeAccountState інтегровано.
3. RuntimeBrokerHealth інтегровано.
4. Runtime Service Protocol введено.
5. connect_ctrader_demo() реалізовано.
6. RuntimeEngine ↔ RuntimeService integration test успішний.

# 16. RoadMap73 Start Point

Наступний етап розвитку runtime architecture:

1. RuntimeReconnectTask;
2. RuntimeBrokerHealth expansion;
3. SessionManager stabilization;
4. SAFE_DISCONNECTED finalization;
5. service-first broker architecture;
6. IB Runtime Service implementation за тим самим шаблоном.


# 17. RoadMap73 Result Summary

---
## 17.1 RuntimeScheduler Integration

Під час RoadMap73:

1. RuntimeScheduler інтегровано в RuntimeEngine.
2. RuntimeEngine створює RuntimeScheduler.
3. startup() запускає RuntimeScheduler.
4. shutdown() зупиняє RuntimeScheduler.
5. RuntimeScheduler став canonical runtime task host.

Підтверджено:

run_runtime_engine_scheduler_check.py

---

## 17.2 RuntimeReconnectTask Integration

---

Під час RoadMap73:

1. RuntimeReconnectTask більше не працює через Adapter.
2. RuntimeReconnectTask працює через Runtime Service protocol.
3. RuntimeReconnectTask не знає про OpenAPI.
4. RuntimeReconnectTask не знає про SessionManager.
5. RuntimeReconnectTask працює лише через Runtime Service Layer.

Архітектура:

RuntimeReconnectTask
↓
Runtime Service
↓
SessionManager
↓
Broker Adapter

---

## 17.3 RuntimeEngine Reconnect Architecture

---

RuntimeEngine отримав можливість:

1. attach_reconnect_task()
2. Реєстрація reconnect task у RuntimeScheduler.
3. Централізоване керування runtime tasks.

Архітектура:

RuntimeEngine
↓
RuntimeScheduler
↓
RuntimeReconnectTask

---

## 17.4 Reconnect Success Scenario

---

Підтверджено:

run_runtime_reconnect_task_ctrader_service_check.py

Успішний reconnect:

RECONNECT_STARTED
↓
RECONNECT_SUCCESS
↓
CONNECTED

---

## 17.5 Reconnect Failure Scenario

---

Підтверджено:

run_runtime_reconnect_task_ctrader_service_check.py

Неуспішний reconnect:

RECONNECT_STARTED
↓
RECONNECT_FAILED
↓
SAFE_DISCONNECTED

RuntimeBrokerHealth переходить у:

SAFE_DISCONNECTED

без аварійного завершення RuntimeEngine.

---

## 17.6 Runtime Lifecycle Integration

---

Підтверджено:

run_runtime_engine_ctrader_service_check.py

Lifecycle:

RuntimeEngine.startup()
↓
RuntimeScheduler.start()
↓
connect_ctrader_demo()
↓
CONNECTED
↓
RuntimeEngine.shutdown()
↓
RuntimeScheduler.stop()
↓
OFF

---

## 17.7 Підтверджені тести RoadMap73

---

1. run_runtime_engine_scheduler_check.py
2. run_runtime_engine_reconnect_task_check.py
3. run_runtime_reconnect_task_ctrader_service_check.py
4. run_runtime_engine_ctrader_runtime_service_check.py
5. run_runtime_engine_ctrader_service_check.py

---

## 17.8 Canonical Runtime Architecture (RoadMap73)

---

Поточна canonical architecture:

LGE GUI
↓
RuntimeEngine
↓
RuntimeScheduler
↓
RuntimeReconnectTask
↓
Broker Runtime Service
↓
SessionManager
↓
Broker Adapter
↓
OpenAPI

---

## 17.9 RoadMap73 Status

---

RoadMap73 завершено.

Підтверджено:

1. RuntimeScheduler інтегровано.
2. RuntimeReconnectTask інтегровано.
3. RuntimeEngine керує runtime tasks.
4. Success reconnect перевірено.
5. Failure reconnect перевірено.
6. SAFE_DISCONNECTED перевірено.
7. Runtime lifecycle перевірено.
8. Service-first runtime architecture підтверджено.

---

# 18. RoadMap74 Result Summary

---

## 18.1 Runtime Foundation Validation

---

1. Production Runtime Path Validation

RuntimeEngine
↓
CTraderRuntimeService
↓
CTraderSessionManager
↓
CTraderAdapter
↓
OpenAPI

Validated by:

- run_runtime_engine_ctrader_production_path_check.py

Result:
CONNECTED reached successfully through production runtime stack.

2. Runtime shutdown lifecycle fixed.

Before:

runtime_state = OFF
broker_connection_state = CONNECTED

After:

runtime_state = OFF
broker_connection_state = DISCONNECTED

RuntimeEngine.shutdown() now:

- stops RuntimeScheduler;
- disconnects CTraderRuntimeService;
- retires active adapter;
- updates RuntimeContext correctly.

Validated by:

- run_runtime_engine_ctrader_production_path_check.py

3. RuntimeReconnectTask no-op validated.

Scenario:

broker_health = CONNECTED
↓
RuntimeReconnectTask.run_once()

Result:

- reconnect not executed;
- reconnect_attempts remains 0.

Validated by:

- run_runtime_reconnect_task_connected_noop_check.py

4. Runtime broker health refresh implemented.

New method:

CTraderRuntimeService.refresh_broker_health()

Behavior:

- no adapter → DISCONNECTED
- healthy adapter → CONNECTED
- broken adapter → SAFE_DISCONNECTED

Validated by:

- run_runtime_ctrader_refresh_broker_health_check.py

5. Production reconnect validated.

Scenario:

CONNECTED
↓
adapter.disconnect()
↓
SAFE_DISCONNECTED
↓
RuntimeReconnectTask
↓
reconnect()
↓
CONNECTED

Results:

- reconnect_attempts = 1
- session_generation increased
- adapter replaced
- health restored to CONNECTED

Validated by:

- run_runtime_ctrader_service_real_reconnect_check.py

6. Runtime broker state ownership clarified.

Source Of Truth:

CTraderRuntimeService

Responsibilities:

- connect()
- disconnect()
- reconnect()
- refresh_broker_health()

RuntimeBrokerHealth is a runtime state container only.

RuntimeReconnectTask consumes RuntimeBrokerHealth and does not own broker state.

RuntimeEngine consumes runtime service state and synchronizes RuntimeContext.

7. Legacy reconnect-watch tests removed.

Removed:

- run_runtime_ctrader_reconnect_watch.py
- run_runtime_ib_reconnect_watch.py

Reason:

Old adapter/session-manager API no longer matches service-based runtime architecture.

8. Twisted reconnect observation.

During adapter retirement the following message may appear:

Twisted reactor run skipped:

This was observed during successful reconnect scenarios and did not prevent reconnect completion.

9. Runtime foundation status.

RoadMap74 confirms that the runtime foundation is ready for future:

- IBRuntimeService
- Runtime broker abstraction
- Unified broker runtime layer
- Multi-broker runtime architecture

---

## 18.2 Runtime Test Inventory

---

run_runtime_engine_ctrader_service_check.py
    Lightweight RuntimeEngine ↔ RuntimeService integration check.

run_runtime_engine_ctrader_production_path_check.py
    Production runtime path validation.

run_runtime_ctrader_refresh_broker_health_check.py
    Runtime broker health validation.

run_runtime_ctrader_service_real_reconnect_check.py
    Production reconnect validation.

run_runtime_reconnect_task_check.py
    RuntimeReconnectTask base validation.

run_runtime_reconnect_task_ctrader_service_check.py
    RuntimeReconnectTask service integration validation.

run_runtime_reconnect_task_connected_noop_check.py
    RuntimeReconnectTask no-op validation when broker is CONNECTED.

run_runtime_engine_reconnect_task_check.py
    RuntimeEngine + RuntimeReconnectTask integration validation.

---

## 18.3 RoadMap74 Status

---

RoadMap74 completed.

Confirmed:

1. Production runtime path validated.
2. Runtime shutdown lifecycle fixed.
3. RuntimeReconnectTask no-op validated.
4. Runtime broker health refresh implemented.
5. Production reconnect validated.
6. Source Of Truth clarified.
7. Runtime foundation prepared for future IBRuntimeService.

---

# 19. RoadMap75 Result Summary

## 19.1 IBRuntimeService Implementation

---

Під час RoadMap75 реалізовано:

IBRuntimeService

Призначення:

1. IB runtime orchestration.
2. Робота через IBSessionManager.
3. Інтеграція RuntimeBrokerHealth.
4. Інтеграція RuntimeAccountState.
5. Runtime reconnect support.
6. Source Of Truth для runtime broker state.

Production path:

RuntimeEngine
↓
IBRuntimeService
↓
IBSessionManager
↓
IBAdapter
↓
TWS / IB Gateway

---

## 19.2 IBSessionManager

---

Реалізовано:

IBSessionManager

Відповідає за:

1. lifecycle adapter;
2. reconnect-safe session recreation;
3. adapter retirement;
4. session generation tracking.

Підтверджено:

session_generation

коректно збільшується під час reconnect.

---

## 19.3 RuntimeAccountState Extension

---

RuntimeAccountState тепер використовується спільно для:

1. cTrader;
2. IB.

Підтверджені поля:

1. account_id;
2. broker_name;
3. currency;
4. balance;
5. equity;
6. margin;
7. free_margin;
8. snapshot_utc.

RuntimeAccountState залишається runtime-only структурою.

---

## 19.4 RuntimeBrokerHealth Extension

---

RuntimeBrokerHealth тепер використовується спільно для:

1. cTrader;
2. IB.

Підтверджені runtime states:

1. CONNECTED
2. DISCONNECTED
3. SAFE_DISCONNECTED

Поле:

updated_utc

успішно інтегроване та оновлюється автоматично.

---

## 19.5 Internet Loss Validation

---

Підтверджено сценарій:

CONNECTED
↓
Internet Lost
↓
SAFE_DISCONNECTED
↓
Internet Restored
↓
CONNECTED

Підтверджено:

1. account state cleanup;
2. broker health downgrade;
3. broker health recovery;
4. account state reload.

Validated by:

run_runtime_ib_tws_loss_watch.py

---

## 19.6 TWS Restart Validation

---

Підтверджено сценарій:

CONNECTED
↓
TWS Closed
↓
SAFE_DISCONNECTED
↓
TWS Restarted
↓
CONNECTED

Підтверджено:

1. reconnect retry;
2. adapter recreation;
3. account reload;
4. broker health recovery.

Validated by:

run_runtime_ib_reconnect_task_watch.py

---

## 19.7 RuntimeReconnectTask Validation

---

Підтверджено роботу:

RuntimeReconnectTask
↓
IBRuntimeService
↓
IBSessionManager
↓
IBAdapter

Reconnect policy:

1. cooldown-based retry;
2. repeated reconnect attempts;
3. reconnect without RuntimeEngine restart.
4. reconnect without LGE restart.

Підтверджено:

Runtime service reconnect successful.

---

## 19.8 Start Without TWS Validation

---

Підтверджено сценарій:

RuntimeEngine startup
↓
TWS unavailable
↓
Reconnect attempts
↓
TWS launched later
↓
CONNECTED

LGE restart не потрібний.

---

## 19.9 Runtime Constants

---

Створено:

engine/runtime_constants.py

Призначення:

1. reconnect cooldown constants;
2. watch test constants;
3. runtime tuning values.

Перші константи:

1. RUNTIME_RECONNECT_COOLDOWN_SECONDS
2. RUNTIME_WATCH_SLEEP_SECONDS
3. RUNTIME_WATCH_ITERATIONS

---

## 19.10 Cleanup

---

Видалено:

brokers/ib_adapter.py

Причина:

старий broker-layer adapter більше не відповідає production runtime architecture.

Canonical IB adapter:

engine/ib_adapter.py

---

## 19.11 Stabilization Notes

---

Під час стабілізації потрібно повернутися до:

Також під час стабілізації потрібно повернутися до:

1. account_id canonical type;
2. RuntimeReconnectTask cooldown policy.

Поточне значення:

RUNTIME_RECONNECT_COOLDOWN_SECONDS = 15.0

Потрібно визначити production значення після накопичення runtime статистики.

Поточний тип:

int | str | None

Майбутня ціль:

str | None

Причина:

cTrader використовує numeric account id;
IB використовує string account id.

---

## 19.12 RoadMap75 Status

---

RoadMap75 завершено.

Підтверджено:

1. IBRuntimeService.
2. IBSessionManager.
3. RuntimeAccountState integration.
4. RuntimeBrokerHealth integration.
5. Internet loss recovery.
6. TWS restart recovery.
7. RuntimeReconnectTask integration.
8. Start without TWS recovery.
9. Runtime constants.
10. Production reconnect architecture.

---

