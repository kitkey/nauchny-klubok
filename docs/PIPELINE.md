# Как строится граф знаний (детальный референс)

Детерминированный конвейер `S0 → S1 → S2 → S3 → S4 → S5 → persist`. Каждый этап — чистая функция
`(Deps, ArticleState) -> ArticleState`. `Deps` — неизменяемые зависимости (llm, embed, prompts, cfg,
graph, docs, tracer). `ArticleState` — состояние прогона по одному документу.

## Модель данных

**Узлы:**
- `Entity` — каноническая сущность. `type ∈ {Material, Property, Process, Technique, Condition, Phase,
  Element, Equipment, Facility, Person, Location}`. Двойной id: `uuid` (durable) + `key` (детерминир.
  ключ дедупа `type:slug`).
- `Fact` — **реифицированный n-арный факт** (`frame_type ∈ {MaterialMeasurement, SynthesisProcedure,
  ClaimFact, HypothesisFact}`). Несёт `statement`, `quantity` (Quantity), `status`, `year`, провенанс.
- `Concept` — кросс-документная абстракция (отдельный слой).

**Рёбра (`EdgeType`):**
- n-арные слоты `Fact→Entity`: `HAS_MATERIAL, HAS_PROPERTY, USES_TECHNIQUE, UNDER_CONDITION, VIA_PROCESS,
  PRODUCES, USES_EQUIPMENT, LOCATED_IN, CONDUCTED_BY`;
- дискурс `Fact↔Fact`: `SUPPORTED_BY, CONTRADICTED_BY`;
- таксономия `Entity→Entity`: `SUBTYPE_OF, PART_OF, IS_A`;
- концепт-слой: `INSTANCE_OF (Entity→Concept), SUBTYPE_OF (Concept→Concept)`;
- якорные: `REPORTS, MENTIONS, AUTHORED_BY, AFFILIATED_WITH`; открытый канал `OPEN`.

**Quantity:** `value, unit, operator (=,~,≥,≤,<,>), uncertainty, lower/upper, raw` — числа хранятся
типизированно, не в тексте.

**Провенанс:** у каждого узла/ребра — `paper_ref + text_hash + локатор` (символьный спан в `raw_text`
или ячейка таблицы). Отсюда цитаты и прослеживаемость.

## Этапы

- **S0 ingest** (`ingest/`): PDF → `Paper` (PyMuPDF; при мусоре PaddleOCR/фолбэк). Эвристическая
  разметка секций/таблиц/фигур/ссылок; `raw_text` иммутабелен.
- **S1 chunk** (`chunk.py`): деление под токен-бюджет внутри секций; атомарные единицы (таблицы) — целиком.
- **S2 roles** (`roles.py`): LLM метит риторическую роль пассажей. *Bulk: пропускается (граф их не
  использует).*
- **S3 extract** (`extract/`): один LLM-вызов на чанк → `_FrameOut[]`. Каждый фрейм → узел `Fact` +
  сущности-участники рёбрами по `FRAME_SLOTS`; числа → `Quantity`. Ошибка одного чанка не роняет документ.
- **S4 link** (`link/`): (a) канонизация сущностей — key-merge + `resolve_mode`: `llm` (LLM-кластеризация
  синонимов + иерархия) или `embed` (эмбеддинг-блокинг + батч-verify, быстрее); (b) канон open-предикатов
  к ядру; (c) дедуп фактов — повтор → merge, конфликт значений → `CONTESTED` + `CONTRADICTED_BY`;
  (d) сшивка claim↔measurement → `SUPPORTED_BY`. Каждый под-шаг терпим к сбою (факты не теряются).
- **S5 verify** (`verify.py`): грунт-чек факта по источнику (3 оси + gate) + `rationale`. *Bulk:
  массовый verify пропускается — вместо него ленивая верификация при запросе (`verify_on_read`, см. ниже).*
- **persist** (`persist.py`): идемпотентный upsert в Neo4j (MERGE по uuid/key, тег `graph_id`),
  артефакты в Mongo, **эмбеддинги сущностей и фактов — в нативный vector-index Neo4j** (считаются раз
  при ингесте).

## Версионирование

Повторный ингест документа с тем же `paper_ref` сначала удаляет старые узлы (`delete_paper`), затем
заливает новые — новая версия вытесняет старую без дублей. Год документа (`Fact.year`) — дата
актуализации.

## Bulk-режим (быстрая заливка)

Флаги в `Config`: `skip_roles`, `skip_verify`, `resolve_mode="embed"`, увеличенный `max_concurrency`.
Убирает два полных LLM-прохода по тексту; эмбеддинг-дедуп вместо LLM-кластеризации. Стоимость ≈ пара
центов на документ.

## Концепт-слой

`p2kg/link/concepts.py`, запуск `build_and_persist_concepts(deps)` (отдельный проход поверх графа).
Линковка сущностей к концептам: косинус-блокинг → LLM решает; иерархия концептов инкрементальная (DAG,
транзитивная редукция). Неразрушающе. *Пока не задействован в ретриве — см. README/Roadmap.*

## Ретрив (поверх Neo4j vector-index)

`retrieve.py`: декомпозиция мультивопроса → векторный поиск по `Fact.statement` (адаптивный порог
релевантности отсекает шум) + PageRank (Neo4j GDS: PPR от якорей + мост по `key` для кросс-дока) →
диверсификация round-robin с **число-предпочтением** (`k=16`) → окрестность участников (1 hop) →
LLM-синтез. Числа — из полей графа, не из модели.

## Ленивая верификация при запросе

`verify_on_read` (`verify.py`): проверяются только факты, попавшие в ответ, и только ещё не
проверявшиеся (`status='unverified'` без флага `v_checked`); источник реконструируется из **units**
(Mongo); LLM-судья по 3 осям + порог → `verified` либо остаётся `unverified`, флаг `v_checked` пишется
в Neo4j (`graphstore.set_fact_verification`). Разовая цена на факт, повторно не гоняется.

## Обогащение: гео и носители экспертизы

Отдельный проход по титулам/интро статей (LLM): гео каждой статьи (РФ / мир / оба) → в `Fact.geography`;
авторы и организации → узлы `Person`/`Facility` + рёбра `WORKS_AT`. Питает фильтр географии и карту
институциональной памяти (кто держит экспертизу и риск её потери) в граф-эксплорере.

## Внешние источники (discovery)

`service.discover` / `GET /api/graphs/{gid}/discover?topic=`: LLM формирует английский научный запрос →
**Crossref** (реальные публикации, без ключа) → дедуп против названий корпуса → кандидаты, которых нет
в базе, со ссылками. Наружу уходит только строка-запрос, без данных корпуса.
