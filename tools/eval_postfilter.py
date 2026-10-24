#!/usr/bin/env python3
"""
ポストフィルタの繰り返し回数の評価。

  python tools/eval_postfilter.py 曲.wav --profile B200MH --seconds 20

回数ごとに次を出す:
  収束    : 十分に回した結果 (--ref-iters 回) との差。信号に対する dB (小さいほど収束している)
  高域誤差: 原音との誤差のうち、高域 (--hf Hz 以上) のエネルギー。ポストフィルタなしに対する dB
  帯域指標・セグメンタル SNR: 参考
"""
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gracefm import metrics, wavio  # noqa: E402
from gracefm.codec import decode_coeffs, encode_block, haar_inverse, ms_to_lr  # noqa: E402
from gracefm.postfilter import PostFilter  # noqa: E402
from gracefm.profiles import PROFILES  # noqa: E402


def run(blocks, p, iters):
    pf = PostFilter(p.levels, iters, p.block) if iters > 0 else None
    out = []
    for coefs, cell in blocks:
        if pf is None:
            M, S = haar_inverse(coefs["M"]), haar_inverse(coefs["S"])
        else:
            M, S = pf.process("M", coefs["M"], cell["M"]), haar_inverse(coefs["S"])
        out.append(ms_to_lr(M, S))
    return np.concatenate(out)


def hf_energy(e, fs, f0):
    E = np.abs(np.fft.rfft(e, axis=0)) ** 2
    f = np.fft.rfftfreq(len(e), 1 / fs)
    return E[f >= f0].sum()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("--profile", default="B200MH", choices=PROFILES)
    ap.add_argument("--seconds", type=float, default=20.0)
    ap.add_argument("--iters", default="0,1,2,3,4,5,7,10,15,20")
    ap.add_argument("--ref-iters", type=int, default=40)
    ap.add_argument("--hf", type=float, default=0, help="高域誤差を測る下限周波数 (0 = 帯域5の下端)")
    args = ap.parse_args()

    p = PROFILES[args.profile]
    x, fs = wavio.read(args.input)
    x = wavio.resample(x, fs, p.fs)[: int(args.seconds * p.fs)]
    x = x * (0.99 / max(np.abs(x).max(), 0.99))
    n = len(x) // p.block * p.block
    x = x[:n]
    blocks = [decode_coeffs(encode_block(x[i:i + p.block], p), p) for i in range(0, n, p.block)]
    f0 = args.hf or p.fs / 8
    bm = metrics.BandMetric(x, p.fs)
    ref = run(blocks, p, args.ref_iters)
    base = run(blocks, p, 0)
    hf0 = hf_energy(base - x, p.fs, f0)
    sig = np.sum(x ** 2)
    print(f"{p.name} ({p.fs}Hz, {p.audio_kbps():.0f}kbps), {n / p.fs:.0f}秒, 基準 = {args.ref_iters}回, "
          f"高域 = {f0 / 1000:g}kHz 以上")
    print(f"{'回数':>4} {'収束(基準との差)':>16} {'高域誤差':>9} {'帯域指標':>8} {'セグメンタル':>12}")
    for k in [int(v) for v in args.iters.split(",")]:
        y = base if k == 0 else run(blocks, p, k)
        conv = 10 * np.log10(max(np.sum((y - ref) ** 2), 1e-30) / sig)
        hf = 10 * np.log10(hf_energy(y - x, p.fs, f0) / hf0)
        seg = np.mean([metrics.seg_snr_db(x[:, c], y[:, c], p.fs) for c in range(2)])
        print(f"{k:4d} {conv:13.1f}dB {hf:+8.1f}dB {bm(y - x):8.2f} {seg:10.1f}dB")


if __name__ == "__main__":
    main()
