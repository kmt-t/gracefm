#!/usr/bin/env python3
"""Git管理外のライセンス確認済み音源でMP3 CBRを比較する。"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from gracefm import metrics  # noqa: E402
from eval_exp_layout import read_clips, visqol  # noqa: E402
from eval_codec_perceptual import mp3_roundtrip  # noqa: E402
from visqol import VisqolApi  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--audio-dir', type=Path, default=ROOT / 'eval_audio')
    ap.add_argument('--seconds', type=float, default=3.0)
    ap.add_argument('--bitrates', default='128,192,320')
    ap.add_argument('--json', type=Path)
    args = ap.parse_args()
    manifest, clips = read_clips(args.audio_dir, args.seconds, 64)
    api = VisqolApi()
    api.create(mode='audio')
    rows = []
    for name, blocks in clips.items():
        if manifest[name]['split'] != 'holdout':
            continue
        x = blocks.reshape(-1, 1)
        for kbps in (int(v) for v in args.bitrates.split(',')):
            y, size = mp3_roundtrip(x, 32000, kbps)
            row = dict(material=name, method='MP3', kbps=kbps, encoded_bytes=size,
                       snr_db=float(metrics.snr_db(x, y)),
                       visqol_moslqo=visqol(api, x[:, 0], y[:, 0]))
            rows.append(row)
            print(row, flush=True)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(dict(seconds=args.seconds, materials=manifest,
                                             channel='codec_only', rows=rows),
                                        ensure_ascii=False, indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
