# LGE_Runtime_06.md

# Algorithm Workspace / WSP Runtime — канонічний документ

Дата створення: 2026-07-25  
Дата актуалізації: 2026-08-16  
Проєкт: LavrGPT05 / LGE  
Статус: фінальна канонічна редакція RoadMap92–99 + технічна передача стану RoadMap100 перед поверненням до 100.1; RoadMap99 ЗАКРИТО  
Мова документа: українська

---

# 1. Призначення документа

`LGE_Runtime_06.md` є канонічним документом для шару Algorithm Workspace, скорочено WSP.

Документ описує:

1. MDI-робочі області алгоритмів;
2. постійну конфігурацію WSP у Session;
3. volatile runtime-контекст окремого WSP;
4. state machine Start / Stop;
5. synthetic Replay;
6. Historical CSV Replay;
7. завантаження історії з cTrader та Interactive Brokers;
8. канонічну broker-independent ринкову подію;
9. Live Read-only для cTrader та IB;
10. warm-up і spread guard;
11. reconnect, `WAIT_BROKER` і повторну підписку;
12. локальні сигнали, журнал і графік;
13. ownership ордерів і позицій;
14. profit drawdown guard;
15. restore і close guards;
16. параметри алгоритму;
17. межі між WSP, RuntimeEngine і broker adapters;
18. поточні обмеження та правильний напрям подальшого розвитку;
19. RoadMap98 Historical Algorithm Improvement і M1 -> M15 multi-resolution Replay;
20. Historical metrics, margin/leverage, MFE/MAE і final Replay summary;
21. RoadMap99 MACD Crossover Quality diagnostics і production filter;
22. manual calibration effective crossover angle;
23. LINEAR / EXTENDED / EXTENDED+ALLIGATOR formal comparison baseline;
24. WSP Journal/Signals/Positions/Orders diagnostic filters;
25. cTrader reconnect backoff guard і поточний broker-connectivity safety behavior.

Документ продовжує Runtime-документацію після завершення RoadMap91 і фіксує фінальну архітектурну істину WSP після RoadMap99: Replay/Live Read-only foundation, risk model, MACD/Alligator multi-timeframe runtime, M1 -> M15 historical pipeline, Replay virtual execution, Historical analytics, MACD Quality, custom indicator profiles, production ABC geometry, chart/navigation, diagnostic UI, localization, safety holds, broker reconnect guards і контрольований shutdown. Основний цикл виробничого відбору RoadMap100 ведеться в `LGE_Runtime_07.md`; у MD6 залишено лише фінальну технічну передачу стану Replay/WSP Runtime, виконану перед поверненням до RoadMap100.1.

---

# 2. Співвідношення з іншими канонічними документами

## 2.1. `LGE_Runtime_05_FINAL.md`

`LGE_Runtime_05_FINAL.md` залишається канонічним документом для:

1. глобального `RuntimeEngine`;
2. broker runtime services;
3. `SessionManager`;
4. IB і cTrader adapters;
5. broker connection lifecycle;
6. RuntimeScheduler і reconnect tasks;
7. OrdersPage;
8. broker orders і positions;
9. IB Virtual FX legs;
10. reconciliation;
11. Open, Close і SL/TP;
12. SQLite runtime persistence.

`LGE_Runtime_05_FINAL.md` не розширюється WSP-функціональністю.

## 2.2. `LGE_Algorithms_01.md`

`LGE_Algorithms_01.md` описує торгові ідеї, індикатори, патерни, сигнали, risk management і математику алгоритмів.

`LGE_Runtime_06.md` не визначає повну математику MACD, Alligator або RailAlgorithm. Він визначає runtime-контракт, через який алгоритм працює у WSP.

## 2.3. Канонічне розділення

```text
LGE_Runtime_05_FINAL.md
    = broker Runtime, OrdersPage і persistence

LGE_Runtime_06.md
    = Algorithm Workspace Runtime

LGE_Algorithms_01.md
    = торгова логіка й математика алгоритмів
```

---

# 3. Межі RoadMap92–97

## 3.1. RoadMap92 — WSP Session і MDI

RoadMap92 створив:

1. MDI-область робочих просторів;
2. створення й перейменування WSP;
3. layout lock;
4. cascade / tile / minimize / restore / maximize;
5. збереження geometry і active panel;
6. broker, account, symbol і timeframe binding;
7. data mode і control mode;
8. незалежне збереження кількох WSP у Session.

## 3.2. RoadMap93 — WSP Runtime Foundation

RoadMap93 створив:

1. `WorkspaceRuntimeContext` і runtime state machine;
2. synthetic deterministic Replay;
3. Pause / Resume / Step / Speed;
4. WSP journal;
5. canonical market event;
6. warm-up і spread guard;
7. ownership foundation;
8. WSP Orders / Position / Signals tabs;
9. `WorkspaceAlgorithm` contract;
10. profit drawdown guard і close guard;
11. Session restore;
12. chart foundation;
13. parameters foundation;
14. Historical CSV Replay;
15. Replay Settings і History Download Settings;
16. cTrader та IB history download;
17. спільний атомарний CSV export.

## 3.3. RoadMap94 — реальний Live Read-only і runtime polish

RoadMap94 підтвердив:

1. реальний cTrader Live Read-only WSP;
2. реальний IB Live Read-only WSP;
3. одночасну незалежну роботу кількох WSP;
4. historical warm-up перед live quotes;
5. `WAIT_BROKER` / `WAIT_SPREAD`;
6. live quote aggregation у timeframe candles;
7. current-bar replacement і new-bucket append;
8. safe disconnect/reconnect без втрати chart/algorithm state;
9. resubscribe без дублів;
10. invalid quote guard;
11. manual disconnect без небажаного auto-reconnect;
12. connection/UI/localization polish.

## 3.4. RoadMap95 — Risk і parameter system

RoadMap95 додав і перевірив:

1. канонічний risk model;
2. `risk_percent`, `maximum_position_volume`, `maximum_open_positions`, `max_daily_loss_percent`, `stop_loss_required`;
3. risk settings окремо для кожного WSP;
4. deterministic signal -> risk decision;
5. synthetic account snapshot для Historical Replay;
6. parameter schema / adapter / tree;
7. read-only параметри під час active runtime;
8. feature/license policy foundation;
9. збереження future keys;
10. risk journal і explainable reason codes.

## 3.5. RoadMap96 — MACD / Alligator runtime

RoadMap96 додав:

1. MACD як окреме джерело сигналу;
2. Alligator як окремий confirmation filter;
3. незалежні enable/disable джерела і фільтра;
4. indicator profiles з `profile_uid`, revision і persisted snapshot;
5. built-in та user profiles, archive/delete rules;
6. MACD deterministic Replay calculation;
7. Alligator `SAME_TIMEFRAME`;
8. Alligator `HIGHER_1`;
9. експериментальний `HIGHER_2`;
10. явні timeframe mapping tables;
11. completed-higher-bar-only aggregation;
12. окремий warm-up для MACD і Alligator;
13. no-look-ahead і future-change-does-not-change-past checks;
14. signal statistics foundation;
15. broker market-data request accounting і subscription deduplication;
16. Replay speeds `1x/2x/5x/10x/100x/1000x/MAX`.

## 3.6. RoadMap97 — Historical Replay UI/UX і virtual execution

RoadMap97 довів до поточного baseline:

1. MACD panel на chart;
2. Alligator overlay;
3. horizontal navigation, full Replay history access, Home/End, scrollbars;
4. crosshair і compact chart layout;
5. synchronized MACD/chart viewport;
6. full-history navigation при bounded retained render buffer;
7. localized Signals reason text і tooltips;
8. source/filter profile UID/revision та causal timestamps у Signals;
9. Replay terminology: «Віртуальний рахунок Replay», «Кошти Replay», «Баланс Replay», «Закритий PnL», «Поточний PnL»;
10. configurable Replay initial balance `100..100000 USD`, default `1000 USD`;
11. live Replay balance/equity/closed/open PnL presentation;
12. `RailAlgorithm` Replay registration;
13. Replay-only virtual order -> position -> close lifecycle у `AUTO`;
14. deterministic SL/TP/profit-drawdown/session-end close reasons;
15. Replay Orders/Positions presentation із localized states і technical tooltips;
16. cTrader Startup Readiness Grace без blind sleep;
17. event-driven late-connect і retired-session-close waits;
18. SessionManager-owned reconnect contract;
19. external exposure alert і `SAFETY_HOLD_EXTERNAL_EXPOSURE`;
20. єдиний контрольований shutdown для WSP/runtime resources.

## 3.7. Свідомо не реалізовано на baseline RoadMap98

1. broker order placement із WSP у `BROKER` mode;
2. Paper algorithm execution через broker;
3. Live algorithm execution;
4. fast batch `BACKTEST` engine;
5. RoadMap98 baseline metrics/reporting;
6. MFE/MAE trade diagnostics;
7. train/validation/test workflow;
8. multi-period historical comparison table;
9. автоматична агрегація Historical CSV `M1 -> M15` для multi-resolution Replay;
10. tick-level execution simulation;
11. повний production-набір chart trade markers;
12. завершена `EXTENDED` MACD logic.

---

# 4. Algorithm Workspace / WSP

## 4.1. Визначення

WSP — це окремий робочий простір одного алгоритму в MDI-області LGE.

Кожен WSP має власні:

1. broker;
2. account;
3. account mode;
4. symbol;
5. timeframe;
6. algorithm;
7. data mode;
8. control mode;
9. parameters;
10. risk settings;
11. profit protection;
12. Replay settings;
13. History Download settings;
14. UI state;
15. volatile runtime state;
16. chart history;
17. journal;
18. signals;
19. owned orders;
20. owned positions.

## 4.2. Стабільна identity

Кожен WSP ідентифікується стабільним:

```text
workspace_uid
```

`display_name` можна змінювати, але він не замінює `workspace_uid`.

## 4.3. Незалежність WSP

Два WSP не повинні ділити:

1. runtime state;
2. startup phase;
3. Replay cursor;
4. Replay speed;
5. broker subscription identity;
6. сигнали;
7. ордери;
8. позиції;
9. peak profit;
10. pending close decisions;
11. chart history;
12. journal filter state;
13. current spread;
14. warm-up progress.

Зупинка або disconnect одного WSP не повинні зупиняти інший WSP, якщо їхні broker bindings залишаються працездатними.

---

# 5. Канонічна архітектура WSP

## 5.1. Загальний шлях

```text
AlgorithmWorkspaceWindow
    -> AlgorithmWorkspaceController
    -> WorkspaceRuntime
```

Далі шлях залежить від data mode.

## 5.2. Replay-шлях

```text
AlgorithmWorkspaceWindow
    -> AlgorithmWorkspaceController
    -> WorkspaceRuntime
    -> WorkspaceReplaySession
    -> WorkspaceMarketEvent
    -> WorkspaceAlgorithm
```

## 5.3. Historical CSV Replay-шлях

```text
CSV file
    -> WorkspaceCsvHistoryLoader
    -> WorkspaceHistoryDataSet
    -> WorkspaceReplaySession
    -> WorkspaceRuntime
    -> WorkspaceMarketEvent
    -> WorkspaceAlgorithm
```

## 5.4. Live Read-only broker-шлях

```text
AlgorithmWorkspaceWindow
    -> AlgorithmWorkspaceController
    -> WorkspaceRuntime
    -> WorkspaceRuntimeEngineMarketProvider
    -> RuntimeEngine
    -> BrokerRuntimeService
    -> SessionManager
    -> Adapter
    -> Broker API / Terminal
```

Повернення market data:

```text
Broker quote snapshot
    -> RuntimeEngine
    -> WorkspaceRuntimeEngineMarketProvider
    -> WorkspaceTimeframeAggregator
    -> WorkspaceMarketEvent
    -> WorkspaceRuntime
    -> WorkspaceAlgorithm
    -> Chart / Signals / Journal
```

## 5.5. Заборонений шлях

```text
AlgorithmWorkspaceWindow
    -> IBAdapter / CTraderAdapter
```

WSP не працює напряму з:

1. broker adapters;
2. broker sockets;
3. Twisted;
4. IB API callbacks;
5. cTrader OpenAPI messages;
6. probe scripts.

## 5.6. Відповідальність шарів

### `AlgorithmWorkspaceWindow`

1. показує UI;
2. передає команди користувача;
3. відображає runtime state;
4. не містить broker API logic;
5. не містить торгової математики.

### `AlgorithmWorkspaceController`

1. керує WSP configuration;
2. створює volatile runtime;
3. зберігає Session;
4. координує UI і runtime;
5. не працює напряму з broker API.

### `WorkspaceRuntime`

1. виконує state machine;
2. приймає market events;
3. застосовує guards;
4. викликає алгоритм;
5. веде журнал;
6. формує local signals і decisions;
7. не виконує прихованих broker orders.

### `RuntimeEngine`

1. залишається єдиним broker coordinator;
2. валідує broker/account binding;
3. надає broker-neutral quote snapshots;
4. не передає WSP чужий broker або account;
5. блокує disconnected і unsupported broker;
6. у майбутньому буде єдиним шляхом execution.

### `BrokerRuntimeService`

1. надає broker-specific market data через стабільний Runtime API;
2. не знає про WSP UI;
3. працює через власний SessionManager і Adapter.

---

# 6. WSP configuration і volatile runtime

## 6.1. Головне правило

```text
WSP configuration
    !=
WSP runtime state
```

## 6.2. Постійна конфігурація

У Session зберігаються:

1. `workspace_uid`;
2. `display_name`;
3. `broker`;
4. `account_id`;
5. `account_mode`;
6. `symbol`;
7. `timeframe`;
8. `algorithm_id`;
9. `data_mode`;
10. `control_mode`;
11. `parameters`;
12. `risk_settings`;
13. `profit_protection`;
14. `replay_settings`;
15. `history_download_settings`;
16. `ui_state`;
17. порядок WSP;
18. active workspace;
19. ознака першого запуску.

## 6.3. Volatile runtime

У `WorkspaceRuntimeContext` живуть:

1. `runtime_state`;
2. `startup_phase`;
3. active order count;
4. open position count;
5. current profit;
6. peak profit;
7. profit drawdown;
8. current market event;
9. current spread;
10. warm-up progress;
11. signal permission;
12. signal block reason;
13. broker operation flag;
14. market-event processing flag;
15. Replay Step flag;
16. restore marker;
17. live quote received flag;
18. pending close decision count.

## 6.4. Що не можна відновлювати як runtime-істину

Після restart не відновлюються як фактичний поточний стан:

1. `RUNNING`;
2. `STARTING`;
3. `WAIT_BROKER`;
4. active Replay session;
5. Replay cursor;
6. active broker subscription;
7. сигнали попереднього запуску;
8. broker operations;
9. market-event processing;
10. pending local decisions;
11. старі active orders і positions без нового snapshot;
12. PnL без актуального джерела.

---

# 7. Режими WSP

## 7.1. Data mode

Кодова модель містить:

```text
BROKER
REPLAY
BACKTEST
```

### `REPLAY`

Працює для:

1. synthetic deterministic data;
2. Historical CSV Replay;
3. Pause / Resume / Step / Speed;
4. повторюваної відладки.

### `BROKER`

У поточній редакції означає:

```text
Live Read-only market data
```

`BROKER` зараз:

1. завантажує historical warm-up bars;
2. підписується на live quote snapshots;
3. будує timeframe candles;
4. виконує guards;
5. передає events алгоритму;
6. формує signals;
7. оновлює chart і journal;
8. не надсилає broker orders.

### `BACKTEST`

Значення зарезервовано моделлю, але повний Backtest engine ще не реалізований.

## 7.2. Account mode

```text
PAPER
DEMO
LIVE
```

`account_mode` описує тип рахунку, а не data source.

Поточні підтверджені реальні bindings:

```text
cTrader DEMO
IB Paper через account_mode=DEMO у поточній конфігурації LGE
```

## 7.3. Control mode

```text
MANUAL
SEMI
AUTO
```

Канонічна семантика залежить від data mode:

```text
REPLAY + MANUAL
    -> signals visible
    -> virtual execution disabled

REPLAY + AUTO
    -> deterministic virtual execution enabled
    -> broker_requests=0
    -> broker_execution_attempted=False

BROKER + MANUAL/SEMI/AUTO
    -> Live Read-only market data/signals
    -> broker execution disabled
```

Правила:

1. control mode зберігається окремо в кожному WSP;
2. глобальне налаштування є лише default для нового WSP;
3. runtime guards мають пріоритет над control mode;
4. `AUTO` у Replay означає тільки virtual execution;
5. `AUTO` не дозволяє обійти risk, spread, warm-up або safety holds;
6. `AUTO` у `BROKER` mode не є дозволом на broker order placement.

---

# 8. Runtime state machine

## 8.1. Runtime states

```text
RESTORED
STOPPED
STARTING
RUNNING
STOPPING
ERROR
```

## 8.2. Нормальний запуск

```text
STOPPED
    -> STARTING
    -> RUNNING
```

## 8.3. Нормальна зупинка

```text
RUNNING
    -> STOPPING
    -> STOPPED
```

Також дозволена контрольована зупинка зі `STARTING` або `ERROR`.

## 8.4. Помилка

```text
STARTING / RUNNING / STOPPING
    -> ERROR
```

`ERROR` використовується для справжньої runtime-помилки, а не для тимчасової відсутності broker connection або одного некоректного quote.

## 8.5. Restore

```text
RESTORED
    -> STOPPED
```

Runtime після restart не запускається автоматично.

## 8.6. Правила

1. повторний Start під час активного запуску блокується;
2. Stop не закриває broker positions автоматично;
3. зміна modes або parameters під час active runtime блокується;
4. WSP не видаляється під час active runtime;
5. непідтримуваний data mode не маскується Replay-режимом;
6. broker disconnect не повинен автоматично перетворювати WSP на `ERROR`;
7. disconnected broker переводить active WSP у безпечне очікування;
8. один некоректний live quote не переводить WSP у `ERROR`.

---

# 9. Startup phases

Внутрішні startup phases:

```text
IDLE
LOAD_DATA
WARMUP
WAIT_BROKER
WAIT_SPREAD
READY
RUNNING
```

## 9.1. Replay startup

```text
IDLE
    -> LOAD_DATA
    -> WARMUP
    -> WAIT_SPREAD
    -> READY
    -> RUNNING
```

## 9.2. Broker startup при доступному broker

```text
IDLE
    -> LOAD_DATA
    -> WARMUP
    -> WAIT_SPREAD
    -> READY
    -> RUNNING
```

Різниця полягає в тому, що `LOAD_DATA` і `WARMUP` використовують broker history, а `WAIT_SPREAD` чекає перший коректний live quote.

## 9.3. Broker startup при disconnected broker

```text
IDLE
    -> LOAD_DATA
    -> WAIT_BROKER
```

Після reconnect:

```text
WAIT_BROKER
    -> WARMUP, якщо треба відновити bars
    -> WAIT_SPREAD
    -> READY
    -> RUNNING
```

## 9.4. Disconnect під час RUNNING

```text
RUNNING
    -> STARTING
    -> WAIT_BROKER
```

Це означає:

1. processing призупинено;
2. signals заблоковано;
3. chart не очищається;
4. algorithm instance не знищується;
5. WSP чекає safe reconnect.

## 9.5. WAIT_SPREAD

Після warm-up або reconnect runtime не повертається до `RUNNING`, доки не отримає новий коректний live quote з допустимим spread.

---

# 10. Start / Stop і execution boundary

## 10.1. Start

Start:

1. створює або готує runtime;
2. очищує volatile history нового запуску;
3. запускає algorithm lifecycle;
4. завантажує data source;
5. проходить warm-up;
6. проходить spread guard;
7. переходить у `RUNNING` лише після guards.

## 10.2. Stop

Stop:

1. припиняє Replay або broker feed для цього WSP;
2. знімає market-data subscription;
3. припиняє local market processing;
4. викликає `algorithm.stop()`;
5. повертає WSP у `STOPPED`;
6. не закриває broker orders;
7. не закриває broker positions;
8. не зупиняє інші WSP.

## 10.3. Execution boundary

Поточна production boundary розділяє Replay virtual execution і реальний broker execution.

```text
Historical/Synthetic Replay
    -> local signals
    -> risk/guards
    -> virtual order/position lifecycle in AUTO
    -> broker_requests=0
    -> broker_execution_attempted=False

BROKER Live Read-only
    -> market data
    -> guards
    -> signals/chart/journal
    -> broker order placement disabled
```

Replay virtual execution не є broker execution і не має права викликати broker adapters, sockets або broker order API.

---

# 11. Synthetic Replay Runtime

## 11.1. Призначення

Synthetic Replay є базовим repeatable test source.

## 11.2. Основні об’єкти

```text
WorkspaceReplayService
WorkspaceReplaySession
WorkspaceMarketBar
WorkspaceQuote
WorkspaceMarketEvent
```

## 11.3. Швидкості

```text
1x
2x
5x
10x
100x
1000x
MAX
```

`MAX` виконується bounded batches і повинен залишатися responsive для Pause/Stop між пакетами. У Session `MAX` зберігається через канонічний zero sentinel.

---

## 11.4. Команди

```text
Start
Pause
Resume
Step
Speed
Stop
```

`Step` працює лише у paused state.

## 11.5. Детермінованість

Однакові:

1. source;
2. start time;
3. event count;
4. timeframe;
5. synthetic settings;

повинні створювати однакову послідовність market events.

---

# 12. Historical CSV Replay

## 12.1. Призначення

Historical CSV Replay проганяє broker history через той самий `WorkspaceRuntime`, що synthetic Replay і Live Read-only, але без broker execution.

## 12.2. Канонічний шлях

```text
CSV
    -> WorkspaceCsvHistoryLoader
    -> validation / quality report
    -> WorkspaceHistoryDataSet
    -> WorkspaceReplaySession
    -> WorkspaceRuntime
    -> MACD / Alligator / risk
    -> virtual execution in AUTO
    -> Chart / Signals / Orders / Positions / Journal
```

## 12.3. Підтримуваний CSV

Обов’язкові логічні поля:

```text
timestamp
open
high
low
close
```

Необов’язкові:

```text
volume
bid
ask
spread
```

## 12.4. Localized CSV

Loader підтримує delimiter auto-detection, comma/semicolon/tab/pipe, decimal `.` або `,`, UTC/source timezone та локальні timestamp formats.

## 12.5. Quote derivation

Коли CSV не містить `bid/ask`, quote формується з `close` і configured/default Replay spread. Це детермінована модель, а не відновлення реального історичного broker spread.

## 12.6. Валідація

Loader блокує missing/empty file, missing required columns, duplicate/decreasing timestamp, invalid number/OHLC, negative volume, invalid quote і empty selected range.

## 12.7. Quality report

`WorkspaceHistoryReport` містить щонайменше:

```text
input_rows
accepted_rows
filtered_rows
derived_quotes
gap_count
first_timestamp
last_timestamp
```

## 12.8. Runtime поведінка

Historical Replay:

1. не має silent synthetic fallback;
2. проходить component warm-up і spread guard;
3. підтримує Pause / Step / `1x..MAX`;
4. оновлює chart, signals, journal і Replay financial UI;
5. має synthetic Replay account snapshot;
6. у `AUTO` створює тільки virtual orders/positions;
7. broker requests і broker execution залишаються нульовими;
8. детерміновано перезапускається;
9. не стартує автоматично після Session restore.

## 12.9. Поточне правило source timeframe

Поточний `WorkspaceCsvHistoryLoader` не виконує automatic resampling між timeframe CSV і timeframe WSP.

Отже Historical CSV має бути підготовлений у timeframe, який відповідає source timeframe Replay. Підкладання M1 CSV у WSP M15 без окремого агрегатора є некоректним.

План RoadMap98 передбачає окремий multi-resolution режим:

```text
M1 source
    -> completed M15 strategy bars
    -> MACD/Alligator on M15+
    -> M1 execution path for finer SL/TP/MFE/MAE chronology
```

Цей режим ще не є частиною baseline після RoadMap97.

---

# 13. Replay Settings

## 13.1. Окремий Designer dialog

Replay settings містять лише параметри відтворення:

1. source type;
2. source name;
3. CSV file path;
4. start UTC;
5. end UTC;
6. source timezone;
7. delimiter;
8. decimal separator;
9. default spread;
10. Replay speed.

## 13.2. Правила

1. download fields видалені з Replay dialog;
2. шлях CSV зберігається як absolute path;
3. active WSP не дозволяє редагування;
4. future keys не видаляються;
5. різні WSP мають незалежні Replay periods;
6. period може бути визначений із CSV;
7. missing file блокує запуск.

---

# 14. History Download Settings

## 14.1. Окрема конфігурація

History Download settings не змішуються з Replay settings.

Вони містять:

1. start date;
2. end date;
3. timezone;
4. destination folder;
5. planned CSV path;
6. planned source name.

## 14.2. Правила

1. legacy download fields мігруються;
2. persistence окрема для кожного WSP;
3. date boundaries перетворюються в UTC;
4. підтримуються міжнародні timezone;
5. default history root будується від application base;
6. active WSP блокує history download editing;
7. invalid date range блокується.

---

# 15. Спільний формат broker history

## 15.1. Канонічний CSV header

```text
timestamp,open,high,low,close,volume
```

## 15.2. Timestamp

Timestamp записується у UTC ISO 8601:

```text
2026-07-29T14:15:00Z
```

## 15.3. Шлях

```text
data/history/<BROKER>/<SYMBOL>/<TIMEFRAME>/
```

Приклад:

```text
data/history/CTRADER/EURUSD/M15/
data/history/IB/GBPUSD/M15/
```

Account folder навмисно не додається до canonical history path.

## 15.4. Ім’я файлу

```text
<start-date>_<end-date>_<BROKER>_<SYMBOL>_<TIMEFRAME>.csv
```

## 15.5. Atomic write

CSV спочатку записується у temporary file, виконується flush і `fsync`, після чого файл атомарно замінює final target.

Частково записаний файл не повинен ставати Replay source.

## 15.6. Автоматичне підключення до Replay

Після успішного download:

1. final CSV path записується у Replay settings;
2. source name оновлюється;
3. detected period доступний WSP;
4. файл може бути одразу перечитаний canonical loader.

---

# 16. cTrader History Download

## 16.1. Канонічний шлях

```text
WSP History Download dialog
    -> AlgorithmWorkspaceController
    -> RuntimeEngine
    -> CTraderRuntimeService
    -> CTraderSessionManager
    -> CTraderAdapter
    -> cTrader OpenAPI trendbars
    -> WorkspaceHistoryCsvWriter
```

## 16.2. Timeframes

Підтримувані mappings:

```text
M1
M5
M15
M30
H1
H4
D1
```

## 16.3. Технічні правила

1. relative-price trendbars декодуються;
2. invalid trendbar блокується;
3. backward pagination працює без залежності від `hasMore`;
4. request burst обмежено;
5. active download блокує повторний download;
6. final CSV створюється атомарно;
7. account folder у history path не використовується.

---

# 17. IB History Download

## 17.1. Канонічний шлях

```text
WSP History Download dialog
    -> AlgorithmWorkspaceController
    -> RuntimeEngine
    -> IBRuntimeService
    -> IBSessionManager
    -> IBAdapter
    -> TWS / IB Gateway historical bars
    -> WorkspaceHistoryCsvWriter
```

## 17.2. Timeframes

Підтримувані mappings:

```text
M1
M5
M15
M30
H1
H4
D1
```

## 17.3. Технічні правила

1. TWS `barSizeSetting` використовується у точному API-форматі;
2. duration визначається timeframe;
3. download виконується backward chunks;
4. `endDateTime` має коректний IB format;
5. epoch timestamps декодуються;
6. MIDPOINT negative volume нормалізується;
7. invalid bar блокується;
8. empty final file не створюється;
9. multi-chunk delay не застосовується після останнього chunk;
10. active download блокує повторний download;
11. final CSV створюється атомарно.

---

# 18. Канонічна ринкова подія

## 18.1. Модель

```text
WorkspaceMarketEvent
    timestamp
    broker
    symbol
    timeframe
    bid
    ask
    spread
    open
    high
    low
    close
    volume
    source_mode
```

## 18.2. Головне правило

Алгоритм не повинен знати, звідки прийшла подія.

Один контракт використовується для:

1. synthetic Replay;
2. Historical CSV Replay;
3. cTrader Live Read-only;
4. IB Live Read-only;
5. майбутнього Paper;
6. майбутнього Live;
7. майбутнього Backtest.

## 18.3. Валідація

Market event перевіряє:

1. timezone-aware timestamp;
2. normalized broker;
3. normalized symbol;
4. normalized timeframe;
5. finite positive prices;
6. `ask >= bid`;
7. spread, узгоджений із `ask - bid`;
8. коректний OHLC range;
9. невід’ємний volume.

---

# 19. Live Read-only Market Bridge

## 19.1. Призначення

Live Read-only дає алгоритму реальні broker market events без права на broker execution.

## 19.2. Binding

Кожна market-data subscription прив’язана до:

```text
workspace_uid
broker
account_id
symbol
timeframe
```

## 19.3. RuntimeEngine validation

RuntimeEngine перевіряє:

1. broker підтримується;
2. broker connected;
3. account належить активній broker session;
4. account WSP збігається з requested account;
5. symbol нормалізовано;
6. quote snapshot належить правильному broker;
7. cTrader і IB events не змішуються.

## 19.4. Confirmed broker support

```text
CTRADER
IB
```

## 19.5. Перший запуск

Broker WSP:

1. починає у `STARTING`;
2. завантажує historical warm-up;
3. не приймає live polling до завершення startup prerequisites;
4. після warm-up переходить у `WAIT_SPREAD`;
5. чекає перший коректний live quote;
6. після acceptable spread переходить у `RUNNING`.

---

# 20. Live quote aggregation

## 20.1. Timeframe bucket

Changing bid/ask quotes агрегуються у canonical timeframe candle.

Для M15 всі quotes в одному 15-хвилинному bucket оновлюють один bar.

## 20.2. Current bar replacement

Якщо новий quote належить поточному timeframe bucket:

1. timestamp bucket не змінюється;
2. open зберігається;
3. high оновлюється максимумом;
4. low оновлюється мінімумом;
5. close замінюється новим midpoint;
6. bid і ask оновлюються;
7. chart замінює останній bar.

## 20.3. New bucket

Якщо quote переходить у наступний timeframe bucket:

1. відкривається новий bar;
2. chart додає новий candle;
3. journal може записати `LIVE_BAR_OPENED`.

## 20.4. Duplicate suppression

Quote з тією самою:

1. timestamp;
2. bid;
3. ask;
4. volume;

ігнорується.

Market-data resubscribe після reconnect не повинен створювати duplicate events.

---

# 21. Invalid live quote guard

## 21.1. Призначення

Broker API під час disconnect, reconnect або неповного snapshot може тимчасово повернути некоректні значення.

Такий row не є достатньою причиною переводити WSP у `ERROR`.

## 21.2. Ігноруються

1. missing bid;
2. missing ask;
3. zero bid;
4. zero ask;
5. negative bid;
6. negative ask;
7. non-finite price;
8. `ask < bid`;
9. invalid payload;
10. stale quote timestamp;
11. exact duplicate quote.

## 21.3. Поведінка

Некоректний quote:

1. не створює market event;
2. не змінює current bar;
3. не очищує chart;
4. не запускає signal;
5. не змінює останній valid spread;
6. не переводить WSP у `ERROR`;
7. під час startup залишає WSP у `WAIT_SPREAD`;
8. дозволяє дочекатися наступного valid quote.

## 21.4. Підтверджений результат

```text
invalid_live_quotes_ignored=True
invalid_startup_quotes_wait_for_valid_spread=True
last_valid_chart_preserved=True
invalid_quote_does_not_enter_error=True
```

---

# 22. Warm-up і spread guard

## 22.1. Параметри

```text
warmup_bars
spread_limit
```

Defaults:

```text
DEFAULT_WORKSPACE_WARMUP_BARS = 3
DEFAULT_WORKSPACE_SPREAD_LIMIT = 0.00020
```

## 22.2. Signal gate

Канонічний вхід:

```python
runtime.can_form_signal()
```

Алгоритм не повинен обходити цей gate.

## 22.3. Broker warm-up

Live Read-only перед першим live event завантажує historical bars.

Warm-up events:

1. оновлюють chart;
2. готують algorithm indicators;
3. не дозволяють signal execution;
4. не замінюють потребу в першому live spread.

## 22.4. WAIT_SPREAD

Після warm-up:

```text
current_spread = None
spread_ok = False
signal_allowed = False
```

Runtime чекає live quote.

## 22.5. Wide spread

Якщо spread перевищує limit:

1. market event залишається видимим;
2. chart оновлюється;
3. signal блокується;
4. runtime не падає;
5. після нормалізації spread signal permission відновлюється.

## 22.6. Reconnect

Після reconnect старий spread не вважається достатнім.

Потрібен новий valid live quote.

---

# 23. Broker disconnect і reconnect

## 23.1. Disconnect

Коли broker connection зникає:

1. market feed конкретного WSP suspend;
2. signal permission вимикається;
3. current spread очищується;
4. runtime переходить із `RUNNING` у `STARTING`;
5. startup phase стає `WAIT_BROKER`;
6. chart і algorithm state зберігаються;
7. сам disconnect не переводить WSP у `ERROR`.

## 23.2. Reconnect

Після відновлення broker connection:

1. broker/account binding перевіряється повторно;
2. subscription відновлюється без дублів;
3. runtime переходить у `WAIT_SPREAD`;
4. потрібен fresh valid quote;
5. після spread guard WSP повертається у `RUNNING`.

## 23.3. Manual disconnect

Explicit `Відключити` блокує auto-reconnect проти волі користувача і не стирає persisted account binding.

## 23.4. cTrader Startup Readiness Grace

Перед startup/autoconnect cTrader виконується bounded readiness check:

1. immediate host availability проходить без штучної затримки;
2. transient startup може відновитися в межах grace;
3. timeout повертає `UNAVAILABLE`;
4. readiness не створює adapter candidate і не змінює session generation;
5. timeout не запускає candidate connect;
6. manual disconnect intent зберігається.

## 23.5. Event-driven waits

cTrader connection lifecycle не використовує blind reconnect sleep для очікування:

1. late connect;
2. retired session close evidence.

Очікування bounded і event-driven. `SessionManager` є власником reconnect lifecycle; legacy adapter reconnect contract видалений.

## 23.6. External exposure safety hold

Для LGE-exclusive WSP точна зовнішня broker exposure переводить runtime у:

```text
state = STARTING
phase = SAFETY_HOLD_EXTERNAL_EXPOSURE
```

При цьому:

1. market data продовжується;
2. signals блокуються;
3. alert/popup не дублюються без потреби;
4. hold очищується лише поточним broker evidence;
5. після очищення потрібен fresh spread;
6. broker execution із WSP не виконується.

## 23.7. Internet outage

Під час network outage broker health може перейти у disconnected/degraded; WSP призупиняє signal processing, зберігає останній valid chart і після canonical reconnect відновлює binding/subscription незалежно для кожного broker/WSP.

---

# 24. UI runtime states

## 24.1. State badge

WSP показує поточний стан окремою кнопкою або badge.

Канонічні технічні values:

```text
STOPPED
STARTING
RUNNING
STOPPING
ERROR
WAIT_BROKER
WAIT_SPREAD
```

`WAIT_BROKER` і `WAIT_SPREAD` є startup phases, але в UI показуються як важливий operational state.

## 24.2. Українські labels

```text
ЗУПИНЕНО
ЗАПУСК
ПРАЦЮЄ
ЗУПИНКА
ПОМИЛКА
ОЧІКУВАННЯ БРОКЕРА
ОЧІКУВАННЯ СПРЕДУ
```

## 24.3. Frame semantics

1. зелена рамка — `RUNNING`;
2. жовта рамка — transitional або waiting state;
3. червона рамка — `ERROR`;
4. neutral frame — `STOPPED`.

Після safe disconnect рамка не повинна залишатися червоною лише через попередню transient error.

## 24.4. Buttons

1. `START` доступний у `STOPPED`;
2. `STOP` доступний під час active runtime;
3. Parameters і Rename блокуються під час active runtime;
4. History і Replay configuration не редагуються під час active runtime.

---

# 25. MDI Runtime

## 25.1. Реалізовані операції

1. Create;
2. Rename;
3. Cascade;
4. Tile;
5. Minimize;
6. Restore;
7. Maximize;
8. manual resize;
9. active WSP selection;
10. layout lock.

## 25.2. Geometry

Зберігаються:

1. x;
2. y;
3. width;
4. height;
5. minimized state;
6. maximized state;
7. normal geometry.

## 25.3. Restore safety

1. geometry clamp до MDI viewport;
2. delayed restore після Qt layout;
3. saved geometry reapply;
4. кілька windows відновлюються distinct;
5. native maximize після Tile і Cascade працює;
6. maximize не залишає window у неправильній geometry.

## 25.4. Незалежний Stop

Stop одного WSP:

1. звільняє лише його subscription;
2. не зупиняє інший WSP;
3. не очищує chart іншого WSP;
4. не змінює runtime state іншого WSP.

---

# 26. Контракт алгоритму

## 26.1. Базовий інтерфейс

```python
class WorkspaceAlgorithm:
    def configure(self, context, parameters): ...
    def start(self): ...
    def on_market_event(self, event): ...
    def on_order_event(self, event): ...
    def stop(self): ...
```

## 26.2. Правила

1. WSP window не містить торгової логіки;
2. алгоритм не знає broker adapter;
3. алгоритм отримує canonical market events;
4. алгоритм повертає signal proposals;
5. runtime вирішує, чи прийняти proposal;
6. runtime guards мають пріоритет;
7. order event передається broker-neutral контрактом;
8. disconnect не повинен знищувати algorithm instance;
9. reconnect не повинен подвійно запускати algorithm.

## 26.3. Passive implementation

`PassiveWorkspaceAlgorithm` є безпечним default для невідомого algorithm id.

Він:

1. підтримує lifecycle;
2. не торгує;
3. не створює прихованих сигналів;
4. дозволяє тестувати WSP runtime.

---

# 27. Signals Runtime

## 27.1. Моделі

```text
WorkspaceSignalProposal
WorkspaceSignalRecord
```

## 27.2. Signal record

Signal record містить broker-neutral identity і explainability data, зокрема:

1. timestamp / observation timestamp / available-at;
2. workspace, broker, account, symbol, base timeframe;
3. signal type і direction;
4. MACD state, reason code і source profile UID/revision;
5. Alligator state, timeframe mode, allow/reject reason і filter profile UID/revision;
6. runtime/risk acceptance state;
7. technical reason codes;
8. localized user-facing reason text;
9. diagnostic reason text для tooltip/journal.

## 27.3. Потік

```text
WorkspaceMarketEvent
    -> MACD source
    -> optional Alligator confirmation
    -> Runtime guards
    -> Risk model
    -> WorkspaceSignalRecord
    -> optional Replay virtual execution
```

## 27.4. Multi-timeframe causal rule

Для `HIGHER_1/HIGHER_2` використовуються тільки завершені higher-timeframe bars. `available_at` не може бути раніше causal close boundary. Incomplete higher bucket не підміняється майбутніми даними.

## 27.5. Control mode decision

```text
MANUAL
    -> signal visible, no virtual execution

SEMI
    -> signal/plan only; broker execution disabled

AUTO + REPLAY
    -> virtual execution allowed after guards

AUTO + BROKER
    -> broker execution disabled
```

## 27.6. Локалізація

User-facing reason text локалізується централізовано. Technical reason codes, profile UID/revision і causal timestamps залишаються language-independent та доступні у tooltip/diagnostics.

## 27.7. Межі історії

Runtime signal history залишається bounded; новий Start очищує volatile signal history нового запуску.

---

# 28. WSP Journal

## 28.1. Призначення

Journal є локальним пояснюваним слідом одного WSP.

## 28.2. Категорії

Підтримуються категорії на кшталт:

```text
LIFECYCLE
SESSION
REPLAY
HISTORY
BROKER
GUARD
MARKET
ALGORITHM
SIGNAL
PROFIT
ERROR
```

## 28.3. Levels

```text
INFO
WARNING
ERROR
```

## 28.4. Filters

UI дозволяє фільтрувати:

1. category;
2. level;
3. market ticks visibility.

Прапорець `Показувати кожен ринковий тік` за замовчуванням вимкнений, щоб journal не перетворювався на потік шуму.

Перший live quote, новий bar, guard transitions, disconnect, reconnect і помилки залишаються видимими.

## 28.5. Ключові broker events

```text
LIVE_READ_ONLY_STARTED
BROKER_WARMUP_LOADED
LIVE_QUOTE_RECEIVED
LIVE_BAR_OPENED
BROKER_DISCONNECTED
BROKER_RECONNECTED
MARKET_DATA_RESUBSCRIBED
```

---

# 29. Ownership ордерів і позицій

## 29.1. Exact binding

Ордер або позиція належить WSP лише при одночасному збігу:

```text
workspace_uid
broker
account_id
symbol
```

## 29.2. Моделі

```text
WorkspaceBinding
WorkspaceOrderSnapshot
WorkspacePositionSnapshot
WorkspaceOwnedSnapshot
WorkspaceOwnershipFilter
```

## 29.3. Fail-closed rule

Рядок без `workspace_uid` не прив’язується до WSP автоматично.

```text
legacy row without workspace_uid
    -> rejected
```

## 29.4. Чужі рядки

Не проходять:

1. інший WSP;
2. інший broker;
3. інший account;
4. інший symbol;
5. відсутня ownership identity.

## 29.5. IB Virtual FX

Для майбутнього IB execution WSP повинен використовувати exact Virtual FX legs, а не лише broker net position.

```text
IB broker net observation
    !=
exact WSP-owned virtual position
```

---

# 30. Вкладки Orders і Position

## 30.1. Orders

WSP показує тільки власні broker-neutral snapshots. У Replay це virtual orders, а не broker orders.

Поля/семантика включають:

```text
order_id
broker_order_id when factual
side
order_type
volume
entry/price
stop_loss
take_profit
status
created_at
close_reason when applicable
realized_profit when applicable
```

Replay broker order id не вигадується і при відсутності не показується як factual identifier.

## 30.2. Position

Replay Positions мають явне розділення active/closed і містять:

```text
side
volume
entry_price
current_price
current_profit
peak_profit
profit_drawdown
stop_loss
take_profit
opened_at
closed_at
status
close_reason
realized_profit
```

User-facing state/close reason локалізується; technical values зберігаються в tooltip/data roles.

---

# 31. Profit drawdown guard

## 31.1. Призначення

Guard захищає вже накопичений плаваючий прибуток.

## 31.2. Модель

```text
WorkspaceProfitProtectionPolicy
WorkspaceProfitProtectionDecision
WorkspaceProfitDrawdownGuard
```

## 31.3. Формула

```text
peak_profit = 100
current_profit = 69
lost_from_peak = 31
profit_drawdown = 31%
limit = 30%
=> CLOSE decision
```

Рівно `30%` не спрацьовує.

Потрібно:

```text
profit_drawdown > limit
```

## 31.4. Умови

Рішення `CLOSE` формується лише коли:

1. position належить цьому WSP;
2. runtime state = `RUNNING`;
3. spread guard пройдено;
4. current price наявна й достовірна;
5. peak profit досяг minimum profit;
6. drawdown перевищив limit.

## 31.5. Replay execution

У Historical/Synthetic Replay `AUTO` guard може завершити virtual position із reason `PROFIT_DRAWDOWN`.

Правила baseline RoadMap97:

1. percentage configurable в межах `1..100`;
2. default `30%`;
3. guard arms лише після positive peak;
4. рішення і close reason детерміновані;
5. broker close не викликається;
6. realized PnL переходить у Replay account balance.

---

# 32. Безпечне закриття WSP

## 32.1. Guard

Закриття перевіряє:

```text
WorkspaceCloseGuard
```

## 32.2. Причини блокування

WSP не можна видалити, якщо:

1. runtime active;
2. є active orders;
3. є open positions;
4. виконується broker operation;
5. обробляється market event;
6. виконується Replay Step;
7. є pending CLOSE decision.

Кодові values:

```text
RUNTIME_ACTIVE
ACTIVE_ORDERS
OPEN_POSITIONS
BROKER_OPERATION
MARKET_EVENT_PROCESSING
REPLAY_STEP_ACTIVE
PENDING_CLOSE_DECISION
```

## 32.3. Defense in depth

`AlgorithmWorkspaceController.delete_workspace()` повторно перевіряє guard.

Програмний виклик не може обійти UI-захист.

---

# 33. Session restore

## 33.1. Канонічний перехід

```text
loaded configuration state = RESTORED
volatile runtime state      = STOPPED
```

## 33.2. Відновлюється

1. workspace order;
2. active workspace;
3. geometry;
4. normal/minimized/maximized;
5. active panel;
6. data mode;
7. control mode;
8. Replay speed;
9. Replay source;
10. Replay time range;
11. algorithm parameters;
12. risk settings;
13. profit protection;
14. history download settings;
15. public broker account name.

## 33.3. Не запускається автоматично

1. algorithm;
2. Replay session;
3. market feed;
4. broker operation;
5. AUTO execution;
6. reconnect від manual-disconnected intent.

---

# 34. WSP Chart

## 34.1. Канонічний шлях

```text
WorkspaceRuntime
    -> WorkspaceChartModel
    -> WorkspaceChartSnapshot
    -> WorkspaceChartWidget
```

Chart не читає broker API напряму.

## 34.2. Реалізовано

1. OHLC candles і wick;
2. price/time axes;
3. current bid/ask;
4. Replay/live cursor;
5. horizontal navigation і scrollbar;
6. Home/End/Latest;
7. zoom і follow-latest;
8. crosshair;
9. synchronized MACD panel;
10. Alligator overlay;
11. profile metadata;
12. causal higher-timeframe series;
13. compact Replay status/layout;
14. splitter-based chart/panel layout;
15. current-bar replacement/new-bucket append;
16. preservation during `WAIT_BROKER`/invalid quote/Stop.

## 34.3. Full history + bounded retained buffer

Канонічні constants:

```text
DEFAULT_WORKSPACE_CHART_MAX_EVENTS = 2000
DEFAULT_WORKSPACE_CHART_VISIBLE_EVENTS = 120
MIN_WORKSPACE_CHART_VISIBLE_EVENTS = 12
MAX_WORKSPACE_CHART_VISIBLE_EVENTS = 500
```

`events` у render tail залишаються bounded, але Replay session може бути attached як immutable full history. Viewport працює по всій уже обробленій історії без відкриття future bars.

Підтверджено:

```text
Home -> first processed Replay bar
End/Latest -> last processed bar
middle history accessible
future events hidden
retained render buffer bounded
```

## 34.4. Indicator rendering

MACD panel показує фактичні series активного MACD profile та синхронізується з price viewport.

Alligator overlay показує Jaws/Teeth/Lips; для higher timeframe point має causal `available_at`, тому майбутня higher bar не малюється назад у минуле.

Disabled MACD source або Alligator filter приховує відповідну series без зміни історичних market events.

## 34.5. Ще не завершено

1. повний production-набір signal/order/position markers;
2. complete SL/TP visual lifecycle;
3. спеціалізований RoadMap98 diagnostics overlay MFE/MAE.

---

# 35. Algorithm Parameters і Indicator Profiles

## 35.1. Designer UI

Параметри WSP редагуються через Designer-based dialogs/tree, не через ad-hoc runtime widgets.

## 35.2. Parameter groups

Система розділяє щонайменше:

1. MACD source enable/mode;
2. Alligator filter enable/confirmation mode;
3. indicator profile bindings;
4. runtime spread/warm-up requirements;
5. risk settings;
6. Replay profit protection.

## 35.3. MACD

Поточні mode values:

```text
LINEAR
EXTENDED
```

`LINEAR` має deterministic Replay implementation. Розширені правила `EXTENDED` не вважаються завершеним production signal logic і є предметом RoadMap98.

Канонічний complete built-in MACD baseline:

```text
source=Close
fast=12
slow=26
signal=9
oscillator MA=EMA
signal MA=EMA
shift=0
```

## 35.4. Alligator

Confirmation modes:

```text
SAME_TIMEFRAME
HIGHER_1
HIGHER_2
DISABLED
```

`HIGHER_2` — експериментальний і не default. Higher mappings задаються явними таблицями; unavailable pair блокується без silent fallback.

Вбудовані complete profiles містять LGE Classic і cTrader Default; профіль binding зберігає `profile_uid`, exact revision і resolved snapshot.

## 35.5. Profile lifecycle

1. built-in profile не видаляється й не архівується;
2. unused user profile може бути фізично видалений;
3. persisted binding блокує delete;
4. bound user profile можна archive без руйнування persisted WSP snapshot;
5. incomplete reference profile не можна bind;
6. profile UID/revision входять до explainable signal record.

## 35.6. Risk / profit defaults

Поточний canonical baseline включає risk model із percent risk, maximum volume/open positions, daily-loss guard та stop-loss-required policy. Replay initial balance задається окремо в Replay settings; default `1000 USD`, valid range `100..100000 USD`.

Profit drawdown close percent має range `1..100`, default `30`.

## 35.7. Зберігання і блокування

```text
workspace.parameters
workspace.risk_settings
workspace.profit_protection
workspace.indicator_profile_bindings
```

Unknown future keys не видаляються. Редагування параметрів дозволено лише у `STOPPED/RESTORED`; active runtime read-only.

---

# 36. Broker account binding і connection UI

## 36.1. WSP binding

WSP зберігає stable `account_id` і public account label.

При disconnect:

1. `account_id` не стирається;
2. public account name не замінюється технічним placeholder;
3. WSP може показати, який account він очікує.

## 36.2. cTrader account selection

Connection dialog після завантаження account list відновлює пріоритетно:

1. поточний selection діалогу;
2. збережений `account_id`;
3. fallback selection лише коли попередній account відсутній.

Порядок account rows не повинен впливати на restore.

Підтверджено:

```text
saved_account_restored=True
current_dialog_selection_restored=True
account_order_independent=True
```

## 36.3. Close semantics

У connection dialogs і Settings використовуються різні дії:

1. `Гаразд` — прийняти поточний стан;
2. `Застосувати` — застосувати Settings;
3. `Закрити` — закрити діалог без значення «скасувати вже виконане broker connect/disconnect».

`Скасувати` не повинно вводити в оману після того, як broker operation уже виконано.

---

# 37. Локалізація WSP

## 37.1. `strings.json`

`lang/strings.json` вручну не редагується, крім рідкісного окремо погодженого випадку.

Нові keys реєструються через:

```python
LangManager.tr(...)
```

Потім запускається:

```text
dev_tools/rebuild_fallback.py
```

## 37.2. Очікуваний `strings.json`

```json
{
  "lang_active": {
    "code": "uk"
  }
}
```

## 37.3. Fallback

Якщо DeepL не дав переклад, використовується English text.

Не допускаються:

1. blank translation;
2. partial key;
3. випадкове залишення старого неправильного перекладу;
4. ручне накопичення keys у `strings.json`.

## 37.4. Translation policy

Централізована policy підтримує:

1. prefix context;
2. glossary context;
3. Polish glossary context;
4. centralized overrides;
5. regular `tr()` calls;
6. WSP UI overrides;
7. Replay dialog overrides;
8. History Download dialog overrides;
9. broker connection `Close` overrides;
10. Settings `Close` override;
11. DeepL context payload;
12. context-aware cache.

## 37.5. Technical identity

Technical values не перекладаються в storage:

```text
RUNNING
WAIT_BROKER
WAIT_SPREAD
BROKER_DISCONNECTED
```

UI перекладає їх через `LangManager`.

---

# 38. Канонічна карта модулів

## 38.1. WSP configuration і MDI

```text
core/algorithm_workspace.py
core/algorithm_workspace_catalog.py
core/algorithm_workspace_controller.py
core/algorithm_workspace_area.py
```

## 38.2. Runtime і market data

```text
core/workspace_runtime.py
core/workspace_replay.py
core/workspace_market_event.py
core/workspace_broker_market.py
core/workspace_ownership.py
```

## 38.3. Historical data

```text
core/workspace_history.py
core/workspace_history_export.py
core/workspace_replay_settings.py
core/workspace_history_download_settings.py
core/algorithm_workspace_history_download_dialog.py
engine/ctrader_history.py
engine/ib_history.py
```

## 38.4. Algorithm decisions

```text
core/workspace_algorithm.py
core/workspace_signal.py
core/workspace_profit_guard.py
core/workspace_close_guard.py
```

## 38.5. Chart

```text
core/workspace_chart.py
core/workspace_chart_widget.py
```

## 38.6. Parameters

```text
core/workspace_parameters.py
core/algorithm_workspace_parameters_dialog.py
ui/algorithm_workspace_parameters_dialog.ui
ui/ui_algorithm_workspace_parameters_dialog.py
```

## 38.7. Broker coordinator

```text
engine/runtime_engine.py
engine/services/ctrader_runtime_service.py
engine/services/ib_runtime_service.py
engine/ctrader_session_manager.py
engine/ib_session_manager.py
```

## 38.8. Constants

```text
engine/runtime_constants.py
```

---

# 39. Підтверджені runtime checks після RoadMap97

## 39.1. Session / MDI / restore / shutdown

Покриті `catalog`, `session`, `area`, `restore`, `close_guard`, `shutdown` checks.

Підтверджено independent workspaces, layout/geometry restore, automatic-start block, volatile runtime clear і контрольований shutdown.

## 39.2. Replay / history / speed

Покриті market-event, Replay, Historical CSV, settings, history download, Replay speed і full-history chart checks.

Підтверджено:

```text
1x,2x,5x,10x,100x,1000x,MAX
MAX deterministic and responsive between bounded batches
Pause/Step deterministic
atomic history export
full processed history navigation
broker_requests=0
```

## 39.3. Risk і Replay account

Покриті risk model/settings/account snapshot, signal-risk, historical Replay risk і Replay account checks.

Підтверджено deterministic risk decisions, synthetic historical account snapshot, configurable initial Replay balance, live balance/equity/closed/open PnL та відсутність broker execution.

## 39.4. MACD / Alligator / profiles

Покриті MACD Replay, SAME_TIMEFRAME, HIGHER_1, HIGHER_2, profile model/lifecycle/runtime/UI і timeframe mapping/aggregation checks.

Підтверджено:

```text
MACD deterministic
Alligator SAME/H1/H2 deterministic
completed higher bars only
no look-ahead
future change does not alter past
unavailable pair blocked without fallback
profile UID/revision snapshot
```

## 39.5. Replay virtual execution

`run_algorithm_workspace_replay_virtual_execution_check.py` підтвердив:

```text
MANUAL signals visible / no virtual execution
AUTO virtual execution enabled
entry policy = NEXT_BAR_OPEN
SL = signal-bar range 1R
TP = signal-bar range 2R
ambiguous OHLC bar = STOP_LOSS_FIRST
PROFIT_DRAWDOWN supported
SESSION_END supported
all virtual positions closed at completion
broker_requests=0
broker_execution_attempted=False
```

Order close reason і Replay position presentation мають окремі regression checks.

## 39.6. Chart / Signals UI

Покриті MACD panel, Alligator overlay, navigation, crosshair, compact layout/status, signal table/layout/localization і Replay terminology checks.

Підтверджено synchronized viewport, causal higher overlay, full-cell tooltips, localized reason text та technical identity preservation.

## 39.7. Live Read-only / broker lifecycle

Підтверджені cTrader/IB Live Read-only, market-data subscription accounting, transient disconnect recovery, cTrader startup readiness/autoconnect/late-connect/retired-session/reconnect regression.

## 39.8. External exposure safety

Окремі checks підтвердили external exposure alert і `SAFETY_HOLD_EXTERNAL_EXPOSURE`: market data продовжується, signals блокуються, current broker evidence очищує hold, fresh spread required.

---

# 40. Реальна Live Read-only перевірка

## 40.1. Сценарій

У LGE одночасно працювали два незалежні WSP:

```text
CTRADER EURUSD M15 — RailAlgorithm
IB GBPUSD M15 — RailAlgorithm
```

## 40.2. Підтверджено в UI

1. обидва WSP перейшли у `RUNNING`;
2. обидва отримували live candles;
3. cTrader і IB charts оновлювалися незалежно;
4. broker balances відображалися;
5. journal фіксував Live Read-only start;
6. Stop одного WSP не зупиняв інший;
7. Tile і Cascade не ламали runtime;
8. maximize після Tile і Cascade працював;
9. manual broker disconnect переводив WSP у waiting state;
10. reconnect відновлював subscription;
11. chart продовжувався після reconnect;
12. обидва WSP після перевірок знову працювали одночасно.

## 40.3. Фінальна regression 2026-07-29

Успішно пройшли:

```text
RUNTIME_BROKER_HEALTH_CHECK=OK
RUNTIME_RECONNECT_TASK_CHECK=OK
RUNTIME_ENGINE_WORKSPACE_MARKET_DATA_CHECK=OK
TRANSLATION_POLICY_CHECK=OK
ALGORITHM_WORKSPACE_LIVE_READONLY_CHECK=OK
ALGORITHM_WORKSPACE_MDI_AREA_CHECK=OK
```

Фінальний LGE запуск підтвердив одночасну роботу cTrader EURUSD M15 та IB GBPUSD M15 у Live Read-only.

---

# 41. Непорушні safety rules

1. WSP не працює напряму з broker adapter.
2. Реальні broker operations можуть проходити тільки через RuntimeEngine canonical chain.
3. Replay virtual execution ніколи не перетворюється на broker request.
4. `broker_execution_attempted=False` є обов’язковим для Historical Replay regression.
5. Configuration не змішується з volatile runtime state.
6. Runtime після restart починається зі `STOPPED`.
7. `AUTO` не означає дозвіл обходити guards.
8. Warm-up, spread, risk і safety holds мають пріоритет над signal proposal.
9. Higher-timeframe indicators використовують лише causal completed bars.
10. No-look-ahead і deterministic Replay не можна послаблювати заради UI або performance.
11. Broker disconnect не є автоматичною runtime-помилкою.
12. `WAIT_BROKER`/safety hold блокують signals, але не повинні псувати останній valid chart.
13. Після reconnect потрібен fresh live spread.
14. Invalid live quote ігнорується.
15. Position/order ownership визначається exact binding.
16. External exposure не привласнюється WSP без exact evidence.
17. Parameters/profile bindings не змінюються під час active runtime.
18. Manual disconnect не запускає auto-reconnect.
19. Stop одного WSP не зупиняє інший.
20. Subscription accounting reference-counted/deduplicated.
21. Historical CSV записується атомарно.
22. Missing/invalid history не має silent synthetic fallback.
23. User text локалізується, technical identity залишається language-independent.
24. `strings.json` вручну не накопичує переклади; нормальний шлях — translation registry/fallback rebuild.
25. Будь-який вихід із LGE проходить єдиний контрольований shutdown.
26. OrdersPage і підтверджені IB/cTrader Open/Close/SL/TP chains не переписуються WSP-шаром без окремого етапу.

---

# 42. Історичний snapshot обмежень baseline після RoadMap97

## 42.1. Реальний execution

WSP у `BROKER` mode не створює, не змінює і не закриває broker orders. Replay virtual execution існує окремо і не є broker execution.

## 42.2. Historical analytics

Ще немає канонічного RoadMap98 Baseline Report, MFE/MAE diagnostics, comparison table та train/validation/test pipeline.

## 42.3. MACD

Deterministic MACD source працює; завершена `EXTENDED` signal logic ще не зафіксована.

## 42.4. Chart trade annotations

MACD panel і Alligator overlay реалізовані. Повний production-набір signal/order/position/SL/TP markers ще не завершений.

## 42.5. Historical spread

Якщо CSV не має factual bid/ask/spread, Replay використовує deterministic configured spread; це не відтворює історичну змінність broker spread.

## 42.6. M1 -> M15 multi-resolution Replay

Automatic source resampling зараз відсутній. M1 CSV не можна просто запускати як M15 WSP. Окремий multi-resolution mode планується в RoadMap98 після baseline mathematics/diagnostics.

## 42.7. Intrabar ambiguity

При одному OHLC bar, який одночасно торкнувся SL і TP, Replay baseline використовує deterministic `STOP_LOSS_FIRST`. Точніша хронологія потребує finer source timeframe або tick data.

## 42.8. Backtest / Paper / Live

Fast batch `BACKTEST` engine не реалізований. Paper і Live algorithm execution через broker не дозволені.

---

# 43. Історичний план RoadMap98, за яким виконано Historical Algorithm Improvement

Після RoadMap97 не оптимізуємо параметри одразу. Канонічний цикл:

```text
виміряли
    -> знайшли слабке місце
    -> змінили ОДНУ річ
    -> повторили той самий Replay
    -> порівняли результат
```

Порядок RoadMap98:

1. Historical Replay Baseline Metrics/Report;
2. Replay execution mathematics і leverage/margin model `1:500`;
3. trade diagnostics MFE/MAE;
4. final Historical Summary UI;
5. MACD без Alligator vs SAME_TIMEFRAME vs HIGHER_1 vs HIGHER_2;
6. profit drawdown experiments;
7. SL/TP geometry experiments;
8. MACD logic improvement;
9. TRAIN / VALIDATION / TEST anti-overfitting;
10. multi-period regression;
11. performance profiling/optimization;
12. documentation.

Після blocks 1–4 доцільно вставити окремий quality-of-measurement package:

```text
RoadMap98_04A
M1 source -> M15 strategy + finer execution chronology
```

Він не повинен змінювати торгову логіку; його мета — точніший historical execution stand.

---

# 44. Історичний канон після RoadMap97

```text
Session configuration
    -> AlgorithmWorkspaceController
    -> volatile WorkspaceRuntime
    -> Replay або broker market provider
    -> canonical WorkspaceMarketEvent
    -> component warm-up / WAIT_BROKER / spread / risk / safety guards
    -> MACD signal source
    -> optional Alligator confirmation
    -> WorkspaceSignalRecord
    -> Replay virtual execution only when REPLAY + AUTO
    -> WSP journal / chart / Signals / Orders / Positions
```

Поточна boundary:

```text
WSP Session і MDI                       = IMPLEMENTED
Synthetic Replay                        = IMPLEMENTED
Historical CSV Replay                   = IMPLEMENTED
Replay speeds through MAX               = IMPLEMENTED
Full processed-history chart navigation = IMPLEMENTED
MACD calculation + chart panel           = IMPLEMENTED
Alligator SAME/H1/H2 + overlay           = IMPLEMENTED
Indicator profiles/revisions             = IMPLEMENTED
Risk model/settings                      = IMPLEMENTED
Replay virtual account                   = IMPLEMENTED
Replay virtual order/position lifecycle  = IMPLEMENTED
SL/TP/profit-drawdown close reasons      = IMPLEMENTED
Localized Signals/Orders/Positions       = IMPLEMENTED
cTrader/IB Live Read-only                = IMPLEMENTED AND REAL-TESTED
WAIT_BROKER/reconnect                    = IMPLEMENTED AND REAL-TESTED
cTrader readiness/event waits            = IMPLEMENTED AND TESTED
External exposure safety hold            = IMPLEMENTED AND TESTED
Controlled application shutdown          = IMPLEMENTED AND TESTED
Broker execution from WSP                = NOT IMPLEMENTED
Paper algorithm broker execution         = NOT IMPLEMENTED
Live algorithm broker execution          = NOT IMPLEMENTED
RoadMap98 baseline analytics              = NEXT
M1 -> M15 multi-resolution Replay        = PLANNED, NOT IMPLEMENTED
```

`LGE_Runtime_06.md` на цьому місці зберігає історичний snapshot перед RoadMap98. Актуальний канон після RoadMap98–99 зафіксований нижче.

---

# 45. RoadMap98 — Historical Algorithm Improvement, виконаний baseline

## 45.1. Метод роботи

RoadMap98 зафіксував принцип:

```text
виміряли
    -> змінили ОДНУ річ
    -> повторили той самий Replay
    -> порівняли результат
```

Оптимізація кількох параметрів одночасно не є канонічним способом розвитку алгоритму.

## 45.2. Historical Replay metrics

Побудовано deterministic Historical Baseline Report з метриками:

1. trades;
2. winners / losers;
3. win rate;
4. gross profit / gross loss;
5. net PnL;
6. average trade;
7. profit factor;
8. maximum drawdown USD / %;
9. close reasons;
10. deterministic duplicate-trade protection.

Historical Summary формується з фактів завершеного Replay і показується в UI після completion.

## 45.3. Replay leverage і margin

Historical Replay використовує канонічне кредитне плече:

```text
1:500
```

Правило:

1. leverage не множить PnL;
2. leverage впливає на required/used/free margin;
3. BUY використовує ask-side execution semantics;
4. SELL використовує bid-side execution semantics;
5. spread cost входить у Replay economics;
6. insufficient free margin блокує virtual position;
7. після close used margin звільняється;
8. `broker_execution_attempted=False`.

Для DEMO/LIVE фіксоване Replay leverage не використовується; коли буде broker execution integration, margin/leverage має братися з broker facts.

## 45.4. Historical Trade Diagnostics

Для закритих virtual trades зберігаються:

1. timestamps;
2. direction;
3. indicator state;
4. Alligator timeframe;
5. SL/TP distance;
6. MFE;
7. MAE;
8. peak profit;
9. final realized profit;
10. close reason;
11. holding time.

MFE/MAE і peak profit не змішуються в одну величину.

## 45.5. M1 -> M15 multi-resolution Replay

RoadMap98 реалізував production historical path:

```text
M1 CSV source
    -> deterministic aggregation
    -> completed M15 strategy bars
    -> MACD / Alligator signal logic
    -> M1 chronology for virtual execution
```

Ключові правила:

1. незавершений M15 bucket не використовується як completed strategy bar;
2. MACD формується тільки з completed M15 bars;
3. M1 не використовується для підглядання всередину майбутнього M15 signal bar;
4. execution chronology після signal може використовувати finer M1 source;
5. no-look-ahead зберігається;
6. Replay залишається deterministic.

На RoadMap99 development dataset:

```text
source_rows=58320
completed_m15_bars=3888
```

## 45.6. NEXT_BAR_OPEN gap policy

Канонічний virtual-order policy:

```text
NEXT_BAR_OPEN
```

Потрібен саме очікуваний наступний M15 bar. Якщо його немає, order не переноситься довільно через gap/weekend і переходить у:

```text
EXPIRED_NEXT_BAR_GAP
```

Expired order звільняє capacity і не створює virtual position.

## 45.7. Alligator mode comparison

Підтримуються незалежні режими confirmation:

```text
DISABLED
SAME_TIMEFRAME
HIGHER_1
HIGHER_2
```

HIGHER_1/HIGHER_2 використовують тільки causal completed higher bars. Alligator не є частиною MACD source; це окремий confirmation component.

## 45.8. RoadMap98 відхилені MACD experiments

Експерименти MACD Strength і MACD Zero-Line були діагностичними та відхилені.

Production MACD після цих experiments не змінювався до RoadMap99.

---

# 46. RoadMap99 — MACD Crossover Quality

## 46.1. Канонічний classic crossover

Для completed M15 bar `t`:

```text
H[t] = MACD[t] - Signal[t]
```

BUY:

```text
H[t-1] <= 0
H[t] > 0
```

SELL:

```text
H[t-1] >= 0
H[t] < 0
```

Сам факт classic crossover не був замінений іншою signal source логікою.

## 46.2. Extremum search

Після crossover шукається попередній histogram extremum:

```text
3 -> 5 -> 7
```

Це послідовний пошук, а не три незалежні режими.

BUY шукає локальний minimum, SELL — локальний maximum.

Якщо придатного extremum немає навіть у window 7, quality criterion не проходить.

## 46.3. Production quality parameters

У WSP parameter schema і UI заведено:

```text
MACD_EXTREMUM_MIN_PROMINENCE         = 0.00001
MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE = 0.00005
MACD_CROSS_MIN_ANGLE                 = 45 degrees
```

У UI small-float values показуються fixed-decimal:

```text
0.000010
0.000050
```

а не scientific notation.

## 46.4. Extremum prominence

BUY minimum:

```text
H[e] < H[e-1]
H[e] <= H[e+1]
```

SELL maximum — дзеркально.

Prominence є deterministic numeric property histogram і не залежить від chart pixels.

## 46.5. Extremum-to-cross distance

Для crossover target `H == 0`, тому production distance criterion використовує:

```text
abs(H[extremum]) >= threshold
```

Це означає: перед crossover MACD і Signal повинні були достатньо розійтися.

## 46.6. Effective crossover angle

Кут не вимірюється з pixels під час Replay.

Він визначається як calibrated angle між напрямками MACD і Signal на completed M15 steps.

Manual calibration RoadMap99 використала візуальний reference:

```text
2026-01-09 14:15 UTC SELL ~= 45 degrees
```

Канонічна calibration scale:

```text
MACD_CROSS_45_Y_PER_M15_BAR = 0.0000535
```

Контрольні cases після calibration:

```text
2026-01-05 09:30 SELL  ~= 40.68 deg
2026-01-05 14:15 BUY   ~= 41.89 deg
2026-01-09 14:15 SELL  ~= 45.01 deg  <- visual reference
2026-01-07 17:30 BUY   ~= 10.88 deg  <- known weak
```

Однакові numerical data завжди дають однаковий effective angle незалежно від chart zoom/autoscale.

## 46.7. Production MACD Quality mode

Канонічне розділення signal modes:

```text
LINEAR   = classic crossover baseline
EXTENDED = classic crossover + MACD Quality
```

EXTENDED пропускає candidate тільки коли одночасно істинні:

```text
CLASSIC CROSS
AND extremum found
AND prominence >= threshold
AND distance >= threshold
AND effective angle >= threshold
```

MACD Quality і Alligator залишаються двома незалежними компонентами:

```text
MACD Quality candidate
    -> optional Alligator confirmation
    -> risk
    -> Replay virtual execution
```

## 46.8. Reason codes

Production reason identity:

```text
MACD_CROSS_ACCEPTED
MACD_EXTREMUM_NOT_FOUND
MACD_EXTREMUM_TOO_WEAK
MACD_EXTREMUM_DISTANCE_TOO_SMALL
MACD_CROSS_TOO_FLAT
```

Signals зберігає technical code і localized user-facing reason/tooltip.

## 46.9. Development dataset RoadMap99

Канонічний швидкий development period:

```text
2026-01-02 -> 2026-02-28
source timeframe   = M1
strategy timeframe = M15
initial balance    = 1000 USD
Replay leverage    = 1:500
```

На цьому dataset:

```text
classic_crosses = 320
BUY/SELL        = 160/160
```

При defaults:

```text
MACD Quality accepted = 23
MACD Quality rejected = 297
```

Reject reasons:

```text
EXTREMUM_NOT_FOUND          = 74
EXTREMUM_TOO_WEAK           = 133
EXTREMUM_DISTANCE_TOO_SMALL = 49
CROSS_TOO_FLAT              = 41
```

Angle distribution після calibration:

```text
<10     = 10
10-20   = 67
20-30   = 65
30-40   = 86
40-45   = 46
45-50   = 18
50-60   = 23
>=60    = 5
```

---

# 47. Formal LINEAR / EXTENDED / EXTENDED+ALLIGATOR baseline

## 47.1. Controlled comparison

RoadMap99_02E/02G зафіксував формальний comparison на одному dataset і з однаковими execution/risk/exit policies.

Controlled variable:

```text
MACD_SIGNAL_PIPELINE_STAGE
```

Незмінні умови:

```text
same M1 dataset              = True
same Replay period           = True
same risk policy             = True
same profit drawdown policy  = True
same SL/TP policy            = True
Replay leverage              = 1:500
broker execution             = 0
```

## 47.2. LINEAR baseline

```text
signals=320
quality=0/0
alligator=0/0
trades=304
W/L=120/184
win_rate=39.47%
net_pnl=-53.48 USD
profit_factor=0.29
max_dd=53.72 USD / 5.37%
average_trade=-0.1759 USD
SL/TP/ProfitDrawdown/SessionEnd=50/0/254/0
expired_gap=2
missed_moves=0
```

## 47.3. EXTENDED — MACD Quality only

```text
signals=320
quality=23/297
alligator=0/0
trades=23
W/L=10/13
win_rate=43.48%
net_pnl=-7.80 USD
profit_factor=0.28
max_dd=7.80 USD / 0.78%
average_trade=-0.3391 USD
SL/TP/ProfitDrawdown/SessionEnd=8/0/15/0
expired_gap=0
missed_moves=115
```

Висновок baseline: MACD Quality різко зменшив кількість trades і drawdown, але ще не дав позитивного expectancy.

## 47.4. EXTENDED + Alligator SAME_TIMEFRAME

```text
signals=320
quality=23/297
alligator=1/22
trades=1
W/L=1/0
win_rate=100.00%
net_pnl=+0.03 USD
profit_factor=N/A
max_dd=0.00 USD / 0.00%
average_trade=+0.0300 USD
SL/TP/ProfitDrawdown/SessionEnd=0/0/1/0
expired_gap=0
missed_moves=125
```

Це перший positive balance RoadMap99, але одна угода не є достатньою статистикою для висновку про прибутковість системи.

## 47.5. Missed move diagnostics

RoadMap99 formal comparison використовує:

```text
quality_horizon_bars = 8 M15 bars
minimum_directional_move = 0.00020
```

`MISSED_MOVE` означає: signal/filter відхилив candidate, але протягом diagnostic horizon ринок усе-таки пройшов мінімальний рух у напрямку candidate.

Missed moves є діагностикою opportunity cost, а не trading signal і не приводом автоматично послаблювати фільтр.

---

# 48. RoadMap99 WSP diagnostic UI

## 48.1. Historical Replay Summary

Summary показує MACD Quality:

```text
accepted / rejected
N / W / D / F reject counters
```

де:

```text
N = extremum not found
W = extremum too weak
D = distance too small
F = cross too flat
```

## 48.2. Journal

Journal має:

1. Category filter;
2. Level filter;
3. text search.

Text search може використовувати technical identity, наприклад:

```text
MACD_CROSS_TOO_FLAT
PROFIT_DRAWDOWN
RPL-POS-...
```

## 48.3. Signals

Signals має filters:

```text
Result    = All / Accepted / Rejected
Direction = All / BUY / SELL
Reason    = dynamic actual reason list
```

Reason display локалізований; technical reason code зберігається для diagnostics.

## 48.4. Positions

Positions має filters:

```text
PnL       = All / Profit + / Loss - / Zero
Reason    = close reason
Direction = All / BUY / SELL
Status    = All / Open / Closed
```

## 48.5. Orders

Orders має filters:

```text
Status
Direction
PnL sign
Reason
```

Orders table потрібна для virtual-order lifecycle diagnostics, зокрема щоб відрізняти `FILLED` від `EXPIRED_NEXT_BAR_GAP`.

## 48.6. Незакритий cosmetic UI issue

Після збільшення vertical space в Parameters WSP основна частина дерева стала зручнішою, але при деяких scroll positions наступний нижній row ще може бути частково видимий/обрізаний на межі viewport.

Це cosmetic issue, не runtime/safety defect. Він залишається pending окремим UI-polish кроком.

---

# 49. cTrader reconnect guard після RoadMap99_02F

## 49.1. Проблема

Реальна мережа до:

```text
demo.ctraderapi.com:5035
```

може бути нестабільною. Спостерігалися два класи відмов:

```text
cTrader host unreachable
TIMEOUT: cTrader auth not completed
```

Token refresh не може виправити `host unreachable`, бо це failure до OAuth/application authorization.

## 49.2. Adaptive backoff

Після невдалих cTrader reconnect attempts використовується:

```text
failure #1 -> 60 s
failure #2 -> 120 s
failure #3+ -> 300 s
```

Backoff рахується після завершення failed attempt.

Успішний reconnect скидає failure count.

IB lifecycle цим backoff не змінюється.

## 49.3. Real check

Після впровадження guard реальний LGE запуск показав:

```text
startup cTrader failed
reconnect #1 failed
backoff 60 seconds
reconnect #2 successful
cTrader connection restored
```

Отже reconnect guard працює в реальному LGE і не заважає автоматичному recovery.

## 49.4. Auth-stage diagnostics

При auth timeout діагностика повинна показувати stage, наприклад:

```text
APPLICATION_AUTH
ACCOUNT_LIST
ACCOUNT_AUTH
TRADER
ASSET_LIST
```

щоб відрізняти network reachability від конкретного OpenAPI authorization/data-loading stage.

---

# 50. Поточний канон після завершення RoadMap99

RoadMap99 завершив експериментальний цикл MACD Crossover Quality і підготував production-ready foundation для чесного відбору MACD у RoadMap100.

Канонічний historical pipeline на виході RoadMap99:

```text
Historical M1 source
    -> completed M15 strategy bars
    -> classic MACD crossover
    -> MACD mode
       LINEAR
       або
       EXTENDED
           -> extremum search 3 -> 5 -> 7
           -> prominence
           -> extremum-to-cross distance
           -> angle model
              LEGACY_CALIBRATED
              або
              ABC_REALTIME_SCALED
    -> optional Alligator SAME_TIMEFRAME / HIGHER_1 / HIGHER_2
    -> warm-up / spread / risk / safety guards
    -> Replay virtual order
    -> NEXT_BAR_OPEN / EXPIRED_NEXT_BAR_GAP
    -> M1 execution chronology
    -> virtual position
    -> SL / TP / Profit Drawdown / Session End
    -> Orders / Positions / Signals / Journal
    -> Historical Summary / diagnostics / comparison
```

Поточна boundary:

```text
WSP Session і MDI                         = IMPLEMENTED
Synthetic Replay                          = IMPLEMENTED
Historical CSV Replay                     = IMPLEMENTED
M1 -> M15 multi-resolution Replay         = IMPLEMENTED
Replay leverage/margin 1:500              = IMPLEMENTED
Historical metrics / summary              = IMPLEMENTED
MFE/MAE trade diagnostics                 = IMPLEMENTED
Replay virtual execution                  = IMPLEMENTED
NEXT_BAR_OPEN gap expiry                  = IMPLEMENTED
MACD classic LINEAR                       = IMPLEMENTED
MACD Quality EXTENDED                     = IMPLEMENTED
Extremum 3 -> 5 -> 7                      = IMPLEMENTED
Prominence / distance filters             = IMPLEMENTED
LEGACY calibrated angle                   = IMPLEMENTED
ABC realtime-scaled angle                 = IMPLEMENTED
Custom MACD profiles/revisions            = IMPLEMENTED
Exact profile revision binding            = IMPLEMENTED
Alligator SAME/H1/H2                      = IMPLEMENTED
Signal/Entry navigation                   = IMPLEMENTED
Formal pipeline/profile diagnostics       = IMPLEMENTED
Journal/Signals/Positions/Orders filters  = IMPLEMENTED
Full processed-history chart navigation   = IMPLEMENTED
cTrader/IB Live Read-only                 = IMPLEMENTED AND REAL-TESTED
cTrader reconnect adaptive backoff        = IMPLEMENTED AND REAL-TESTED
External exposure safety hold             = IMPLEMENTED AND TESTED
Controlled application shutdown           = IMPLEMENTED AND TESTED
Broker execution from WSP                 = NOT IMPLEMENTED
Paper algorithm broker execution          = NOT IMPLEMENTED
Live algorithm broker execution           = NOT IMPLEMENTED
Parameters lower-row cosmetic polish      = PENDING
RoadMap100 production selection           = NEXT
```

Непорушні Historical Replay invariants після RoadMap99:

```text
no look-ahead
only completed strategy bars
signal_timestamp != NEXT_BAR_OPEN entry_timestamp
M1 chronology after signal
broker_requests = 0
broker_execution_attempted = False
Replay leverage = 1:500
```

---

# 51. RoadMap99_03–04K — parameter diagnostics, profile comparison і ABC production geometry

## 51.1. Controlled parameter principle

RoadMap99 після baseline 02G продовжився за правилом:

```text
measure
-> change ONE variable
-> same Replay
-> compare
```

Одночасна оптимізація prominence, distance, angle, Alligator, Profit Drawdown і risk заборонена.

Параметри MACD Quality не трактуються як універсальні константи. Їх допустимі значення залежать від instrument / timeframe / volatility / regime.

## 51.2. Development dataset

Основний development horizon RoadMap99:

```text
EURUSD
M1 historical source
M15 strategy bars
2026-01-02 -> 2026-02-28
```

Canonical defaults для фінальних RoadMap99 diagnostics:

```text
prominence = 0.000005
distance   = 0.000050
ABC angle  = 2.00 degrees
```

`2.00°` є лише experimental reference для RoadMap100, а не універсальною production-константою.

## 51.3. Legacy calibrated angle

Manual visual calibration за reference SELL `2026-01-09 14:15` дала:

```text
manual_calibrated_45_y_per_m15_bar = 0.00005350
```

Після калібрування historical pass показав:

```text
classic crosses          = 320
MACD Quality accepted    = 23
MACD Quality rejected    = 297
```

Manual acceptance cases підтвердили, що calibrated legacy angle відтворює обраний візуальний reference приблизно як `45°`.

Legacy модель зберігається для backward compatibility старих WSP, але більше не є єдиною production angle geometry.

## 51.4. ABC_REALTIME_SCALED

RoadMap99 ввів нову production angle model:

```text
LEGACY_CALIBRATED
ABC_REALTIME_SCALED
```

Для ABC:

```text
X = real UTC elapsed time in minutes
Y = indicator value * instrument price scale
C = interpolated MACD/Signal crossover
angle = ∠ACB
```

Instrument price scale:

```text
EURUSD / non-JPY Forex = 10000
JPY Forex pairs        = 100
unknown instrument     = fail closed
```

ABC threshold є окремим parameter value і не використовує legacy `45°`.

Backward compatibility:

```text
missing angle-model in legacy WSP
    -> LEGACY_CALIBRATED
```

## 51.5. Custom MACD profiles

RoadMap99 довів exact profile binding і custom revisions для щонайменше трьох робочих profiles:

```text
12 / 26 / 9 = baseline
8 / 17 / 5  = FAST
6 / 13 / 4  = VERY_FAST
```

WSP зберігає точний `profile_uid` і `profile_revision`; Replay snapshot також повинен бути прив'язаний до exact revision.

RoadMap99 не обирав один profile як остаточно найкращий. Це свідомо перенесено в RoadMap100.

## 51.6. ABC cross-profile result

RoadMap99 comparison показав, що ABC_REALTIME_SCALED геометрично значно стабільніший між MACD profiles, ніж legacy calibrated `45°`.

Водночас raw prominence + distance для EURUSD M15 уже давали близьку cross-profile selectivity. Тому naive histogram normalization не дала достатнього покращення і була відхилена.

Рішення:

```text
не нормалізувати MACD Quality лише заради однакових histogram magnitudes;
зберегти raw prominence + raw distance;
angle geometry винести в ABC realtime-scaled model.
```

## 51.7. MACD latency comparison

RoadMap99 окремо порівнював MACD profiles за latency від price-turn proxy.

Висновок не зводиться до PnL:

1. швидші MACD можуть зменшувати signal latency;
2. одночасно вони можуть збільшувати candidate density і noise;
3. production selection має враховувати latency, structural selectivity, BUY/SELL symmetry, MFE/MAE і stability між часовими ділянками;
4. WR/PF/PnL/DD є secondary metrics, а не єдиним критерієм.

Це стало прямим входом у RoadMap100.

## 51.8. Lower-timeframe Alligator diagnostic

RoadMap99 окремо перевіряв lower-timeframe Alligator і не отримав переконливого доказу production selectivity для M5/M1 схеми.

Тому canonical production directions на виході RoadMap99:

```text
OFF
SAME_TIMEFRAME
HIGHER_1
HIGHER_2
```

M5/M1 Alligator не повертати в production без нових доказів.

## 51.9. Signal / Entry navigation

Для manual diagnostics додано розділення:

```text
До сигналу
До входу
```

Це закріплює причинний контракт:

```text
signal_timestamp
    !=
NEXT_BAR_OPEN entry_timestamp
```

і дозволяє вручну перевіряти price action, MACD/Signal, extremum, crossover geometry та entry delay на конкретних historical cases.

## 51.10. Long-period EURUSD validation

Після development diagnostics RoadMap99 перевіряв ту саму infrastructure на довшому EURUSD historical horizon, не змінюючи deterministic M1 -> M15 contract.

Мета long-period run була не підібрати один оптимальний threshold, а перевірити:

1. що source/profile/revision binding не дрейфує;
2. що ABC geometry залишається обчислюваною на всьому horizon;
3. що historical Signal/Entry navigation працює на віддалених ділянках;
4. що Replay chronology, gap policy, MFE/MAE, risk і virtual execution не змінюють semantics;
5. що `broker_requests=0` і `broker_execution_attempted=False` зберігаються.

Цей long-period check не перетворював RoadMap99 на optimization по всьому dataset. Chronological Development / Validation / Holdout selection свідомо перенесено в RoadMap100.

## 51.11. Missed / false candidate direction

RoadMap99 сформував наступну diagnostic boundary:

```text
false positive:
    Quality ACCEPTED, але після signal немає достатнього move

false negative:
    Quality REJECTED, але після signal є сильний move
```

Для rejected strong move потрібно пояснювати конкретного blocker:

```text
extremum
prominence
distance
angle
Alligator
risk
```

Це не було перетворено на нову production logic у RoadMap99; воно передане в RoadMap100 як окремий validation block.

---

# 52. MD6 final checkpoint 2026-08-16 — RoadMap99 CLOSED

Ця редакція `LGE_Runtime_06.md` є фінальним канонічним checkpoint RoadMap92–99.

RoadMap99 закритий не вибором «найприбутковіших цифр», а підготовкою explainable і deterministic MACD Quality foundation:

```text
classic crossover remains canonical source
EXTENDED quality = extremum + prominence + distance + angle
angle model = LEGACY_CALIBRATED або ABC_REALTIME_SCALED
ABC = time-based, price-scale-aware geometry
custom MACD profiles = exact revision-bound
M1 -> M15 Replay = deterministic, no look-ahead
broker execution = 0
```

Ключові RoadMap99 conclusions:

1. extremum search `3 -> 5 -> 7` працює детерміновано;
2. prominence і distance мають окремі explainable reject reasons;
3. legacy `45°` manual calibration підтверджена, але є profile-sensitive;
4. ABC_REALTIME_SCALED стабільніший між MACD profiles;
5. experimental ABC reference `2.00°` не є універсальною константою;
6. custom profiles `12/26/9`, `8/17/5`, `6/13/4` готові до чесного production comparison;
7. naive normalization відхилена;
8. lower-timeframe Alligator M5/M1 не отримав достатнього production evidence;
9. Signal/Entry navigation готова для manual acceptance;
10. наступний етап повинен перевіряти переносимість між Development / Validation / Holdout, а не підганяти один historical interval.

Перехід документації:

```text
LGE_Runtime_06.md
    = FINAL canon through RoadMap99

LGE_Runtime_07.md
    = RoadMap100 and later production-selection cycle
```

RoadMap100 починається з:

```text
100.1 ABC persistence / restore acceptance
100.2 honest 12/26/9 vs 8/17/5 vs 6/13/4 comparison
100.3 Development / Validation / Holdout
100.4 ABC admissible range
100.5 MACD speed region
100.6 prominence range
100.7 distance range
100.8 manual signal-quality acceptance
100.9 missed-move / false-candidate diagnostics
100.10 Alligator return only after MACD stabilization
```

`broker_requests=0` і `broker_execution_attempted=False` залишаються mandatory invariants Historical Replay.

---

# 53. Потенційна майбутня інтеграція DeepL через MCP

## 53.1. Статус

DeepL повідомив про Remote MCP server для MCP-сумісних AI-асистентів, зокрема ChatGPT, Claude і Copilot.

Endpoint:

```text
https://mcp-api.deepl.com/v1/mcp
```

Для доступу потрібна автентифікація DeepL API key. API key не повинен зберігатися у вихідному коді, Git або документації проєкту.

## 53.2. Поточні можливості, які можуть бути корисні LGE

За інформацією DeepL, у поточному плані доступні через MCP:

```text
Translation
Write
```

Додаткові можливості тарифу Growth включають, зокрема, розширені glossaries/style rules, вищі usage limits та real-time voice translation.

## 53.3. Boundary для LavrGPT05

На поточному етапі DeepL MCP **не інтегрується** в runtime або localization architecture LGE.

Канонічна локалізація LGE залишається автономною:

```text
translation registry
    -> fallback rebuild
    -> strings/fallback resources
    -> deterministic UA/EN/DE/FR UI localization
```

DeepL MCP може бути розглянутий пізніше як допоміжний інструмент для:

1. підготовки або перевірки перекладів;
2. стилістичного вирівнювання текстів;
3. роботи з glossary/термінологією;
4. перекладу зовнішніх листів, документації або support-текстів.

Він не повинен створювати runtime dependency для Replay, broker integration, trading logic або safety-critical paths.

## 53.4. Рішення

Тему відкладено без окремого RoadMap. Повернутися до неї можна пізніше, якщо з'явиться практична потреба у зовнішньому AI-assisted translation workflow.

---

# 54. Технічна передача стану RoadMap100 перед поверненням до 100.1 — 2026-08-16

## 54.1. Причина цього контрольного зрізу

Після закриття RoadMap99, перед продовженням виробничого відбору RoadMap100, було виконано окремий технічний цикл стабілізації Historical Replay і WSP UI. Цей блок не змінює торгову математику MACD/Alligator і не замінює `LGE_Runtime_07.md`; він фіксує Runtime-основу, на якій далі виконується RoadMap100.1.

Канонічні незмінні правила залишаються такими:

```text
M1 historical source
    -> completed M15 strategy bars
    -> signal/filter/risk
    -> virtual order
    -> M1 execution chronology

no look-ahead = mandatory
broker_requests = 0
broker_execution_attempted = False
```

Технічні ідентифікатори в кодовому блоці залишено без перекладу, бо саме в такому вигляді вони використовуються в коді, тестах і журналі.

## 54.2. Replay `Тік` і розділення часу стратегії та виконання

У Historical Replay додано окрему дію `Тік` для діагностики багаторівневого виконання.

Канонічна поведінка:

```text
Крок
    = один крок стратегії до межі вікна виконання

Тік
    = рівно одна найдрібніша підготовлена подія виконання
```

Для поточної схеми M1 -> M15 це означає:

1. `Крок` зупиняється перед вікном M1-виконання;
2. перший `Тік` обробляє одну подію M1;
3. один `Тік` ніколи не пересуває стратегічний M15-бар;
4. алгоритм отримує лише завершені M15-бари;
5. призупинений планувальник зберігає M1-тіки, що очікують обробки;
6. наступний `Крок` може детерміновано обробити залишок вікна виконання;
7. хронологія M1-виконання не створює випереджального доступу до майбутніх даних.

Підтверджено тестом:

```text
strategy_step_stops_before_execution_window=True
one_tick_one_execution_event=True
paused_scheduler_preserves_pending_ticks=True
next_strategy_step_consumes_remaining_window=True
tick_never_advances_strategy_bar=True
algorithm_receives_only_completed_m15=True
no_look_ahead=True
```

## 54.3. Поточна ціна M1-виконання на графіку та в рядку стану

Replay UI тепер окремо показує останню оброблену подію виконання:

```text
Tick Bid
Tick Ask
Tick
```

Ціна вибирається з урахуванням напрямку для контексту віртуальної позиції або виконання. Подія M1-виконання є діагностичною накладкою і не домальовується як фальшива M1-свічка на M15-графіку.

Навігаційна дія `До поточного` означає повернення до поточного вже обробленого Replay-бару, а не до фізично останнього рядка CSV.

## 54.4. Накладка активної позиції та ручне перетягування SL/TP

На ціновому графіку Historical Replay підтверджено накладку активної віртуальної позиції:

1. ціна входу;
2. Stop Loss;
3. Take Profit;
4. поточний PnL;
5. актуальна ціна M1-виконання.

Лінія входу доступна лише для перегляду і не перетягується.

Перетягування SL/TP дозволене лише тоді, коли активний Historical Replay стоїть на паузі:

```text
RUNNING Replay
    -> зміна відхиляється

PAUSED active Historical Replay
    -> наведення на SL/TP
    -> вертикальне перетягування
    -> запит на зміну захисного рівня
```

Канонічний шлях:

```text
Chart Widget
    -> AlgorithmWorkspaceWindow
    -> AlgorithmWorkspaceArea
    -> AlgorithmWorkspaceController
    -> WorkspaceRuntime
    -> virtual Replay position/order state
```

UI не змінює знімок виконання напряму і не виконує брокерської операції.

Після перетягування:

1. уже оброблена M1-подія не запускається повторно;
2. наступна M1-подія використовує новий SL/TP;
3. віртуальний ордер і віртуальна позиція залишаються синхронізованими;
4. у журналі джерело зміни фіксується як `CHART_DRAG`;
5. підказка при наведенні пояснює, що SL/TP можна перетягувати лише на паузі.

Підтверджено тестом:

```text
entry_draggable=False
paused_replay_drag_emitted=True
running_replay_modify_rejected=True
current_processed_m1_not_reprocessed=True
next_m1_uses_modified_sl=True
order_position_sl_synchronized=True
journal_source=CHART_DRAG
```

## 54.5. Реакція інтерфейсу на високих швидкостях Replay

Під час ручного тесту виявлено, що старий режим `1000x` міг надовго займати GUI-потік одним великим логічним пакетом. Через це `Пауза` і `СТОП` реагували неприйнятно пізно.

Тому високошвидкісний Replay розділено на короткі обмежені порції обробки, між якими керування повертається Qt.

Поточний набір швидкостей:

```text
1x
2x
5x
10x
100x
1000x
MAX
MAX FAST
```

Для звичайних високошвидкісних режимів і `MAX` захисне правило UI використовує порції не більше 16 подій із поверненням керування Qt між ними.

Внаслідок цього:

```text
логічна квота 1000x = 1000
але GUI не обробляє всі 1000 подій як один невідривний блок
Pause/Stop перевіряються між короткими порціями
```

Збережені службові значення швидкості:

```text
MAX      = 0
MAX FAST = -1
```

## 54.6. `MAX` і `MAX FAST` мають різне призначення

`MAX` залишається консервативним режимом максимальної швидкості зі звичайним оновленням діагностичного інтерфейсу.

`MAX FAST` призначений для повного швидкого проходу історичних даних, коли проміжна візуалізація менш важлива за швидкість, але хронологія, детермінованість і реакція на `Пауза`/`СТОП` мають зберігатися.

`MAX FAST` використовує:

```text
часовий бюджет обчислення = 40 ms
граничний пакет           = 256 events
інтервал важкого UI       = 500 ms
```

Розмір пакета адаптується за фактично виміряною продуктивністю, але кожна коротка порція обчислення обов'язково повертає керування Qt.

`MAX FAST` може пропускати лише проміжне важке оновлення UI. Він **не пропускає Replay-події**, не змінює сигнатури сигналів, віртуальне виконання, хронологію закриття або кінцевий торговий результат.

Ручне контрольне вимірювання на поточному комп'ютері та на тому самому історичному діапазоні дало приблизно:

```text
MAX      ≈ 18:04
MAX FAST ≈ 01:36
```

Ці цифри є лише локальним спостереженням швидкодії, а не нормативом Runtime. Обов'язковим є однаковий детермінований результат.

## 54.7. Швидкодія і кеш закритих позицій

Окремий контрольний тест підтвердив, що обчислення Replay не повинно деградувати через повторне повне сканування закритих позицій.

Контрольний результат:

```text
strategy_bars_total=14941
startup_seconds=10.755
first_1000_compute_seconds=1.106
second_1000_compute_seconds=1.140
processed_strategy_bars=2000
signals_after_2000=329
virtual_positions_after_2000=32
closed_snapshot_cache_reused=True
```

Часові значення залежать від конкретного комп'ютера і не є нормативом. Канонічний висновок — `closed_snapshot_cache_reused=True` і відсутність накопичувальної O(N²)-подібної деградації через повторну побудову списку закритих позицій.

## 54.8. Вікно `Параметри WSP` — остаточна геометрія без піврядка

У `Параметри WSP` закрито довгий дефект інтерфейсу, коли нижній видимий параметр міг показуватись як половина або чверть рядка залежно від поточного вибору та геометрії правого редактора.

Причина була не в простій кратності `viewport_height / row_height`. Реальна геометрія Qt залежить від рамки, заголовка, layout, splitter і може змінюватися після `show`, зміни вибору та проходу перерахунку layout.

Фінальний контракт:

1. Designer `.ui` лишається джерелом компонування;
2. кореневий splitter отримує вертикальне розтягування;
3. ліве дерево і правий редактор не повинні взаємно змінювати висоту залежно від вибраного параметра;
4. дерево використовує `ScrollPerItem`;
5. вирівнювання виконується після `show/layout` у кілька відкладених проходів;
6. `visualItemRect()` визначає елемент, який реально перетинає нижню межу viewport;
7. унизу viewport резервуються саме видимі пікселі обрізаного елемента;
8. зміна вибору не змінює висоту дерева.

Підсумкове підтвердження у живому Qt:

```text
splitter_vertical_policy=Expanding
right_editor_vertical_policy=Ignored
note_vertical_policy=Maximum
splitter_root_stretch=1
post_layout_passes=4
bottom_visible_parameter_row_alignment=LIVE_VISUAL_ITEM_RECT_EDGE
bottom_visible_parameter_row_not_half_clipped=True
viewport_bottom_reserve=PARTIAL_ITEM_VISIBLE_PIXELS
checked_dialog_heights=650,671,707,743,790
checked_viewport_heights=460,481,517,553,600
selection_probe_count=18
stable_selection_splitter_height=632
stable_selection_tree_height=632
stable_selection_viewport_height=600
selection_does_not_change_tree_height=True
live_qt_geometry_checked=True
designer_ui_source=True
```

Два послідовні фінальні регресійні прогони дали `ALGORITHM_WORKSPACE_PARAMETERS_VERTICAL_SPACE_CHECK=OK`, а ручна перевірка GUI підтвердила відображення лише цілих рядків.

## 54.9. Фінальний набір регресійних перевірок цієї передачі стану

Перед закриттям MD6 підтверджені:

```text
ALGORITHM_WORKSPACE_REPLAY_TICK_CHECK=OK
ALGORITHM_WORKSPACE_CHART_POSITION_OVERLAY_CHECK=OK
ALGORITHM_WORKSPACE_REPLAY_SPEED_CHECK=OK
ALGORITHM_WORKSPACE_REPLAY_VIRTUAL_EXECUTION_CHECK=OK
ALGORITHM_WORKSPACE_REPLAY_PERFORMANCE_BENCHMARK=OK
ALGORITHM_WORKSPACE_PARAMETERS_VERTICAL_SPACE_CHECK=OK
```

Регресія швидкості Replay додатково підтвердила:

```text
speed_1x_10x_100x_1000x_max_maxfast_step_deterministic=True
speed_1000x_keeps_logical_quota_1000=True
max_continuous_burst_yields_between_chunks=True
max_fast_continuous_burst_yields_between_chunks=True
max_fast_batch_grows_and_shrinks_from_measured_throughput=True
pause_responsive_between_high_speed_chunks=True
stop_responsive_between_high_speed_chunks=True
broker_requests=0
broker_execution_attempted=False
```

## 54.10. Стан на момент передачі

На завершення 2026-08-16 технічний цикл Replay/WSP вважається закритим.

Не повертатися до цих частин без конкретного підтвердженого регресійного дефекту:

```text
Replay Tick chronology
M1 execution-price overlay
paused SL/TP chart drag
1000x/MAX responsiveness
MAX FAST adaptive batching
Parameters tree full-row geometry
```

Технічні назви у цьому блоці залишено без перекладу, оскільки вони відповідають назвам реалізованих механізмів і тестових ознак.

Наступна робоча точка:

```text
RoadMap100.1
ABC persistence / restore acceptance
```

Українською це означає: перевірка збереження та відновлення ABC-параметрів і стану.

Після цього контрольного зрізу `LGE_Runtime_06.md` вважається закритим. Подальша робота RoadMap100 з виробничого відбору належить `LGE_Runtime_07.md`.

---
