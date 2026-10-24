#!/usr/bin/env python3
"""
最終構成の評価: アナログFM (モノラル)・QPSK 1系統・階層 16QAM・主系＋副系を、同じ受信電力 (C/N0) で比べる。

  python tools/eval_final.py --seconds 5 --json docs/results/final_eval.json

電波の強さは C/N0 [dB-Hz]。C/N (雑音帯域 180kHz) = C/N0 - 52.6dB。2系統の構成は送信電力の合計が同じ。
通信路: awgn (白色雑音のみ)、rayleigh (系統ごとに独立なレイリーフェージング、時定数 100ms。FM も同じモデル)、
fade10 (主系の周波数だけ 10dB 落ちる。FM・1系統はその周波数で受ける)。
数値: 波形SNR [dB] / BandMetric / 欠けて PLC で埋めた時間の割合 [%]。
"""
import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)

from gracefm import channel, metrics, wavio  # noqa: E402
from gracefm.analog_fm import AnalogFM  # noqa: E402

MONO = [("FM", None), ("B200M", dict(main="B200M", sub=None)),
        ("B200MH", dict(main="B200MH", sub=None)),
        ("B200MH+S50M 50:50", dict(main="B200MH", sub="S50M", power_main=0.5)),
        ("B200MH+S50M 75:25", dict(main="B200MH", sub="S50M", power_main=0.75))]
STEREO = [("B200", dict(main="B200", sub=None)), ("B200H", dict(main="B200H", sub=None)),
          ("B200H+S100 50:50", dict(main="B200H", sub="S100", power_main=0.5)),
          ("B200H+S100 75:25", dict(main="B200H", sub="S100", power_main=0.75))]


def job(a):
    mat, kind, cn0, seed, sec = a
    x, fs = wavio.read(os.path.join(ROOT, "samples", f"{mat}__32k__reference.flac"))
    x = x[: int(sec * fs)]
    bm = metrics.BandMetric(x, fs)
    stereo = mat == "demo"
    out = {}
    for name, cfg in (STEREO if stereo else MONO):
        if cfg is None:
            fm = AnalogFM(x[:, 0], fs)
            g = None
            if kind != "awgn":
                g = channel.fading_gains(int(np.ceil(len(x) / 64)), kind, np.random.default_rng(seed + 100))
            y1 = fm.receive(cn0, np.random.default_rng(seed), g)
            y = np.stack([y1, y1], axis=1)
            plc = 0.0
        else:
            two = cfg.get("sub") is not None
            y, st, _ = channel.link(x, cfg["main"], cn0, sub=cfg.get("sub"), power_main=cfg.get("power_main", 0.5),
                                    kind_main=kind, kind_sub="awgn" if kind == "fade10" else kind, seed=seed)
            plc = st["plc_samples"] / len(x) * 100
        out[name] = (metrics.snr_db(x, y), bm(y - x), plc)
    return a, out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seconds", type=float, default=5.0)
    ap.add_argument("--materials", default="fishin,vibeace,demo")
    ap.add_argument("--cn0", default="54,57,60,63,66,70,75,80")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--json")
    args = ap.parse_args()
    if args.workers < 1:
        ap.error("workers は 1 以上にしてください")
    jobs = []
    for m in args.materials.split(","):
        for c in map(float, args.cn0.split(",")):
            jobs.append((m, "awgn", c, 1, args.seconds))
        for c in (60.0, 66.0):
            for s in (1, 2):
                jobs.append((m, "rayleigh", c, s, args.seconds))
            jobs.append((m, "fade10", c, 1, args.seconds))
    res = {}
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for a, o in ex.map(job, jobs):
            res.setdefault(f"{a[0]}|{a[1]}|{a[2]:g}", []).append(o)
    summ = {k: {n: [round(float(v), 2) for v in np.mean([o[n] for o in L], axis=0)] for n in L[0]}
            for k, L in res.items()}
    for k, d in summ.items():
        m, kind, c = k.split("|")
        print(f"{m:8s} {kind:8s} C/N0 {c}dB-Hz (C/N {float(c) - 52.55:.1f}dB) | "
              + " | ".join(f"{n} {v[0]:.1f}dB/{v[1]:.1f}/{v[2]:.1f}%" for n, v in d.items()), flush=True)
    if args.json:
        with open(args.json, "w") as f:
            json.dump(summ, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
