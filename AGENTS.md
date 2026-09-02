# AGENTS.md — LavrGPT05 / LGE05

## 1. Область дії

Ці правила застосовуються до всього репозиторію:

`D:\LavrGPT\LavrGPT05`

Вони доповнюють глобальний `AGENTS.md`.
Якщо конкретне завдання поточного RoadMap містить точніші інструкції, вони мають вищий пріоритет.

### Пріоритет правил

Правила застосовуються від загальних до конкретних:

1. Глобальний `AGENTS.md` задає загальні правила Python/Codex.
2. `LavrGPT05/AGENTS.md` доповнює і спеціалізує їх для LGE/LavrGPT05.
3. Конкретне завдання `T105-xx` має найвищий пріоритет для поточного кроку та
   може уточнювати або перевизначати менш конкретні правила.

Коротко: глобальний `AGENTS.md` -> `LavrGPT05/AGENTS.md` -> завдання `T105-xx`.

---

## 2. Роль і робочий процес

- Працювати послідовно: одна перевірювана зміна за один крок.
- Не змішувати кілька неперевірених алгоритмічних або production-змін в одному кроці.
- Один RoadMap відповідає одному робочому чату/циклу.
- Кожен окремий runnable-тест має короткий послідовний ID відповідного RoadMap:
  `T105-01`, `T105-02`, `T105-03` тощо.
- Не пропускати номер runnable-тесту без причини.
- Documentation-only крок сам по собі не повинен займати номер runnable-тесту, якщо окремого runnable немає.
- Після зміни executable logic запускати точний релевантний runnable/regression test.
- Після кожної перевірки чітко фіксувати очікуваний і фактичний final marker.

### Розміщення runtime tests

- `tests/runtime_workspace/` містить тільки retained canonical
  runnable/regression tests, які свідомо залишені як постійні контрольні
  тести RoadMap.
- `tests/runtime_temp/` містить temporary / exploratory / probe / diagnostic /
  anatomy / sweep / counterfactual / prototype / one-off / helper runners,
  створені під час дослідження.
- Новий TEST_ONLY research runner за замовчуванням створювати в
  `tests/runtime_temp/`.
- У `tests/runtime_workspace/` переносити його лише після явного рішення, що
  він стає retained canonical regression/checkpoint.
- T-ID сам по собі не робить тест canonical.
- Перед видаленням `runtime_temp` перевіряти, що retained tests не імпортують
  його модулі.

---

## 3. Production і TEST_ONLY

- Production-логіку змінювати тільки після окремої перевірки та явного рішення.
- Дослідницьку логіку позначати `TEST_ONLY`.
- `TEST_ONLY` logic не змішувати з production wiring.
- PASS дослідницького тесту означає лише коректність тесту/діагностики, а не автоматичне production-рішення.
- Не productionize алгоритмічну ідею лише тому, що вона покращила один період.
- Перед production-рішенням порівнювати baseline і candidate на однакових метриках та щонайменше на окремих періодах.
- Якщо production baseline не збігається з канонічним checkpoint, зупинитися і знайти причину. Не підганяти тест.

---

## 4. Replay і причинність

- У Replay та алгоритмічних тестах не допускати look-ahead.
- Використовувати лише дані, які були доступні на відповідний момент часу.
- Для M15/Multi-Timeframe logic використовувати completed bars only там, де це визначено алгоритмом.
- Поточний signal bar не включати до історичного reference window, якщо правило використовує previous completed bars.
- Future bars можуть використовуватися лише як factual outcome label після entry, але не як input у entry-time classification.
- Чітко відокремлювати:
  - entry-time causal features;
  - factual future outcome/PnL labels.
- Replay повинен залишатися детермінованим.
- Для тестів без broker interaction:
  - `broker_requests=0`;
  - `broker_execution_attempted=False`.

---

## 5. Алгоритмічні експерименти

- Entry, SL, TP, Profit Drawdown, exit filters і re-entry досліджувати окремими контрольованими тестами.
- Не змішувати кілька нових guards/filters в одному тесті, якщо їхній внесок не можна окремо виміряти.
- Параметри індикаторів не вважати універсальними константами без cross-period підтвердження.
- Threshold sweep не виконувати, якщо завдання визначене як anatomy/diagnostic only.
- Не створювати threshold після перегляду результатів того самого тесту без окремого наступного runnable.
- При порівнянні варіантів показувати однакові метрики для baseline і candidate.
- Мінімальний набір метрик, якщо застосовно:
  - trades;
  - wins;
  - losses;
  - break-even;
  - net;
  - profit factor;
  - maximum drawdown;
  - close-reason counts.
- Результат, який покращує один період і погіршує інший, не вважати production-ready без окремого аналізу.
- Не оптимізувати лише під один короткий період.

---

## 6. Current production truth

Під час алгоритмічних робіт не припускати production state з пам'яті.
Перед тестом використовувати фактичний код та актуальний regression/checkpoint.

На поточному RoadMap105 production truth включає:
- Candidate F production path;
- Stochastic `14/1/3` CURRENT_BAR reject;
- Donchian production gate = False;
- Profit Drawdown canonical default = 35%;
- SL = `max(signal_bar_range, spread * 10)`;
- TP = `2R`;
- negative-PD recovery без змін;
- Replay без broker execution.

Якщо цей розділ застарів, оновлювати його тільки після окремого підтвердженого production-рішення.

---

## 7. Архітектура

- Дотримуватися наявної архітектури LavrGPT05.
- Не робити broad refactor без прямої необхідності.
- GUI не повинен напряму працювати з broker adapter, якщо існує RuntimeEngine/RuntimeService/SessionManager path.
- Test-only helper не повинен ламати production type contract.
- Якщо WorkspaceRuntime execution залежить від конкретного production algorithm type, тестові wrappers мають зберігати цей contract.
- Не викликати protected/private production API напряму, якщо можна використати public/test helper або локальну TEST_ONLY еквівалентну функцію.
- Test helper reuse переважніший за копіювання великих runner-ів.

---

## 8. Python і PySide6

- Python: 3.13.
- Для всіх команд цього проєкту використовувати interpreter із venv313:
  `D:\LavrGPT\venv313\Scripts\python.exe`.
- Runnable, regression, `py_compile` та інші Python-перевірки не запускати
  через системні `python`, `py -3.13` або
  `C:\Program Files\Python313\python.exe`, якщо це не окрема діагностика
  середовища.
- `flake8` запускати через
  `D:\LavrGPT\venv313\Scripts\flake8.exe` або через interpreter venv313,
  якщо відповідний модуль доступний у цьому середовищі.
- У звіті після перевірки вказувати, що використано venv313, та не називати
  системний Python проєктним середовищем.
- GUI: PySide6.
- Дотримуватися наявного стилю конкретного файлу.
- Українські comments/docstrings використовувати там, де це відповідає стилю модуля.
- Для runnable/regression/diagnostic Python-модулів module docstring повинен бути змістовним:
  - точна назва модуля;
  - призначення;
  - pipeline;
  - джерела і рух даних;
  - causality/safety contracts;
  - outputs/assertions;
  - non-goals.
- Класи та функції, створені або суттєво змінені в межах завдання, повинні мати змістовні українські docstrings, якщо це не суперечить локальному стилю.
- Documentation-only cleanup не повинен змінювати executable semantics.

---

## 9. Локалізація

- `lang/strings.json` вручну не редагувати без окремої явної вказівки.
- Нові localization keys додавати через прийнятий у проєкті механізм.
- Не змінювати localization files у алгоритмічному TEST_ONLY кроці без потреби.

---

## 10. MD7

Канонічний high-level документ:

`doc/LGE_Runtime_07.md`

Правила:
- MD7 містить тільки архітектурні, алгоритмічні та прийняті production-рішення.
- Не перетворювати MD7 на журнал усіх експериментів.
- TEST_ONLY research results не переносити в MD7 автоматично.
- Поточні дослідницькі результати фіксувати в runner/output або окремому research-документі.
- У MD7 переносити висновок лише після прийняття production-рішення або канонічного rejection/architecture decision.
- Historical sections не переписувати під поточну production truth без причини.
- Current truth має бути явно відділена від historical checkpoints.

---

## 11. Файли і ZIP

- Якщо користувач передає ZIP проєкту або overlay, спочатку перевірити фактичний код. Не вигадувати структуру чи API.
- Зазвичай повертати малий overlay ZIP лише зі зміненими файлами.
- Готовий ZIP для передачі користувачу записувати в `D:\A\ChatGPT`.
- У фінальній відповіді давати посилання на ZIP саме з `D:\A\ChatGPT`,
  а не з тимчасового workspace або каталогу ChatGPT/Codex project mirror.
- Структура ZIP повинна бути придатна для накладання поверх робочого дерева:
  `LavrGPT05/...`
- Не створювати `.patch` замість готових змінених файлів.
- Повний ZIP проєкту робити тільки для аварійного відновлення або за окремою вказівкою.
- Не включати сторонні, тимчасові або Office lock-файли.
- Якщо production files не повинні змінюватися, після роботи перевірити, що вони справді не змінені.

---

## 12. Перевірки після змін

Для executable Python change:
1. `py_compile`;
2. `flake8` або релевантна статична перевірка, якщо застосовно;
3. IDE/type warnings/errors, які стосуються зміненого коду, усунути без зміни semantics;
4. запустити релевантний runnable/regression;
5. перевірити final marker і ключові canonical metrics.

Для documentation-only change:
- повний Replay не запускати без необхідності;
- достатньо статичних перевірок, якщо executable semantics не змінено.

Після будь-якої зміни executable logic не покладатися лише на `py_compile`.

---

## 13. Поведінка при розбіжності

Якщо:
- baseline змінився;
- production metrics не збігаються;
- `broker_requests` став ненульовим;
- з'явився look-ahead;
- змінився production file, який не мав змінюватися;
- TEST_ONLY logic потрапила в production path;

негайно зупинитися і повідомити про розбіжність.

Не компенсувати проблему новими змінами та не "підганяти" assertion.

---

## 14. Принцип найменшої зміни

Для кожного кроку вибирати найменшу зміну, яка:
- перевіряє одну гіпотезу;
- не змінює інші незалежні компоненти;
- має окремий runnable result;
- дозволяє однозначно зрозуміти внесок зміни.

Якщо простіший test-only diagnostic може дати відповідь, не змінювати production.
