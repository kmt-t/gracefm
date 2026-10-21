#!/usr/bin/env python3
"""
帯域ごとのビット割り当てを、手元の音源で探索する。

  python tools/alloc_search.py 曲.wav --fs 32000 --targets 150,200,300
  python tools/alloc_search.py 曲.wav --fs 48000 --targets 500,700 --mono

各帯域の量子化は独立で、逆変換も M/S→L/R も線形なので、全体の誤差は帯域ごとの誤差の和と一致する。
帯域ごとの誤差波形をキャッシュし、「1bit 足したときの帯域指標の改善 / ビットレートの増加」が
最大の帯域に 1bit ずつ足していく (0bit の帯域は 2bit へ)。
帯域指標は誤差の量の目安なので、最終的な判断は試聴で行うこと。
"""
import argparse
import os
import sys
from dataclasses import replace

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gracefm import metrics, wavio  # noqa: E402
from gracefm.codec import dequantize, haar_forward, haar_inverse, quantize  # noqa: E402
from gracefm.profiles import PROFILES, band_edges  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("--fs", type=int, default=32000)
    ap.add_argument("--targets", default="150,200,300,400")
    ap.add_argument("--mono", action="store_true", help="S を送らない")
    ap.add_argument("--stereo-bands", type=int, default=0,
                    help="S の帯域 0〜(N-1) に最低 2bit を必ず割り当てる (ステレオの定位を保つ)")
    ap.add_argument("--seconds", type=float, default=30.0)
    args = ap.parse_args()

    base = replace(PROFILES["B200"], fs=args.fs)
    nb = base.nbands
    x, fs = wavio.read(args.input)
    x = wavio.resample(x, fs, args.fs)[: int(args.seconds * args.fs)]
    x = x * (0.99 / max(np.abs(x).max(), 0.99))
    n = len(x)
    nblk = int(np.ceil(n / base.block))
    xp = np.pad(x, ((0, nblk * base.block - n), (0, 0)))
    sig = {"M": (xp[:, 0] + xp[:, 1]) / 2, "S": (xp[:, 0] - xp[:, 1]) / 2}
    bands = {ch: haar_forward(sig[ch].reshape(nblk, base.block), base.levels) for ch in sig}
    metric = metrics.BandMetric(x, args.fs)
    cache = {}

    def err(ch, k, b):
        key = (ch, k, b)
        if key not in cache:
            c = bands[ch][k]
            z = [np.zeros_like(bb) for bb in bands[ch]]
            if b == 0:
                z[k] = -c
            else:
                m, e = quantize(c, k, b, base)
                z[k] = dequantize(m, e, k, b, base) - c
            cache[key] = haar_inverse(z).reshape(-1)[:n]
        return cache[key]

    def score(eM, eS):
        return metric(np.stack([eM + eS, eM - eS], axis=1))

    def kbps(bits):
        tot = sum(base.ncoef(k) * b + (base.exp_bits if b else 0)
                  for ch in bits for k, b in enumerate(bits[ch]))
        return tot * args.fs / base.block / 1000

    # S は 0bit から始め、効く帯域にだけ足す (--stereo-bands の帯域は最低 2bit)
    bits = {"M": [2] * nb, "S": [2 if (k < args.stereo_bands and not args.mono) else 0 for k in range(nb)]}
    tot = {ch: sum(err(ch, k, bits[ch][k]) for k in range(nb)) for ch in bits}
    cur = score(tot["M"], tot["S"])
    targets = sorted(float(t) for t in args.targets.split(","))
    path = [(kbps(bits), cur, {c: list(v) for c, v in bits.items()})]
    chans = ("M",) if args.mono else ("M", "S")
    while kbps(bits) < targets[-1]:
        best = None
        for ch in chans:
            for k in range(nb):
                b = bits[ch][k]
                if b >= 16:
                    continue
                nb_ = 2 if b == 0 else b + 1
                trial = tot[ch] - err(ch, k, b) + err(ch, k, nb_)
                s = score(trial, tot["S"]) if ch == "M" else score(tot["M"], trial)
                cost = base.ncoef(k) * (nb_ - b) + (base.exp_bits if b == 0 else 0)
                eff = (s - cur) / cost
                if best is None or eff > best[0]:
                    best = (eff, ch, k, nb_, s, trial)
        _, ch, k, nb_, s, trial = best
        bits[ch][k] = nb_
        tot[ch] = trial
        cur = s
        path.append((kbps(bits), cur, {c: list(v) for c, v in bits.items()}))

    print("帯域: " + "  ".join(f"{lo / 1000:g}-{hi / 1000:g}k" for lo, hi in band_edges(args.fs, base.levels)))
    for t in targets:
        kb, sc, b = [q for q in path if q[0] <= t][-1]
        print(f"  {t:5.0f}k (実際 {kb:5.0f}k)  帯域指標 {sc:5.2f}  bits_m={tuple(b['M'])}  bits_s={tuple(b['S'])}")


if __name__ == "__main__":
    main()
