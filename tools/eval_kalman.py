#!/usr/bin/env python3
"""
帯域カルマン (時間方向の予測を加えた更新) の評価。1系統 (全電力)、白色雑音。

  python tools/eval_kalman.py --seconds 3 --json docs/results/kalman_eval.json

構成: なし (観測だけ) / 低3帯域 AR(2) / 全帯域 AR(2) / 低3帯域 AR(8)
数値: 波形SNR [dB] / BandMetric
"""
import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)

from gracefm import channel, metrics, plc, txrx, wavio  # noqa: E402
from gracefm.profiles import PROFILES  # noqa: E402

VARS = {"なし": None, "低3帯域 AR(2)": dict(kalman_bands=[0, 1, 2]), "全帯域 AR(2)": dict(kalman_bands="all"),
        "低3帯域 AR(8)": dict(kalman_bands=[0, 1, 2], kalman_order=8)}
MATS = (("fishin", "B200MH-A4"), ("vibeace", "B200MH-A4"), ("demo", "B200H"))
CN0S = (54.0, 60.0, 66.0)


def job(a):
    mat, prof, cn0, seed, sec = a
    p = PROFILES[prof]
    x, fs = wavio.read(os.path.join(ROOT, "samples", f"{mat}_orig.flac"))
    x = x[: int(sec * fs)]
    bm = metrics.BandMetric(x, fs)
    es = cn0 - 10 * np.log10(channel.symbol_rate(p))
    f0 = txrx.Transmitter(p, 0, 0).run(x)
    fr = channel.through(f0, es, np.ones(len(f0)), np.random.default_rng(seed))
    out = {}
    for vn, kw in VARS.items():
        y, v = txrx.StreamDecoder(p, **(kw or {})).run(fr, len(x), 0)
        y = plc.conceal(y, v, fs)
        out[vn] = (float(metrics.snr_db(x, y)), float(bm(y - x)))
    return a, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=3)
    ap.add_argument("--seeds", type=int, default=2)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--json")
    a = ap.parse_args()
    if a.workers < 1:
        ap.error("workers は 1 以上にしてください")
    jobs = [(m, p, c, s, a.seconds) for m, p in MATS for c in CN0S for s in range(a.seeds)]
    res = {}
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for j, o in ex.map(job, jobs):
            res.setdefault(f"{j[0]}|{j[2]:.0f}", []).append(o)
    table = {k: {v: [float(np.mean([o[v][i] for o in L])) for i in (0, 1)] for v in VARS} for k, L in res.items()}
    print("素材|C/N0 : " + " | ".join(VARS) + "   (波形SNR dB / BandMetric)")
    for k, t in table.items():
        print(k, " | ".join(f"{t[v][0]:5.2f}/{t[v][1]:5.2f}" for v in VARS), flush=True)
    if a.json:
        with open(a.json, "w") as f:
            json.dump(dict(variants=list(VARS), cn0=CN0S, table=table), f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
