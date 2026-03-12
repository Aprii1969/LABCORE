# KANON IMPLEMENTATION: MODE DETECTOR AND PROFILE STANDARD

## 1. Назначение документа
Этот документ фиксирует внедряемый стандарт:
- единый детектор режимов живёт только в генераторе;
- профиль не определяет режим повторно;
- профиль содержит только логику сборки по уже переданному режиму;
- данные живут только в `draw_metrics(T-1)`;
- `winners` используются только после генерации и только из `draws_history.csv`;
- `carcass` используется только для анализа и настройки, но не в runtime профиля.

---

## 2. Единый принцип работы

### Шаг 1. Генератор
Генератор:
1. загружает `draw_metrics(T-1)`;
2. запускает единый детектор режима;
3. определяет `MODE_A / MODE_B / MODE_C`;
4. передаёт выбранный режим в профиль;
5. профиль собирает комбинации по своей квоте и своей логике этого режима.

### Шаг 2. Профиль
Профиль:
- режим не определяет;
- данные из метрик не хранит;
- использует только текущие `draw_metrics(T-1)`;
- собирает комбинации по общей схеме сборки этого профиля.

---

## 3. Что должно быть в профиле

В профиле допустимо:
- `PROFILE_ID`
- `SUPPORTED_MODES`
- `CLOSED_MODES`
- `TARGET_COUNTS`
- `GenParams`
- критерии и пороги сборки
- пошаговая логика сборки по режимам:
  - `build_mode_a(...)`
  - `build_mode_b(...)`
  - `build_mode_c(...)`
- общие предохранители режима
- комментарии, описывающие смысл шагов сборки

---

## 4. Что в профиле запрещено

В профиле не должно быть:
- `SIGS`
- `fingerprint`
- `draw_id`
- `winners`
- `rescue_ticket`
- `baseline_best_hit`
- `base_portfolio`
- `portfolio_fp`
- `lattice`
- `carcass`
- ссылок на carcass-файлы
- заранее выписанных значений из `draw_metrics`
- заранее выписанных `top_pairs`, `top_next`, `top_node`, `top_states`, `top_edges`
- исторических кейсов
- логики генератора
- trace/plumbing
- `GeneratorSandbox`
- больших мусорных numeric-banks, если они подменяют понятную пошаговую сборку

---

## 5. Общий вид параметров профиля

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

### Физика
Физика трактуется как константа:
- `overlap_max = 5`
- `spread = 0.4`
- `cooldown_rate = 0.02`

### Химия
Химия подключается в scoring/postpass:
- `theta`
- `alpha_spike`
- `anti_lip`
- `entropy`

---

## 6. Что использует профиль из draw_metrics(T-1)

Профиль может использовать только runtime-поля текущих метрик, например:
- `node_score`
- `state_next_p`
- `transition_entropy`
- `top_pairs`
- `pair_strength`
- `triad_strength`
- `glue_index`
- `state_lift`
- `state_E_next`
- другие поля текущего `draw_metrics(T-1)`

Но профиль не хранит их заранее как данные.
Он только читает их из текущего файла метрик при запуске.

---

## 7. Обязательный канон пошаговой сборки профиля

Профиль обязан быть описан как **сборка**, а не как список чисел или исторических шаблонов.

### Обязательные стадии сборки

Каждый режим профиля должен описывать сборку по шагам:

1. **anchor #1**  
   Первый основной якорь билета.  
   Обычно выбирается из сильнейшего списка режима (`node/core/next` в зависимости от режима).

2. **anchor #2**  
   Второй якорь билета.  
   Должен усиливать первую опору, но не дублировать её бессмысленно.

3. **bridge / expand**  
   Третий шаг сборки:
   - либо связывающий bridge,
   - либо расширяющий expand.  
   Его задача — соединить anchors или увеличить покрытие структуры состояния.

4. **closers pair**  
   Пара закрывающих элементов, которые:
   - замыкают структуру билета,
   - усиливают парную/topology-сцепку,
   - не дают билету распасться на случайный набор.

5. **fresh / tail slot**  
   Последний слот:
   - свежий элемент,
   - tail-элемент,
   - или управляемый late-slot.  
   Это нужно для покрытия края распределения, а не только центра режима.

---

## 8. Общие предохранители профиля

Эти правила можно использовать в любом режиме, если они оформлены как общие правила, а не как historical case.

### `fresh-injection`
Добавление хотя бы одного fresh/tail-слота в билет или часть квоты профиля, чтобы:
- не замыкаться только на top-core;
- не терять late coverage;
- уменьшать переуплотнение одинаковых комбинаций.

### `closer-by-pairs`
Закрытие билета через pair/topology-логику:
- если anchors уже собраны,
- closers должны усиливать pair-closure,
- а не быть случайной добивкой.

---

## 9. Как должен выглядеть профиль концептуально

```python
PROFILE_ID = "..."
SUPPORTED_MODES = ("MODE_A", "MODE_B", "MODE_C")
CLOSED_MODES = ()
TARGET_COUNTS = {...}

def build_mode_a(metrics, quota, params):
    # anchor #1
    # anchor #2
    # bridge / expand
    # closers pair
    # fresh / tail slot
    ...

def build_mode_b(metrics, quota, params):
    # anchor #1
    # anchor #2
    # bridge / expand
    # closers pair
    # fresh / tail slot
    ...

def build_mode_c(metrics, quota, params):
    # anchor #1
    # anchor #2
    # bridge / expand
    # closers pair
    # fresh / tail slot
    ...

def generate_for_mode(metrics, mode, quota, params):
    if mode == "MODE_A":
        return build_mode_a(metrics, quota, params)
    if mode == "MODE_B":
        return build_mode_b(metrics, quota, params)
    return build_mode_c(metrics, quota, params)
```

---

## 10. Где хранится что

### Генератор
Генератор содержит:
- единый детектор режима;
- `Mode_detector_report.json`;
- orchestration вызова профилей.

### carcass config
Файл вида:
- `h5_carcass_config.py`
- `h3_m2_carcass_config.py`

содержит:
- список профилей каркаса;
- квоты;
- `supported_modes`;
- `closed_modes`;
- `mode_weights`.

### Профиль
Профиль содержит только:
- параметры;
- критерии;
- пороги;
- пошаговую сборку по режимам.

---

## 11. Mode_detector_report.json

На этапе настройки генератор обязан создавать общий файл:

`Mode_detector_report.json`

Он:
- не привязан к конкретному каркасу;
- перезаписывается на каждом запуске;
- показывает, какой режим определил генератор по каждому draw.

Минимальный состав:
- `template_id`
- `profiles_requested`
- `draw_id`
- `metrics_file`
- `mode`
- `mode_scores`

Этот файл нужен только для настройки.
Routing по каркасу включается позже, когда каркас закрыт.

---

## 12. Routing после закрытия каркаса

После закрытия каркаса:
- генератор определяет режим;
- carcass config определяет, какие профили участвуют;
- профиль собирает только по переданному режиму.

Если профиль закрыт только по `MODE_A`, то:
- он участвует только в `MODE_A`;
- в `MODE_B/C` он не участвует, пока не будет закрыт и по этим режимам.

---

## 13. Trace

Trace допустим и нужен:
- для анализа;
- для настройки;
- для проверки сборки.

Но trace:
- не является логикой профиля;
- не должен жить в профиле как runtime-plumbing;
- не должен тянуть carcass или winners в профиль.

---

## 14. Definition of Done для режима профиля

Профиль считается закрытым только по конкретному режиму, если:
1. режим определён генератором по self-серии;
2. профиль собран только по `RULE_PROFILE_CLEAN_MODE`;
3. official self-check по `draws_history.csv` даёт целевой уровень;
4. есть итоговый файл профиля;
5. есть итоговый отчёт;
6. есть канон профиля.

То есть закрытие фиксируется не просто как:
- `profile closed`

а как:
- `profile / MODE_A closed`
- `profile / MODE_B closed`
- `profile / MODE_C closed`

---

## 15. Главное правило

Профиль — это **сборка** и описание того,
**как собирать этот профиль по режиму**.

Профиль — это **не**:
- история тиражей,
- архив метрик,
- список winners,
- список корреляционных пар,
- список выписанных чисел.

Профиль должен быть:
- чистым,
- читаемым,
- параметрическим,
- режимным,
- пригодным для любого тиража этого профиля.
