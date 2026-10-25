#!/usr/bin/env python3
"""
送信 → 通信路 (AWGN + フレーム欠落) → 受信 の一括シミュレーション。

  python tools/sim_link.py 入力.wav 出力.wav --profile B200 --snr 8 --loss 0.02
  python tools/sim_link.py 入力.wav 出力.wav --profile M700M --snr-a 6 --snr-b 15 --single
  python tools/sim_link.py 入力.wav --profile B200 --sweep        # SNR を振って表を出す
  python tools/sim_link.py 入力.wav --profile B200M --snr 8 --power total   # 合計電力を固定して2系統に等分

SNR は Es/N0 (1シンボルあたり、各系統)。--loss は系統ごとに独立なフレーム欠落率 (干渉・フェージングの谷の代わり)。
換算 (同じ平均シンボルエネルギー・シンボルレートのモデル):
  C/N0 [dB-Hz] = Es/N0 [dB] + 10 log10(Rs [symbol/s])
  C/N  [dB]    = C/N0 [dB-Hz] - 10 log10(Bn [Hz])      Bn = C/N を定義する雑音帯域 (--bn)
--power per-stream: 各系統の Es/N0 を --snr にそろえる (単系統と同じ条件の波をもう1本足す比較)
--power total     : 2系統の合計受信電力を、単系統で --snr になる電力に固定して等分する
                    (同じシンボルレート・雑音密度・伝搬条件なら、各系統の Es/N0 は --snr - 3.01dB)
2系統の占有帯域の合計は 1系統の 2倍 (2つの周波数の外端間の幅とは別)。
入力の原音は評価にだけ使い、受信アルゴリズムには渡さない。
"""
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gracefm import metrics, modem, wavio  # noqa: E402
from gracefm.postfilter import OUT_FS, postfilter  # noqa: E402
from gracefm.profiles import PROFILES  # noqa: E402
from gracefm.timing import min_latency  # noqa: E402
from gracefm.txrx import Transmitter, receive  # noqa: E402


def channel(frames, snr_db, loss, rng):
    out = []
    for f in frames:
        if rng.random() < loss:
            out.append(None)
        else:
            out.append(modem.awgn(f, snr_db, rng))
    return out


def run_once(x, p, snr_a, snr_b, loss, single, seed, power="per-stream"):
    """power="total" なら 2系統の各 Es/N0 を 10log10(2) 下げる (合計電力固定)"""
    rng = np.random.default_rng(seed)
    off = p.block // 2
    split = 0.0 if (single or power == "per-stream") else 10 * np.log10(2)
    fa = channel(Transmitter(p, 0, 0).run(x), snr_a - split, loss, rng)
    fb = None if single else channel(Transmitter(p, 1, off).run(x), snr_b - split, loss, rng)
    return receive(p, fa, fb, len(x), off)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("output", nargs="?")
    ap.add_argument("--profile", default="B200", choices=PROFILES)
    ap.add_argument("--snr", type=float, default=20.0, help="両系統の Es/N0 [dB]")
    ap.add_argument("--snr-a", type=float)
    ap.add_argument("--snr-b", type=float)
    ap.add_argument("--loss", type=float, default=0.0, help="系統ごとのフレーム欠落率")
    ap.add_argument("--single", action="store_true", help="系統 A だけで送る")
    ap.add_argument("--no-postfilter", action="store_true", help="出力にポストフィルタ (48 kHz / int32) を使わない")
    ap.add_argument("--seconds", type=float, default=0, help="先頭から何秒を使うか (0 = 全部)")
    ap.add_argument("--sweep", action="store_true", help="SNR を振って表を出す")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--power", default="per-stream", choices=["per-stream", "total"])
    ap.add_argument("--bn", type=float, default=180e3, help="C/N を表示するときの雑音帯域 [Hz]")
    args = ap.parse_args()

    p = PROFILES[args.profile]
    x, fs = wavio.read(args.input)
    x = wavio.resample(x, fs, p.fs)
    if args.seconds:
        x = x[: int(args.seconds * p.fs)]
    x = x * (0.99 / max(np.abs(x).max(), 0.99))
    tx = Transmitter(p)
    rs = tx.symbol_rate()
    print(f"{p.name}: {p.fs}Hz / {p.audio_kbps():.0f}kbps / ブロック長 {p.frame_ms:.2f}ms "
          f"(伝送込みの最小遅延 {min_latency(p) * 1000:.2f}ms + 処理時間) / {p.modulation} / "
          f"1系統 {rs / 1000:.1f}kシンボル/秒 (ロールオフ{p.pulse_beta:g}で理論支持幅 "
          f"{rs * (1 + p.pulse_beta) / 1000:.0f}kHz。"
          f"同じプロファイル2系統の合計 {rs * (1 + p.pulse_beta) * 2 / 1000:.0f}kHz)")
    print(f"  電力条件 {args.power} / C/N0 = Es/N0 + {10 * np.log10(rs):.2f}dB, "
          f"C/N({args.bn / 1000:g}kHz) = Es/N0 + {10 * np.log10(rs / args.bn):+.2f}dB (各系統)")
    bm = metrics.BandMetric(x, p.fs)

    def report(y):
        return (bm(y - x), np.mean([metrics.seg_snr_db(x[:, c], y[:, c], p.fs) for c in range(2)]))

    if args.sweep:
        snrs = [-2, 0, 2, 4, 6, 8, 10, 12, 15, 20]
        print(f"  {'構成':30s} " + " ".join(f"{s:>6}dB" for s in snrs) + "  (横軸: 1系統あたりの Es/N0。"
              "合計電力固定では単系統の値)")
        for label, single, loss, power in [("1系統", True, 0.0, "per-stream"),
                                           ("2系統 (各系統同じEs/N0)", False, 0.0, "per-stream"),
                                           ("2系統 (合計電力固定)", False, 0.0, "total"),
                                           ("2系統 + 欠落5% (各系統同じ)", False, 0.05, "per-stream")]:
            row = []
            for s in snrs:
                y, _ = run_once(x, p, s, s, loss, single, args.seed, power)
                row.append(report(y)[0])
            print(f"  {label:30s} " + " ".join(f"{v:8.2f}" for v in row), flush=True)
        print("  (帯域指標。誤りなしの値は tools/codec_wav.py で確認できる)")
        return

    sa = args.snr if args.snr_a is None else args.snr_a
    sb = args.snr if args.snr_b is None else args.snr_b
    y, st = run_once(x, p, sa, sb, args.loss, args.single, args.seed,
                     args.power)
    for k in ("A", "B"):
        if k in st:
            s = st[k]
            print(f"  系統{k}: {s['frames']}フレーム中 欠落 {s['lost']} / "
                  f"基本CRC不一致 {s['crc_fail']} / H1/H2 CRC不一致 {s['high_crc_fail']}")
    print(f"  PLC で埋めたサンプル {st['plc_samples']} ({st['plc_samples'] / len(x) * 100:.2f}%)")
    m, seg = report(y)
    print(f"  波形SNR {metrics.snr_db(x, y):.2f}dB  セグメンタルSNR {seg:.1f}dB  帯域指標 {m:.2f}")
    if args.output:
        if args.no_postfilter:
            wavio.write(args.output, y, p.fs)
        else:
            wavio.write_int32(args.output, postfilter(y, p.fs), OUT_FS)


if __name__ == "__main__":
    main()
