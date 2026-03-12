# АДАПТИВНЫЙ ДЕТЕКТОР РЕЖИМОВ — КАНОН ДЛЯ ГЕНЕРАТОРА

## Назначение
Этот документ фиксирует канон детектора режима, который живёт только в генераторе. Его задача — один раз по `draw_metrics(T-1)` определить `MODE_A / MODE_B / MODE_C`, вернуть `mode_scores / mode_weights / cover_plan` и записать результат в общий `Mode_detector_report.json`.

## Жёсткий архитектурный контракт
- Генератор читает только `draw_metrics(T-1)` и один раз запускает единый детектор режима.
- Профиль режим повторно не определяет и не содержит второй detector-layer.
- `carcass` разрешён только для trace, диагностики и калибровки; `winners` — только после генерации и только для оценки.
- `Mode_detector_report.json` перезаписывается на каждом запуске и служит настройке, а не runtime-routing.

## Семантика режимов
- `MODE_A` — Node / Transition.
- `MODE_B` — Triad / Topology.
- `MODE_C` — Split / Dual-Cluster.

## Порядок распознавания
1. `top_k = 20` по `node_score`.
2. Граф `top_pairs` на top-K.
3. Сильные рёбра: `q = 0.85` по весам внутри top-K.
4. Вычисление признаков и компонент.
5. Расчёт `score_A / score_B / score_C`.
6. Проверка hard-guards.
7. Выбор `argmax(score)`.

## Признаки
- `anchor_mass = sum(node_score top5 in topK) / sum(node_score all)`
- `peak_ratio = max(node_score topK) / mean(node_score topK)`
- `next_mean = mean(state_next_p topK)`
- `entropy_mean = mean(transition_entropy topK)`
- `entropy_inverse = 1 / (1 + entropy_mean)`
- `density_mean = mean(pair_strength + glue_index + triad_strength topK)`
- `coef_mean = mean(coef_participation topK)`
- `component_1_size`, `component_2_size`, `component_balance`, `cross_ratio`, `dominant_groups_differ`

## Hard-guards и пороги
- `MODE_C`: `component_2_size >= 5`, `dominant_groups_differ = True`, `cross_ratio <= 0.25`, `component_balance >= 0.35`
- `MODE_B`: `density_mean >= 0.84`, `coef_mean >= 0.90`, `component_1_size >= 10`
- `MODE_A`: `next_mean >= 0.59`, `entropy_mean <= 1.04`, `density_mean <= 0.82`

## Score-формулы
```text
score_A = 1.90*anchor_mass + 1.25*next_mean + 0.80*entropy_inverse - 0.75*density_mean - 0.10*(component_2_size/top_k)
score_B = 1.45*density_mean + 0.90*coef_mean + 0.60*(component_1_size/top_k) - 0.45*cross_ratio
score_C = 1.10*component_balance + 1.05*(1 - min(cross_ratio, 1.0)) + 0.45*I(dominant_groups_differ) + 0.25*(component_2_size/5.0) - 0.15*(component_1_size/top_k)
if guard_A: score_A += 1.25
if guard_B: score_B += 1.10
if guard_C: score_C += 1.35
mode = argmax({MODE_A: score_A, MODE_B: score_B, MODE_C: score_C})
```

## Resolver
- `confidence = best_score - second_score`
- `winner_margin = confidence`
- `mode_weights = normalize(score - min(score_set) + 1e-9)`
- если список `numbers` пуст, детектор принудительно возвращает `MODE_A`

## Cover plan
- `MODE_A`: `[0,1,2,3]` -> `node_transition_core`, `anchor_variation`, `fresh_tail`
- `MODE_B`: `[0,1,2,3]` -> `topology_core`, `triad_closure`, `dense_bridge`
- `MODE_C`: `[0,1,2,3]` -> `island_A`, `island_B`, `split_cover`, `late_tail`

## Output contract
- `mode`
- `mode_scores`
- `mode_weights`
- `confidence / winner_margin`
- `cover_plan`
- `features`
- `guards`
- запись в `Mode_detector_report.json`

## Главное правило
`draw_metrics(T-1) -> generator mode detector -> profile build for mode -> compare with draws_history.csv`
