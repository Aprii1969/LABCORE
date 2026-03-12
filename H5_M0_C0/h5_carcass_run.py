# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8-sig'))


def read_draws_history(path: Path) -> Dict[int, List[int]]:
    out: Dict[int, List[int]] = {}
    with path.open('r', encoding='utf-8-sig', errors='replace', newline='') as f:
        rdr = csv.DictReader(f)
        for row in rdr:
            tid = row.get('draw_id') or row.get('T') or row.get('tirazh') or row.get('тираж')
            if not str(tid).strip().isdigit():
                continue
            nums = []
            for k in ('n1','n2','n3','n4','n5','w1','w2','w3','w4','w5'):
                v = row.get(k)
                if v and str(v).strip().isdigit():
                    nums.append(int(v))
            if len(nums) >= 5:
                out[int(tid)] = nums[:5]
    return out


def hit(combo: List[int], winners: List[int]) -> int:
    return len(set(combo).intersection(set(winners)))


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--template', default='H5_M0_C0')
    ap.add_argument('--draws', required=True)
    ns = ap.parse_args(argv)
    root = Path(__file__).resolve().parent
    draws = [int(x) for x in str(ns.draws).split(',') if str(x).strip().isdigit()]
    winners_map = read_draws_history(root / 'draws_history.csv')
    from generator_A_sandbox import GeneratorSandbox
    report = {'template_id': ns.template, 'draws': []}
    for T in draws:
        mp = root / 'rolling' / 'draw_metrics' / f'draw_metrics_{T-1}.json'
        if not mp.exists():
            print(f'[WARN] metrics not found for T={T}: {mp.name}')
            continue
        metrics = load_json(mp)
        winners = winners_map.get(T)
        gen = GeneratorSandbox(str(mp), '')
        res = gen.generate_template(template_id=str(ns.template).strip().upper(), draw_id=T, metrics=metrics, return_meta=True)
        tickets = res.get('tickets') or []
        meta = res.get('meta') or {}
        best = None
        if winners:
            best = max((hit(t, winners) for t in tickets), default=0)
        print(f'[OK] {ns.template} T={T}: generated={len(tickets)}/{meta.get("total_quota", 0)} best_hit={best}')
        draw_row = {'draw_id': T, 'generated': len(tickets), 'best_hit': best, 'profiles': {}}
        for mid, pm in (meta.get('profiles') or {}).items():
            pt = pm.get('tickets') or []
            pbest = max((hit(t, winners) for t in pt), default=0) if winners else None
            print(f'      - {mid}: generated={len(pt)}/{pm.get("quota", 0)} best_hit={pbest}')
            draw_row['profiles'][mid] = {'generated': len(pt), 'best_hit': pbest}
        report['draws'].append(draw_row)
    out = root / 'H5_carcass_report.json'
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[OK] Saved {out.name}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
