#!/usr/bin/env python3
"""
samples/ の試聴音声を、素材 × 形（モノラル・ステレオ）× 主系 × 副系 × 条件のマトリクスで作る。

  python tools/samples/make_samples.py                 # eval_audio/lossless の原音から全部作り直す
  python tools/samples/make_samples.py --source demo   # 素材を一つだけ

素材: demo（合成試験信号）、piano、percussion（どちらもステレオの CC0 音源）。各10秒、32 kHz。
モノラル形は (L+R)/2、ステレオ形は原音のまま。同じ素材・同じ条件で両形が揃う。
主系: モノラル形は B200M・B200MY、ステレオ形は B200・B200Y。副系: なし または SUB50M。
条件: コーデックだけ（副系なしのみ）、AWGN の C/N0 54・57・60・66・80、レイリーフェージング（C/N0 60）、
主系の周波数だけ10dB低下（C/N0 66）。同じ受信条件のアナログFMはモノラル形だけ。
通信路は主系・副系とも独立のチャンネルで、C/N0は同じ値。
"""
import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, ROOT)

from tools.samples.sample_names import sample_name, reference_name

from gracefm import channel, wavio  # noqa: E402
from gracefm.analog_fm import AnalogFM  # noqa: E402
from gracefm.codec import roundtrip  # noqa: E402
from gracefm.profiles import PROFILES  # noqa: E402

OUT = os.path.join(ROOT, "samples")
SEC = 10.0
FS = 32000

# 素材: (名前, 原音ファイル (eval_audio 下), 開始秒)。demo は合成。
MATERIALS = (("demo", None, 0.0),
             ("piano", "lossless/Emotional_piano.wav", 1.0),
             ("percussion", "lossless/Ceramic_Djembe.wav", 0.5))
FORMS = {"mono": ("B200M", "B200MY"), "stereo": ("B200", "B200Y")}
SUBS = (None, "SUB50M")
CN0_LIST = (54, 57, 60, 66, 80)      # C/N0 [dB-Hz]。66 は 5m・室内の保守的な見積もり (SPEC 付録D)
CASES = tuple(f"awgn{c}" for c in CN0_LIST) + ("rayleigh60", "main_minus10db66")
BN = 180e3                           # C/N を表示する雑音帯域 [Hz] (FM放送 1波ぶん)


def source_name(material, form):
    return f"{material}-{form}"


def make_demo(fs=48000, dur=10.0, seed=0):
    """弱点を突く合成試験信号: 大きい 55Hz + 小さい和音 (同じ最低域), キック/スネア, 静かなピアノ風 + 残響"""
    rng = np.random.default_rng(seed)
    n = int(fs * dur)
    t = np.arange(n) / fs
    L = np.zeros(n)
    R = np.zeros(n)
    sec1 = t < 6.0
    bass = 0.45 * np.sin(2 * np.pi * 55 * t) * (0.8 + 0.2 * np.sin(2 * np.pi * 0.5 * t)) * sec1
    pad = sum(np.sin(2 * np.pi * f0 * t + ph) for f0, ph in [(660, 0), (825, 1), (990, 2)]) * 0.006 * sec1
    L += bass + 1.2 * pad
    R += bass + 0.8 * pad
    for hit in np.arange(0.0, 6.0, 0.5):
        i0 = int(hit * fs)
        tt = np.arange(int(0.25 * fs)) / fs
        kick = 0.5 * np.sin(2 * np.pi * np.cumsum(50 + 70 * np.exp(-tt * 30)) / fs) * np.exp(-tt * 12)
        e = min(i0 + len(tt), n)
        L[i0:e] += kick[:e - i0]
        R[i0:e] += kick[:e - i0]
    for hit in np.arange(0.25, 6.0, 1.0):
        i0 = int(hit * fs)
        k = int(0.18 * fs)
        tt = np.arange(k) / fs
        env = np.exp(-tt * 25)
        body = 0.15 * np.sin(2 * np.pi * 190 * tt) * np.exp(-tt * 30)
        e = min(i0 + k, n)
        L[i0:e] += (np.diff(rng.standard_normal(k + 1)) * 0.12 * env + body)[:e - i0]
        R[i0:e] += (np.diff(rng.standard_normal(k + 1)) * 0.12 * env + body)[:e - i0]
    for j, f0 in enumerate([261.6, 329.6, 392.0, 523.3, 392.0, 329.6, 293.7, 261.6]):
        i0 = int((6.0 + j * 0.5) * fs)
        tt = np.arange(n - i0) / fs
        tone = sum((0.5 ** h) * np.sin(2 * np.pi * f0 * (h + 1) * tt) for h in range(6))
        tone *= 0.05 * np.exp(-tt * 3) * (1 - np.exp(-tt * 400))
        L[i0:] += tone
        R[i0:] += tone * 0.9
    for dly, g in [(0.031, 0.35), (0.047, 0.3), (0.071, 0.25), (0.113, 0.2), (0.167, 0.15)]:
        d = int(dly * fs)
        L2, R2 = np.zeros(n), np.zeros(n)
        L2[d:], R2[d:] = R[:-d] * g, L[:-d] * g
        L[t >= 6.0] += L2[t >= 6.0]
        R[t >= 6.0] += R2[t >= 6.0]
    x = np.stack([L, R], axis=1)
    return x * (0.89 / np.abs(x).max())



def cn(c):
    return c - 10 * np.log10(BN)


def load_material(material, path, start, eval_audio):
    """10秒・32 kHz・ピーク0.89のステレオ原音"""
    if path is None:
        x, fs = make_demo(48000), 48000
    else:
        x, fs = wavio.read(os.path.join(eval_audio, path))
        x = x[int(start * fs):int((start + SEC) * fs)]
    x = x * (0.89 / np.abs(x).max())
    x = wavio.resample(x, fs, FS)[: int(SEC * FS)]
    return x * (0.89 / np.abs(x).max())


def to_form(x, form):
    return np.repeat(((x[:, 0] + x[:, 1]) / 2)[:, None], 2, axis=1) if form == "mono" else x


def save(name, y, mono):
    path = os.path.join(OUT, name)
    wavio.write_flac24(path, y[:, :1] if mono else y, FS)


def generate(task):
    material, form, x = task
    mono = form == "mono"
    src = source_name(material, form)
    print(src, flush=True)
    wavio.write_flac24(os.path.join(OUT, reference_name(src, FS)), x[:, :1] if mono else x, FS)
    fm = AnalogFM(x[:, 0], FS) if mono else None
    for main in FORMS[form]:
        save(sample_name(src, FS, main), roundtrip(x, PROFILES[main]), mono)
        for sub in SUBS:
            for case in CASES:
                kind = {"rayleigh60": "rayleigh", "main_minus10db66": "fade10"}.get(case, "awgn")
                cn0 = int(case[len(case.rstrip("0123456789")):])
                y, _, _ = channel.link(x, main, cn0, sub=sub, kind_main=kind,
                                       kind_sub="awgn" if kind == "fade10" else kind, seed=1)
                save(sample_name(src, FS, main, case, sub=sub), y, mono)
        print(f"  {src} {main} done", flush=True)
    if fm is not None:
        for case in CASES:
            kind = {"rayleigh60": "rayleigh", "main_minus10db66": "fade10"}.get(case, "awgn")
            cn0 = int(case[len(case.rstrip("0123456789")):])
            g = None if kind == "awgn" else channel.fading_gains(int(np.ceil(len(x) / 64)), kind, np.random.default_rng(101))
            y1 = fm.receive(cn0, np.random.default_rng(1), g) if g is not None else fm.receive(cn0, np.random.default_rng(1))
            save(sample_name(src, FS, "FM", case), np.stack([y1, y1], 1), True)
    return src


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--eval-audio", default=os.path.join(ROOT, "eval_audio"), help="原音の置き場")
    ap.add_argument("--source", choices=[m[0] for m in MATERIALS], help="素材を一つだけ作る")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    tasks = []
    for material, path, start in MATERIALS:
        if args.source and material != args.source:
            continue
        x = load_material(material, path, start, args.eval_audio)
        for form in FORMS:
            tasks.append((material, form, to_form(x, form)))
    with ProcessPoolExecutor(max_workers=min(args.workers, len(tasks))) as ex:
        list(ex.map(generate, tasks))
    print("generated; run tools/samples/sample_catalog.py to validate and write the index")


if __name__ == "__main__":
    main()
