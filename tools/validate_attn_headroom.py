#!/usr/bin/env python3
"""eval_attn_layout.py の帯域別ピーク余裕付き探索結果を保留音源で検証する。"""
import argparse
import json
from pathlib import Path

from eval_attn_layout import link_rows, perceptual_rows, profile_for
from eval_exp_layout import read_clips
from gracefm import channel
from gracefm.profiles import PROFILES

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--scan', type=Path, default=ROOT / 'docs/results/attn_layout_scan.json')
    ap.add_argument('--json', type=Path, default=ROOT / 'docs/results/attn_headroom_validation.json')
    args = ap.parse_args()
    scan = json.loads(args.scan.read_text())
    base = PROFILES['B200MH']
    manifest, all_clips = read_clips(ROOT / 'eval_audio', scan['seconds'], base.block)
    clips = {k: v for k, v in all_clips.items() if manifest[k]['split'] == 'holdout'}
    specs = {k: scan['specs'][k] for k in ('attn4_same_rate', 'attn4_plus8')}
    perceptual = perceptual_rows(clips, manifest, base, specs, (0, -40))
    link = link_rows(clips, manifest, base, specs, (60, 66))
    layout = {}
    for name, spec in specs.items():
        p = profile_for(base, spec)
        layout[name] = dict(widths=spec[0], offsets=p.exp_offset_m,
                            symbol_rate_khz=channel.symbol_rate(p) / 1000)
    result = dict(scan=str(args.scan.relative_to(ROOT)), materials=manifest,
                  headroom_db=scan['headroom_db'], layout=layout,
                  codec=[r for r in scan['codec'] if r['split'] == 'holdout' and r['layout'] in specs],
                  perceptual=perceptual, link=link)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
