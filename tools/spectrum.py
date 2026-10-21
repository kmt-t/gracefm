#!/usr/bin/env python3
"""
プロファイルごとのスペクトル。

  python tools/spectrum.py

1. 送信スペクトル (RF、複素ベースバンド): 各プロファイルのフレームを連続で送り、ルートレイズドコサイン (β = 0.25) で
   パルス成形した波形の電力スペクトル密度。送信電力を 1 にそろえ、搬送波からの周波数 [kHz] に対する dB/Hz。
   占有帯域 (電力の 99% が入る帯域) と、−30dB 帯域 (ピークから 30dB 下がるところの幅) も求める。
   比較用にアナログFM (モノラル、±75kHz 偏移、50µs プリエンファシス) も同じ素材で。
2. 音声のスペクトル: 原音と、各プロファイルのコーデックだけを通したときの誤差 (出力 − 原音) の長時間平均スペクトル。
   素材は合成試験信号 demo (全帯域・ステレオ) の M チャンネル。

出力: docs/figures/rf_spectrum.png, docs/figures/audio_spectrum.png, docs/results/spectrum.json
"""
import json
import os
import sys

import numpy as np
from scipy.signal import welch

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

from gracefm import channel, wavio  # noqa: E402
from gracefm.analog_fm import AnalogFM  # noqa: E402
from gracefm.profiles import PROFILES  # noqa: E402
from gracefm.pulse import shape  # noqa: E402
from gracefm.txrx import Transmitter  # noqa: E402
from make_samples import codec, make_demo  # noqa: E402

for f in font_manager.findSystemFonts():
    if "NotoSansCJK" in f:
        font_manager.fontManager.addfont(f)
plt.rcParams["font.family"] = ["Noto Sans CJK JP", "DejaVu Sans"]
COL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]       # 分類色 (固定順)
LS = ["-", "--", "-.", ":"]
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
SPS = 8


def rf_psd(p, x):
    syms = np.concatenate(Transmitter(p).run(x))
    rs = channel.symbol_rate(p)
    w = shape(syms, sps=SPS)
    w = w / np.sqrt(np.mean(np.abs(w) ** 2))
    f, P = welch(w, fs=SPS * rs, nperseg=4096, return_onesided=False, scaling="density")
    i = np.argsort(f)
    return f[i], P[i]


def bandwidths(f, P):
    df = f[1] - f[0]
    c = np.cumsum(P) * df
    c /= c[-1]
    obw = f[np.searchsorted(c, 0.995)] - f[np.searchsorted(c, 0.005)]
    pk = P.max()
    above = f[P >= pk * 1e-3]
    return float(obw), float(above.max() - above.min())


def axes_style(ax):
    ax.set_facecolor(SURF)
    ax.grid(True, color=GRID, linewidth=0.8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(INK2)
    ax.tick_params(colors=INK2, labelsize=9)


def main():
    x, fs = wavio.read(os.path.join(ROOT, "samples", "fishin_orig.flac"))
    x = x[: 4 * fs]
    x48 = wavio.resample(x, fs, 48000)
    groups = [
        ("放送の主系（32kHz）とアナログFM", ["FM", "B200MH", "B200H", "B200M"]),
        ("放送の副系（32kHz）", ["S50M", "S100", "S85M"]),
        ("モニター（48kHz）", ["M700", "M700Q16", "M700H", "S100W"]),
    ]
    res = {}
    fig, axs = plt.subplots(len(groups), 1, figsize=(8, 9.5), facecolor=SURF)
    for ax, (title, names) in zip(axs, groups):
        axes_style(ax)
        for j, n in enumerate(names):
            if n == "FM":
                fm = AnalogFM(x[:, 0], fs)
                f, P = welch(fm.tx, fs=fm.fs_rf, nperseg=8192, return_onesided=False, scaling="density")
                i = np.argsort(f)
                f, P = f[i], P[i]
                label = "アナログFM（モノラル）"
            else:
                p = PROFILES[n]
                f, P = rf_psd(p, x48 if p.fs == 48000 else x)
                label = f"{n}（{p.audio_kbps():.0f}kbps）"
            obw, b30 = bandwidths(f, P)
            res[n] = {"occupied_99_kHz": round(obw / 1e3, 1), "bw_minus30dB_kHz": round(b30 / 1e3, 1)}
            if n != "FM":
                res[n]["symbol_rate_ksps"] = round(channel.symbol_rate(PROFILES[n]) / 1e3, 1)
                res[n]["modulation"] = PROFILES[n].modulation
            ax.plot(f / 1e3, 10 * np.log10(P + 1e-30), color=COL[j], ls=LS[j], lw=1.6,
                    label=f"{label}  99%帯域 {obw / 1e3:.0f}kHz")
        lim = 450 if "モニター" in title else 200
        ax.set_xlim(-lim, lim)
        ax.set_ylim(-110, -10)
        ax.set_title(title, loc="left", fontsize=11, color=INK)
        ax.set_ylabel("電力スペクトル密度 [dB/Hz]\n（送信電力 = 1）", fontsize=9, color=INK2)
        ax.legend(fontsize=8.5, frameon=False, loc="upper right", labelcolor=INK)
    axs[-1].set_xlabel("搬送波からの周波数 [kHz]", fontsize=9, color=INK2)
    fig.suptitle("送信スペクトル（ルートレイズドコサイン β=0.25、送信電力をそろえた比較）", fontsize=12, color=INK, x=0.02,
                 ha="left")
    fig.tight_layout()
    fig.savefig(os.path.join(ROOT, "docs", "figures", "rf_spectrum.png"), dpi=130, facecolor=SURF)

    # 音声のスペクトル
    demo48 = make_demo(48000)
    demo32 = wavio.resample(demo48, 48000, 32000)
    demo32 *= 0.89 / np.abs(demo32).max()
    agroups = [("放送（32kHz、demo の M）", demo32, 32000, ["B200H", "B200", "S100"]),
               ("モニター（48kHz、demo の M）", demo48, 48000, ["M700H", "M700", "M700H基本層"])]
    from dataclasses import replace
    mh = PROFILES["M700H"]
    PROFILES["M700H基本層"] = replace(mh, name="M700H基本層", bits_m=mh.base_m, bits_s=mh.base_s, base_m=None,
                                     base_s=None, modulation="qpsk", alpha=1.0)
    fig, axs = plt.subplots(2, 1, figsize=(8, 7), facecolor=SURF)
    for ax, (title, xx, fsa, names) in zip(axs, agroups):
        axes_style(ax)
        m = (xx[:, 0] + xx[:, 1]) / 2
        f, P0 = welch(m, fs=fsa, nperseg=4096)
        ax.plot(f / 1e3, 10 * np.log10(P0 + 1e-30), color=INK2, lw=1.2, label="原音")
        for j, n in enumerate(names):
            y = codec(xx, PROFILES[n])
            e = (y[:, 0] + y[:, 1]) / 2 - m
            f, P = welch(e, fs=fsa, nperseg=4096)
            ax.plot(f / 1e3, 10 * np.log10(P + 1e-30), color=COL[j], ls=LS[j], lw=1.5,
                    label=f"誤差：{n}（{PROFILES[n].audio_kbps():.0f}kbps）")
            res.setdefault("audio_error_snr_dB", {})[n] = round(float(10 * np.log10(np.sum(m ** 2) / np.sum(e ** 2))), 1)
        ax.set_xlim(0, fsa / 2e3)
        ax.set_ylim(-200, -20)
        ax.set_title(title, loc="left", fontsize=11, color=INK)
        ax.set_ylabel("パワー [dB/Hz]", fontsize=9, color=INK2)
        ax.legend(fontsize=8.5, frameon=False, loc="upper right", labelcolor=INK)
    axs[-1].set_xlabel("周波数 [kHz]", fontsize=9, color=INK2)
    fig.suptitle("音声のスペクトル：原音と、コーデックだけを通したときの誤差", fontsize=12, color=INK, x=0.02, ha="left")
    fig.tight_layout()
    fig.savefig(os.path.join(ROOT, "docs", "figures", "audio_spectrum.png"), dpi=130, facecolor=SURF)
    with open(os.path.join(ROOT, "docs", "results", "spectrum.json"), "w") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    for k, v in res.items():
        print(k, v)


if __name__ == "__main__":
    main()
