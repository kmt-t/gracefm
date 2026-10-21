#!/usr/bin/env python3
"""
ポストフィルタ (量子化雑音の除去) の説明図と数値。コーデックだけ (通信路なし)。

  python tools/fig_postfilter.py --profile S50M --json docs/results/postfilter_fig.json

図: docs/figures/postfilter.png
  (a) 波形: 原音 / ポストフィルタなし (Haar 合成のまま) / 平滑化だけ (射影なし) / ポストフィルタ (4回)
  (b) 誤差の波形
  (c) 誤差のスペクトル (と原音のスペクトル)
  (d) 同じく --profile2 (既定 B200M: 全帯域を送る基本層)
数値: 波形SNR [dB]、帯域ごとの誤差電力 [dB]
"""
import argparse
import json
import os
import sys

import numpy as np
from scipy.signal import welch

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

from gracefm import metrics, wavio  # noqa: E402
from gracefm.codec import decode_coeffs, encode_block, haar_inverse  # noqa: E402
from gracefm.postfilter import KERNEL, PostFilter  # noqa: E402
from gracefm.profiles import PROFILES  # noqa: E402

for f in font_manager.findSystemFonts():
    if "NotoSansCJK" in f:
        font_manager.fontManager.addfont(f)
plt.rcParams["font.family"] = ["Noto Sans CJK JP", "DejaVu Sans"]
COL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"


def decode(x, p, mode):
    """mode: none / smooth / pf → M チャンネルの復号波形"""
    pf = PostFilter(p.levels, p.pf_iters, p.block) if mode == "pf" else None
    out = []
    for i in range(0, len(x), p.block):
        coefs, cell = decode_coeffs(encode_block(x[i:i + p.block], p), p)
        out.append(pf.process("M", coefs["M"], cell["M"]) if pf else haar_inverse(coefs["M"]))
    y = np.concatenate(out)
    if mode == "smooth":
        y = np.convolve(y, KERNEL, mode="same")
    return y


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="S50M")
    ap.add_argument("--profile2", default="B200M")
    ap.add_argument("--material", default="fishin")
    ap.add_argument("--seconds", type=float, default=10)
    ap.add_argument("--json")
    ap.add_argument("--fig", default=os.path.join(ROOT, "docs", "figures", "postfilter.png"))
    ap.add_argument("--t0", type=float, default=None, help="波形を描く位置 [s] (省略時は誤差の大きい所を選ぶ)")
    a = ap.parse_args()
    p = PROFILES[a.profile]
    x, fs = wavio.read(os.path.join(ROOT, "samples", f"{a.material}_orig.flac"))
    x = x[: int(a.seconds * fs) // p.block * p.block]
    m = (x[:, 0] + x[:, 1]) / 2
    ys = {k: decode(np.stack([m, m], 1), p, k) for k in ("none", "smooth", "pf")}
    names = {"none": "なし（Haar 合成のまま）", "smooth": "平滑化だけ（射影なし）", "pf": "ポストフィルタ（4回）"}

    edges = [0, fs / 2 ** (p.levels + 1)] + [fs / 2 ** (p.levels + 1 - k) for k in range(1, p.levels + 1)]
    res = {}
    for k, y in ys.items():
        e = y - m
        f, E = welch(e, fs, nperseg=1024)
        band = [float(10 * np.log10(E[(f >= lo) & (f < hi)].sum() + 1e-30)) for lo, hi in zip(edges[:-1], edges[1:])]
        res[k] = dict(snr=float(metrics.snr_db(m, y)), band_err_db=band)
        print(f"{names[k]:16s} SNR {res[k]['snr']:6.2f}dB  帯域ごとの誤差 " + " ".join(f"{b:6.1f}" for b in band))

    # 描く位置: 誤差 (なし) の大きいブロックの付近
    blk = p.block
    if a.t0 is None:
        eb = ((ys["none"] - m) ** 2).reshape(-1, blk).sum(1)
        sb = (m ** 2).reshape(-1, blk).sum(1)
        i0 = int(np.argmax(eb * (sb > np.median(sb))))
    else:
        i0 = int(a.t0 * fs) // blk
    s0, s1 = max(i0 - 1, 0) * blk, (max(i0 - 1, 0) + 3) * blk
    t = (np.arange(s0, s1) - s0) / fs * 1000

    p2 = PROFILES[a.profile2]
    ys2 = {k: decode(np.stack([m, m], 1), p2, k) for k in ("none", "smooth", "pf")}
    res2 = {}
    for k, y in ys2.items():
        res2[k] = dict(snr=float(metrics.snr_db(m, y)))
        print(f"{a.profile2} {names[k]:16s} SNR {res2[k]['snr']:6.2f}dB")
    fig, ax = plt.subplots(4, 1, figsize=(8.5, 12.5), gridspec_kw=dict(height_ratios=[1.3, 1, 1.2, 1.2]))
    ax[0].plot(t, m[s0:s1], color=INK, lw=1.6, label="原音")
    for c, k in zip(COL, ("none", "smooth", "pf")):
        ax[0].plot(t, ys[k][s0:s1], color=c, lw=1.1, drawstyle="steps-mid" if k == "none" else "default", label=names[k])
    ax[1].axhline(0, color=GRID, lw=0.8)
    for c, k in zip(COL, ("none", "smooth", "pf")):
        ax[1].plot(t, ys[k][s0:s1] - m[s0:s1], color=c, lw=1.1,
                   drawstyle="steps-mid" if k == "none" else "default", label=names[k])
    for axi in ax[:2]:
        for b in range(1, 3):
            axi.axvline(b * blk / fs * 1000, color=INK2, lw=0.6, ls=":")
        axi.set_xlabel("時間 [ms]（点線：ブロック境界）", fontsize=9, color=INK2)
    ax[0].set_ylabel("振幅", fontsize=9, color=INK2)
    ax[1].set_ylabel("誤差（復号 − 原音）", fontsize=9, color=INK2)
    ax[0].set_title(f"(a) 波形（{a.profile}、{a.material} の M、3ブロック）", loc="left", fontsize=11, color=INK)
    ax[1].set_title("(b) 誤差の波形", loc="left", fontsize=11, color=INK)
    f, X = welch(m, fs, nperseg=1024)
    ax[2].plot(f / 1000, 10 * np.log10(X + 1e-30), color=INK, lw=1.4, label="原音")
    for c, k in zip(COL, ("none", "smooth", "pf")):
        f, E = welch(ys[k] - m, fs, nperseg=1024)
        ax[2].plot(f / 1000, 10 * np.log10(E + 1e-30), color=c, lw=1.1, label=f"誤差：{names[k]}（SNR {res[k]['snr']:.1f}dB）")
    ax[2].set_xlabel("周波数 [kHz]", fontsize=9, color=INK2)
    ax[2].set_ylabel("電力スペクトル密度 [dB/Hz]", fontsize=9, color=INK2)
    ax[2].set_title(f"(c) 誤差のスペクトル（{a.profile}、{a.seconds:.0f}秒）", loc="left", fontsize=11, color=INK)
    f, X = welch(m, fs, nperseg=1024)
    ax[3].plot(f / 1000, 10 * np.log10(X + 1e-30), color=INK, lw=1.4, label="原音")
    for c, k in zip(COL, ("none", "smooth", "pf")):
        f, E = welch(ys2[k] - m, fs, nperseg=1024)
        ax[3].plot(f / 1000, 10 * np.log10(E + 1e-30), color=c, lw=1.1, label=f"誤差：{names[k]}（SNR {res2[k]['snr']:.1f}dB）")
    ax[3].set_xlabel("周波数 [kHz]", fontsize=9, color=INK2)
    ax[3].set_ylabel("電力スペクトル密度 [dB/Hz]", fontsize=9, color=INK2)
    ax[3].set_title(f"(d) 誤差のスペクトル（{a.profile2}、{a.seconds:.0f}秒）", loc="left", fontsize=11, color=INK)
    for axi in ax[2:]:
        axi.set_ylim(-150, -40)
    for axi in ax:
        axi.grid(color=GRID, lw=0.6)
        axi.legend(fontsize=8, frameon=False, labelcolor=INK)
        for sp in ("top", "right"):
            axi.spines[sp].set_visible(False)
    fig.tight_layout()
    fig.savefig(a.fig, dpi=130)
    print("図:", a.fig, " 位置:", s0 / fs, "s")
    if a.json:
        with open(a.json, "w") as fjs:
            json.dump(dict(profile=a.profile, profile2=a.profile2, material=a.material, band_edges_hz=edges,
                           result=res, result2=res2), fjs,
                      ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
