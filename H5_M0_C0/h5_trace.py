# -*- coding: utf-8 -*-
"""
h5_trace.py

Lightweight TRACE helper (runner-independent).

Enable:
  $env:H5_TRACE="1"
  $env:H5_TRACE_DIR="rolling/debug"   # optional (default: rolling/debug)

File naming:
  draw_metrics_{T-1}__{template_id}__{mode_id}.jsonl

Important: TRACE must never break generation. All helpers are fail-safe.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


def trace_enabled(explicit: Optional[bool] = None) -> bool:
    if explicit is not None:
        return bool(explicit)
    v = str(os.environ.get("H5_TRACE", "")).strip().lower()
    return v in ("1", "true", "yes", "on")


def trace_dir(explicit_dir: Optional[str] = None) -> str:
    d = (explicit_dir or "").strip() or str(os.environ.get("H5_TRACE_DIR", "")).strip() or os.path.join("rolling", "debug")
    return d


def trace_path(metrics_path: str, template_id: str, mode_id: str, explicit_dir: Optional[str] = None) -> str:
    base = os.path.basename(str(metrics_path))
    name = base.replace(".json", f"__{template_id}__{mode_id}.jsonl")
    return os.path.join(trace_dir(explicit_dir), name)


def trace_write(path: str, record: Dict[str, Any]) -> None:
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        # TRACE must never break generation
        return
