#!/usr/bin/env python3
"""
モニター用 (48kHz) の主系の変調の比較: M700 (QPSK) と階層16QAMを、同じ C/N0 で比べる。

  python tools/eval_m700.py --json docs/results/m700_eval.json

素材は samples/*__32k__reference.flac (32kHz) を 48kHz に変換したもの (帯域は元の音源のまま)。1系統は全電力、
主系＋副系 (S100-48K) は電力 75:25。通信路は白色雑音のみ。波形SNR [dB]、1kHz・−6dBFS の正弦波の THD・THD+N [%]。
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
from gracefm.profiles import PROFILES  # noqa: E402

CONFIGS = [("M700 (QPSK)", "M700", None),
           ("M700H (階層)", "M700H", None),
           ("M700H＋S100-48K 75:25", "M700H", "S100-48K")]


def job(a):
    mat, cn0, sec = a
    x, fs = wavio.read(os.path.join(ROOT, "samples", f"{mat}__32k__reference.flac"))
    x = wavio.resample(x[: int(sec * fs)], fs, 48000)
    t = np.arange(int(1.2 * 48000)) / 48000
    tone = np.repeat((0.5 * np.sin(2 * np.pi * 1000 * t))[:, None], 2, axis=1)
    out = {}
    for name, pm, ps in CONFIGS:
        y, st, es = channel.link(x, PROFILES[pm], cn0, sub=ps, power_main=0.75 if ps else 1.0, seed=1)
        yt, _, _ = channel.link(tone, PROFILES[pm], cn0, sub=ps, power_main=0.75 if ps else 1.0, seed=1)
        thd, thdn = metrics.thd(yt[:, 0], 48000, 1000.0)
        out[name] = (metrics.snr_db(x, y), thd, thdn, es["esn0_main"], st["plc_samples"] / len(x) * 100)
    return a, out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seconds", type=float, default=3.0)
    ap.add_argument("--cn0", default="65,70,75,80,85")
    ap.add_argument("--json")
    args = ap.parse_args()
    for n, pm, ps in CONFIGS:
        p = PROFILES[pm]
        print(f"{n}: {p.audio_kbps():.0f}kbps, 1系統の占有帯域 約{1.25 * channel.symbol_rate(p) / 1e3:.0f}kHz"
              + (f" + 副系 約{1.25 * channel.symbol_rate(PROFILES[ps]) / 1e3:.0f}kHz" if ps else ""))
    jobs = [(m, float(c), args.seconds) for m in ("fishin", "demo") for c in args.cn0.split(",")]
    res = {}
    with ProcessPoolExecutor() as ex:
        for a, o in ex.map(job, jobs):
            res[f"{a[0]}|{a[1]:g}"] = {k: [round(float(v), 4) for v in vals] for k, vals in o.items()}
            print(f"{a[0]:7s} C/N0 {a[1]:g}dB-Hz | " + " | ".join(
                f"{k}: SNR {v[0]:.1f}dB THD {v[1]:.3f}% THD+N {v[2]:.3f}% (Es/N0 {v[3]:.1f}dB, 欠落 {v[4]:.1f}%)"
                for k, v in o.items()), flush=True)
    if args.json:
        with open(args.json, "w") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
