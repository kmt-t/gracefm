#!/usr/bin/env python3
"""
指数のビット数の評価。入力の音量を下げていったときに、相対的な音質が保たれるかを見る。

  python tools/eval_expbits.py 曲.wav --profile B200M

ブロック浮動小数点は本来、音量が変わっても相対的な音質は変わらない。指数の範囲 (2^exp_bits 段 × 6dB)
の下限を割ると、量子化のステップがそれ以上細かくならず、仮数のビットが少ない帯域から 0 に潰れていく。
出力: 音量ごとの SNR / セグメンタル SNR と、指数が下限に張り付いたブロックの割合 (送る帯域の平均)。
"""
import argparse
import os
import sys
from dataclasses import replace

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gracefm import metrics, wavio  # noqa: E402
from gracefm.codec import decode_block, encode_block  # noqa: E402
from gracefm.profiles import PROFILES  # noqa: E402


def run(x, p):
    n = len(x) // p.block * p.block
    ys, floor_hits, total = [], 0, 0
    for i in range(0, n, p.block):
        bd = encode_block(x[i:i + p.block], p)
        ys.append(decode_block(bd, p))
        for ch in ("M", "S"):
            for e in bd.eidx[ch]:
                if e is not None:
                    total += 1
                    floor_hits += e == 0
    return np.concatenate(ys), x[:n], floor_hits / max(total, 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("--profile", default="B200M", choices=PROFILES)
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--levels", default="0,-20,-40,-60,-80")
    ap.add_argument("--exp-bits", default="3,4,5")
    args = ap.parse_args()
    base = PROFILES[args.profile]
    x, fs = wavio.read(args.input)
    x = wavio.resample(x, fs, base.fs)[: int(args.seconds * base.fs)]
    x = x * (0.99 / np.abs(x).max())
    lv = [float(v) for v in args.levels.split(",")]
    print(f"{base.name}: 入力の音量ごとの SNR / セグメンタル SNR (下限張り付き率)")
    print(f"{'指数':>4} {'kbps':>5} " + " ".join(f"{v:>+5.0f}dB入力{'':12s}" for v in lv))
    for eb in [int(v) for v in args.exp_bits.split(",")]:
        p = replace(base, exp_bits=eb)
        row = []
        for db in lv:
            g = 10 ** (db / 20)
            y, xr, hit = run(x * g, p)
            snr = np.mean([metrics.snr_db(xr[:, c], y[:, c]) for c in range(2)])
            seg = np.mean([metrics.seg_snr_db(xr[:, c] / g, y[:, c] / g, p.fs) for c in range(2)])
            row.append(f"{snr:5.1f}/{seg:5.1f}dB ({hit * 100:4.1f}%)")
        print(f"{eb:4d} {p.audio_kbps():5.0f} " + " ".join(row))


if __name__ == "__main__":
    main()
