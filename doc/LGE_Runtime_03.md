# LGE_Runtime_03.md
"""
LGE Runtime 03
RoadMap68 / RoadMap69
Runtime Scheduler / Reconnect / Heartbeat / Market State

Статус:
- runtime scheduler foundation: IMPLEMENTED
- heartbeat scheduler: IMPLEMENTED
- market state scheduler: IMPLEMENTED
- IB reconnect runtime: MOSTLY STABLE
- cTrader reconnect runtime: IMPLEMENTED / TESTED / RUNTIME RECONNECT TASK INTEGRATED

Дата:
2026-05-20
"""

# 1. Призначення

Документ фіксує runtime scheduler architecture,
heartbeat tasks, reconnect behavior,
market-state refresh logic та результати
runtime reconnect testing для IB і cTrader.

RoadMap69 доповнює RoadMap68 production-рішенням
для cTrader reconnect без перезапуску всього LGE.

---

# 2. RuntimeScheduler

## 2.1. Призначення

RuntimeScheduler є базовим runtime loop layer для:
- periodic runtime tasks;
- reconnect checks;
- heartbeat updates;
- market-state refresh;
- future runtime services.

RuntimeScheduler НЕ є trading engine.
Це lightweight orchestration layer.

---

## 2.2. Реалізовано

Поточна реалізація:
- periodic tasks;
- startup tasks;
- safe stop;
- logger integration;
- cooldown-safe execution;
- runtime loop thread.

---

## 2.3. RuntimeScheduler tests

Підтверджено:
- scheduler start;
- scheduler stop;
- periodic execution;
- multiple periodic tasks;
- runtime stability;
- reconnect integration.

Tests:
- run_runtime_scheduler_check.py
- run_runtime_heartbeat_scheduler_check.py
- run_runtime_market_state_scheduler_check.py
- run_runtime_reconnect_task_check.py

---

# 3. Runtime Heartbeat

## 3.1. Призначення

Heartbeat task використовується для:
- runtime liveness;
- monitoring;
- watchdog support;
- future GUI/runtime status sync.

---

## 3.2. Поведінка

Heartbeat:
- запускається scheduler;
- оновлює UTC timestamp;
- інкрементує heartbeat counter;
- логгується через logger.

---

## 3.3. Статус

Heartbeat scheduler:
- IMPLEMENTED
- TESTED
- STABLE

---

# 4. Runtime Market State Scheduler

## 4.1. Призначення

Market-state scheduler:
- periodically refresh market state;
- визначає MARKET_OPEN / MARKET_CLOSED;
- перевіряє market order availability;
- перевіряє pending order availability.

---

## 4.2. Поточний стан

Підтверджено:
- weekend detection;
- periodic refresh;
- scheduler integration;
- runtime logging.

---

## 4.3. Поточна policy

При MARKET_CLOSED:
- market orders blocked;
- pending orders allowed.

---

# 5. RuntimeReconnectTask

## 5.1. Призначення

RuntimeReconnectTask:
- periodically checks broker connection;
- performs reconnect attempts;
- prevents reconnect storm;
- supports reconnect cooldown.

---

## 5.2. Реалізовано

Реалізовано:
- reconnect cooldown;
- reconnect attempts counter;
- reconnect logging;
- broker adapter replacement;
- reconnect factory support.

---

## 5.3. BrokerAdapterProtocol

Додано:
- BrokerAdapterProtocol;
- reconnect typing support;
- runtime-safe adapter interface.

---

## 5.4. RoadMap69 уточнення для cTrader

Для cTrader RuntimeReconnectTask не повинен
працювати напряму зі старим adapter як із простим об'єктом.

Правильний production flow:

RuntimeReconnectTask
-> CTraderSessionManager
-> retire old adapter
-> create new adapter
-> connect/auth
-> late-connect grace check
-> replace active adapter

Після RoadMap69 реалізовано dual-mode behavior:

1. IB / generic broker:
   - RuntimeReconnectTask працює через adapter / reconnect_factory;
   - існуючий IB reconnect flow не ламається.

2. cTrader:
   - RuntimeReconnectTask працює через CTraderSessionManager;
   - active adapter береться через manager.get_active_adapter();
   - reconnect виконується через manager.reconnect();
   - після reconnect RuntimeReconnectTask оновлює self.adapter на новий active adapter.

IB reconnect flow не чіпати без окремої потреби.

---

# 6. IB Runtime Reconnect

## 6.1. Поточний статус

IB reconnect:
- IMPLEMENTED
- TESTED
- MOSTLY STABLE

---

## 6.2. Підтверджено tests

Підтверджено:
1. запуск без TWS;
2. запуск TWS після runtime start;
3. TWS stop/start during runtime;
4. internet loss / internet restore;
5. reconnect cooldown behavior;
6. runtime scheduler stability.

---

## 6.3. Поточна поведінка

При disconnect:
- runtime detects DISCONNECTED;
- reconnect task performs reconnect;
- runtime restores IB session;
- runtime remains alive.

---

## 6.4. Важливі повідомлення

IB codes:
- 2104
- 2106
- 2158

НЕ є fatal errors.

Це informational connectivity messages.

---

# 7. cTrader Runtime Reconnect

## 7.1. Поточний статус

cTrader reconnect:
- IMPLEMENTED
- TESTED
- NEEDS RUNTIME INTEGRATION

Після RoadMap69 підтверджено:
- reconnect без перезапуску LGE можливий;
- старт без інтернету не валить process;
- втрата інтернету під час runtime не вимагає restart LGE;
- старі callbacks із retired adapter ігноруються;
- delayed/late connect обробляється grace-period логікою.

---

## 7.2. Що підтверджено

Підтверджено:
- internet loss detection;
- DISCONNECTED state;
- reconnect attempts;
- reconnect через new adapter instance;
- old adapter retire;
- old callbacks ignore;
- successful reconnect після відновлення інтернету;
- startup без internet не валить runtime process;
- reconnect після появи internet проходить без перезапуску LGE.

---

## 7.3. Основна проблема

Початкова проблема RoadMap68/RoadMap69:

Після reconnect:
- старі Twisted deferred objects лишались активними;
- старі callbacks продовжували працювати;
- старі sessions конфліктували із новими.

Симптоми:
- ALREADY_LOGGED_IN;
- UNSUPPORTED_MESSAGE;
- Deferred TimeoutError;
- stale callbacks після reconnect;
- timeout після фактичного TCP/auth success.

---

## 7.4. Важливе архітектурне рішення

cTrader reconnect НЕ можна реалізовувати
простим reconnect() поверх старого adapter.

Правильна архітектура:

old adapter
-> retire_session()
-> detach callbacks
-> stop old client service
-> mark old adapter DEAD
-> create new adapter
-> connect/auth
-> late-connect grace check
-> replace active runtime adapter

---

## 7.5. SAFE_DISCONNECTED policy

При cTrader disconnect:
- trading actions blocked;
- runtime stays alive;
- broker state -> SAFE_DISCONNECTED;
- GUI must show reconnect warning/status;
- operator не повинен перезапускати LGE вручну;
- reconnect task продовжує спроби за cooldown/backoff policy.

SAFE_DISCONNECTED — це не fatal error.

Це нормальний проміжний стан:

CONNECTED
-> SAFE_DISCONNECTED
-> RECONNECTING
-> CONNECTED

Якщо reconnect не вдався:

CONNECTED
-> SAFE_DISCONNECTED
-> RECONNECTING
-> SAFE_DISCONNECTED
-> RECONNECTING
-> ...

---

# 8. cTrader SessionManager

## 8.1. Необхідний етап RoadMap69

Додано:
- ctrader_session_manager.py

SessionManager є окремим lifecycle-controller поверх CTraderAdapter.

---

## 8.2. SessionManager responsibilities

SessionManager має:
- create new adapter;
- store active adapter;
- stop old adapter;
- retire old adapter;
- ignore old callbacks;
- cleanup old client;
- create new adapter;
- replace runtime adapter;
- manage reconnect lifecycle;
- provide late-connect grace check;
- isolate old Twisted callbacks/deferreds.

---

## 8.3. Причина

Twisted reactor:
- запускається 1 раз на process;
- reactor restart unsupported;
- після network loss може ще довго віддавати callbacks/deferreds.

Тому reconnect повинен:
- reuse global reactor;
- recreate client/session;
- retire old adapter;
- detach callbacks from old client;
- not stop global reactor.

---

## 8.4. Session generation

SessionManager використовує session generation:

- кожна нова session отримує новий generation;
- старий adapter позначається retired;
- active adapter замінюється новим;
- старі callbacks не мають права змінювати runtime state.

---

## 8.5. Retired adapter policy

У CTraderAdapter додано:
- _retired;
- _session_generation;
- _connect_generation.

retire_session() має:
- поставити _retired = True;
- збільшити _connect_generation;
- скинути _connecting;
- відв'язати callbacks;
- викликати stopService для client;
- поставити client = None;
- перевести state у DISCONNECTED.

---

## 8.6. Callback isolation

Early-exit додано у реальні handlers:

- _on_connected;
- _on_disconnected;
- _on_message_received;
- _on_deferred_error;
- _on_reconcile_res;
- _on_positions_deferred_error.

Якщо adapter retired — callback ігнорується.

---

## 8.7. Deferred policy

Deferred error ігнорується якщо:
- adapter retired;
- generation mismatch;
- callback належить старій session.

Це прибирає deferred timeout storm після reconnect.

---

## 8.8. Late-connect grace period

Проблема:

Після втрати інтернету cTrader/Twisted може завершити TCP/auth
із запізненням.

Симптом:
- adapter.connect() уже повернув False;
- у логах був TIMEOUT;
- через кілька секунд приходить:
  - cTrader TCP connected;
  - cTrader application auth OK;
  - cTrader account auth OK.

Рішення:

У CTraderSessionManager додано:

_wait_for_late_connect(...)

Поведінка:
- якщо adapter.connect() повернув False;
- manager чекає короткий grace-period;
- якщо adapter став connected — late connect приймається;
- якщо ні — session лишається not connected.

Поточне значення:
- 15 seconds

---

# 9. RoadMap69 goals

## 9.1. Обов'язкові runtime scenarios

Потрібно знайти production-safe рішення для:

1. запуск LGE без internet;
2. internet loss during runtime;
3. broker reconnect recovery;
4. safe runtime continuation;
5. reconnect UI flow.

Статус після тестів RoadMap69:
- сценарій 1 пройдено;
- сценарій 2 пройдено;
- broker reconnect recovery підтверджено;
- safe runtime continuation підтверджено на test script рівні;
- reconnect UI flow ще не інтегровано.

---

## 9.2. cTrader reconnect

RoadMap69:
- дослідити clean Twisted cleanup;
- дослідити deferred cancellation;
- реалізувати SessionManager;
- уникнути ALREADY_LOGGED_IN;
- уникнути stale callbacks;
- уникнути deferred timeout storms.

Статус:
- SessionManager реалізовано;
- stale callbacks із retired adapter приглушено;
- reconnect без restart LGE підтверджено;
- deferred timeout storm зменшено через retire/detach/generation policy;
- late success обробляється grace-period логікою.

---

## 9.3. RoadMap69 test 1 — normal reconnect

Сценарій:
1. internet ON;
2. connect;
3. reconnect;
4. disconnect.

Результат:
1. перший adapter підключився;
2. reconnect створив новий adapter;
3. старий adapter retired;
4. старі callbacks ignored;
5. adapter1 alive: False;
6. adapter2 alive: True;
7. process exit code 0.

Статус:
- PASSED

---

## 9.4. RoadMap69 test 2 — startup without internet

Сценарій:
1. LGE/runtime стартує без інтернету;
2. перший connect дає timeout;
3. process не падає;
4. після появи інтернету reconnect створює новий adapter;
5. cTrader TCP/auth проходить;
6. runtime завершується clean.

Підтверджено:
1. TIMEOUT: cTrader auth not completed;
2. manager не падає;
3. Waiting for late cTrader connect;
4. старий adapter retired;
5. новий adapter connected;
6. application auth OK;
7. account auth OK;
8. adapter1 alive: False;
9. adapter2 alive: True;
10. process exit code 0.

Статус:
- PASSED

---

## 9.5. RoadMap69 test 3 — internet loss during runtime

Сценарій:
1. runtime стартує з інтернетом;
2. cTrader connected;
3. під час pause інтернет вимикається;
4. runtime фіксує ConnectionLost;
5. reconnect attempts ідуть через SessionManager;
6. після відновлення інтернету reconnect проходить;
7. process завершується clean.

Підтверджено:
1. cTrader disconnected: ConnectionLost;
2. старий adapter retired;
3. reconnect attempt створює new adapter;
4. після відновлення інтернету:
   - cTrader TCP connected;
   - cTrader application auth OK;
   - cTrader account auth OK;
5. adapter1 alive: False;
6. adapter2 alive: True;
7. process exit code 0.

Статус:
- PASSED

---


## 9.6. RoadMap69 test 4 — RuntimeReconnectTask + CTraderSessionManager watch

Сценарій:

1. запускається `run_runtime_ctrader_reconnect_watch.py`;
2. створюється `CTraderSessionManager`;
3. перший adapter створюється через `manager.connect_demo()`;
4. `RuntimeReconnectTask` отримує:
   - active adapter;
   - reconnect_cooldown_seconds;
   - session_manager;
5. reconnect loop виконує `reconnect_task.run_once()`;
6. active adapter читається через `manager.get_active_adapter()`.

Підтверджено:

1. RuntimeReconnectTask працює через CTraderSessionManager;
2. reconnect іде не напряму через старий adapter;
3. старий adapter retired;
4. новий adapter стає active;
5. після reconnect стан стабільний:
   - connected: True;
   - alive: True;
6. нескінченний watch-loop зупиняється вручну через KeyboardInterrupt;
7. KeyboardInterrupt у цьому тесті не є помилкою.

Статус:
- PASSED

---

## 9.7. RoadMap69 test 5 — watch startup without internet

Сценарій:

1. запуск watch-тесту без інтернету;
2. перший connect дає timeout;
3. SessionManager виконує late-connect grace check;
4. RuntimeReconnectTask запускає reconnect attempts;
5. після появи інтернету reconnect проходить;
6. active adapter стає connected.

Підтверджено:

1. `TIMEOUT: cTrader auth not completed`;
2. `Waiting for late cTrader connect`;
3. reconnect attempts через RuntimeReconnectTask;
4. reconnect через CTraderSessionManager;
5. `Late cTrader connect accepted`;
6. `New cTrader adapter connected`;
7. stable watch state:
   - connected: True;
   - alive: True.

Статус:
- PASSED

---

## 9.8. RoadMap69 test 6 — watch internet loss during runtime

Сценарій:

1. запуск watch-тесту з інтернетом;
2. cTrader успішно підключається;
3. під час runtime інтернет вимикається;
4. cTrader фіксує `ConnectionLost`;
5. RuntimeReconnectTask запускає reconnect attempts;
6. після появи інтернету reconnect проходить через SessionManager;
7. watch-loop показує стабільний connected state.

Підтверджено:

1. `cTrader disconnected: ConnectionLost`;
2. RuntimeReconnectTask запустив reconnect attempt;
3. reconnect пішов через CTraderSessionManager;
4. старий adapter retired;
5. новий adapter connected;
6. після reconnect:
   - cTrader TCP connected;
   - cTrader application auth OK;
   - cTrader account auth OK;
7. stable watch state:
   - connected: True;
   - alive: True.

Статус:
- PASSED

---

## 9.9. RoadMap69 фінальний статус reconnect stage

Після додаткових watch-тестів підтверджено:

1. cTrader reconnect працює не лише у разовому test script;
2. reconnect працює у scheduler-loop style через RuntimeReconnectTask;
3. RuntimeReconnectTask інтегровано з CTraderSessionManager;
4. IB reconnect flow не змінювався;
5. старт без інтернету не валить process;
6. втрата інтернету під час runtime не вимагає restart LGE;
7. old callbacks/deferreds із retired adapter не мають керувати новою session;
8. late-connect grace period зменшує ризик помилкового fatal UI error;
9. stage RoadMap69 по cTrader reconnect можна закривати.

Фінальний статус:

```text
RoadMap69 cTrader reconnect stage: CLOSED / PASSED
```

Залишок переноситься у наступний етап:

1. підключення trader controls у LGE UI/runtime;
2. broker connection settings pages;
3. SAFE_DISCONNECTED status для UI;
4. блокування trading actions при broker disconnect;
5. runtime events logging у DB.

---

# 10. Постійні правила проєкту

## 10.1. Коментарі

Усі:
- comments;
- docstrings;
- runtime documentation;

Мають бути українською.

---

## 10.2. Нумерація

У runtime docs і планах:
- використовувати нумерацію пунктів;
- не робити суцільні blocks text.

---

## 10.3. Повний файл для MD

Для .md файлів бажаний формат роботи:
- повна заміна файла;
- без diff-fragment;
- без урізання;
- одним готовим блоком.

---

# 11. Поточний висновок

Runtime foundation:
- уже існує;
- scheduler працює;
- heartbeat працює;
- market-state scheduler працює;
- IB reconnect майже production-ready.

Основна runtime задача RoadMap69:
- production-safe cTrader reconnect architecture.

Поточний стан після RoadMap69 tests:
- cTrader SessionManager реалізовано;
- reconnect без restart LGE підтверджено;
- старт без інтернету пройдено;
- втрата інтернету під час runtime пройдена;
- old callbacks isolation реалізовано;
- retired adapter policy реалізовано;
- late-connect grace period реалізовано;
- RuntimeReconnectTask інтегровано з CTraderSessionManager;
- reconnect watch tests пройдено;
- scheduler-loop reconnect підтверджено;
- stable reconnect watch підтверджено.

RoadMap69 reconnect stage:
- CLOSED / PASSED.

Залишилось для наступної стадії:
- підключити trader controls у LGE UI/runtime;
- додати SAFE_DISCONNECTED runtime state mapping у UI;
- додати reconnect events у runtime log / DB;
- додати коректний UI status без panic error;
- підготувати сторінки налаштувань broker connection для cTrader та IB.

---

# 12. Наступний етап

## 12.1. Перехід до підключення trader controls у LGE

Наступний технічний етап після RoadMap69:

1. перейти від reconnect foundation до broker/trader integration у LGE;
2. не ламати runtime reconnect layer;
3. підключати UI поступово;
4. спочатку статус/налаштування;
5. потім trader controls;
6. тільки після цього — order actions.

---

## 12.2. Adapter ownership

Canonical ownership:

1. RuntimeEngine володіє broker runtime;
2. для IB може лишатись прямий adapter;
3. для cTrader RuntimeEngine має володіти SessionManager;
4. active adapter для cTrader береться через manager.get_active_adapter();
5. RuntimeReconnectTask не створює cTrader adapter напряму.

---

## 12.3. Runtime state events

Потрібно логувати події:

1. CTRADER_SESSION_CREATED;
2. CTRADER_SESSION_RETIRED;
3. CTRADER_RECONNECT_STARTED;
4. CTRADER_RECONNECT_FAILED;
5. CTRADER_RECONNECT_CONNECTED;
6. BROKER_SAFE_DISCONNECTED;
7. BROKER_CONNECTED;
8. BROKER_CONNECTION_TIMEOUT;
9. BROKER_CONNECTION_RESTORED.

---

## 12.4. UI behavior

UI не має показувати panic/fatal error при першому timeout.

Правильна UI логіка:

1. SAFE_DISCONNECTED;
2. повідомлення типу:
   "З'єднання з cTrader втрачено. Виконується reconnect.";
3. кнопки торгових дій blocked;
4. налаштування/діагностика доступні;
5. після reconnect статус автоматично оновлюється.

---

## 12.5. Broker connection settings

У наступній стадії треба додати/підключити:

1. сторінку налаштувань з'єднання з cTrader;
2. сторінку налаштувань з'єднання з IB;
3. перевірку наявності required credentials;
4. зрозумілі diagnostics messages;
5. окреме пояснення для IB:
   - чи запущено TWS / IB Gateway;
   - чи увімкнено Enable ActiveX and Socket Clients;
   - чи правильний port 7497 / 7496 / 4002 / 4001.

---

## 12.6. Trading actions safety

До реального виставлення ордерів треба гарантувати:

1. broker connected;
2. account mode valid;
3. execution mode not OFF;
4. market state valid;
5. license permits selected action;
6. order actions blocked при SAFE_DISCONNECTED;
7. demo/live paths не змішуються.

---