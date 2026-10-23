#!/usr/bin/env python3
"""docs/results/hybrid_eval.json から実験用高域変調の比較図を作る。"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RESULT = os.path.join(ROOT, "docs/results/hybrid_eval.json")
OUT = os.path.join(ROOT, "docs/figures")
PAIRS = (("B200MH-A4", "B200MHY-A4", "Mono"),
         ("B200H-A4", "B200HY-A4", "Stereo"))


def main():
    with open(RESULT) as f:
        data = json.load(f)
    spectra = {row["profile"]: row for row in data["spectra"]}
    budgets = {row["profile"]: row for row in data["budgets"]}
    rows = data["results"]
    os.makedirs(OUT, exist_ok=True)

    fig, ax = plt.subplots(figsize=(7.8, 4.4))
    x = np.arange(2)
    for i, (_, _, label) in enumerate(PAIRS):
        base, hybrid, _ = PAIRS[i]
        ax.bar(x[i] - .18, spectra[base]["occupied_99_khz"], .34,
               color="#526f92", label="Conventional" if i == 0 else None)
        ax.bar(x[i] + .18, spectra[hybrid]["occupied_99_khz"], .34,
               color="#dd7d43", label="Y hybrid" if i == 0 else None)
    ax.set_xticks(x, [p[2] for p in PAIRS])
    ax.set_ylabel("99% occupied bandwidth (kHz)")
    ax.set_title("RRC shaped waveform; same source and PSD method")
    ax.grid(axis="y", alpha=.2)
    ax.legend(frameon=False)
    for i, (base, hybrid, _) in enumerate(PAIRS):
        for pos, name in ((x[i] - .18, base), (x[i] + .18, hybrid)):
            ax.text(pos, spectra[name]["occupied_99_khz"] + 2,
                    f"{budgets[name]['symbol_rate_ksym_s']:.1f} ksps",
                    ha="center", fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "hybrid_bandwidth.png"), dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(3, 2, figsize=(10.4, 10.0), sharex="col")
    metrics = (("snr_db", "Waveform SNR (dB)"),
               ("high_4_16khz", "4–16 kHz Haar SNR (dB)"),
               ("visqol_moslqo", "ViSQOL Audio MOS-LQO"))
    for col, (base, hybrid, label) in enumerate(PAIRS):
        for name, phase_only, style, color, legend in (
                (base, False, "-o", "#526f92", "Conventional"),
                (hybrid, False, "-s", "#dd7d43", "Y hybrid"),
                (hybrid, True, "--^", "#6c9c72", "Y phase only")):
            selected = sorted((r for r in rows if r["profile"] == name and
                               r["scenario"] == "awgn" and r["secondary"] is None and
                               bool(r["phase_only"]) == phase_only),
                              key=lambda r: r["cn0_db_hz"])
            for row, (field, ylabel) in enumerate(metrics):
                axes[row, col].plot([r["cn0_db_hz"] for r in selected],
                                    [r[field] for r in selected], style,
                                    color=color, label=legend)
                axes[row, col].set_ylabel(ylabel)
                axes[row, col].grid(alpha=.2)
        axes[0, col].set_title(label)
        axes[0, col].legend(frameon=False, fontsize=8)
        axes[-1, col].set_xlabel("C/N0 (dB-Hz)")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "hybrid_quality.png"), dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
