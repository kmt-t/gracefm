#!/usr/bin/env python3
"""
量子化雑音の除去 (ポストフィルタ) の効果。1系統 (主系、全電力)、白色雑音、軟判定の復号。

  python tools/eval_pf_link.py --seconds 3 --json docs/results/pf_link_eval.json

構成: なし (中点 / 期待値から Haar 合成) / 区間を広げない (量子化区間だけ) / 既定 (軟判定で区間を広げる)
C/N0 = None はコーデックだけ (通信路なし)。
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

VARS = {"なし": dict(postfilter=False), "区間を広げない": dict(eps=0.5), "既定": dict()}
MATS = (("fishin", "B200MH-A4"), ("vibeace", "B200MH-A4"), ("demo", "B200H-A4"))
CN0S = (None, 57.0, 63.0, 70.0, 80.0)


def job(a):
    mat, prof, cn0, seed, sec = a
    p = PROFILES[prof]
    x, fs = wavio.read(os.path.join(ROOT, "samples", f"{mat}_orig.flac"))
    x = x[: int(sec * fs)]
    bm = metrics.BandMetric(x, fs)
    fr = txrx.Transmitter(p, 0, 0).run(x)
    es = 200.0 if cn0 is None else cn0 - 10 * np.log10(channel.symbol_rate(p))
    fr = channel.through(fr, es, np.ones(len(fr)), np.random.default_rng(seed))
    out = {}
    for vn, kw in VARS.items():
        y, v = txrx.StreamDecoder(p, **kw).run(fr, len(x), 0)
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
    jobs = [(m, p, c, s, a.seconds) for m, p in MATS for c in CN0S for s in range(a.seeds if c else 1)]
    res = {}
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for j, o in ex.map(job, jobs):
            res.setdefault(f"{j[0]}|{'codec' if j[2] is None else int(j[2])}", []).append(o)
    table = {k: {v: [float(np.mean([o[v][i] for o in L])) for i in (0, 1)] for v in VARS} for k, L in res.items()}
    print("素材|C/N0 : " + " | ".join(VARS) + "   (波形SNR dB / BandMetric)")
    for k, t in table.items():
        print(k, " | ".join(f"{t[v][0]:5.2f}/{t[v][1]:5.2f}" for v in VARS), flush=True)
    if a.json:
        with open(a.json, "w") as f:
            json.dump(dict(variants=list(VARS), cn0=[c for c in CN0S], table=table), f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
