#!/usr/bin/env python3
"""
wav をコーデックに通す (通信路なし)。

  python tools/codec_wav.py 入力.wav 出力.wav --profile B200
  python tools/codec_wav.py 入力.wav 出力.wav --profile M700M --no-postfilter

入力はプロファイルのサンプリング周波数に変換して処理し、出力もそのサンプリング周波数 (32bit float)。
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
from gracefm.timing import min_latency  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--profile", default="B200", choices=PROFILES)
    ap.add_argument("--no-postfilter", action="store_true")
    ap.add_argument("--pf-iters", type=int, help="ポストフィルタの繰り返し回数 (省略時はプロファイルの値)")
    args = ap.parse_args()

    p = PROFILES[args.profile]
    x, fs = wavio.read(args.input)
    x = wavio.resample(x, fs, p.fs)
    peak = np.abs(x).max()
    if peak > 0.99:
        x = x * (0.99 / peak)
    n = len(x)
    nfr = int(np.ceil(n / p.block))
    xp = np.pad(x, ((0, nfr * p.block - n), (0, 0)))
    iters = p.pf_iters if args.pf_iters is None else args.pf_iters
    pf = None if args.no_postfilter else PostFilter(p.levels, iters, p.block)
    out = np.zeros_like(xp)
    for i in range(nfr):
        coefs, cell = decode_coeffs(encode_block(xp[i * p.block:(i + 1) * p.block], p), p)
        if pf is None:
            M, S = haar_inverse(coefs["M"]), haar_inverse(coefs["S"])
        else:
            M, S = pf.process("M", coefs["M"], cell["M"]), haar_inverse(coefs["S"])
        out[i * p.block:(i + 1) * p.block] = ms_to_lr(M, S)
    y = out[:n]
    wavio.write(args.output, y, p.fs)
    bm = metrics.BandMetric(x, p.fs)
    print(f"{p.name}: {p.fs}Hz, {p.audio_kbps():.0f}kbps (音声データ), ブロック長 {p.frame_ms:.2f}ms "
          f"(伝送込みの最小遅延 {min_latency(p) * 1000:.2f}ms + 処理時間), "
          f"ポストフィルタ {'なし' if pf is None else f'あり ({iters}回)'}")
    print(f"  SNR {np.mean([metrics.snr_db(x[:, c], y[:, c]) for c in range(2)]):.1f}dB  "
          f"セグメンタル {np.mean([metrics.seg_snr_db(x[:, c], y[:, c], p.fs) for c in range(2)]):.1f}dB  "
          f"帯域指標 {bm(y - x):.2f}")
    # M/S 別 (全体の SNR では、エネルギーの小さい S の相対誤差が見えにくいため)
    for name, a, b in (("M", (x[:, 0] + x[:, 1]) / 2, (y[:, 0] + y[:, 1]) / 2),
                       ("S", (x[:, 0] - x[:, 1]) / 2, (y[:, 0] - y[:, 1]) / 2)):
        if np.sum(a ** 2) > 0:
            print(f"  {name}: SNR {metrics.snr_db(a, b):.1f}dB (エネルギー {10 * np.log10(np.sum(a ** 2) / len(a)):.1f}dBFS)")


if __name__ == "__main__":
    main()
