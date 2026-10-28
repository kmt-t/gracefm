#!/usr/bin/env python3
"""
プロファイルごとの音声量を16bit PCMと比べる。

  python tools/report/pcm_equivalent.py

圧縮率 = 16bit PCM のビットレート (fs × チャンネル数 × 16) / 音声量。
PCM換算bit = (コーデックだけを通した波形SNR [dB] − 1.76) / 6.02。理想的な一様量子化のSNRからbit数に直した値で、
素材 (samples の demo・piano・percussion、各10秒) の平均。波形SNRは信号レベルによって変わるので、ダイナミックレンジの規格値ではない。
モノラル系 (末尾 M・MY・SUB50M) はモノラル形、それ以外はステレオ形の原音を使う。

あわせて、入力レベルを下げたときの波形SNRも測る (主系のみ)。素材は piano と、1 kHz正弦波 (ピーク0.89を0 dBとする)。
係数は帯域ごとの共有指数を持つので、入力が下がっても相対精度が保たれる範囲がある。

出力: docs/results/pcm_equivalent.json
"""
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from gracefm.codec import roundtrip  # noqa: E402
from gracefm.profiles import PROFILES  # noqa: E402
from tools.common import metrics, wavio  # noqa: E402

MATERIALS = ("demo", "piano", "percussion")
LEVELS = (0, -20, -40, -60, -80, -90, -100, -110, -120)      # 入力ピーク [dB]


def measure(name, p):
    mono = name.endswith(("M", "MY")) or name == "SUB50M"
    channels = 1 if mono else 2
    snrs = []
    for material in MATERIALS:
        x, _ = wavio.read(ROOT / "samples" / f"{material}-{'mono' if mono else 'stereo'}__{p.fs // 1000}k__reference.flac")
        x = np.repeat(x, 2, axis=1) if x.shape[1] == 1 else x
        y = roundtrip(x, p)
        snrs.append(float(metrics.snr_db(x[:, :channels], y[:, :channels])))
    snr = float(np.mean(snrs))
    pcm = p.fs * channels * 16 / 1000
    return dict(name=name, fs=p.fs, channels=channels, audio_kbps=p.audio_kbps(), pcm16_kbps=pcm,
                compression_ratio=round(pcm / p.audio_kbps(), 2), snr_db=round(snr, 1),
                pcm_bits=round((snr - 1.76) / 6.02, 1), snr_by_material=dict(zip(MATERIALS, (round(s, 1) for s in snrs))))


def level_curve(name):
    p = PROFILES[name]
    mono = name.endswith(("M", "MY"))
    x, _ = wavio.read(ROOT / "samples" / f"piano-{'mono' if mono else 'stereo'}__{p.fs // 1000}k__reference.flac")
    x = np.repeat(x, 2, axis=1) if x.shape[1] == 1 else x
    t = np.arange(len(x)) / p.fs
    sine = np.repeat((0.89 * np.sin(2 * np.pi * 1000 * t))[:, None], 2, axis=1)
    channels = 1 if mono else 2
    curve = {}
    for level in LEVELS:
        gain = 10 ** (level / 20)
        row = []
        for source in (x, sine):
            s = source * gain
            row.append(round(float(metrics.snr_db(s[:, :channels], roundtrip(s, p)[:, :channels])), 1))
        curve[level] = dict(piano=row[0], sine_1khz=row[1])
    return name, curve


MAIN = ("B200M", "B200MY", "B200", "B200Y", "M700M", "M700MY", "M700", "M700Y")


def main():
    rows = [measure(name, p) for name, p in PROFILES.items()]
    with ProcessPoolExecutor(6) as ex:
        curves = dict(ex.map(level_curve, MAIN))
    for r in rows:
        if r["name"] in curves:
            r["snr_by_input_level_db"] = curves[r["name"]]
    (ROOT / "docs/results/pcm_equivalent.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    for r in rows:
        print(r["name"], r["audio_kbps"], r["compression_ratio"], r["snr_db"], r["pcm_bits"])


if __name__ == "__main__":
    main()
