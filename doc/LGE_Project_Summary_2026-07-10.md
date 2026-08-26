# LavrGPT05 / LGE — узагальнений технічний документ

**Стан документації:** 10 липня 2026 року  
Проаналізовано: 12 вихідних файлів *.md у папці doc, без урахування цього summary-файлу, включно з doc/99_ToFix.
**Актуальний етап:** RoadMap86 завершено  
**Призначення:** єдина коротка карта проєкту, його чинної архітектури, реалізованих можливостей, правил і наступних робіт.

---

## 1. Загальна оцінка документації

Документація фіксує послідовний перехід LavrGPT05 від ранньої основи застосунку до працездатного multi-broker Runtime для ручної торгівлі. Вона складається з трьох шарів:

1. **Історичні Runtime-зрізи** — `LGE_Runtime.md`, `LGE_Runtime_00.md` … `LGE_Runtime_04.md`. Вони пояснюють походження рішень RoadMap66–75, але частина їхніх статусів `TODO` та `IN_PROGRESS` уже закрита наступними етапами.
2. **Чинний Runtime-канон** — `LGE_Runtime_05.md`. Це основне джерело актуального стану після RoadMap86.
3. **Цільова алгоритмічна модель** — `LGE_Algorithms_01.md`. Вона описує майбутні Market Intelligence, Order Intelligence, Risk, Position Control і Backtest, але не означає, що ці шари вже реалізовано.

`README_DOCS.md` і `DevNotes_LGE.md` у корені `doc` є короткими новими файлами. Їхні старіші й докладніші варіанти лежать у `99_ToFix`. Вони мають історичну цінність, але більше не виконують роль повного індексу документації.

---

## 2. Що таке LGE

LGE — настільна ATS-платформа проєкту LavrGPT05 на Python/PySide6 з підтримкою Interactive Brokers і cTrader. Поточний практичний рівень — ручне відкриття, перегляд, супровід базових захисних параметрів і закриття брокерських позицій через єдиний Runtime-шар із журналюванням торгового ланцюга в SQLite.

Стратегічна мета ширша: одна broker-independent система для режимів MANUAL, SEMI та AUTO, у якій ручні й алгоритмічні угоди проходять спільний життєвий цикл і залишають пояснюваний слід у базі даних.

---

## 3. Чинні архітектурні правила

### 3.1. Єдиний RuntimeEngine

У межах процесу LGE існує один спільний `RuntimeEngine`. Він створюється під час запуску головного вікна та використовується GUI, брокерськими діалогами, сторінкою ордерів, scheduler-ом і runtime services.

GUI не повинен викликати брокерські API напряму. Канонічний шлях:

```text
GUI
→ RuntimeEngine
→ Broker Runtime Service
→ SessionManager
→ Broker Adapter
→ Broker API
```

### 3.2. Розподіл відповідальності

- **GUI** збирає введення, показує стан і передає команди.
- **RuntimeEngine** керує загальним lifecycle, маршрутизацією, runtime state і persistence chain.
- **Runtime Service** надає broker-independent операції конкретного брокера.
- **SessionManager** володіє активною сесією, поколіннями адаптерів і reconnect lifecycle.
- **Broker Adapter** містить специфіку API cTrader або IB.
- **RuntimeRepository** читає та записує канонічні сутності SQLite.

### 3.3. Конфігурація і runtime-факти

`LGE.conf` зберігає тільки наміри користувача:

- параметри підключення;
- вибраний broker/account;
- `account_mode`;
- прапорці auto-connect;
- інші сталі налаштування.

До `LGE.conf` не записуються поточний connection state, health, balance snapshot, runtime errors, reconnect state або інші змінні факти. Їхнім джерелом правди є Runtime.

### 3.4. Runtime та broker states

Загальний lifecycle використовує стани `OFF`, `STARTING`, `RUNNING`, `STOPPING`, `ERROR`. Стан окремого брокера описується через broker health/connection state, зокрема `CONNECTED`, `DISCONNECTED`, `SAFE_DISCONNECTED`, `RECONNECTING`, `ERROR`.

`SAFE_DISCONNECTED` означає контрольовану втрату зв’язку без падіння застосунку. Runtime продовжує reconnect watch, але не дозволяє небезпечні торгові дії.

### 3.5. Broker-independent моделі

Внутрішні моделі LGE не повинні залежати від назв полів конкретного API. Особливо важливі правила:

- `account_id` має канонічний тип `str | None`;
- cTrader volume відображається в lot, IB Forex quantity — в units;
- алгоритм не повинен знати broker symbol id або IB contract details;
- broker-specific mapping виконується на межі service/adapter.

---

## 4. Runtime, підключення та відновлення

### 4.1. Startup і AutoConnect

Під час запуску LGE створює єдиний Runtime, завантажує дозволені параметри з `LGE.conf`, запускає runtime services та виконує auto-connect лише для брокерів, для яких користувач зберіг такий намір. Помилка одного брокера не повинна зупиняти весь застосунок або змінювати конфігурацію.

### 4.2. Scheduler і reconnect

`RuntimeScheduler` запускає періодичні runtime tasks. `RuntimeReconnectTask` контролює відновлення з’єднання. Для кожного брокера діє окремий reconnect watch із захистом від дубльованого запуску.

### 4.3. cTrader

Підтверджено:

- OAuth/token flow;
- завантаження рахунків через Runtime account snapshot / Trader-Asset flow;
- account snapshot, balance і currency;
- connect/disconnect;
- SessionManager із generation/retired-adapter policy;
- process-level Twisted reactor;
- відновлення після втрати Інтернету;
- приглушення callback-ів і Deferred-помилок від старих сесій.

Головне рішення RoadMap79: Twisted reactor належить процесу, а не окремому адаптеру, і не перезапускається при reconnect.

### 4.4. Interactive Brokers

Підтверджено:

- TWS/IB Paper connection;
- account summary і account snapshot;
- positions;
- reconnect після недоступності TWS або мережі;
- коректне завершення IB session;
- ручні MARKET Open/Close;
- читання PnL, execution time і attached SL/TP orders;
- розміщення optional SL/TP bracket orders.

### 4.5. Runtime UI

StatusBar читає broker health і account snapshot із Runtime та показує кількість підключених брокерів, їхній стан і баланс. Runtime alerts повідомляють про втрату та відновлення підключення. UI не виконує власних broker-запитів для формування цих даних.

---

## 5. SQLite та канонічний торговий ланцюг

### 5.1. Фізичні бази

```text
DEMO → data/demo.db
LIVE → data/live.db
TEST → data/test.db
```

`OFF` не має окремої runtime database mapping. Для SQLite застосовуються `foreign_keys=ON`, `journal_mode=WAL`, `synchronous=NORMAL` і `busy_timeout`.

### 5.2. Поточна persistence foundation

`RuntimeRepository` забезпечує створення та читання основних сутностей:

- `trades`;
- `order_plans`;
- `broker_orders`;
- `positions`.

Для ручної угоди підтверджено ланцюг:

```text
Trade
→ OrderPlan MARKET
→ BrokerOrder FILLED
→ Position OPEN
→ OrderPlan CLOSE_MARKET
→ BrokerOrder FILLED
→ Position CLOSED
```

Фінальний persistence chain створюється після фактичного `FILLED`, а не після попереднього `ACCEPTED`.

### 5.3. Matching брокерської позиції

Після Open Runtime порівнює snapshots позицій до і після виконання. Перевага надається точному broker position id; якщо його немає, використовуються новий id, symbol, side, volume і час відкриття. Слабкий пошук «перша позиція з тим самим symbol і side» заборонений.

### 5.4. Read-only Refresh

Кнопка `Оновити` на OrdersPage читає broker positions і оновлює таблицю, але не пише до SQLite. Позиції, відкриті вручну в TWS або cTrader, можуть відображатися, однак автоматично не імпортуються в `RuntimeRepository`.

---

## 6. Реалізована ручна торгівля

### 6.1. cTrader DEMO

RoadMap83 підтвердив через LGE:

- BUY Open і Close;
- SELL Open і Close;
- створення повного SQLite chain;
- відображення позицій, volume у lot, PnL, SL/TP і часу;
- явне закриття лише вибраної позиції.

### 6.2. IB Paper

RoadMap84–86 підтвердили:

- MARKET BUY/SELL Open;
- повне Close позиції;
- volume в units;
- entry price;
- PnL через `reqPnLSingle`;
- час ручного TWS виконання через `reqExecutions`;
- SL/TP через open orders;
- bracket order із двома, одним або без child orders;
- cleanup пов’язаних STP/LMT перед MARKET Close.

### 6.3. IB bracket policy

Для BUY parent захисні orders мають сторону SELL; для SELL parent — BUY. Stop Loss використовує STP, Take Profit — LMT. Parent та проміжні orders мають `transmit=False`, останній child — `transmit=True`. Якщо child один, саме він завершує передачу bracket.

Перед Close LGE скасовує пов’язані активні protective orders. Це запобігає ситуації, коли старий SL/TP після закриття позиції створить небажану нову угоду.

### 6.4. Netted IB positions і часткове покриття

IB Forex об’єднує однаково спрямовані операції в net position. Protective orders при цьому можуть покривати лише частину загального volume. LGE не маскує часткове покриття як повне:

- додає `***` до SL/TP;
- підсвічує клітинку warning color;
- показує співвідношення covered/total volume.

Це є важливим правилом достовірності UI.

---

## 7. Цільова модель Market Intelligence

Алгоритмічний документ описує не готовий AUTO, а майбутній broker-independent pipeline:

```text
Market Data
→ Market Structure
→ Market Context
→ Market Observation
→ Signal Candidate
→ Filter Result
→ Trade Decision
→ Trade
→ OrderPlan
→ Risk Manager
→ Execution Gateway
→ Broker Service
→ Broker Adapter
→ Broker Order
→ Position
→ Position Control
→ Result
```

Критичне правило: прямі переходи `Market Data → Broker Order`, `Indicator → Order` або `Signal → Order` заборонені. Кожний шар має одну відповідальність і може дозволити, змінити або заблокувати подальший рух.

### 7.1. Спільний lifecycle

Ручна та алгоритмічна торгівля повинні сходитися в `OrderPlan` і далі використовувати однакові risk checks, execution path, persistence та position control. `trade_id` має зв’язувати спостереження, сигнал, рішення, план, broker order, position і result.

### 7.2. Candle-based foundation

Перший алгоритмічний етап має працювати зі свічками, а не з повним tick archive. Алгоритм отримує однаковий `MarketCandle` у backtest і live; різниться лише джерело — SQLite history або broker stream/candle builder.

Початкова практична область:

- WatchList: EURUSD, GBPUSD;
- M15 як робочий timeframe;
- H1 як старший trend filter;
- Forex як перший asset class;
- MARKET BUY/SELL як перші order types.

### 7.3. Observation, Signal і Decision

`MarketObservation` фіксує факт ринку, а не торгову команду. `SignalCandidate` є гіпотезою. `TradeDecision` є результатом оцінки, але ще не broker order. Таке розділення потрібне для пояснюваності та тестування.

### 7.4. Режими виконання

- **MANUAL** — остаточне рішення приймає користувач.
- **SEMI** — LGE формує OrderPlan, користувач підтверджує виконання.
- **AUTO** — LGE виконує повний дозволений ланцюг самостійно.

Execution mode перевіряється перед створенням BrokerOrder. Алгоритми не повинні самостійно обходити policy layer.

### 7.5. Зовнішні позиції

Передбачені джерела `LGE`, `BROKER_MANUAL`, `IMPORTED` і режими `IGNORE`, `MONITOR`, `TAKE_CONTROL`. LGE не має права змінювати зовнішню позицію без явного дозволу користувача.

### 7.6. Перший кандидат алгоритму

Першим описаним кандидатом є `ALG-001 Trend Pullback`: H1 визначає напрям, M15 шукає відкат, після чого послідовно формуються observation, signal candidate, filters, decision та order plan. Його реалізація має починатися лише після стабілізації ручного Order Layer.

---

## 8. Дані, Risk і майбутні шари

Цільова схема розширює SQLite таблицями watchlists, symbol states, market contexts, observations, signals, filter results, decisions, position events, virtual orders/positions і backtest results.

Запропоновані окремі шари:

- Market Session;
- Asset Class rules;
- License Policy;
- Risk Manager і Risk Rails;
- News Layer;
- Position Control;
- Algorithm Framework;
- Backtest Foundation;
- Execution Gateway;
- External Position Manager;
- Portfolio Layer.

Головний принцип даних: якщо значуща подія не записана в SQLite, LGE не може вважати її частиною відтворюваної історії рішення.

Розробка має йти методом послідовних ітерацій: спочатку мінімальна модель і перевірюваний шлях, потім розширення без руйнування вже підтвердженого lifecycle.

---

## 9. Локалізація та UI-правила

Переклади проходять через єдиний `LangManager.tr()`. `strings.json` зберігає активну мову; ключі та fallback формуються через прийнятий workflow, а GUI не повинен мати власної паралельної системи перекладів.

Для `QComboBox` текст і канонічне значення розділяються через `addItem(text, userData)`. Runtime logic читає `userData`, а не локалізований текст.

OrdersPage має чотири різні дії: `Відкрити`, `Оновити`, `Закрити позицію`, `Вихід`. Trading action виконується лише через RuntimeEngine; вибрана позиція повинна бути чітко видимою.

---

## 10. Підтверджений стан RoadMap66–86

| Етап         | Головний результат                                                                           | Стан у новішій документації                                          |
|--------------|----------------------------------------------------------------------------------------------|----------------------------------------------------------------------|
| RoadMap66–67 | Runtime foundation, states, context, events, SQLite bootstrap, broker integration            | Виконано як основа                                                   |
| RoadMap68–69 | Unified positions, scheduler, heartbeat, reconnect, SessionManager                           | Виконано та перевірено                                               |
| RoadMap71–75 | cTrader OAuth/runtime service, IB runtime service, account/health models                     | Виконано                                                             |
| RoadMap76–79 | Shared RuntimeEngine, AutoConnect, StatusBar, process-level reactor, reconnect stabilization | Виконано й перевірено                                                |
| RoadMap80    | Market/Order Intelligence architecture                                                       | Спроєктовано; реалізовано тільки foundation через manual Order Layer |
| RoadMap81–83 | Manual cTrader Open/Close і SQLite lifecycle                                                 | Виконано                                                             |
| RoadMap84    | IB Paper manual Open/Close                                                                   | Виконано                                                             |
| RoadMap85    | IB positions enrichment у OrdersPage                                                         | Виконано                                                             |
| RoadMap86    | IB optional SL/TP bracket orders, cleanup і partial coverage warning                         | Виконано                                                             |

---

## 11. Справді відкриті роботи

Після відсіву застарілих TODO з ранніх документів актуальними залишаються:

1. **IB SL/TP Modify from LGE** — окрема команда для create/modify/cancel existing STP/LMT без змішування з Open або Close.
2. **Імпорт і політика зовнішніх позицій** — явні `BROKER_MANUAL`/`IMPORTED`, режими IGNORE/MONITOR/TAKE_CONTROL і контроль користувача.
3. **Order Layer beyond MARKET** — LIMIT/STOP та їхній lifecycle.
4. **Risk Manager і Position Control** — формалізація risk checks, break-even, trailing stop, emergency actions.
5. **Market Data/Candle storage** — історичні свічки, candle builder і однаковий MarketCandle для backtest/live.
6. **Market Intelligence pipeline** — structure, context, observations, signals, filters і decisions.
7. **Backtest foundation** — virtual execution і результати, що використовують ті самі канонічні моделі.
8. **SEMI/AUTO** — тільки після стабілізації попередніх шарів і policy gates.
9. **Documentation cleanup** — оновити `README_DOCS.md`, перенести або позначити історичні Runtime-файли, прибрати дублікати з `99_ToFix` після ручної перевірки.
10. **Невеликий UI-борг** — перевірити поведінку default/highlighted buttons у broker dialogs.

Найближчий логічний етап за чинним Runtime-документом: окремий RoadMap для зміни або вилучення SL/TP уже відкритої IB position.

---

## 12. Ризики та застереження

- Старі Runtime-документи не можна використовувати як єдине джерело поточного статусу: їхні історичні `TODO` часто вже виконані.
- IB Forex є netted; одна broker position не завжди відповідає одній LGE trade або одному комплекту protective orders.
- Broker terminal positions зараз відображаються, але не мають автоматичного persistence/import lifecycle.
- Market availability і session quality — різні поняття; відкритий ринок не означає дозвіл конкретної стратегії.
- LIVE, SEMI та AUTO не слід вважати готовими лише тому, що manual DEMO/Paper execution працює.
- SQLite schema майбутнього Market Intelligence значно ширша за вже реалізовані `trades/order_plans/broker_orders/positions`.

---

## 13. Рекомендована документаційна структура

Щоб надалі уникнути суперечностей, доцільно закріпити такі ролі:

- `LGE_Project_Summary.md` — короткий актуальний паспорт проєкту;
- `LGE_Runtime_05.md` або його наступник — повний Runtime-канон;
- `LGE_Algorithms_01.md` — цільова модель алгоритмів;
- `README_DOCS.md` — реальний індекс усіх чинних і архівних документів;
- старі `LGE_Runtime*` — історичні snapshots із явною позначкою `ARCHIVE`;
- `99_ToFix` — тимчасова папка, а не паралельне джерело правди.

---

## 14. Джерела узагальнення

Проаналізовано:

- `doc/DevNotes_LGE.md`;
- `doc/README_DOCS.md`;
- `doc/LGE_Runtime.md`;
- `doc/LGE_Runtime_00.md`;
- `doc/LGE_Runtime_01.md`;
- `doc/LGE_Runtime_02.md`;
- `doc/LGE_Runtime_03.md`;
- `doc/LGE_Runtime_04.md`;
- `doc/LGE_Runtime_05.md`;
- `doc/LGE_Algorithms_01.md`;
- `doc/99_ToFix/DevNotes_LGE.md`;
- `doc/99_ToFix/README_DOCS.md`.

Пріоритет актуальності під час суперечностей:

```text
LGE_Runtime_05.md
→ LGE_Algorithms_01.md (для цільової моделі)
→ LGE_Runtime_04.md … LGE_Runtime.md (для історії рішень)
→ README/DevNotes (для індексу й ранньої хронології)
```

---

**Підсумок:** LavrGPT05 уже має перевірений multi-broker Runtime і ручний торговий lifecycle для cTrader DEMO та IB Paper. Найсильніша частина проєкту — чітка межа GUI/Runtime/Service/Adapter, стійкий reconnect і persistence chain. Наступна стадія має не переписувати цю основу, а послідовно нарощувати modify SL/TP, зовнішні позиції, Risk/Position Control, Market Intelligence і Backtest.
