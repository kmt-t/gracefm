#!/usr/bin/env python3
"""
フレーム欠落の評価: フレームが届かないとき (CRC 不一致・同期外れ・遮断) に音が途切れるかを見る。

  python tools/eval_loss.py --seconds 5 --json docs/results/loss_eval.json

通信路は強い電波 (C/N0 80dB-Hz、雑音による誤りはほぼ無い) とし、欠落だけを与える:
  random p%      : 各系統のフレームを独立に p% 落とす
  burst L ms     : 1秒ごとに L ms の遮断。main = 主系だけ、both = 両系統が同時
構成:
  1系統・無音     : B200M のみ (全電力)。欠落は 0 (無音) で埋める
  1系統・PLC      : B200M のみ。欠落は PLC (32次 LPC の外挿、10ms 保持・20ms で減衰)
  2系統・PLC      : B200M＋SUB50M (独立チャンネル)。帯域ごとに融合し、両方欠けた区間だけ PLC
数値: 波形SNR [dB] / 両系統とも欠けた時間 (PLC で埋めた時間) [%] / 無音になった時間 [%] / 最長の欠け [ms]
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

CN0 = 80.0
PATTERNS = [("none", 0), ("random", 1), ("random", 5), ("random", 20), ("random", 50),
            ("main", 20), ("main", 200), ("both", 4), ("both", 20), ("both", 100)]
CONFIGS = ["1系統・無音", "1系統・PLC", "2系統・PLC"]
HOLD_MS, FADE_MS = 10.0, 20.0


def drop(frames, mask):
    return [None if m else f for f, m in zip(frames, mask)]


def masks(kind, val, nfr_a, nfr_b, block_ms, rng):
    if kind == "none":
        return np.zeros(nfr_a, bool), np.zeros(nfr_b, bool)
    if kind == "random":
        return rng.random(nfr_a) < val / 100, rng.random(nfr_b) < val / 100
    per = int(round(1000 / block_ms))                      # 1秒あたりのフレーム数
    L = max(1, int(round(val / block_ms)))
    def burst(n, start):
        idx = np.arange(n)
        return ((idx - start) % per) < L
    st = int(rng.integers(per))
    a = burst(nfr_a, st)
    b = burst(nfr_b, st) if kind == "both" else np.zeros(nfr_b, bool)
    return a, b


def runs(v):
    """欠けた区間 (False が続く区間) の長さの列"""
    d = np.diff(np.concatenate([[0], (~v).astype(int), [0]]))
    return np.flatnonzero(d == -1) - np.flatnonzero(d == 1)


def job(a):
    mat, kind, val, seed, sec = a
    x, fs = wavio.read(os.path.join(ROOT, "samples", f"{mat}__32k__reference.flac"))
    x = x[: int(sec * fs)]
    pm, ps = PROFILES["B200M"], PROFILES["SUB50M"]
    off = 0
    block_ms = 1000 * pm.block / pm.fs
    rng = np.random.default_rng(seed)
    fa0 = txrx.Transmitter(pm, 0, 0).run(x)
    fb0 = txrx.Transmitter(ps, 1, off).run(x)
    ma, mb = masks(kind, val, len(fa0), len(fb0), block_ms, np.random.default_rng(seed + 7))
    out = {}
    for cfg in CONFIGS:
        two = cfg.startswith("2")
        es = CN0 + (10 * np.log10(0.5) if two else 0) - 10 * np.log10(channel.symbol_rate(pm))
        fa = drop(channel.through(fa0, es, np.ones(len(fa0)), rng), ma)
        fb = None
        if two:
            esb = CN0 + 10 * np.log10(0.5) - 10 * np.log10(channel.symbol_rate(ps))
            fb = drop(channel.through(fb0, esb, np.ones(len(fb0)), rng), mb)
        if two:
            y, st = txrx.receive(pm, fa, fb, len(x), off, profile_b=ps, return_streams=True)
            v = st["vA"] | st["vB"]
        else:
            yA, v = txrx.StreamDecoder(pm).run(fa, len(x), 0)
            y = yA * v[:, None] if cfg.endswith("無音") else plc.conceal(yA, v, fs, order=32)
        L = runs(v)
        if cfg.endswith("無音"):
            muted = (~v).mean() * 100
        else:
            muted = np.maximum(L - int(fs * (HOLD_MS + FADE_MS) / 1000), 0).sum() / len(v) * 100
        out[cfg] = dict(snr=float(metrics.snr_db(x, y)), plc=float((~v).mean() * 100), muted=float(muted),
                        longest_ms=float(L.max() / fs * 1000) if len(L) else 0.0)
    return a, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=5)
    ap.add_argument("--seeds", type=int, default=2)
    ap.add_argument("--materials", default="fishin,vibeace")
    ap.add_argument("--patterns", default="all", help="all または none:0,random:20,main:200,both:100 の形式")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--json")
    a = ap.parse_args()
    if a.workers < 1:
        ap.error("workers は 1 以上にしてください")
    if a.patterns == "all":
        patterns = PATTERNS
    else:
        try:
            patterns = [(kind, int(value)) for kind, value in
                        (part.split(":", 1) for part in a.patterns.split(","))]
        except (ValueError, TypeError):
            ap.error("patterns は kind:value をカンマで並べてください")
    if any(pattern not in PATTERNS for pattern in patterns):
        ap.error("patterns に未定義の欠落条件があります")
    jobs = [(m, k, v, s, a.seconds) for m in a.materials.split(",") for k, v in patterns for s in range(a.seeds)]
    res = {}
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for j, o in ex.map(job, jobs):
            res.setdefault(f"{j[0]}|{j[1]}|{j[2]}", []).append(o)
    table = {}
    for key, L in res.items():
        table[key] = {c: {m: float(np.mean([o[c][m] for o in L])) for m in L[0][c]} for c in CONFIGS}
    print("素材|欠落|値 : " + " | ".join(CONFIGS) + "   (SNR dB / PLC % / 無音 % / 最長 ms)")
    for key, t in table.items():
        print(key, " | ".join(f"{t[c]['snr']:5.1f}/{t[c]['plc']:4.1f}/{t[c]['muted']:4.1f}/{t[c]['longest_ms']:4.0f}"
                              for c in CONFIGS), flush=True)
    if a.json:
        with open(a.json, "w") as f:
            json.dump(dict(cn0=CN0, configs=CONFIGS, patterns=patterns, seconds=a.seconds,
                           seeds=a.seeds, main_profile="B200M", sub_profile="SUB50M", table=table),
                      f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
