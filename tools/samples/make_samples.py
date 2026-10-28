#!/usr/bin/env python3
"""
samples/ の試聴音声を、素材 × 形（モノラル・ステレオ）× 主系 × 副系 × 条件のマトリクスで作る。

  python tools/samples/make_samples.py                 # eval_audio/lossless の原音から全部作り直す
  python tools/samples/make_samples.py --source demo   # 素材を一つだけ

素材: demo（合成試験信号）、piano、percussion（どちらもステレオの CC0 音源）。各10秒。
モノラル形は (L+R)/2、ステレオ形は原音のまま。同じ素材・同じ条件で両形が揃う。
32 kHz: 主系はモノラル形が B200M・B200MY、ステレオ形が B200・B200Y、副系は なし または SUB50M。
48 kHz: 主系はモノラル形が M700M・M700MY、ステレオ形が M700・M700Y、副系は なし または SUB100-48K。
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

from tools.common.demo_signal import make_demo
from tools.samples.sample_names import sample_name, reference_name

from gracefm import channel  # noqa: E402
from tools.common import wavio  # noqa: E402
from tools.common.analog_fm import AnalogFM  # noqa: E402
from gracefm.codec import roundtrip  # noqa: E402
from gracefm.profiles import PROFILES  # noqa: E402

OUT = os.path.join(ROOT, "samples")
SEC = 10.0

# 素材: (名前, 原音ファイル (eval_audio 下), 開始秒)。demo は合成。
MATERIALS = (("demo", None, 0.0),
             ("piano", "lossless/Emotional_piano.wav", 1.0),
             ("percussion", "lossless/Ceramic_Djembe.wav", 0.5))
# (サンプリング周波数, 形, 主系, 副系)
SETS = ((32000, "mono", ("B200M", "B200MY"), (None, "SUB50M")),
        (32000, "stereo", ("B200", "B200Y"), (None, "SUB50M")),
        (48000, "mono", ("M700M", "M700MY"), (None, "SUB100-48K")),
        (48000, "stereo", ("M700", "M700Y"), (None, "SUB100-48K")))
CN0_LIST = (54, 57, 60, 66, 80)      # C/N0 [dB-Hz]。66 は 5m・室内の保守的な見積もり (SPEC 付録D)
CASES = tuple(f"awgn{c}" for c in CN0_LIST) + ("rayleigh60", "main_minus10db66")
BN = 180e3                           # C/N を表示する雑音帯域 [Hz] (FM放送 1波ぶん)


def source_name(material, form):
    return f"{material}-{form}"


def cn(c):
    return c - 10 * np.log10(BN)


def load_material(material, path, start, eval_audio, fs_out):
    """10秒・fs_out・ピーク0.89のステレオ原音"""
    if path is None:
        x, fs = make_demo(48000), 48000
    else:
        x, fs = wavio.read(os.path.join(eval_audio, path))
        x = x[int(start * fs):int((start + SEC) * fs)]
    x = x * (0.89 / np.abs(x).max())
    x = wavio.resample(x, fs, fs_out)[: int(SEC * fs_out)]
    return x * (0.89 / np.abs(x).max())


def to_form(x, form):
    return np.repeat(((x[:, 0] + x[:, 1]) / 2)[:, None], 2, axis=1) if form == "mono" else x


def save(name, y, mono, fs):
    path = os.path.join(OUT, name)
    wavio.write_flac24(path, y[:, :1] if mono else y, fs)


def generate(task):
    material, form, fs, mains, subs, x = task
    mono = form == "mono"
    src = source_name(material, form)
    print(src, flush=True)
    wavio.write_flac24(os.path.join(OUT, reference_name(src, fs)), x[:, :1] if mono else x, fs)
    fm = AnalogFM(x[:, 0], fs) if mono and fs == 32000 else None
    xi = wavio.to_pcm24(x)
    for main in mains:
        save(sample_name(src, fs, main), wavio.from_pcm24(roundtrip(xi, PROFILES[main])), mono, fs)
        for sub in subs:
            for case in CASES:
                kind = {"rayleigh60": "rayleigh", "main_minus10db66": "fade10"}.get(case, "awgn")
                cn0 = int(case[len(case.rstrip("0123456789")):])
                y, _, _ = channel.link(xi, main, cn0, sub=sub, kind_main=kind,
                                       kind_sub="awgn" if kind == "fade10" else kind, seed=1)
                save(sample_name(src, fs, main, case, sub=sub), wavio.from_pcm24(y), mono, fs)
        print(f"  {src} {main} done", flush=True)
    if fm is not None:
        for case in CASES:
            kind = {"rayleigh60": "rayleigh", "main_minus10db66": "fade10"}.get(case, "awgn")
            cn0 = int(case[len(case.rstrip("0123456789")):])
            g = None if kind == "awgn" else channel.fading_gains(int(np.ceil(len(x) / 64)), kind, np.random.default_rng(101))
            y1 = fm.receive(cn0, np.random.default_rng(1), g) if g is not None else fm.receive(cn0, np.random.default_rng(1))
            save(sample_name(src, fs, "FM", case), np.stack([y1, y1], 1), True, fs)
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
        loaded = {}
        for fs, form, mains, subs in SETS:
            if fs not in loaded:
                loaded[fs] = load_material(material, path, start, args.eval_audio, fs)
            tasks.append((material, form, fs, mains, subs, to_form(loaded[fs], form)))
    with ProcessPoolExecutor(max_workers=min(args.workers, len(tasks))) as ex:
        list(ex.map(generate, tasks))
    print("generated; run tools/samples/sample_catalog.py to validate and write the index")


if __name__ == "__main__":
    main()
