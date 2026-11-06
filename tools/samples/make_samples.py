#!/usr/bin/env python3
"""
samples/ の試聴音声を、素材 × 形（モノラル・ステレオ）× 主系 × 副系 × 条件のマトリクスで作る。

  python tools/samples/make_samples.py                 # eval_audio/lossless の原音から全部作り直す
  python tools/samples/make_samples.py --source demo   # 素材を一つだけ
  python tools/samples/make_samples.py --legall-only   # -L の試料だけ (原音と Haar・FM の試料は作らない)

素材: demo（合成試験信号）、piano、percussion（どちらもステレオの CC0 音源）。各10秒。
COMPARISON.md の数値に使う試料だけを作る: モノラル形、32 kHz、主系 B200M + 副系 SUB50M、
AWGN の C/N0 54・57・60・66・80、および同じ条件のアナログFM。各主系には LeGall 5/3 の -L 版も作る (副系も -L にそろえる)。
通信路は主系・副系とも独立のチャンネルで、C/N0は同じ値。
"""
import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, ROOT)

from gracefm import channel
from gracefm.decoder import roundtrip
from gracefm.iir import ALT_DELAY
from gracefm.profiles import LEGALL_SUFFIX, PROFILES
from tools.common import wavio
from tools.common.analog_fm import AnalogFM
from tools.common.demo_signal import make_demo
from tools.samples.sample_names import reference_name, sample_name

OUT = os.path.join(ROOT, "samples")
SEC = 10.0

# 素材: (名前, 原音ファイル (eval_audio 下), 開始秒)。demo は合成。
MATERIALS = (("demo", None, 0.0),
             ("piano", "lossless/Emotional_piano.wav", 1.0),
             ("percussion", "lossless/Ceramic_Djembe.wav", 0.5))
CN0_LIST = (54, 57, 60, 66, 80)      # C/N0 [dB-Hz]。66 は 5m・室内の保守的な見積もり (SPEC 付録D)
CASES = tuple(f"awgn{c}" for c in CN0_LIST)
# (サンプリング周波数, 形, 主系, 副系, 条件)。ステレオ形は C/N0 57 だけ、主系＋副系で作る
SETS = ((32000, "mono", ("B200M", "B200M-L"), ("SUB50M",), CASES),
        (32000, "stereo", ("B200", "B200Y", "B200-L", "B200Y-L"), ("SUB50M",), ("awgn57",)),
        (48000, "stereo", ("M700", "M700Y", "M700-L", "M700Y-L"), ("SUB100-48K",), ("awgn57",)))
# コーデックだけの試料 (通信路なし): (サンプリング周波数, 形, 主系, 副系は空, 条件は空)
CODEC_SETS = ((32000, "stereo", ("B200", "B200Y", "B200-L", "B200Y-L"), (), ()),
              (48000, "stereo", ("M700", "M700Y", "M700-L", "M700Y-L"), (), ()))
ALL_SETS = SETS + CODEC_SETS
BN = 180e3                           # C/N を表示する雑音帯域 [Hz] (FM放送 1波ぶん)


def paired_sub(main, sub):
    """主系に組み合わせる副系の名前。-L の主系には、帯域分割をそろえた -L の副系を使う"""
    return sub + LEGALL_SUFFIX if PROFILES[main].overlapped else sub


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


def aligned(y, fs):
    """通信路を通した受信出力は、出力段の切り替え用 IIR に揃えるため ALT_DELAY サンプル遅れる。
    試料は原音と時刻を揃えて保存する (末尾に同じ数の無音を足す)。コーデックだけと FM は遅れないので使わない。"""
    d = ALT_DELAY[fs]
    return np.concatenate([y[d:], np.zeros((d,) + y.shape[1:], y.dtype)])


def save(name, y, mono, fs):
    path = os.path.join(OUT, name)
    wavio.write_flac24(path, y[:, :1] if mono else y, fs)


def generate(task):
    material, form, fs, mains, subs, cases, x, legall_only = task
    mono = form == "mono"
    src = source_name(material, form)
    print(src, flush=True)
    if legall_only:
        mains = tuple(m for m in mains if PROFILES[m].overlapped)
    else:
        wavio.write_flac24(os.path.join(OUT, reference_name(src, fs)), x[:, :1] if mono else x, fs)
    fm = AnalogFM(x[:, 0], fs) if mono and fs == 32000 and not legall_only else None
    xi = wavio.to_pcm24(x)
    for main in mains:
        if not subs:
            save(sample_name(src, fs, main), wavio.from_pcm24(roundtrip(xi, PROFILES[main])), mono, fs)
        for sub in (paired_sub(main, s) for s in subs):
            for case in cases:
                cn0 = int(case[len("awgn"):])
                y, _, _ = channel.link(xi, main, cn0, sub=sub, seed=1)
                save(sample_name(src, fs, main, case, sub=sub), wavio.from_pcm24(aligned(y, fs)), mono, fs)
        print(f"  {src} {main} done", flush=True)
    if fm is not None:
        for case in CASES:
            cn0 = int(case[len("awgn"):])
            y1 = fm.receive(cn0, np.random.default_rng(1))
            save(sample_name(src, fs, "FM", case), np.stack([y1, y1], 1), True, fs)
    return src


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--eval-audio", default=os.path.join(ROOT, "eval_audio"), help="原音の置き場")
    ap.add_argument("--source", choices=[m[0] for m in MATERIALS], help="素材を一つだけ作る")
    ap.add_argument("--legall-only", action="store_true", help="-L の試料だけ作る")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    tasks = []
    for material, path, start in MATERIALS:
        if args.source and material != args.source:
            continue
        loaded = {}
        for fs, form, mains, subs, cases in ALL_SETS:
            if fs not in loaded:
                loaded[fs] = load_material(material, path, start, args.eval_audio, fs)
            tasks.append((material, form, fs, mains, subs, cases, to_form(loaded[fs], form), args.legall_only))
    with ProcessPoolExecutor(max_workers=min(args.workers, len(tasks))) as ex:
        list(ex.map(generate, tasks))
    print("generated; run tools/samples/sample_catalog.py to validate and write the index")


if __name__ == "__main__":
    main()
