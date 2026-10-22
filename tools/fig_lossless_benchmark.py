#!/usr/bin/env python3
"""Plot the lossless-source radio-link benchmark from its saved numeric results."""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(ROOT, "docs/results/lossless_benchmark.json"), encoding="utf-8") as source:
    results = json.load(source)

materials = [source["name"] for source in results["sources"]]
fig, axes = plt.subplots(2, len(materials), figsize=(4.2 * len(materials), 6.6),
                         sharex=True, sharey="row")
styles = {"FM": ("#596777", "o"), "GraceFM": ("#006f9f", "s")}
for col, material in enumerate(materials):
    for method, (color, marker) in styles.items():
        rows = sorted((row for row in results["rows"]
                       if row["material"] == material and row["method"] == method),
                      key=lambda row: row["cn0_db_hz"])
        x = [row["cn0_db_hz"] for row in rows]
        axes[0, col].plot(x, [row["snr_db"] for row in rows], marker=marker,
                          color=color, label=method, linewidth=1.8)
        axes[1, col].plot(x, [row["visqol_moslqo"] for row in rows], marker=marker,
                          color=color, label=method, linewidth=1.8)
    axes[0, col].set_title(material)
    axes[1, col].set_xlabel("C/N0 [dB-Hz]")
    for row in axes[:, col]:
        row.grid(True, color="#dce2e7", linewidth=0.8)
        row.set_xticks([54, 60, 66, 80])
axes[0, 0].set_ylabel("Waveform SNR [dB]")
axes[1, 0].set_ylabel("ViSQOL Audio MOS-LQO")
axes[1, 0].set_ylim(1, 4.9)
axes[0, -1].legend(loc="upper left")
fig.suptitle("Licensed lossless sources · AWGN · mono FM vs GraceFM B200MH-A4 + S50M")
fig.tight_layout()
out = os.path.join(ROOT, "docs/figures/lossless_benchmark.png")
fig.savefig(out, dpi=180)
print(out)
