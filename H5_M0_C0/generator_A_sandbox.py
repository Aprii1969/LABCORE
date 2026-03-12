# -*- coding: utf-8 -*-
"""Clean generic generator sandbox.

Contract:
- one runtime detector in generator;
- no hard-coded profile maps;
- no portfolio fallback fill / signature overrides / winners plumbing;
- profiles are loaded dynamically from external files;
- template routing is read from external carcasses registry only;
- profile receives only metrics + detected mode + quota + params.
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


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
    trace: bool = False
    trace_dir: str = "rolling/debug"
    draw_id: Optional[int] = None
    cover_tickets: int = 0


MODE_DETECTOR_CONFIG: Dict[str, Any] = {
    "top_k": 20,
    "strong_edge_q": 0.85,
    "guard_a": {
        "next_mean": 0.59,
        "entropy_mean": 1.04,
        "density_mean": 0.82,
    },
    "guard_b": {
        "density_mean": 0.84,
        "coef_mean": 0.90,
        "component_1_size": 10,
    },
    "guard_c": {
        "component_2_size": 5,
        "cross_ratio": 0.25,
        "component_balance": 0.35,
    },
    "resolver_thresholds": {
        "MODE_C": 1.75,
        "MODE_A": 0.78,
        "MODE_B": 2.20,
    },
    # metrics-only evidence for split/dual-cluster edge cases like 3765
    "split_hint_bonus": 0.75,
}


_PROFILE_CACHE: Dict[Tuple[str, str], Any] = {}


def _root() -> Path:
    return Path(__file__).resolve().parent


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


def _stable_numbers(metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
    nums = (metrics or {}).get("numbers") or []
    return [r for r in nums if isinstance(r, dict) and str(r.get("type_name", "")).strip().lower() == "stable"]


def _group_label(rec: Dict[str, Any]) -> str:
    return f"{str(rec.get('type_name') or '').strip().lower()}.{str(rec.get('zone_name') or '').strip().lower()}"


def _compute_mode_features(metrics: Dict[str, Any]) -> Dict[str, Any]:
    stable = _stable_numbers(metrics)
    if not stable:
        return {
            "top_k": MODE_DETECTOR_CONFIG["top_k"],
            "anchor_mass": 0.0,
            "peak_ratio": 0.0,
            "next_mean": 0.0,
            "entropy_mean": 9.9,
            "entropy_inverse": 0.0,
            "density_mean": 0.0,
            "coef_mean": 0.0,
            "component_1_size": 0,
            "component_2_size": 0,
            "component_balance": 0.0,
            "cross_ratio": 1.0,
            "dominant_groups_differ": False,
            "dominant_group_1": None,
            "dominant_group_2": None,
            "fresh_m": 0,
            "due_m": 0,
            "tail_w": 0,
            "hotlowp_w": 0,
            "split_hint_c": False,
            "strong_edge_thr": 0.0,
        }

    top_k = int(MODE_DETECTOR_CONFIG["top_k"])
    strong_edge_q = float(MODE_DETECTOR_CONFIG["strong_edge_q"])
    top = sorted(stable, key=lambda r: _safe_float(r.get("node_score"), 0.0), reverse=True)[:top_k]

    total_node = sum(max(0.0, _safe_float(r.get("node_score"), 0.0)) for r in stable) or 1.0
    top_nodes = [max(0.0, _safe_float(r.get("node_score"), 0.0)) for r in top]
    mean_top_node = sum(top_nodes) / max(1, len(top_nodes))

    anchor_mass = sum(top_nodes[:5]) / total_node if top_nodes else 0.0
    peak_ratio = (max(top_nodes) / mean_top_node) if mean_top_node > 0 else 0.0
    next_mean = sum(_safe_float(r.get("state_next_p"), 0.0) for r in top) / max(1, len(top))
    entropy_mean = sum(_safe_float(r.get("transition_entropy"), 0.0) for r in top) / max(1, len(top))
    entropy_inverse = 1.0 / (1.0 + entropy_mean)
    density_mean = sum(
        _safe_float(r.get("pair_strength"), 0.0)
        + _safe_float(r.get("glue_index"), 0.0)
        + _safe_float(r.get("triad_strength"), 0.0)
        for r in top
    ) / max(1, len(top))
    coef_mean = sum(_safe_float(r.get("coef_participation"), 0.0) for r in top) / max(1, len(top))

    top_ids = {_safe_int(r.get("n"), -1) for r in top if _safe_int(r.get("n"), -1) > 0}
    weights: List[float] = []
    adj: Dict[int, Dict[int, float]] = {n: {} for n in top_ids}
    labels: Dict[int, str] = {}
    for r in top:
        n = _safe_int(r.get("n"), -1)
        if n <= 0:
            continue
        labels[n] = _group_label(r)
        for p in (r.get("top_pairs") or []):
            if not isinstance(p, dict):
                continue
            m = _safe_int(p.get("n"), -1)
            w = _safe_float(p.get("w"), 0.0)
            if m in top_ids and w > 0:
                adj[n][m] = max(adj[n].get(m, 0.0), w)
                weights.append(w)

    strong_edge_thr = 0.0
    if weights:
        s = sorted(weights)
        idx = min(len(s) - 1, max(0, int(math.ceil(strong_edge_q * len(s)) - 1)))
        strong_edge_thr = s[idx]

    seen = set()
    comps: List[List[int]] = []
    for n in sorted(top_ids):
        if n in seen:
            continue
        stack = [n]
        seen.add(n)
        comp: List[int] = []
        while stack:
            a = stack.pop()
            comp.append(a)
            neigh = {k for k, v in adj.get(a, {}).items() if v >= strong_edge_thr}
            neigh.update({k for k, vals in adj.items() if a in vals and vals[a] >= strong_edge_thr})
            for b in neigh:
                if b not in seen:
                    seen.add(b)
                    stack.append(b)
        comps.append(sorted(comp))
    comps = sorted(comps, key=lambda c: (len(c), c), reverse=True)
    c1 = comps[0] if comps else []
    c2 = comps[1] if len(comps) > 1 else []

    def intra(comp: List[int]) -> float:
        s = 0.0
        comp_set = set(comp)
        for a in comp:
            for b, w in adj.get(a, {}).items():
                if b in comp_set:
                    s += w
        return s / 2.0

    intra1, intra2 = intra(c1), intra(c2)
    cross = 0.0
    set1, set2 = set(c1), set(c2)
    for a in set1:
        for b, w in adj.get(a, {}).items():
            if b in set2:
                cross += w
    cross_ratio = (cross / (intra1 + intra2)) if (intra1 + intra2) > 0 else 1.0

    def dominant_group(comp: List[int]) -> Optional[str]:
        if not comp:
            return None
        cnt = Counter(labels[n] for n in comp if n in labels)
        return cnt.most_common(1)[0][0] if cnt else None

    dg1 = dominant_group(c1)
    dg2 = dominant_group(c2)
    dominant_groups_differ = bool(dg1 and dg2 and dg1 != dg2)

    fresh_m = sum(
        1 for r in stable
        if str(r.get("zone_name", "")).strip().lower().endswith("medium")
        and _safe_float(r.get("gap_last"), 99.0) <= 2.0
        and _safe_float(r.get("state_next_p"), 0.0) >= 0.72
    )
    due_m = sum(
        1 for r in stable
        if str(r.get("zone_name", "")).strip().lower().endswith("medium")
        and 1.0 <= _safe_float(r.get("gap_last"), 0.0) <= 3.0
        and _safe_float(r.get("state_next_p"), 1.0) <= 0.55
    )
    tail_w = sum(
        1 for r in stable
        if str(r.get("zone_name", "")).strip().lower().endswith("weak")
        and _safe_float(r.get("gap_last"), 0.0) >= 5.0
        and _safe_float(r.get("state_next_p"), 1.0) <= 0.70
    )
    hotlowp_w = sum(
        1 for r in stable
        if str(r.get("zone_name", "")).strip().lower().endswith("weak")
        and (int((r.get("hot") or {}).get("flag") or 0) if isinstance(r.get("hot"), dict) else 0) == 1
        and _safe_float(r.get("state_next_p"), 1.0) <= 0.45
        and _safe_float(r.get("gap_last"), 0.0) >= 3.0
    )
    split_hint_c = bool(density_mean < 0.80 and fresh_m >= 1 and due_m >= 2 and tail_w >= 5 and hotlowp_w >= 2)

    return {
        "top_k": top_k,
        "anchor_mass": anchor_mass,
        "peak_ratio": peak_ratio,
        "next_mean": next_mean,
        "entropy_mean": entropy_mean,
        "entropy_inverse": entropy_inverse,
        "density_mean": density_mean,
        "coef_mean": coef_mean,
        "component_1_size": len(c1),
        "component_2_size": len(c2),
        "component_balance": (len(c2) / max(1, len(c1))) if c1 else 0.0,
        "cross_ratio": cross_ratio,
        "dominant_groups_differ": dominant_groups_differ,
        "dominant_group_1": dg1,
        "dominant_group_2": dg2,
        "fresh_m": fresh_m,
        "due_m": due_m,
        "tail_w": tail_w,
        "hotlowp_w": hotlowp_w,
        "split_hint_c": split_hint_c,
        "strong_edge_thr": strong_edge_thr,
    }


def analyze_runtime_mode(metrics: Dict[str, Any]) -> Dict[str, Any]:
    feats = _compute_mode_features(metrics or {})
    if not _stable_numbers(metrics or {}):
        scores = {"MODE_A": 0.0, "MODE_B": 0.0, "MODE_C": 0.0}
        weights = {"MODE_A": 1.0, "MODE_B": 0.0, "MODE_C": 0.0}
        return {
            "mode": "MODE_A",
            "mode_scores": scores,
            "mode_weights": weights,
            "confidence": 0.0,
            "winner_margin": 0.0,
            "cover_plan": ["node_transition_core", "anchor_variation", "fresh_tail"],
            "features": feats,
            "guards": {"guard_A": False, "guard_B": False, "guard_C": False, "split_hint_C": False},
            "triggered_rule": "forced_empty",
            "resolver_path": ["forced_empty"],
        }

    a = 1.90 * feats["anchor_mass"] + 1.25 * feats["next_mean"] + 0.80 * feats["entropy_inverse"] - 0.75 * feats["density_mean"] - 0.10 * (feats["component_2_size"] / feats["top_k"])
    b = 1.45 * feats["density_mean"] + 0.90 * feats["coef_mean"] + 0.60 * (feats["component_1_size"] / feats["top_k"]) - 0.45 * feats["cross_ratio"]
    c = 1.10 * feats["component_balance"] + 1.05 * (1 - min(feats["cross_ratio"], 1.0)) + 0.45 * (1.0 if feats["dominant_groups_differ"] else 0.0) + 0.25 * (feats["component_2_size"] / 5.0) - 0.15 * (feats["component_1_size"] / feats["top_k"])

    ga = feats["next_mean"] >= MODE_DETECTOR_CONFIG["guard_a"]["next_mean"] and feats["entropy_mean"] <= MODE_DETECTOR_CONFIG["guard_a"]["entropy_mean"] and feats["density_mean"] <= MODE_DETECTOR_CONFIG["guard_a"]["density_mean"]
    gb = feats["density_mean"] >= MODE_DETECTOR_CONFIG["guard_b"]["density_mean"] and feats["coef_mean"] >= MODE_DETECTOR_CONFIG["guard_b"]["coef_mean"] and feats["component_1_size"] >= MODE_DETECTOR_CONFIG["guard_b"]["component_1_size"]
    gc = feats["component_2_size"] >= MODE_DETECTOR_CONFIG["guard_c"]["component_2_size"] and feats["dominant_groups_differ"] and feats["cross_ratio"] <= MODE_DETECTOR_CONFIG["guard_c"]["cross_ratio"] and feats["component_balance"] >= MODE_DETECTOR_CONFIG["guard_c"]["component_balance"]

    resolver_steps: List[str] = ["raw_scores"]
    if ga:
        a += 1.25
        resolver_steps.append("guard_A_bonus")
    if gb:
        b += 1.10
        resolver_steps.append("guard_B_bonus")
    if gc:
        c += 1.35
        resolver_steps.append("guard_C_bonus")
    if feats["split_hint_c"]:
        c += MODE_DETECTOR_CONFIG["split_hint_bonus"]
        resolver_steps.append("split_hint_C_bonus")

    scores = {"MODE_A": a, "MODE_B": b, "MODE_C": c}
    ordered = sorted(scores.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)
    thr = MODE_DETECTOR_CONFIG["resolver_thresholds"]

    if gc and c >= float(thr["MODE_C"]):
        mode = "MODE_C"
        triggered_rule = "guard_C_and_score_threshold"
        resolver_steps.append("resolver_guard_C")
    elif ga and a >= float(thr["MODE_A"]):
        mode = "MODE_A"
        triggered_rule = "guard_A_and_score_threshold"
        resolver_steps.append("resolver_guard_A")
    elif gb and b >= float(thr["MODE_B"]):
        mode = "MODE_B"
        triggered_rule = "guard_B_and_score_threshold"
        resolver_steps.append("resolver_guard_B")
    else:
        mode = ordered[0][0]
        triggered_rule = "argmax_scores"
        resolver_steps.append("resolver_argmax")

    confidence = float(ordered[0][1] - ordered[1][1]) if len(ordered) > 1 else 0.0
    mn = min(scores.values())
    norm = {k: (v - mn + 1e-9) for k, v in scores.items()}
    sm = sum(norm.values()) or 1.0
    weights = {k: v / sm for k, v in norm.items()}

    cover = {
        "MODE_A": ["node_transition_core", "node_transition_core", "anchor_variation", "fresh_tail"],
        "MODE_B": ["topology_core", "topology_core", "triad_closure", "dense_bridge"],
        "MODE_C": ["island_A", "island_B", "split_cover", "late_tail"],
    }[mode]

    return {
        "mode": mode,
        "mode_scores": scores,
        "mode_weights": weights,
        "confidence": confidence,
        "winner_margin": confidence,
        "cover_plan": cover,
        "features": feats,
        "guards": {"guard_A": ga, "guard_B": gb, "guard_C": gc, "split_hint_C": feats["split_hint_c"]},
        "triggered_rule": triggered_rule,
        "resolver_path": resolver_steps,
    }


def detect_runtime_mode(metrics: Dict[str, Any]) -> str:
    return analyze_runtime_mode(metrics or {}).get("mode", "MODE_A")


def _normalize_id(value: Optional[str]) -> str:
    return str(value or "").strip().upper()


def _profile_search_dirs(root: Path) -> List[Path]:
    dirs: List[Path] = []
    direct = [root / "h5_generators", root / "profiles", root / "generators"]
    for p in direct:
        if p.is_dir() and p not in dirs:
            dirs.append(p)
    for p in root.iterdir():
        if p.is_dir() and p.name.endswith("_generators") and p not in dirs:
            dirs.append(p)
    return dirs


def _find_profile_path(mode_id: str) -> Path:
    root = _root()
    filename = f"{str(mode_id).strip().lower()}.py"
    candidates = [root / filename]
    for d in _profile_search_dirs(root):
        candidates.append(d / filename)
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError(f"Profile module file not found for mode_id='{mode_id}'")


def _load_profile_module(mode_id: str):
    path = _find_profile_path(mode_id)
    key = (_normalize_id(mode_id), str(path))
    if key in _PROFILE_CACHE:
        return _PROFILE_CACHE[key]
    module_name = f"profile_{key[0].lower()}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load profile module from {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    _PROFILE_CACHE[key] = mod
    return mod


def _templates_registry_candidates(root: Path) -> List[Path]:
    env_path = os.environ.get("CARCASSES_REGISTRY", "").strip()
    out: List[Path] = []
    if env_path:
        p = Path(env_path)
        if not p.is_absolute():
            p = root / p
        out.append(p)
    out.extend(sorted(root.glob("*_carcasses_registry.json")))
    out.append(root / "carcasses_registry.json")
    return out


def _load_templates_registry(root: Path) -> Dict[str, Any]:
    for p in _templates_registry_candidates(root):
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8-sig"))
            except Exception:
                return json.loads(p.read_text(encoding="utf-8"))
    return {"carcasses": {}}


def _load_template_config(template_id: str) -> Dict[str, Any]:
    payload = _load_templates_registry(_root())
    carcasses = payload.get("carcasses") or {}
    cfg = carcasses.get(template_id)
    if not isinstance(cfg, dict):
        raise KeyError(f"Template '{template_id}' not found in carcasses registry")
    return cfg


def _is_template_id(value: str) -> bool:
    if not value:
        return False
    payload = _load_templates_registry(_root())
    carcasses = payload.get("carcasses") or {}
    return value in carcasses


class GeneratorSandbox:
    def __init__(self, metrics_path: str = "", lattice_path: str = "", **_: Any) -> None:
        self.metrics_path = str(metrics_path or "")
        self.lattice_path = str(lattice_path or "")

    def _make_gp(self, impl: Any, draw_id: Optional[int], cover_tickets: int = 0, gp: Optional[Any] = None) -> Any:
        if gp is not None:
            try:
                if hasattr(gp, "draw_id"):
                    gp.draw_id = draw_id
                if hasattr(gp, "cover_tickets"):
                    gp.cover_tickets = int(cover_tickets or 0)
                return gp
            except Exception:
                pass
        gp_cls = getattr(impl, "GenParams", GenParams)
        try:
            gp_obj = gp_cls() if callable(gp_cls) else GenParams()
        except Exception:
            gp_obj = GenParams()
        if hasattr(gp_obj, "draw_id"):
            gp_obj.draw_id = draw_id
        if hasattr(gp_obj, "cover_tickets"):
            gp_obj.cover_tickets = int(cover_tickets or 0)
        return gp_obj

    def generate_template(
        self,
        *,
        template_id: str,
        draw_id: Optional[int],
        metrics: Optional[Dict[str, Any]] = None,
        gp: Optional[Any] = None,
        cover_tickets: int = 0,
        return_meta: bool = False,
    ):
        cfg = _load_template_config(template_id)
        order = [str(x).strip().upper() for x in (cfg.get("order") or []) if str(x).strip()]
        profiles = {str(k).strip().upper(): (v or {}) for k, v in (cfg.get("profiles") or {}).items()}
        m = metrics or {}
        analysis = analyze_runtime_mode(m)
        runtime_mode = str(analysis["mode"]).upper()
        portfolio: List[List[int]] = []
        meta_profiles: Dict[str, Any] = {}
        for profile_id in order:
            rec = profiles.get(profile_id) or {}
            quota = int(rec.get("quota") or 0)
            impl = _load_profile_module(profile_id)
            closed_modes = tuple(str(x).strip().upper() for x in (getattr(impl, "CLOSED_MODES", ()) or ()))
            if closed_modes and runtime_mode not in closed_modes:
                meta_profiles[profile_id] = {
                    "quota": quota,
                    "tickets": [],
                    "skipped": True,
                    "reason": f"runtime_mode={runtime_mode} not in closed_modes={closed_modes}",
                }
                continue
            gp_obj = self._make_gp(impl, draw_id, cover_tickets, gp)
            tickets = impl.generate_for_mode(m, runtime_mode, quota, gp_obj)
            meta_profiles[profile_id] = {
                "quota": quota,
                "tickets": tickets,
                "runtime_mode": runtime_mode,
                "closed_modes": closed_modes,
            }
            portfolio.extend(tickets)
        meta = {
            "template_id": template_id,
            "draw_id": draw_id,
            "runtime_mode": runtime_mode,
            "detector": analysis,
            "profiles": meta_profiles,
            "total_quota": sum(int((profiles.get(pid) or {}).get("quota") or 0) for pid in order),
        }
        return {"tickets": portfolio, "meta": meta} if return_meta else portfolio

    def generate(
        self,
        count: Optional[int] = None,
        gp: Optional[Any] = None,
        template_id: str = "",
        mode_id: Optional[str] = None,
        *,
        metrics: Optional[Dict[str, Any]] = None,
        draw_metrics: Optional[Dict[str, Any]] = None,
        draw_id: Optional[int] = None,
        T: Optional[int] = None,
        cover_tickets: int = 0,
        return_meta: bool = False,
        **_: Any,
    ):
        did = draw_id if draw_id is not None else T
        m = metrics or draw_metrics or {}
        mid = _normalize_id(mode_id)
        tid = _normalize_id(template_id)

        if (not mid and tid and _is_template_id(tid)) or (mid and _is_template_id(mid) and (not tid or tid == mid)):
            target_template = tid or mid
            return self.generate_template(
                template_id=target_template,
                draw_id=did,
                metrics=m,
                gp=gp,
                cover_tickets=cover_tickets,
                return_meta=return_meta,
            )

        if not mid:
            raise ValueError("mode_id is required for direct profile generation when template routing is not used")

        impl = _load_profile_module(mid)
        analysis = analyze_runtime_mode(m)
        runtime_mode = str(analysis["mode"]).upper()
        closed_modes = tuple(str(x).strip().upper() for x in (getattr(impl, "CLOSED_MODES", ()) or ()))
        if closed_modes and runtime_mode not in closed_modes:
            meta = {
                "template_id": tid,
                "draw_id": did,
                "runtime_mode": runtime_mode,
                "detector": analysis,
                "profiles": {
                    mid: {
                        "quota": int(count or 0),
                        "tickets": [],
                        "skipped": True,
                        "reason": f"runtime_mode={runtime_mode} not in closed_modes={closed_modes}",
                    }
                },
            }
            return {"tickets": [], "meta": meta} if return_meta else []

        n = int(count or 0)
        if n <= 0:
            n = int(getattr(impl, "QUOTA", 0) or 0) or 9
        gp_obj = self._make_gp(impl, did, cover_tickets, gp)
        tickets = impl.generate_for_mode(m, runtime_mode, n, gp_obj)
        meta = {
            "template_id": tid,
            "draw_id": did,
            "runtime_mode": runtime_mode,
            "detector": analysis,
            "profiles": {
                mid: {
                    "quota": n,
                    "tickets": tickets,
                    "runtime_mode": runtime_mode,
                    "closed_modes": closed_modes,
                }
            },
        }
        return {"tickets": tickets, "meta": meta} if return_meta else tickets
