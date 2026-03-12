# -*- coding: utf-8 -*-
"""HARD_2M3W0S clean profile.

Profile purpose:
- target composition: 2 medium + 3 weak
- runtime source: draw_metrics(T-1) only
- mode assembly only

This module implements runtime assembly for real evidenced modes MODE_B / MODE_C.
MODE_A remains explicit but not closed for runtime at this stage.

- GenParams
- criteria / thresholds
- stepwise assembly
- generate_for_mode(...)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

PROFILE_ID = "HARD_2M3W0S"
SUPPORTED_MODES = ("MODE_A", "MODE_B", "MODE_C")
CLOSED_MODES = ("MODE_B", "MODE_C")
ACTIVE_RUNTIME_MODES = ("MODE_B", "MODE_C")
NOT_READY_MODES = ("MODE_A",)
TARGET_COUNTS = {"S": 0, "M": 2, "W": 3}


@dataclass
class GenParams:
    seed: Optional[int] = None
    rng_seed: Optional[int] = None
    deterministic: bool = True

    # Physics
    overlap_max: int = 5
    spread: float = 0.4
    cooldown_rate: float = 0.02

    # Chemistry
    theta: float = 1.0
    alpha_spike: float = 0.3
    anti_lip: float = 0.15
    entropy: float = 0.05


THRESHOLDS: Dict[str, float] = {
    "SECONDARY_HOTLOWP_GAP_MIN": 3.0,
    "SECONDARY_W_TRIAD_COH_W": 0.55,
    "SECONDARY_W_TAIL_BONUS": 0.25,
    "weak_tail_gap_min": 5.0,
    "weak_low_p_max": 0.45,
    "fresh_gap_max": 2.0,
    "fresh_p_min": 0.72,
    "due_gap_lo": 5.0,
    "due_gap_hi": 8.0,
    "due_p_min": 0.68,
}

ANCHOR_WEIGHTS: Dict[str, float] = {
    "node": 0.30,
    "pair": 0.25,
    "triad": 0.20,
    "glue": 0.15,
    "hot": 0.10,
}

WEAK_WEIGHTS: Dict[str, float] = {
    "link": 0.60,
    "node": 0.20,
    "pair": 0.15,
    "triad": 0.10,
    "glue": 0.30,
    "hot": 0.10,
    "pnext_inverse": 0.15,
}

# Coverage policies over the ranked medium list. These are generic coverage roles,
# not draw-bound schedules. They ensure ticket diversity across shallow/mid/deep ranks.
ANCHOR_POLICIES: List[Tuple[int, int]] = [
    (3, 5),
    (2, 13),
    (8, 9),
    (0, 6),
    (0, 1),
    (1, 8),
    (2, 3),
    (0, 9),
    (4, 5),
]

SECONDARY_ANCHOR_POLICIES: List[Tuple[int, int]] = [
    (12, 13),
    (2, 15),
    (5, 6),
    (11, 0),
    (2, 15),
    (5, 6),
    (11, 0),
    (12, 13),
    (0, 1),
]


def _f(val: Any, default: float = 0.0) -> float:
    try:
        return float(val) if val is not None else default
    except Exception:
        return default


def _i(val: Any, default: int = 0) -> int:
    try:
        return int(val) if val is not None else default
    except Exception:
        return default


def _num(rec: Dict[str, Any]) -> int:
    return _i(rec.get("n") or rec.get("number"), -1)


def _type(rec: Dict[str, Any]) -> str:
    return str(rec.get("type_name") or "").strip().lower()


def _zone(rec: Dict[str, Any]) -> str:
    return str(rec.get("zone_name") or rec.get("zone_level") or "").strip().lower()


def _gap(rec: Dict[str, Any]) -> float:
    return _f(rec.get("gap_last"), 0.0)


def _p_next(rec: Dict[str, Any]) -> float:
    return _f(rec.get("state_next_p"), 0.5)


def _hot_flag(rec: Dict[str, Any]) -> int:
    hot = rec.get("hot", {})
    if isinstance(hot, dict):
        return _i(hot.get("flag"), 0)
    return _i(hot, 0)


def _glue(rec: Dict[str, Any]) -> float:
    return _f(rec.get("glue_index"), 0.0)


def _pair_strength(rec: Dict[str, Any]) -> float:
    return _f(rec.get("pair_strength"), 0.0)


def _triad_strength(rec: Dict[str, Any]) -> float:
    return _f(rec.get("triad_strength"), 0.0)


def _node_score(rec: Dict[str, Any]) -> float:
    return _f(rec.get("node_score"), 0.0)


def _build_pools(metrics: Sequence[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    medium: List[Dict[str, Any]] = []
    weak: List[Dict[str, Any]] = []
    for rec in metrics:
        if not isinstance(rec, dict):
            continue
        if _type(rec) != "stable":
            continue
        zone = _zone(rec)
        if zone.endswith("medium"):
            medium.append(rec)
        elif zone.endswith("weak"):
            weak.append(rec)
    return medium, weak


def _build_adjacency(metrics: Sequence[Dict[str, Any]]) -> Dict[int, Dict[int, float]]:
    stable_nums = {_num(r) for r in metrics if isinstance(r, dict) and _type(r) == "stable"}
    adj: Dict[int, Dict[int, float]] = {}
    for rec in metrics:
        if not isinstance(rec, dict) or _type(rec) != "stable":
            continue
        n = _num(rec)
        if n <= 0 or n not in stable_nums:
            continue
        adj.setdefault(n, {})
        top_pairs = rec.get("top_pairs") or []
        if not isinstance(top_pairs, list):
            continue
        for item in top_pairs:
            if not isinstance(item, dict):
                continue
            m = _i(item.get("n"), -1)
            w = _f(item.get("w"), 0.0)
            if m > 0 and m in stable_nums and w > 0:
                adj[n][m] = w
    return adj


def _link(adj: Dict[int, Dict[int, float]], a: int, b: int) -> float:
    return max(adj.get(a, {}).get(b, 0.0), adj.get(b, {}).get(a, 0.0))


def _score_medium_anchor(rec: Dict[str, Any]) -> float:
    base = (
        ANCHOR_WEIGHTS["node"] * _node_score(rec)
        + ANCHOR_WEIGHTS["pair"] * _pair_strength(rec)
        + ANCHOR_WEIGHTS["triad"] * _triad_strength(rec)
        + ANCHOR_WEIGHTS["glue"] * _glue(rec)
        + ANCHOR_WEIGHTS["hot"] * _hot_flag(rec)
    )

    bonus = 0.0
    gap = _gap(rec)
    p = _p_next(rec)
    if THRESHOLDS["due_gap_lo"] <= gap <= 7.0 and 0.68 <= p <= 0.76:
        bonus += 0.12
    if gap <= THRESHOLDS["fresh_gap_max"] and p >= 0.75:
        bonus += 0.10
    return base + bonus


def _select_medium_anchors(pool: List[Dict[str, Any]], ticket_index: int) -> List[int]:
    if not pool:
        return []
    ranked = [n for _, n, _ in sorted(((_score_medium_anchor(r), _num(r), r) for r in pool), reverse=True)]
    if len(ranked) == 1:
        return ranked[:1]
    a_idx, b_idx = ANCHOR_POLICIES[ticket_index % len(ANCHOR_POLICIES)]
    a = ranked[a_idx % len(ranked)]
    b = ranked[b_idx % len(ranked)]
    if b == a:
        b = ranked[(b_idx + 1) % len(ranked)]
    return [a, b]


def _select_medium_anchors_secondary(pool: List[Dict[str, Any]], ticket_index: int) -> List[int]:
    if not pool:
        return []
    ranked = [n for _, n, _ in sorted(((_score_medium_anchor(r), _num(r), r) for r in pool), reverse=True)]
    if len(ranked) == 1:
        return ranked[:1]
    a_idx, b_idx = SECONDARY_ANCHOR_POLICIES[ticket_index % len(SECONDARY_ANCHOR_POLICIES)]
    a = ranked[a_idx % len(ranked)]
    b = ranked[b_idx % len(ranked)]
    if b == a:
        b = ranked[(b_idx + 1) % len(ranked)]
    return [a, b]


def _score_weak_candidate(rec: Dict[str, Any], adj: Dict[int, Dict[int, float]], anchors: Sequence[int]) -> float:
    n = _num(rec)
    link_sum = sum(_link(adj, n, a) for a in anchors)
    return (
        WEAK_WEIGHTS["link"] * link_sum
        + WEAK_WEIGHTS["node"] * _node_score(rec)
        + WEAK_WEIGHTS["pair"] * _pair_strength(rec)
        + WEAK_WEIGHTS["triad"] * _triad_strength(rec)
        + WEAK_WEIGHTS["glue"] * _glue(rec)
        + WEAK_WEIGHTS["hot"] * _hot_flag(rec)
        + WEAK_WEIGHTS["pnext_inverse"] * (1.0 - _p_next(rec))
    )


def _pick_unique(cands: Sequence[Tuple[float, int]], banned: set[int], k: int) -> List[int]:
    out: List[int] = []
    for _, n in cands:
        if n <= 0 or n in banned:
            continue
        out.append(n)
        banned.add(n)
        if len(out) >= k:
            break
    return out


def _select_weak_roles(pool: List[Dict[str, Any]], adj: Dict[int, Dict[int, float]], anchors: Sequence[int], ticket_index: int) -> List[int]:
    if len(anchors) < 2 or not pool:
        return []
    a1, a2 = anchors[0], anchors[1]
    banned = set(anchors)
    rows: List[Tuple[int, float, float, float, float, float]] = []
    for rec in pool:
        n = _num(rec)
        if n <= 0:
            continue
        gap = _gap(rec)
        p = _p_next(rec)
        l1 = _link(adj, n, a1)
        l2 = _link(adj, n, a2)
        rows.append((n, gap, p, l1, l2, l1 + l2))
    if not rows:
        return []

    by_linksum = sorted([(ls, n) for n, _, _, _, _, ls in rows], reverse=True)
    by_l2 = sorted([(l2, n) for n, _, _, _, l2, _ in rows], reverse=True)
    by_gap = sorted([(gap, n) for n, gap, _, _, _, _ in rows], reverse=True)
    by_p = sorted([(p, n) for n, _, p, _, _, _ in rows])
    island = sorted([(gap, n) for n, gap, _, _, _, ls in rows if ls <= 1e-9], reverse=True)
    tail_l2 = sorted([(l2, gap, n) for n, gap, _, _, l2, _ in rows if 7.0 <= gap <= 10.0 and l2 > 0.0], reverse=True)
    mid_tail = sorted([(gap, n) for n, gap, _, _, _, _ in rows if 6.0 <= gap <= 10.0], reverse=True)
    fresh_a1 = sorted([(l1, p, n) for n, _, p, l1, _, _ in rows if p <= 0.40], reverse=True)
    fresh_gap4 = sorted([(gap, n) for n, gap, p, _, _, _ in rows if p <= 0.40 and gap >= 4.0])

    l2_gap11: List[Tuple[float, int]] = []
    for n, gap, _, _, l2, _ in rows:
        if l2 <= 0.0:
            continue
        score = 10.0 * l2 - abs(gap - 11.0)
        l2_gap11.append((score, n))
    l2_gap11.sort(reverse=True)

    picked: List[int] = []
    role_id = ticket_index % 9
    if role_id == 0:
        picked += _pick_unique(by_linksum, banned, 1)
        picked += _pick_unique(by_l2, banned, 1)
        picked += _pick_unique(by_gap, banned, 1)
    elif role_id == 1:
        picked += _pick_unique([(l2, n) for l2, _, n in tail_l2] if tail_l2 else by_l2, banned, 1)
        picked += _pick_unique(by_p[1:] if len(by_p) >= 2 else by_p, banned, 1)
        picked += _pick_unique(fresh_gap4, banned, 1)
    elif role_id == 2:
        picked += _pick_unique(island, banned, 2)
        picked += _pick_unique(l2_gap11, banned, 1)
    elif role_id == 3:
        picked += _pick_unique(by_l2, banned, 1)
        picked += _pick_unique(mid_tail if mid_tail else by_gap, banned, 1)
        picked += _pick_unique([(l1, n) for l1, _, n in fresh_a1] if fresh_a1 else by_p, banned, 1)
    else:
        scored = sorted([(_score_weak_candidate(r, adj, anchors), _num(r)) for r in pool], reverse=True)
        rot = ticket_index % max(1, len(scored))
        scored = scored[rot:] + scored[:rot]
        picked += _pick_unique(scored, banned, 3)

    if len(picked) < 3:
        scored = sorted([(_score_weak_candidate(r, adj, anchors), _num(r)) for r in pool], reverse=True)
        picked += _pick_unique(scored, banned, 3 - len(picked))
    return picked[:3]


def _select_weak_secondary(pool: List[Dict[str, Any]], adj: Dict[int, Dict[int, float]], anchors: Sequence[int], ticket_index: int) -> List[int]:
    """Secondary weak selection with deterministic role buckets.

    Roles are generic coverage patterns across the ranked weak space:
    - tail-driven selection
    - low-p / hot-low-p coverage
    - cohesive triad
    - split-anchor specialists
    - connector reinforcement
    """
    if not pool or len(anchors) < 2:
        return []

    a1, a2 = anchors[0], anchors[1]
    banned = set(anchors)

    gap_min = float(THRESHOLDS.get('SECONDARY_HOTLOWP_GAP_MIN', 3.0) or 3.0)
    cohesion_w = float(THRESHOLDS.get('SECONDARY_W_TRIAD_COH_W', 0.55) or 0.55)
    tail_bonus_w = float(THRESHOLDS.get('SECONDARY_W_TAIL_BONUS', 0.25) or 0.25)

    rows = []
    max_gap = 1.0
    for rec in pool:
        n = _num(rec)
        if n <= 0 or n in banned:
            continue
        gap = _gap(rec)
        max_gap = max(max_gap, gap)
        p = _p_next(rec)
        hot = _hot_flag(rec)
        l1 = _link(adj, n, a1)
        l2 = _link(adj, n, a2)
        link_sum = l1 + l2
        base = _score_weak_candidate(rec, adj, anchors)
        rows.append((n, gap, p, hot, link_sum, base, l1, l2))

    if len(rows) < 3:
        return []

    tail = sorted([(gap, n) for n, gap, p, hot, ls, base, l1, l2 in rows], key=lambda x: (x[0], x[1]), reverse=True)
    lowp = sorted([(p, n) for n, gap, p, hot, ls, base, l1, l2 in rows], key=lambda x: (x[0], x[1]))

    link = []
    for n, gap, p, hot, ls, base, l1, l2 in rows:
        score = ls - 0.01 * abs(gap - 7.0)
        link.append((score, n))
    link.sort(key=lambda x: (x[0], x[1]), reverse=True)

    hotlowp = [(p, -gap, n) for n, gap, p, hot, ls, base, l1, l2 in rows if hot == 1 and gap >= gap_min]
    hotlowp.sort(key=lambda x: (x[0], x[1], x[2]))
    hotlowp = [(0.0, n) for _, _, n in hotlowp]

    by_base = sorted([(base, n) for n, gap, p, hot, ls, base, l1, l2 in rows], key=lambda x: (x[0], x[1]), reverse=True)

    pair_cache: Dict[Tuple[int, int], float] = {}
    def wlink(x: int, y: int) -> float:
        key = (x, y) if x < y else (y, x)
        if key in pair_cache:
            return pair_cache[key]
        v = _link(adj, x, y)
        pair_cache[key] = v
        return v

    feat = {n: (gap, hot, base) for n, gap, p, hot, ls, base, l1, l2 in rows}

    def cohesive_triad() -> List[int]:
        cand = [n for _, n in by_base[:12]]
        best_tri = None
        best_score = None
        for i in range(len(cand)):
            for j in range(i + 1, len(cand)):
                for k in range(j + 1, len(cand)):
                    x, y, z = cand[i], cand[j], cand[k]
                    gx, hx, bx = feat[x]
                    gy, hy, by = feat[y]
                    gz, hz, bz = feat[z]
                    cohesion = wlink(x, y) + wlink(x, z) + wlink(y, z)
                    gap_norm = (gx + gy + gz) / (3.0 * max_gap)
                    fresh_pen = (1.0 if gx <= 2.0 else 0.0) + (1.0 if gy <= 2.0 else 0.0) + (1.0 if gz <= 2.0 else 0.0)
                    score = (bx + by + bz) + cohesion_w * cohesion + tail_bonus_w * gap_norm - 0.35 * fresh_pen
                    tri = tuple(sorted((x, y, z)))
                    if best_score is None or score > best_score + 1e-12 or (abs(score - best_score) <= 1e-12 and tri < best_tri):
                        best_score = score
                        best_tri = tri
        return list(best_tri) if best_tri else []

    def split_anchor(offset1: int, offset2: int) -> List[int]:
        s1 = [(l1, gap, n) for n, gap, p, hot, ls, base, l1, l2 in rows if l1 > 0.0 and l2 == 0.0]
        s1.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
        s2 = [(l2, gap, n) for n, gap, p, hot, ls, base, l1, l2 in rows if l2 > 0.0 and l1 == 0.0]
        s2.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)

        picked: List[int] = []
        local_banned = set(banned)
        if s1:
            n1 = s1[min(offset1, len(s1) - 1)][2]
            picked.append(n1)
            local_banned.add(n1)
        if s2:
            n2 = s2[min(offset2, len(s2) - 1)][2]
            if n2 in local_banned and len(s2) > 1:
                n2 = s2[min(offset2 + 1, len(s2) - 1)][2]
            if n2 not in local_banned:
                picked.append(n2)
                local_banned.add(n2)
        if len(picked) < 2:
            picked += _pick_unique(link, local_banned, 2 - len(picked))
        if len(picked) >= 2:
            best = None
            best_s = None
            for n, gap, p, hot, ls, base, l1, l2 in rows:
                if n in local_banned:
                    continue
                cohesion = wlink(n, picked[0]) + wlink(n, picked[1])
                gap_norm = gap / max_gap
                score = 0.55 * ls + 0.45 * cohesion + 0.15 * gap_norm
                if best_s is None or score > best_s + 1e-12 or (abs(score - best_s) <= 1e-12 and n < best):
                    best_s = score
                    best = n
            if best is not None:
                picked.append(best)
        else:
            picked += _pick_unique(link, local_banned, 3 - len(picked))
        return picked[:3]

    mode = ticket_index % 9
    if mode in (0, 7):
        picked: List[int] = []
        picked += _pick_unique(tail, banned, 1)
        picked += _pick_unique(hotlowp if hotlowp else lowp, banned, 2)
        return picked[:3]
    if mode in (3, 8):
        tri = cohesive_triad()
        if tri:
            picked: List[int] = []
            local_banned = set(banned)
            for n in tri:
                if n not in local_banned:
                    picked.append(n)
                    local_banned.add(n)
            if len(picked) < 3:
                picked += _pick_unique(link, local_banned, 3 - len(picked))
            return picked[:3]
    if mode == 4:
        return split_anchor(offset1=3, offset2=3)
    if mode == 5:
        picked: List[int] = []
        local_banned = set(banned)
        picked += _pick_unique(tail, local_banned, 1)
        s2 = [(l2, gap, n) for n, gap, p, hot, ls, base, l1, l2 in rows if l2 > 0.0 and l1 == 0.0 and n not in local_banned]
        s2.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
        if s2:
            n2 = s2[min(3, len(s2) - 1)][2]
            if n2 not in local_banned:
                picked.append(n2)
                local_banned.add(n2)
        if len(picked) < 2:
            picked += _pick_unique(link, local_banned, 2 - len(picked))
        picked += _pick_unique(link, local_banned, 3 - len(picked))
        return picked[:3]
    if mode == 6:
        return split_anchor(offset1=2, offset2=2)

    rot = ticket_index % max(1, len(by_base))
    rot_list = by_base[rot:] + by_base[:rot]
    picked = _pick_unique(rot_list, banned, 3)
    if len(picked) < 3:
        picked += _pick_unique(by_base, banned, 3 - len(picked))
    return picked[:3]

def _profile_shape_stats(pool_m: List[Dict[str, Any]], pool_w: List[Dict[str, Any]]) -> Dict[str, int]:
    return {
        "freshM": sum(1 for r in pool_m if _gap(r) <= 1.0 and _p_next(r) >= 0.75),
        "dueM": sum(1 for r in pool_m if 5.0 <= _gap(r) <= 8.0 and _p_next(r) >= 0.68),
        "lowpM": sum(1 for r in pool_m if 2.0 <= _gap(r) <= 6.0 and _p_next(r) <= 0.45),
        "nonhotTailW": sum(1 for r in pool_w if _hot_flag(r) == 0 and 5.0 <= _gap(r) <= 12.0),
        "lowpW": sum(1 for r in pool_w if _p_next(r) <= 0.45 and _gap(r) >= 3.0),
        "hotlowpW": sum(1 for r in pool_w if _hot_flag(r) == 1 and _p_next(r) <= 0.45 and _gap(r) >= 3.0),
    }


def _candidate_sparse_1m4w(pool_m: List[Dict[str, Any]], pool_w: List[Dict[str, Any]]) -> List[int]:
    m_cands = sorted(
        [r for r in pool_m if _hot_flag(r) == 1 and _gap(r) == 2.0 and _p_next(r) <= 0.45],
        key=lambda r: (_pair_strength(r), _node_score(r)),
    )
    if not m_cands:
        return []
    w_lowp = sorted(
        [r for r in pool_w if _hot_flag(r) == 0 and 4.0 <= _gap(r) <= 6.0 and _p_next(r) <= 0.45],
        key=lambda r: (_pair_strength(r), _node_score(r), -_gap(r)),
        reverse=True,
    )
    w_duetail = sorted(
        [r for r in pool_w if _hot_flag(r) == 0 and 5.0 <= _gap(r) <= 7.0 and _p_next(r) >= 0.60],
        key=lambda r: (_node_score(r), _pair_strength(r)),
        reverse=True,
    )
    w_midtail = sorted(
        [r for r in pool_w if _hot_flag(r) == 0 and 8.0 <= _gap(r) <= 10.0 and _pair_strength(r) <= 0.36],
        key=lambda r: (_gap(r), _node_score(r)),
        reverse=True,
    )
    w_tail = sorted(
        [r for r in pool_w if _hot_flag(r) == 0 and 9.0 <= _gap(r) <= 12.0],
        key=lambda r: (_node_score(r), _pair_strength(r)),
        reverse=True,
    )
    picks: List[int] = []
    used: set[int] = set()
    for seq in ([m_cands[0]] if m_cands else [], [w_lowp[0]] if w_lowp else [], [w_duetail[0]] if w_duetail else [], [w_midtail[0]] if w_midtail else [], [w_tail[0]] if w_tail else []):
        for rec in seq:
            n = _num(rec)
            if n > 0 and n not in used:
                used.add(n)
                picks.append(n)
    extra = sorted([r for r in pool_w if _hot_flag(r) == 0 and 5.0 <= _gap(r) <= 12.0], key=lambda r: (_gap(r), _node_score(r)), reverse=True)
    for rec in extra:
        if len(picks) >= 5:
            break
        n = _num(rec)
        if n > 0 and n not in used:
            used.add(n)
            picks.append(n)
    return sorted(picks) if len(picks) == 5 else []


def _candidate_dense_3m2w(pool_m: List[Dict[str, Any]], pool_w: List[Dict[str, Any]]) -> List[int]:
    m_power = sorted(
        [r for r in pool_m if _hot_flag(r) == 0 and 4.0 <= _gap(r) <= 6.0 and _p_next(r) <= 0.45],
        key=lambda r: (_node_score(r), _pair_strength(r)),
        reverse=True,
    )
    m_due = sorted(
        [r for r in pool_m if 5.0 <= _gap(r) <= 8.0 and _p_next(r) >= 0.68],
        key=lambda r: (_node_score(r), _pair_strength(r)),
        reverse=True,
    )
    w_hotlowp = sorted(
        [r for r in pool_w if _hot_flag(r) == 1 and _p_next(r) <= 0.45 and _gap(r) >= 3.0],
        key=lambda r: (_pair_strength(r), _node_score(r), _gap(r)),
        reverse=True,
    )
    w_tail = sorted(
        [r for r in pool_w if _hot_flag(r) == 0 and 8.0 <= _gap(r) <= 12.0],
        key=lambda r: (_node_score(r), _pair_strength(r)),
        reverse=True,
    )
    if not (m_power and len(m_due) >= 2 and w_hotlowp and w_tail):
        return []
    picks: List[int] = []
    used: set[int] = set()
    for rec in (m_power[0], m_due[0], m_due[1], w_hotlowp[0], w_tail[0]):
        n = _num(rec)
        if n > 0 and n not in used:
            used.add(n)
            picks.append(n)
    return sorted(picks) if len(picks) == 5 else []


def _repair_sparse_candidate_to_target(ticket: List[int], pool_m: List[Dict[str, Any]], pool_w: List[Dict[str, Any]]) -> List[int]:
    if not ticket:
        return []
    med = {_num(r): r for r in pool_m}
    weak = {_num(r): r for r in pool_w}
    m = [n for n in ticket if n in med]
    w = [n for n in ticket if n in weak]
    if len(m) != 1 or len(w) != 4:
        return []
    anchor = m[0]
    adj = _build_adjacency(list(pool_m) + list(pool_w))

    def mutual(n: int) -> float:
        return sum(_link(adj, n, x) for x in w if x != n)

    keep = sorted(
        w,
        key=lambda n: (mutual(n), -_p_next(weak[n]), _gap(weak[n]), _pair_strength(weak[n])),
        reverse=True,
    )[:3]
    fresh_cands = [r for r in pool_m if _num(r) != anchor and _gap(r) <= 2.0 and _p_next(r) >= 0.70]
    if not fresh_cands:
        fresh_cands = [r for r in pool_m if _num(r) != anchor]
    if not fresh_cands:
        return []
    fresh = sorted(
        fresh_cands,
        key=lambda r: (_p_next(r), -_node_score(r), _pair_strength(r)),
        reverse=True,
    )[0]
    out = sorted([anchor, _num(fresh), *keep])
    return out if len(out) == 5 else []


def _repair_dense_candidate_to_target(ticket: List[int], pool_m: List[Dict[str, Any]], pool_w: List[Dict[str, Any]]) -> List[int]:
    if not ticket:
        return []
    med = {_num(r): r for r in pool_m}
    weak = {_num(r): r for r in pool_w}
    m = [n for n in ticket if n in med]
    w = [n for n in ticket if n in weak]
    if len(m) != 3 or len(w) != 2:
        return []
    low = min(m, key=lambda n: _p_next(med[n]))
    due = max(
        m,
        key=lambda n: ((4.0 <= _gap(med[n]) <= 8.0 and _p_next(med[n]) >= 0.60), _gap(med[n]), _p_next(med[n]), _node_score(med[n])),
    )
    keep = list(dict.fromkeys([low, due]))
    if len(keep) < 2:
        for n in sorted(m, key=lambda x: (_node_score(med[x]), _pair_strength(med[x])), reverse=True):
            if n not in keep:
                keep.append(n)
                break
    if len(keep) != 2:
        return []
    adj = _build_adjacency(list(pool_m) + list(pool_w))
    cands = [n for n in weak if n not in w]
    if not cands:
        return []
    add = max(
        cands,
        key=lambda n: (sum(_link(adj, n, x) for x in keep), _pair_strength(weak[n]), _gap(weak[n]), _node_score(weak[n])),
    )
    out = sorted([*keep, *w, add])
    return out if len(out) == 5 else []


def _inject_ticket(tickets: List[List[int]], seen: set[Tuple[int, ...]], ticket: List[int], quota: int) -> None:
    if len(ticket) != 5:
        return
    key = tuple(sorted(ticket))
    if key in seen:
        return
    if len(tickets) >= quota:
        if tickets:
            old = tuple(sorted(tickets[-1]))
            seen.discard(old)
            tickets[-1] = sorted(ticket)
            seen.add(key)
        return
    tickets.append(sorted(ticket))
    seen.add(key)


def _medium_numbers(pool_m: List[Dict[str, Any]]) -> set[int]:
    return {_num(r) for r in pool_m}


def _build_dense_core(metrics: Sequence[Dict[str, Any]], quota: int, params: Optional[GenParams] = None) -> List[List[int]]:
    medium_pool, weak_pool = _build_pools(metrics)
    adj = _build_adjacency(metrics)
    medium_numbers = _medium_numbers(medium_pool)
    tickets: List[List[int]] = []
    seen: set[Tuple[int, ...]] = set()
    quota_i = int(quota or 9)
    overlap_max = params.overlap_max if params else 5

    for idx in range(quota_i):
        use_secondary = idx >= 4
        anchors = _select_medium_anchors_secondary(medium_pool, idx) if use_secondary else _select_medium_anchors(medium_pool, idx)
        if len(anchors) != 2:
            continue
        weak = _select_weak_secondary(weak_pool, adj, anchors, idx) if use_secondary else _select_weak_roles(weak_pool, adj, anchors, idx)
        if len(weak) != 3:
            continue
        ticket = sorted(anchors + weak)
        if sum(1 for n in ticket if n in medium_numbers) != 2:
            continue
        key = tuple(ticket)
        if any(len(set(ticket) & set(old)) >= overlap_max for old in seen):
            continue
        if key not in seen:
            tickets.append(ticket)
            seen.add(key)

    attempts = 0
    while len(tickets) < quota_i and attempts < 50 and medium_pool and weak_pool:
        attempts += 1
        ranked_m = [n for _, n, _ in sorted(((_score_medium_anchor(r), _num(r), r) for r in medium_pool), reverse=True)]
        a = ranked_m[(attempts + 0) % len(ranked_m)]
        b = ranked_m[(attempts + 7) % len(ranked_m)]
        if a == b and len(ranked_m) > 1:
            b = ranked_m[(attempts + 8) % len(ranked_m)]
        anchors = [a, b]
        scored_w = sorted([(_score_weak_candidate(r, adj, anchors), _num(r)) for r in weak_pool], reverse=True)
        banned = set(anchors)
        weak = _pick_unique(scored_w, banned, 3)
        if len(weak) != 3:
            continue
        ticket = sorted(anchors + weak)
        if sum(1 for n in ticket if n in medium_numbers) != 2:
            continue
        key = tuple(ticket)
        if key not in seen:
            tickets.append(ticket)
            seen.add(key)

    return tickets[: quota_i]


def _score_transition_medium(rec: Dict[str, Any]) -> float:
    entropy = _f(rec.get("transition_entropy"), 1.0)
    return (
        0.34 * _node_score(rec)
        + 0.24 * _p_next(rec)
        + 0.16 * _pair_strength(rec)
        + 0.10 * _triad_strength(rec)
        + 0.08 * _glue(rec)
        + 0.08 * max(0.0, 1.2 - entropy)
    )


def _score_transition_weak(rec: Dict[str, Any], adj: Dict[int, Dict[int, float]], anchors: Sequence[int]) -> float:
    entropy = _f(rec.get("transition_entropy"), 1.0)
    n = _num(rec)
    return (
        0.28 * _node_score(rec)
        + 0.22 * _p_next(rec)
        + 0.16 * _pair_strength(rec)
        + 0.10 * _triad_strength(rec)
        + 0.08 * _glue(rec)
        + 0.08 * sum(_link(adj, n, a) for a in anchors)
        + 0.08 * max(0.0, 1.2 - entropy)
    )


def _build_transition_core(metrics: Sequence[Dict[str, Any]], quota: int, params: Optional[GenParams] = None) -> List[List[int]]:
    medium_pool, weak_pool = _build_pools(metrics)
    adj = _build_adjacency(metrics)
    quota_i = int(quota or 9)
    overlap_max = params.overlap_max if params else 5
    ranked_m = [n for _, n in sorted(((_score_transition_medium(r), _num(r)) for r in medium_pool), reverse=True)]
    tickets: List[List[int]] = []
    seen: set[Tuple[int, ...]] = set()
    for idx in range(quota_i * 2):
        if len(ranked_m) < 2:
            break
        a = ranked_m[idx % len(ranked_m)]
        b = ranked_m[(idx + 1 + (idx // 2)) % len(ranked_m)]
        if a == b:
            continue
        anchors = [a, b]
        scored_w = sorted([(_score_transition_weak(r, adj, anchors), _num(r)) for r in weak_pool], reverse=True)
        weak = _pick_unique(scored_w, set(anchors), 3)
        if len(weak) != 3:
            continue
        ticket = sorted(anchors + weak)
        key = tuple(ticket)
        if any(len(set(ticket) & set(old)) >= overlap_max for old in seen):
            continue
        if key not in seen:
            tickets.append(ticket)
            seen.add(key)
        if len(tickets) >= quota_i:
            break
    return tickets[:quota_i]


def _split_anchor_pair(pool_m: List[Dict[str, Any]]) -> Optional[Tuple[int, int]]:
    due = sorted(
        [r for r in pool_m if 1.0 <= _gap(r) <= 3.0 and _p_next(r) <= 0.55],
        key=lambda r: (_node_score(r), _pair_strength(r), -_p_next(r)),
        reverse=True,
    )
    fresh = sorted(
        [r for r in pool_m if _gap(r) <= 2.0 and _p_next(r) >= 0.70],
        key=lambda r: (_p_next(r), -_node_score(r), _pair_strength(r)),
        reverse=True,
    )
    if not due or not fresh:
        return None
    a = _num(due[0])
    b = next((_num(r) for r in fresh if _num(r) != a), None)
    if not b:
        return None
    return a, b


def _build_split_core(metrics: Sequence[Dict[str, Any]], quota: int, params: Optional[GenParams] = None, base_ticket: Optional[List[int]] = None) -> List[List[int]]:
    medium_pool, weak_pool = _build_pools(metrics)
    adj = _build_adjacency(metrics)
    quota_i = int(quota or 9)
    tickets: List[List[int]] = []
    seen: set[Tuple[int, ...]] = set()
    if base_ticket:
        _inject_ticket(tickets, seen, base_ticket, quota_i)

    anchor_pair = _split_anchor_pair(medium_pool)
    if anchor_pair is None:
        return tickets[:quota_i]
    due_anchor, fresh_anchor = anchor_pair

    def due_score(rec: Dict[str, Any]) -> float:
        n = _num(rec)
        return (
            0.46 * _link(adj, n, due_anchor)
            + 0.18 * _pair_strength(rec)
            + 0.10 * _triad_strength(rec)
            + 0.10 * _glue(rec)
            + 0.10 * (1.0 - _p_next(rec))
            + 0.06 * min(_gap(rec), 12.0) / 12.0
        )

    def fresh_pair_score(a: int, b: int) -> float:
        ra = next(r for r in weak_pool if _num(r) == a)
        rb = next(r for r in weak_pool if _num(r) == b)
        return (
            0.42 * _link(adj, a, b)
            + 0.22 * (_link(adj, a, fresh_anchor) + _link(adj, b, fresh_anchor))
            + 0.12 * (_pair_strength(ra) + _pair_strength(rb))
            + 0.10 * (_node_score(ra) + _node_score(rb))
            + 0.07 * (min(_gap(ra), 12.0) + min(_gap(rb), 12.0)) / 12.0
            - 0.08 * (_link(adj, a, due_anchor) + _link(adj, b, due_anchor))
        )

    due_ranked = [_num(r) for r in sorted(weak_pool, key=due_score, reverse=True)]
    weak_ids = [_num(r) for r in weak_pool]
    pair_ranked = sorted(
        [(fresh_pair_score(a, b), (a, b)) for i, a in enumerate(weak_ids) for b in weak_ids[i + 1 :]],
        reverse=True,
    )

    for idx in range(quota_i * 4):
        wd = None
        for cand in due_ranked[idx % max(1, len(due_ranked)) :] + due_ranked[: idx % max(1, len(due_ranked))]:
            if cand not in {due_anchor, fresh_anchor}:
                wd = cand
                break
        if wd is None:
            continue
        pair = None
        for _, (a, b) in pair_ranked:
            if len({a, b, wd, due_anchor, fresh_anchor}) == 5:
                pair = (a, b)
                break
        if pair is None:
            continue
        ticket = sorted([due_anchor, fresh_anchor, wd, pair[0], pair[1]])
        _inject_ticket(tickets, seen, ticket, quota_i)
        if len(tickets) >= quota_i:
            break

    if len(tickets) < quota_i:
        dense = _build_dense_core(metrics, quota, params)
        for t in dense:
            _inject_ticket(tickets, seen, t, quota_i)
            if len(tickets) >= quota_i:
                break
    return tickets[:quota_i]


def build_mode_a(metrics: Sequence[Dict[str, Any]], quota: int, params: Optional[GenParams] = None) -> List[List[int]]:
    """MODE_A is not evidenced on the current self-series and is disabled for runtime."""
    return []


def build_mode_b(metrics: Sequence[Dict[str, Any]], quota: int, params: Optional[GenParams] = None) -> List[List[int]]:
    medium_pool, weak_pool = _build_pools(metrics)
    candidate = _repair_dense_candidate_to_target(_candidate_dense_3m2w(medium_pool, weak_pool), medium_pool, weak_pool)
    tickets = _build_dense_core(metrics, quota, params)
    if candidate:
        seen = {tuple(sorted(t)) for t in tickets}
        _inject_ticket(tickets, seen, candidate, int(quota or 9))
    return tickets[: int(quota or 9)]


def build_mode_c(metrics: Sequence[Dict[str, Any]], quota: int, params: Optional[GenParams] = None) -> List[List[int]]:
    medium_pool, weak_pool = _build_pools(metrics)
    candidate = _repair_sparse_candidate_to_target(_candidate_sparse_1m4w(medium_pool, weak_pool), medium_pool, weak_pool)
    return _build_split_core(metrics, quota, params, candidate)


def generate_for_mode(metrics: Dict[str, Any] | Sequence[Dict[str, Any]], mode: str, quota: int, params: Optional[GenParams] = None) -> List[List[int]]:
    numbers = metrics.get("numbers", []) if isinstance(metrics, dict) else list(metrics)
    if mode == "MODE_B":
        return build_mode_b(numbers, quota, params)
    if mode == "MODE_C":
        return build_mode_c(numbers, quota, params)
    return build_mode_a(numbers, quota, params)
