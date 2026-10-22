#!/usr/bin/env python3
"""docs/results/perceptual_eval.json から SNR と ViSQOL の C/N0 曲線を描く。"""
import argparse
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
COLORS = {"GraceFM": "#2468a0", "FM": "#ce6b24", "AM": "#5c8a52"}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", default=os.path.join(ROOT, "docs/results/perceptual_eval.json"))
    ap.add_argument("--output", default=os.path.join(ROOT, "docs/figures/perceptual_eval.png"))
    args = ap.parse_args()
    with open(args.json) as f:
        rows = json.load(f)["summary"]
    materials = sorted({row["material"] for row in rows})
    fig, axes = plt.subplots(len(materials), 2, figsize=(10, 3.6 * len(materials)), squeeze=False,
                             sharex=True)
    for i, material in enumerate(materials):
        for method in ("GraceFM", "FM", "AM"):
            subset = sorted((r for r in rows if r["material"] == material and r["channel"] == "awgn"
                             and r["method"] == method), key=lambda r: r["cn0_db_hz"])
            if not subset:
                continue
            x = [r["cn0_db_hz"] for r in subset]
            color = COLORS[method]
            style = "o--" if method == "AM" else "o-"
            label = "AM (diagnostic)" if method == "AM" else method
            axes[i, 0].plot(x, [r["snr_db"] for r in subset], style, color=color, label=label)
            axes[i, 1].plot(x, [r["visqol_moslqo"] for r in subset], style, color=color, label=label)
        for ax in axes[i]:
            ax.set_title(material)
            ax.grid(True, alpha=0.25)
            ax.set_xlabel("C/N0 (dB-Hz)")
        axes[i, 0].set_ylabel("Waveform SNR (dB)")
        axes[i, 1].set_ylabel("ViSQOL Audio MOS-LQO")
        axes[i, 1].set_ylim(1, 5)
    axes[0, 0].legend(loc="upper left")
    fig.suptitle("GraceFM, analog FM and AM under equal received C/N0 (AWGN)")
    fig.tight_layout()
    fig.savefig(args.output, dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
