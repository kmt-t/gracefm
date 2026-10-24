#!/usr/bin/env python3
"""GraceFM の符号化だけと MP3 を波形SNR・ViSQOL Audio で比較する。

  python tools/eval_codec_perceptual.py --json docs/results/codec_perceptual_eval.json

原音は samples/*__32k__reference.flac の10秒全体（32kHz・モノラル）。GraceFM は通信路と
誤り訂正を通さず、MP3 は FFmpeg/libmp3lame の CBR で符号化・復号する。
MP3 のデコードには gapless メタデータを使い、長さが原音と違えば失敗させる。
MP3 には無線路を含めないので、この結果を C/N0 別の結果とは混同しない。
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor

import numpy as np

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gracefm import metrics, wavio  # noqa: E402
from gracefm.profiles import PROFILES  # noqa: E402
from make_samples import codec  # noqa: E402


def mp3_roundtrip(x, fs, bitrate):
    from imageio_ffmpeg import get_ffmpeg_exe

    ffmpeg = get_ffmpeg_exe()
    with tempfile.TemporaryDirectory() as directory:
        source = os.path.join(directory, "source.wav")
        encoded = os.path.join(directory, "encoded.mp3")
        decoded = os.path.join(directory, "decoded.wav")
        wavio.write(source, x[:, :1], fs)
        subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", source,
                        "-c:a", "libmp3lame", "-b:a", f"{bitrate}k", encoded], check=True)
        subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", encoded,
                        "-c:a", "pcm_f32le", decoded], check=True)
        y, output_fs = wavio.read(decoded)
        size = os.path.getsize(encoded)
    if output_fs != fs or len(y) != len(x):
        raise ValueError(f"MP3 {bitrate}kbps: 復号後の長さ/サンプリング周波数が原音と異なります")
    return y, size


def job(args):
    material, seconds, method = args
    from visqol import VisqolApi

    x, fs = wavio.read(os.path.join(ROOT, "samples", f"{material}__32k__reference.flac"))
    x = x[: int(seconds * fs)]
    if fs != 32000 or len(x) != int(seconds * fs):
        raise ValueError(f"{material}: 32kHz、{seconds:g}秒以上の原音が必要")
    if method.startswith("MP3-"):
        bitrate = int(method.split("-", 1)[1])
        y, encoded_bytes = mp3_roundtrip(x, fs, bitrate)
        nominal_kbps = bitrate
    else:
        profile = PROFILES[method]
        y = codec(x, profile)
        encoded_bytes = None
        nominal_kbps = round(profile.audio_kbps(), 1)
    snr = float(metrics.snr_db(x, y))
    ref48 = wavio.resample(x.mean(axis=1), fs, 48000)
    deg48 = wavio.resample(y.mean(axis=1), fs, 48000)
    api = VisqolApi()
    api.create(mode="audio")
    mos = float(api.measure_from_arrays(ref48, deg48, sample_rate=48000).moslqo)
    if not np.isfinite(mos):
        raise ValueError(f"{args}: ViSQOL が有限の値を返しませんでした")
    return dict(material=material, method=method, nominal_audio_kbps=nominal_kbps,
                encoded_bytes=encoded_bytes, snr_db=round(snr, 2), visqol_moslqo=round(mos, 3))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--materials", default="fishin,vibeace")
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--bitrates", default="128,192,320", help="MP3 CBR の kbps")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--json")
    args = ap.parse_args()
    materials = [s.strip() for s in args.materials.split(",") if s.strip()]
    bitrates = [int(s.strip()) for s in args.bitrates.split(",") if s.strip()]
    if any(m not in ("fishin", "vibeace") for m in materials) or not materials:
        ap.error("materials は fishin,vibeace から選んでください")
    if any(b not in (32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320) for b in bitrates):
        ap.error("bitrates は MPEG-1 Layer III の対応ビットレートから選んでください")
    if not bitrates or args.seconds < 3 or args.seconds > 10 or args.workers < 1:
        ap.error("bitrates は空にせず、seconds は 3〜10、workers は 1 以上にしてください")
    methods = ["B200M"] + [f"MP3-{b}" for b in bitrates]
    jobs = [(material, args.seconds, method) for material in materials for method in methods]
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        rows = []
        for row in executor.map(job, jobs):
            rows.append(row)
            print(f"{row['material']:8s} {row['method']:8s} {row['nominal_audio_kbps']:5.1f}kbps "
                  f"SNR {row['snr_db']:6.2f}dB ViSQOL {row['visqol_moslqo']:.3f}", flush=True)
    if args.json:
        from imageio_ffmpeg import get_ffmpeg_exe
        ffmpeg_version = subprocess.run([get_ffmpeg_exe(), "-version"], check=True,
                                        capture_output=True, text=True).stdout.splitlines()[0]
        result = dict(metric="ViSQOL Audio MOS-LQO", metric_implementation="visqol-python 3.8.0",
                      mp3_encoder=f"{ffmpeg_version} / libmp3lame, CBR", seconds=args.seconds,
                      source_sample_rate_hz=32000, visqol_sample_rate_hz=48000,
                      notes="全方式とも符号化・復号のみ。MP3 の CBR kbps と GraceFM の音声ペイロードkbpsを表示。"
                            "無線路・FEC・ヘッダ・ガード帯域は含まない。",
                      rows=rows)
        with open(args.json, "w") as f:
            json.dump(result, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write("\n")


if __name__ == "__main__":
    main()
