#!/usr/bin/env python3
"""
系統の切り替わりのクロスフェード (plc.crossfade_switch) の効果を測る (docs/SPEC.md 5.2節)。

  python tools/eval/eval_crossfade.py --json docs/results/crossfade.json

雑音なしで、主系のフレームを確率 --loss でランダムに落とし、副系はすべて届く。誤差信号の2階差分の平均絶対値を、
ブロック境界とそれ以外で求めた比を、クロスフェードの有無で比べる。この比は本書で定めた指標で、聴感との対応は確認していない。
"""
import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, ROOT)

from gracefm import channel, plc
from gracefm.encoder import Encoder
from gracefm.iir import ALT_DELAY
from gracefm.profiles import PROFILES
from gracefm.receiver import receive
from tools.common import metrics, wavio

MATERIALS = ("demo", "piano", "percussion")
MAINS = ("B200M", "B200M-L")
SEED = 5


def run(task):
    from visqol import VisqolApi

    material, main, fade, loss = task
    if not fade:
        plc.crossfade_switch = lambda y, *args, **kwargs: y
    p, q = PROFILES[main], PROFILES[channel.DEFAULT_SUB[main]]
    x, _ = wavio.read(os.path.join(ROOT, "samples", f"{material}-mono__{p.fs // 1000}k__reference.flac"))
    x = np.repeat(x[:, :1], 2, axis=1)
    xi = wavio.to_pcm24(x)
    rng = np.random.default_rng(SEED)
    frames = [channel.adc(f / float(1 << 22)) for f in Encoder(p, 0, 0).run(xi)]
    framesA = [None if rng.random() < loss else f for f in frames]
    framesB = [channel.adc(f / float(1 << 22)) for f in Encoder(q, 1, 0).run(xi)]
    y, _ = receive(p, framesA, framesB, len(xi), 0, profile_b=q)
    d = ALT_DELAY[p.fs]
    ref, out = x[:len(x) - d, 0], wavio.from_pcm24(y)[d:, 0]
    second = np.abs(np.diff(ref - out, 2))              # second[i] は out[i + 1] を中心とする
    boundary = np.zeros(len(second), bool)
    boundary[p.block - 1::p.block] = True
    api = VisqolApi()
    api.create(mode="audio")
    mos = api.measure_from_arrays(wavio.resample(ref[:, None], p.fs, 48000)[:, 0],
                                  wavio.resample(out[:, None], p.fs, 48000)[:, 0], sample_rate=48000).moslqo
    return {"material": material, "main": main, "crossfade": fade, "main_received": round(sum(f is not None for f in framesA) / len(framesA), 3),
            "boundary_ratio": round(float(second[boundary].mean() / second[~boundary].mean()), 3),
            "snr_db": round(float(metrics.snr_db(ref, out)), 2), "visqol": round(float(mos), 3)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--loss", type=float, default=0.32, help="主系のフレームを落とす確率")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--json", help="結果の書き出し先")
    args = ap.parse_args()
    tasks = [(m, s, f, args.loss) for m in MATERIALS for s in MAINS for f in (False, True)]
    with ProcessPoolExecutor(args.workers, max_tasks_per_child=1) as ex:      # クロスフェードなしの差し替えを次へ持ち越さない
        rows = list(ex.map(run, tasks))
    for r in rows:
        print(r, flush=True)
    if args.json:
        with open(args.json, "w") as f:
            json.dump({"condition": "no noise; main frames dropped at random; see tools/eval/eval_crossfade.py", "seed": SEED, "rows": rows}, f, ensure_ascii=False, indent=1)
            f.write("\n")


if __name__ == "__main__":
    main()
