# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

TEMPLATE_ID = "H5_M0_C0"
DEFAULT_TRACE_DIR = Path("rolling") / "debug"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def dump_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_draws_history(path: Path) -> Dict[int, List[int]]:
    out: Dict[int, List[int]] = {}
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as f:
        rdr = csv.DictReader(f)
        for row in rdr:
            tid = row.get("draw_id") or row.get("T") or row.get("tirazh") or row.get("тираж")
            if not str(tid).strip().isdigit():
                continue
            nums: List[int] = []
            for k in ("n1", "n2", "n3", "n4", "n5", "w1", "w2", "w3", "w4", "w5"):
                v = row.get(k)
                if v and str(v).strip().isdigit():
                    nums.append(int(v))
            if len(nums) >= 5:
                out[int(tid)] = nums[:5]
    return out


def hit(combo: List[int], winners: List[int]) -> int:
    return len(set(map(int, combo)).intersection(set(map(int, winners))))


def _norm_mode_list(raw: str) -> List[str]:
    return [x.strip().upper() for x in str(raw).split(",") if x.strip()]


def parse_args(argv: List[str]) -> Dict[str, Any]:
    args: Dict[str, Any] = {
        "stage": os.environ.get("H5_STAGE", "self").strip().lower(),
        "modes": [],
        "trace_enabled": False,
        "trace_dir": str(DEFAULT_TRACE_DIR),
        "cover_tickets": 0,
        "template_id": TEMPLATE_ID,
        "registry_path": "h5_profiles_registry.json",
    }

    i = 0
    while i < len(argv):
        a = argv[i].strip()
        nxt = argv[i + 1].strip() if i + 1 < len(argv) else None
        if a.startswith("--stage="):
            args["stage"] = a.split("=", 1)[1].strip().lower()
        elif a == "--stage" and nxt is not None:
            args["stage"] = nxt.lower(); i += 1
        elif a == "--trace":
            args["trace_enabled"] = True
        elif a.startswith("--trace-dir="):
            args["trace_enabled"] = True
            args["trace_dir"] = a.split("=", 1)[1].strip()
        elif a == "--trace-dir" and nxt is not None:
            args["trace_enabled"] = True
            args["trace_dir"] = nxt; i += 1
        elif a.startswith("--cover="):
            try:
                args["cover_tickets"] = int(a.split("=", 1)[1].strip())
            except Exception:
                args["cover_tickets"] = 0
        elif a == "--cover" and nxt is not None:
            try:
                args["cover_tickets"] = int(nxt)
            except Exception:
                args["cover_tickets"] = 0
            i += 1
        elif a.startswith("--template="):
            args["template_id"] = a.split("=", 1)[1].strip() or TEMPLATE_ID
        elif a == "--template" and nxt is not None:
            args["template_id"] = nxt or TEMPLATE_ID; i += 1
        elif a.startswith("--registry="):
            args["registry_path"] = a.split("=", 1)[1].strip() or "h5_profiles_registry.json"
        elif a == "--registry" and nxt is not None:
            args["registry_path"] = nxt or "h5_profiles_registry.json"; i += 1
        elif not a.startswith("--"):
            args["modes"].extend(_norm_mode_list(a))
        i += 1

    if args["stage"] not in ("self", "cross", "all"):
        args["stage"] = "self"
    args["cover_tickets"] = max(0, int(args["cover_tickets"] or 0))
    return args


def stage_draws(rec: Dict[str, Any], stage: str) -> List[int]:
    self_d = [int(x) for x in (rec.get("self") or [])]
    cross_d = [int(x) for x in (rec.get("cross") or [])]
    if stage == "self":
        return self_d
    if stage == "cross":
        return cross_d
    out: List[int] = []
    seen = set()
    for x in self_d + cross_d:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _resolve_trace_root(script_dir: Path, trace_dir_raw: str, template_id: str) -> Path:
    base = Path(trace_dir_raw)
    if not base.is_absolute():
        base = script_dir / base
    return base / template_id


def _extract_tickets(result: Any) -> Tuple[List[List[int]], Dict[str, Any]]:
    if isinstance(result, dict) and "tickets" in result:
        tickets_raw = result.get("tickets") or []
        meta = result.get("meta") or {}
    else:
        tickets_raw = result or []
        meta = {}

    tickets: List[List[int]] = []
    for c in tickets_raw:
        if isinstance(c, (list, tuple)) and len(c) == 5:
            try:
                tickets.append(sorted(int(x) for x in c))
            except Exception:
                continue
    return tickets, meta


def main(argv: List[str]) -> int:
    opts = parse_args(argv)
    script_dir = Path(__file__).resolve().parent
    stage = str(opts["stage"])
    template_id = str(opts["template_id"])
    registry_path = Path(str(opts["registry_path"]))
    if not registry_path.is_absolute():
        registry_path = script_dir / registry_path

    reg = load_json(registry_path).get("profiles") or {}
    winners_path = script_dir / "draws_history.csv"
    winners_map = read_draws_history(winners_path)

    os.environ["H5_STAGE"] = stage
    print(f"[INFO] root={script_dir}")
    print(f"[INFO] stage={stage.upper()}  (set via --stage or $env:H5_STAGE)")
    print(f"[INFO] winners_source={winners_path}")
    print(f"[INFO] registry={registry_path}")
    print(f"[INFO] template={template_id}")
    print(f"[INFO] trace_enabled={opts['trace_enabled']}")
    print(f"[INFO] trace_dir={opts['trace_dir']}")
    print(f"[INFO] cover_tickets={opts['cover_tickets']}")

    modes: List[str] = opts["modes"] or [str(k).upper() for k in reg.keys()]

    from generator_A_sandbox import GeneratorSandbox, detect_runtime_mode

    report: Dict[str, Any] = {"stage": stage, "modes": modes, "draws": []}
    mode_report: Dict[str, Any] = {
        "template_id": template_id,
        "stage": stage,
        "profiles_requested": modes,
        "draws": [],
    }

    trace_root = _resolve_trace_root(script_dir, str(opts["trace_dir"]), template_id)
    trace_manifest: Dict[str, Any] = {
        "template_id": template_id,
        "stage": stage,
        "trace_enabled": bool(opts["trace_enabled"]),
        "trace_root": str(trace_root),
        "draws": [],
    }
    if opts["trace_enabled"]:
        trace_root.mkdir(parents=True, exist_ok=True)

    rc = 0
    for mid in modes:
        rec = reg.get(mid) or {}
        q = int(rec.get("quota") or 0)
        draws = stage_draws(rec, stage)
        print(f"[PLAN] {mid}: quota={q} draws={draws}")
        for T in draws:
            mp = script_dir / "rolling" / "draw_metrics" / f"draw_metrics_{T-1}.json"
            if not mp.exists() or T not in winners_map:
                continue
            metrics = load_json(mp)
            winners = winners_map[T]
            runtime_mode = detect_runtime_mode(metrics)
            mode_report["draws"].append({
                "draw_id": T,
                "profile_id": mid,
                "metrics_file": str(mp.relative_to(script_dir)).replace("/", "\\"),
                "mode": runtime_mode,
            })

            try:
                gen = GeneratorSandbox(str(mp), str(trace_root) if opts["trace_enabled"] else "")
                result = gen.generate(
                    count=q,
                    template_id=template_id,
                    mode_id=mid,
                    metrics=metrics,
                    draw_id=T,
                    cover_tickets=opts["cover_tickets"],
                    return_meta=True,
                )
            except Exception as e:
                print(f"[ERR] {mid} T={T}: generate failed: {e}")
                rc = 1
                continue

            tickets, meta = _extract_tickets(result)
            best = max([hit(c, winners) for c in tickets], default=0)
            print(f"[OK]   {mid} T={T}: mode={runtime_mode} generated={len(tickets)}/{q} best_hit={best}")

            report["draws"].append({
                "draw_id": T,
                "profile_id": mid,
                "mode": runtime_mode,
                "best_hit": best,
                "generated": len(tickets),
            })

            if opts["trace_enabled"]:
                per_draw_dir = trace_root / mid / stage
                per_draw_dir.mkdir(parents=True, exist_ok=True)
                trace_file = per_draw_dir / f"T_{T}.trace.json"
                detector_meta = meta.get("detector") if isinstance(meta, dict) else None
                profile_meta = {}
                if isinstance(meta, dict):
                    p = (meta.get("profiles") or {}).get(mid) or {}
                    if isinstance(p, dict):
                        profile_meta = {
                            "quota": p.get("quota"),
                            "runtime_mode": p.get("runtime_mode"),
                            "skipped": p.get("skipped", False),
                            "reason": p.get("reason"),
                        }
                trace_payload = {
                    "template_id": template_id,
                    "stage": stage,
                    "profile_id": mid,
                    "draw_id": T,
                    "metrics_file": str(mp.relative_to(script_dir)).replace("/", "\\"),
                    "runtime_mode": runtime_mode,
                    "quota": q,
                    "cover_tickets": opts["cover_tickets"],
                    "generated": len(tickets),
                    "tickets": tickets,
                    "detector": detector_meta,
                    "profile_meta": profile_meta,
                }
                dump_json(trace_file, trace_payload)
                trace_manifest["draws"].append({
                    "draw_id": T,
                    "profile_id": mid,
                    "trace_file": str(trace_file.relative_to(script_dir)).replace("/", "\\"),
                })

    out = script_dir / f"H5_preflight_report.{stage}.json"
    dump_json(out, report)
    mr = script_dir / "Mode_detector_report.json"
    dump_json(mr, mode_report)
    print(f"[OK] Saved {out.name}")
    print(f"[OK] Saved {mr.name}")

    if opts["trace_enabled"]:
        manifest_path = trace_root / f"trace_manifest.{stage}.json"
        dump_json(manifest_path, trace_manifest)
        print(f"[OK] Saved {manifest_path.relative_to(script_dir)}")

    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
