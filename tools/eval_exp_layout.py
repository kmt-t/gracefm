#!/usr/bin/env python3
"""帯域別指数幅と固定オフセットを探索する。音源は eval_audio/ に置く。

  python tools/fetch_exp_audio.py
  python tools/eval_exp_layout.py --json docs/results/exp_layout_eval.json

探索: M 成分のみを送る B200MH の6詳細帯域＋低域近似で、各指数を 2/3/4bit から選ぶ。
各候補のオフセットは、全振幅入力の頭打ちを避ける emax から一意に決めて固定する。
訓練3素材・保留2素材 × 入力0/-20/-40dB の量子化SNRを使い、基準の全4bitから
最大何bit減らせるかを1dBの最大SNR低下制約で探索する。保留素材は選択に使わない。
選ばれた案と基準を ViSQOL Audio と通信路込みで別途検証する。
"""
import argparse
from dataclasses import replace
import itertools
import json
from pathlib import Path

import numpy as np
import soundfile as sf
from visqol import VisqolApi

import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from gracefm import channel, metrics, wavio  # noqa: E402
from gracefm.codec import dequantize, exp_range, haar_forward, haar_inverse, quantize  # noqa: E402
from gracefm.framing import Layout  # noqa: E402
from gracefm.profiles import PROFILES  # noqa: E402


def fixed_profile(base, widths):
    """幅とオフセットをプロファイルに固定。各帯域の上限は全振幅対応の既定値を維持。"""
    offsets = tuple(exp_range(k, b, base, "M")[1] - (2 ** widths[k] - 1)
                    for k, b in enumerate(base.bits_m))
    return replace(base, exp_bits_m=tuple(widths), exp_offset_m=offsets)


def read_clips(directory, seconds, block):
    manifest = json.loads((directory / "manifest.json").read_text())
    clips = {}
    n = int(seconds * 32000) // block * block
    for key, item in manifest.items():
        x, fs = sf.read(directory / item["file"], dtype="float64", always_2d=True)
        x = wavio.resample(x.mean(axis=1), fs, 32000)[:n]
        if len(x) != n or not np.all(np.isfinite(x)) or np.max(np.abs(x)) == 0:
            raise ValueError(f"{key}: {seconds:g}秒の有効な音声がありません")
        clips[key] = (x * (0.95 / np.max(np.abs(x)))).reshape(-1, block)
    return manifest, clips


def measure_quantization(clips, base, widths, levels):
    """正規直交 Haar なので帯域別 MSE の和が波形 MSE と一致する。"""
    candidates = {w: fixed_profile(base, (w,) * base.nbands) for w in widths}
    reference, errors, recon = {}, {}, {}
    for key, blocks in clips.items():
        for db in levels:
            scaled = blocks * (10 ** (db / 20))
            bands = haar_forward(scaled, base.levels)
            case = (key, db)
            reference[case] = float(np.sum(scaled ** 2))
            errors[case], recon[case] = {}, {}
            for w, p in candidates.items():
                errors[case][w], recon[case][w] = [], []
                for k, (c, b) in enumerate(zip(bands, base.bits_m)):
                    m, e = quantize(c, k, b, p, ch="M")
                    rec = dequantize(m, e, k, b, p, "M")
                    errors[case][w].append(float(np.sum((c - rec) ** 2)))
                    recon[case][w].append(rec)
    return reference, errors, recon


def snr(energy, error):
    return 10 * np.log10(energy / max(error, np.finfo(float).tiny))


def search(manifest, reference, errors, widths, base, max_loss):
    cases = list(reference)
    baseline = (base.exp_bits,) * base.nbands
    if any(w not in widths for w in baseline):
        raise ValueError("探索幅に基準の4bitを含めてください")
    base_snr = {case: snr(reference[case], sum(errors[case][w][k]
                                             for k, w in enumerate(baseline))) for case in cases}
    frontier = {}
    for choice in itertools.product(widths, repeat=base.nbands):
        saved = sum(base.exp_bits - w for w in choice)
        train, holdout = [], []
        for case in cases:
            value = snr(reference[case], sum(errors[case][w][k] for k, w in enumerate(choice)))
            (train if manifest[case[0]]["split"] == "train" else holdout).append(base_snr[case] - value)
        score = (max(train), float(np.mean(train)))
        if saved not in frontier or score < frontier[saved]["score"]:
            frontier[saved] = dict(widths=choice, saved_bits_per_frame=saved, score=score,
                                   max_train_snr_loss_db=float(max(train)),
                                   max_holdout_snr_loss_db=float(max(holdout)))
    rows = [frontier[s] for s in sorted(frontier)]
    feasible = [r for r in rows if r["max_train_snr_loss_db"] <= max_loss]
    selected = max(feasible, key=lambda r: r["saved_bits_per_frame"])
    return rows, selected, baseline, base_snr


def visqol(api, reference, decoded, fs=32000):
    ref = wavio.resample(reference, fs, 48000)
    deg = wavio.resample(decoded, fs, 48000)
    result = float(api.measure_from_arrays(ref, deg, sample_rate=48000).moslqo)
    if not np.isfinite(result):
        raise ValueError("ViSQOL の測定値が有限ではありません")
    return result


def perceptual_eval(api, clips, manifest, recon, choices, levels):
    rows = []
    for key in clips:
        for db in levels:
            case = (key, db)
            gain = 10 ** (db / 20)
            reference = clips[key].reshape(-1)
            for name, choice in choices.items():
                bands = [recon[case][w][k] for k, w in enumerate(choice)]
                decoded = haar_inverse(bands).reshape(-1) / gain
                rows.append(dict(material=key, split=manifest[key]["split"], input_db=db,
                                 layout=name, snr_db=float(metrics.snr_db(reference, decoded)),
                                 visqol_moslqo=visqol(api, reference, decoded)))
    return rows


def link_eval(api, clips, manifest, base, choices, cn0s):
    rows = []
    for key, blocks in clips.items():
        if manifest[key]["split"] != "holdout":
            continue
        x = np.repeat(blocks.reshape(-1, 1), 2, axis=1)
        for cn0 in cn0s:
            for name, widths in choices.items():
                profile = fixed_profile(base, widths)
                y, state, _ = channel.link(x, profile, cn0, sub="S50M", power_main=0.5, seed=1)
                rows.append(dict(material=key, cn0_db_hz=cn0, layout=name,
                                 snr_db=float(metrics.snr_db(x, y)),
                                 visqol_moslqo=visqol(api, x[:, 0], y.mean(axis=1)),
                                 plc_percent=100 * state["plc_samples"] / len(x),
                                 symbol_rate_khz=channel.symbol_rate(profile) / 1000))
                print(f"link {key} {cn0} {name}: SNR {rows[-1]['snr_db']:.2f}, "
                      f"ViSQOL {rows[-1]['visqol_moslqo']:.3f}", flush=True)
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--audio-dir", type=Path, default=ROOT / "eval_audio")
    ap.add_argument("--seconds", type=float, default=5.0)
    ap.add_argument("--widths", default="2,3,4")
    ap.add_argument("--levels", default="0,-20,-40")
    ap.add_argument("--max-snr-loss", type=float, default=1.0)
    ap.add_argument("--link-cn0", default="60,66")
    ap.add_argument("--skip-link", action="store_true")
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()
    widths = tuple(sorted({int(v) for v in args.widths.split(",")}))
    levels = tuple(float(v) for v in args.levels.split(","))
    cn0s = tuple(float(v) for v in args.link_cn0.split(","))
    if args.seconds < 3 or not widths or any(w < 1 or w > 8 for w in widths) or 4 not in widths:
        ap.error("seconds は3以上、探索幅は1〜8で4bitを含めてください")
    base = replace(PROFILES["B200MH"], attn_group_m=None, exp_offset_m=None)
    if any(base.bits_s):
        raise ValueError("この探索は M のみのプロファイル用です")
    manifest, clips = read_clips(args.audio_dir, args.seconds, base.block)
    reference, errors, recon = measure_quantization(clips, base, widths, levels)
    frontier, selected, baseline, base_snr = search(manifest, reference, errors, widths, base, args.max_snr_loss)
    choices = {"baseline": baseline, "selected": selected["widths"]}
    print("chosen widths:", choices, "saved protected bits/frame:", selected["saved_bits_per_frame"])
    print("max SNR loss train/holdout:", selected["max_train_snr_loss_db"],
          selected["max_holdout_snr_loss_db"])
    api = VisqolApi()
    api.create(mode="audio")
    perceptual = perceptual_eval(api, clips, manifest, recon, choices, (0.0, -40.0))
    link = [] if args.skip_link else link_eval(api, clips, manifest, base, choices, cn0s)
    layout = {}
    for name, choice in choices.items():
        p = fixed_profile(base, choice)
        lay = Layout(p)
        layout[name] = dict(widths=list(choice), offsets=list(p.exp_offset_m),
                            protected_bits_including_crc=lay.n_prot_crc,
                            coded_bits=lay.n_coded, audio_kbps=p.audio_kbps(),
                            symbol_rate_khz=channel.symbol_rate(p) / 1000)
    result = dict(profile=base.name, search_widths=widths, input_levels_db=levels,
                  max_train_snr_loss_db=args.max_snr_loss, seconds=args.seconds,
                  materials=manifest, baseline_snr_db={f"{k}|{db:g}":v for (k, db), v in base_snr.items()},
                  frontier=[{k: v for k, v in row.items() if k != "score"} for row in frontier],
                  selected=selected["widths"], layout=layout,
                  codec_perceptual=perceptual, link=link,
                  method="各帯域の幅2/3/4bitと固定オフセット。上限はフルスケール対応のまま。"
                         "訓練の最大波形SNR低下が1dB以内となる最大節約ビット数を選び、"
                         "保留音源とViSQOL/通信路で検証。リンクはB200MH+S50M、50:50電力、seed 1。")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    return result


if __name__ == "__main__":
    main()
