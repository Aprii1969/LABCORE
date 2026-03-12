# RULE_PROFILE_CLEAN_MODE

## Назначение
Этот документ задаёт обязательный стандарт сборки, проверки и закрытия профиля.
Он приведён в соответствие с новым внедряемым форматом:
- единый детектор режима живёт только в генераторе;
- маршрутизация профилей и квоты живут в `_carcass_config.py`;
- профиль режим повторно не определяет;
- профиль содержит только логику сборки по уже переданному режиму.

---

## 1. Базовая архитектура
Рабочая цепочка всегда только такая:

1. Генератор читает `draw_metrics(T-1)`.
2. Генератор один раз прогоняет единый детектор режима.
3. Генератор получает:
   - `mode`
   - `mode_scores`
   - `mode_weights`
   - `cover_plan`
4. Генератор читает `_carcass_config.py` и строит routing:
   - какие профили закрыты для этого режима;
   - какие квоты и режимные веса действуют;
   - какие профили участвуют в текущем запуске.
5. Генератор вызывает каждый активный профиль уже с готовым `mode`.
6. Профиль собирает комбинации по своей квоте и по логике этого режима.
7. Только после завершения генерации результат сравнивается с `draws_history.csv`.
8. Только после проверки создаются файл профиля, checkpoint, отчёт и канон.

Короткая формула:

`draw_metrics(T-1) -> generator mode detector -> _carcass_config routing -> profile build for mode -> compare with draws_history.csv`

---

## 2. Главный принцип
### 2.1. Профиль не хранит данные из metrics
В профиле не должно быть данных, выписанных из `draw_metrics(T-1)`.

Запрещено хранить в профиле:
- числа, выписанные из metrics;
- пары, выписанные из metrics;
- `top_pairs`, `top_next`, `top_node`, `top_edges` как сохранённые списки;
- `SIGS`, `fingerprint`, `portfolio_fp`;
- `draw`, `draw_id`, списки тиражей;
- `winners`, `rescue_ticket`, `baseline_best_hit`;
- любые historical signatures и draw-bound blocks.

Профиль содержит только:
- шаги сборки;
- критерии;
- пороги;
- параметры;
- режимные правила;
- реализацию сборки для `MODE_A / MODE_B / MODE_C`.

### 2.2. Источник данных
Единственный runtime-источник фактических данных состояния:
- `draw_metrics(T-1)`

Разрешённые признаки:
- `state_next_p`
- `node_score`
- `top_pairs`
- `state_id_next`
- `transition_*`
- `pair_strength`
- `triad_strength`
- `glue_index`
- `type_name`
- `zone_name`
- другие поля `draw_metrics(T-1)`

Важно:
эти поля используются только как текущие runtime-данные.
Их значения не должны переноситься в код профиля как заранее выписанные списки или корреляционные блоки.

---

## 3. Winners и carcass
### 3.1. Winners
`winners` разрешены только после генерации и только через `draws_history.csv`.

Разрешено:
- сравнение уже сгенерированных комбинаций с `draws_history.csv`;
- расчёт `best_hit`, hit-distribution и итогового отчёта.

Запрещено:
- читать winners в runtime логике профиля;
- читать winners в генераторе до завершения сборки;
- использовать winners для селекции, фильтрации, выбора режима или выбора билета.

### 3.2. Carcass
`carcass_Txxxx.json` разрешён только как внешний аналитический слой:
- разбор проблемного тиража;
- диагностика по trace;
- понимание, на каком этапе winner должен был войти;
- настройка критериев и порогов.

Запрещено:
- читать carcass в runtime логике профиля;
- ссылаться на carcass из профиля;
- использовать carcass как источник билета, lookup, rescue или mode-selection.

---

## 4. Физика и химия
Физика глобальна и постоянна.
Химия параметрическая и может настраиваться.

Обязательная форма параметров:

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class GenParams:
    seed: Optional[int] = None
    rng_seed: Optional[int] = None
    deterministic: bool = True

    overlap_max: int = 5
    spread: float = 0.4
    cooldown_rate: float = 0.02

    theta: float = 1.2
    alpha_spike: float = 0.8
    anti_lip: float = 0.15
    entropy: float = 0.15
```

Правило применения:
- физика — общая рамка диверсификации и postpass;
- химия — влияет на scoring/postpass, а не на чтение winners или carcass.

---

## 5. Где живёт детектор режима
Детектор режима живёт только в генераторе.

Профиль не содержит второй независимый детектор режима.
Профиль получает режим от генератора и строит портфель по этому режиму.

Генератор обязан:
- один раз определить режим по `draw_metrics(T-1)`;
- использовать один и тот же режим для всех профилей данного запуска;
- передать режим в профиль вместе с metrics и quota.

---

## 6. Где живут квоты и режимная пригодность
Каркасная маршрутизация живёт в `_carcass_config.py`.

В `_carcass_config.py` разрешено хранить:
- `CARCASS_ID`;
- список профилей каркаса;
- базовые квоты;
- `supported_modes`;
- `closed_modes`;
- `mode_weights`;
- notes/priority/routing policy.

В `_carcass_config.py` запрещено хранить:
- scoring профиля;
- thresholds профиля;
- recipes профиля;
- данные из metrics;
- historical cases;
- winners / draw_id / carcass-разбор.

### 6.1. Статус профиля фиксируется по режимам
Профиль считается закрытым не вообще, а по режимам.

Пример:

```python
closed_modes = ("MODE_A",)
```

Это означает:
- в `MODE_A` профиль участвует в прогнозе;
- в `MODE_B / MODE_C` профиль не участвует, пока эти режимы не закрыты.

---

## 7. Интерфейс профиля
Профиль должен быть самодостаточным и читать runtime-данные только из переданных metrics.

Профиль обязан иметь:
- `PROFILE_ID`
- `QUOTA`
- `SUPPORTED_MODES = ("MODE_A", "MODE_B", "MODE_C")`
- `GenParams`
- функцию извлечения runtime context из `draw_metrics(T-1)`
- сборку для `MODE_A`
- сборку для `MODE_B`
- сборку для `MODE_C`
- единый вход `generate_for_mode(metrics, mode, quota, params)` либо эквивалентный интерфейс

Минимальная схема:

```python
PROFILE_ID = "..."
QUOTA = ...
SUPPORTED_MODES = ("MODE_A", "MODE_B", "MODE_C")


def build_context(metrics, params):
    ...


def build_mode_a(context, quota, params):
    ...


def build_mode_b(context, quota, params):
    ...


def build_mode_c(context, quota, params):
    ...


def generate_for_mode(metrics, mode, quota, params):
    context = build_context(metrics, params)
    if mode == "MODE_A":
        return build_mode_a(context, quota, params)
    if mode == "MODE_B":
        return build_mode_b(context, quota, params)
    return build_mode_c(context, quota, params)
```

### 7.1. Что может быть в профиле
Допустимо:
- profile-passport;
- квота;
- режимные steps;
- scoring rules;
- threshold rules;
- windows как общие режимные окна выбора;
- recipes как общая схема выбора из runtime ranking-списков,
  если это именно схема, а не historical data-bank.

### 7.2. Что запрещено в профиле
Запрещено:
- `draw`
- `draw_id`
- `_SIGS`
- `RESCUE_MAP`
- `fingerprint_rescue`
- `fingerprint_key -> ticket`
- `ticket` для конкретных исторических случаев
- `winners`
- `carcass`
- `pool-report` в runtime-логике
- `lattice`
- второй детектор режима внутри профиля
- данные из metrics как заранее вшитые списки

---

## 8. `_common.py`
Для нового стандарта `_common.py` не используется как носитель профильной логики.

Предпочтительный вариант для новых каркасов:
- убрать `_common.py`;
- использовать `_carcass_config.py` для routing и каркасной мета-информации , который будет находится в корне каталога рядом с генератором

---

## 9. Жёсткий порядок работы
Порядок всегда только такой:

1. взять `draw_metrics(T-1)` по self-серии профиля;
2. прогнать единый детектор режима генератора;
3. зафиксировать, какие режимы реально есть в профиле;
4. отдельно по каждому найденному режиму делать тест и настройку;
5. профиль собирать только по `RULE_PROFILE_CLEAN_MODE`;
6. затем проверка по `draws_history.csv`;
7. только после этого:
   - файл профиля,
   - отчёт,
   - checkpoint,
   - канон профиля.

Коротко:
- сначала режимы;
- потом сборка по режимам;
- потом проверка по `draws_history.csv`;
- и только после этого файл, отчёт и канон.

---

## 10. Канон профиля
Канон профиля должен содержать только:
- тип профиля;
- смысл профиля;
- поддерживаемые режимы;
- закрытые режимы;
- пошаговую логику сборки;
- критерии;
- пороги;
- описание того, как профиль строится в `MODE_A / MODE_B / MODE_C`.

В каноне запрещены:
- тиражи;
- `winners`;
- validation-серии;
- historical signatures;
- конкретные билеты;
- correlation-case blocks.

---

## 11. Definition of Done
Профиль может считаться завершённым только если одновременно выполнено всё:
1. профиль соответствует этому правилу;
2. в профиле нет запрещённых маркеров;
3. режимы по self-серии зафиксированы;
4. настройка проведена отдельно по найденным режимам;
5. official self-check по `draws_history.csv` пройден;
6. создан clean файл профиля;
7. создан checkpoint;
8. создан отчёт;
9. создан канон профиля.

### 11.1. Полностью закрытый профиль
Профиль считается полностью закрытым только если все режимы, которые он обязан поддерживать для данного каркаса, закрыты и отражены в `_carcass_config.py`.

### 11.2. Частично закрытый профиль
Если закрыт только один режим, это фиксируется явно.
Пример:
- `HARD_2M2W1S / MODE_A = closed`
- `HARD_2M2W1S / MODE_B = not_ready`
- `HARD_2M2W1S / MODE_C = not_ready`

---

## 12. Жёсткий критерий дефектного файла
Если в профиле найдено хотя бы одно из ниже — профиль считается дефектным:
- `draw`
- `draw_id`
- `_SIGS`
- `RESCUE_MAP`
- `fingerprint_rescue`
- `portfolio_fp`
- заранее зашитый `ticket`
- lookup по `fingerprint_key`
- `winners` в runtime
- `carcass` в runtime
- `lattice`
- профильный детектор, дублирующий генераторный
- данные из metrics, заранее перенесённые в код профиля

---

## 13. Короткая итоговая формула
Генератор один раз определяет режим по `draw_metrics(T-1)`.
Профиль не определяет режим повторно.
`_carcass_config.py` определяет routing, квоты и режимную пригодность профилей.
Профиль только собирает по переданному режиму.
Сначала генерация, потом проверка по `draws_history.csv`.
Никогда не наоборот.



Запрет на выдачу файла без доказательства

не имею права выводить файл профиля, пока не выполнены одновременно все 4 проверки:

Архитектурная чистота
В профиле нет:
draw_id
winners
fingerprint
SIGS
rescue
GeneratorSandbox
trace
lattice
historical comments
self-target comments

Формат профиля
В файле есть только:
PROFILE_ID
SUPPORTED_MODES
CLOSED_MODES
TARGET_COUNTS

GenParams
критерии и пороги
пошаговая сборка режима:
anchor #1 -> anchor #2 -> bridge/expand -> closers pair -> fresh/tail slot

Результат
Профиль проходит официальный self-check на целевом уровне.
Сверка с baseline
Новый файл не хуже последнего рабочего baseline.

Пока все 4 пункта не выполнены, файл наружу не выходит вообще.

делаю только это:
беру последний рабочий baseline
рефакторю его в writable-tree
не вывожу ничего, пока не получу:
чистый grep
self-check 4/5+
diff к baseline
И только потом вывожу пакет.
