# -*- coding: utf-8 -*-
"""HARD_2M2W1S clean profile.

Runtime contract
- source: draw_metrics(T-1) only
- detector mode is passed from generator
- active runtime mode for this profile: MODE_B only
- MODE_A / MODE_C are explicit but not closed and must not be substituted

Shape contract
- target ticket shape: 1 strong + 2 medium + 2 weak
- no winners / carcass / draw_id / external model / prefit tables
- no sandbox / routing / detector logic inside profile

MODE_B build idea
1) choose strong anchor from topology-dense strong pool
2) choose 2 medium anchors by density + link to strong anchor
3) choose weak bridge and weak tail by pair/glue/triad coverage
4) generate a compact portfolio of variants around the same MODE_B topology core
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

PROFILE_ID = "HARD_2M2W1S"
SUPPORTED_MODES = ("MODE_A", "MODE_B", "MODE_C")
CLOSED_MODES = ("MODE_B",)
ACTIVE_RUNTIME_MODES = ("MODE_B",)
NOT_READY_MODES = ("MODE_A", "MODE_C")
TARGET_COUNTS = {"S": 1, "M": 2, "W": 2}


@dataclass
class GenParams:
    seed: Optional[int] = None
    rng_seed: Optional[int] = None
    deterministic: bool = True
    overlap_max: int = 4
    diversity_min: int = 1


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


def _zone_key(rec: Dict[str, Any]) -> str:
    z = _zone(rec)
    if z.endswith("strong"):
        return "strong"
    if z.endswith("medium"):
        return "medium"
    if z.endswith("weak"):
        return "weak"
    return ""


def _hot_flag(rec: Dict[str, Any]) -> int:
    hot = rec.get("hot", {})
    if isinstance(hot, dict):
        return _i(hot.get("flag"), 0)
    return _i(hot, 0)


def _stable_numbers(series: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [r for r in series if isinstance(r, dict) and _type(r) == "stable"]


def _feature(rec: Dict[str, Any], key: str) -> float:
    return _f(rec.get(key), 0.0)


def _link(adj: Dict[int, Dict[int, float]], a: int, b: int) -> float:
    return max(adj.get(a, {}).get(b, 0.0), adj.get(b, {}).get(a, 0.0))


def _build_context(metrics: Dict[str, Any]) -> Tuple[Dict[str, List[int]], Dict[int, Dict[str, Any]], Dict[int, Dict[int, float]]]:
    pools: Dict[str, List[int]] = {"strong": [], "medium": [], "weak": []}
    recmap: Dict[int, Dict[str, Any]] = {}
    adj: Dict[int, Dict[int, float]] = {}
    stable_nums = set()

    for rec in _stable_numbers(metrics.get("numbers") or []):
        n = _num(rec)
        if n <= 0:
            continue
        recmap[n] = rec
        adj.setdefault(n, {})
        stable_nums.add(n)
        key = _zone_key(rec)
        if key:
            pools[key].append(n)

    for n, rec in recmap.items():
        for item in rec.get("top_pairs") or []:
            if not isinstance(item, dict):
                continue
            m = _i(item.get("n"), -1)
            w = _f(item.get("w"), 0.0)
            if m in stable_nums and w > 0:
                adj[n][m] = w

    return pools, recmap, adj


def _density_score(rec: Dict[str, Any]) -> float:
    return (
        0.34 * _feature(rec, "pair_strength")
        + 0.28 * _feature(rec, "triad_strength")
        + 0.18 * _feature(rec, "glue_index")
        + 0.14 * _feature(rec, "node_score")
        + 0.06 * _hot_flag(rec)
    )


def _strong_score(rec: Dict[str, Any]) -> float:
    return (
        0.42 * _feature(rec, "node_score")
        + 0.22 * _feature(rec, "pair_strength")
        + 0.18 * _feature(rec, "triad_strength")
        + 0.10 * _feature(rec, "glue_index")
        + 0.08 * _hot_flag(rec)
    )


def _medium_score(rec: Dict[str, Any], strong_anchor: int, adj: Dict[int, Dict[int, float]]) -> float:
    return _density_score(rec) + 0.55 * _link(adj, _num(rec), strong_anchor)


def _weak_bridge_score(rec: Dict[str, Any], anchors: Sequence[int], adj: Dict[int, Dict[int, float]]) -> float:
    n = _num(rec)
    return (
        0.32 * _feature(rec, "pair_strength")
        + 0.24 * _feature(rec, "glue_index")
        + 0.20 * _feature(rec, "triad_strength")
        + 0.14 * sum(_link(adj, n, a) for a in anchors)
        + 0.10 * _feature(rec, "state_next_p")
    )


def _weak_tail_score(rec: Dict[str, Any], anchors: Sequence[int], adj: Dict[int, Dict[int, float]]) -> float:
    n = _num(rec)
    return (
        0.28 * _feature(rec, "gap_last")
        + 0.22 * _feature(rec, "state_next_p")
        + 0.20 * _feature(rec, "glue_index")
        + 0.18 * sum(_link(adj, n, a) for a in anchors)
        + 0.12 * _hot_flag(rec)
    )


def _rank_strongs(strongs: Sequence[int], recmap: Dict[int, Dict[str, Any]]) -> List[int]:
    return sorted(strongs, key=lambda n: (_strong_score(recmap[n]), n), reverse=True)


def _rank_mediums(mediums: Sequence[int], recmap: Dict[int, Dict[str, Any]], adj: Dict[int, Dict[int, float]], strong_anchor: int) -> List[int]:
    return sorted(mediums, key=lambda n: (_medium_score(recmap[n], strong_anchor, adj), n), reverse=True)


def _rank_weak_bridges(weaks: Sequence[int], recmap: Dict[int, Dict[str, Any]], adj: Dict[int, Dict[int, float]], anchors: Sequence[int]) -> List[int]:
    return sorted(weaks, key=lambda n: (_weak_bridge_score(recmap[n], anchors, adj), n), reverse=True)


def _rank_weak_tails(weaks: Sequence[int], recmap: Dict[int, Dict[str, Any]], adj: Dict[int, Dict[int, float]], anchors: Sequence[int]) -> List[int]:
    return sorted(weaks, key=lambda n: (_weak_tail_score(recmap[n], anchors, adj), n), reverse=True)


def _ticket_score(ticket: Sequence[int], recmap: Dict[int, Dict[str, Any]], adj: Dict[int, Dict[int, float]]) -> float:
    nums = list(ticket)
    pairs = 0.0
    for i in range(len(nums)):
        for j in range(i + 1, len(nums)):
            pairs += _link(adj, nums[i], nums[j])
    feats = sum(_feature(recmap[n], "pair_strength") + _feature(recmap[n], "triad_strength") + _feature(recmap[n], "glue_index") for n in nums)
    return feats + 0.7 * pairs


def _shape_ok(ticket: Sequence[int], recmap: Dict[int, Dict[str, Any]]) -> bool:
    s = m = w = 0
    for n in ticket:
        key = _zone_key(recmap[n])
        if key == "strong":
            s += 1
        elif key == "medium":
            m += 1
        elif key == "weak":
            w += 1
    return (s, m, w) == (1, 2, 2)


def _overlap(a: Sequence[int], b: Sequence[int]) -> int:
    return len(set(a) & set(b))


def _unique_tickets(candidates: Sequence[Tuple[float, Tuple[int, ...]]], quota: int, params: Optional[GenParams]) -> List[List[int]]:
    out: List[List[int]] = []
    seen = set()
    overlap_max = params.overlap_max if params else 4
    for _, ticket in candidates:
        key = tuple(ticket)
        if key in seen:
            continue
        if any(_overlap(ticket, prev) > overlap_max for prev in out):
            continue
        seen.add(key)
        out.append(list(ticket))
        if len(out) >= quota:
            break
    return out


def build_mode_b(metrics: Dict[str, Any], quota: int, params: Optional[GenParams] = None) -> List[List[int]]:
    pools, recmap, adj = _build_context(metrics)
    strongs = _rank_strongs(pools["strong"], recmap)[:5]
    if not strongs:
        return []

    candidates: List[Tuple[float, Tuple[int, ...]]] = []

    for strong_anchor in strongs:
        mediums_ranked = _rank_mediums(pools["medium"], recmap, adj, strong_anchor)[:8]
        for i in range(len(mediums_ranked)):
            for j in range(i + 1, len(mediums_ranked)):
                m1, m2 = mediums_ranked[i], mediums_ranked[j]
                anchors = (strong_anchor, m1, m2)
                weak_bridge_ranked = [n for n in _rank_weak_bridges(pools["weak"], recmap, adj, anchors) if n not in anchors][:8]
                weak_tail_ranked = [n for n in _rank_weak_tails(pools["weak"], recmap, adj, anchors) if n not in anchors][:8]

                for wb in weak_bridge_ranked[:4]:
                    for wt in weak_tail_ranked[:5]:
                        if wt == wb:
                            continue
                        ticket = tuple(sorted((strong_anchor, m1, m2, wb, wt)))
                        if not _shape_ok(ticket, recmap):
                            continue
                        score = _ticket_score(ticket, recmap, adj)
                        candidates.append((score, ticket))

    candidates.sort(reverse=True)
    tickets = _unique_tickets(candidates, quota, params)

    if len(tickets) < quota:
        for _, ticket in candidates:
            t = list(ticket)
            if t not in tickets:
                tickets.append(t)
                if len(tickets) >= quota:
                    break
    return tickets[:quota]


def build_mode_a(metrics: Dict[str, Any], quota: int, params: Optional[GenParams] = None) -> List[List[int]]:
    return []


def build_mode_c(metrics: Dict[str, Any], quota: int, params: Optional[GenParams] = None) -> List[List[int]]:
    return []


def generate_for_mode(metrics: Dict[str, Any], mode: str, quota: int, params: Optional[GenParams] = None) -> List[List[int]]:
    if mode == "MODE_B":
        return build_mode_b(metrics, quota, params)
    if mode == "MODE_A":
        return build_mode_a(metrics, quota, params)
    if mode == "MODE_C":
        return build_mode_c(metrics, quota, params)
    return []
