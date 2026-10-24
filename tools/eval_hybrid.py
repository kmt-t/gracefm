#!/usr/bin/env python3
"""実験用高域ハイブリッド主系の再現可能な帯域・音質評価。

例: .venv/bin/python tools/eval_hybrid.py --seconds 3
"""
import argparse
import json
import os
import sys

import numpy as np
from scipy.signal import welch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(__file__))

from gracefm import channel, metrics, modem, wavio  # noqa: E402
from gracefm.codec import encode_block, haar_forward  # noqa: E402
from gracefm.framing import HybridLayout, Layout  # noqa: E402
from gracefm.profiles import PROFILES, make_hybrid  # noqa: E402
from gracefm.pulse import shape  # noqa: E402
from gracefm.txrx import Transmitter  # noqa: E402
from make_samples import codec  # noqa: E402

CN0 = (54, 60, 66, 70, 80)
PAIRS = (("B200M", "B200MY", "fishin", "SUB50M"),
         ("B200", "B200Y", "demo", "SUB100"))


def band_snr(x, y, profile):
    n = len(x) // profile.block * profile.block
    xb = x[:n].T.reshape(2, -1, profile.block)
    eb = (y[:n] - x[:n]).T.reshape(2, -1, profile.block)
    a = haar_forward(xb, profile.levels)
    e = haar_forward(eb, profile.levels)
    result = {}
    boundary = profile.fs // 8000
    nyquist = profile.fs // 2000
    for label, indices in ((f"low_0_{boundary}khz", range(5)),
                           (f"high_{boundary}_{nyquist}khz", range(5, 7))):
        sig = sum(float(np.sum(a[k] ** 2)) for k in indices)
        err = sum(float(np.sum(e[k] ** 2)) for k in indices)
        result[label] = float(10 * np.log10(max(sig, 1e-30) / max(err, 1e-30)))
    return result


def visqol_score(x, y, fs):
    from visqol import VisqolApi

    api = VisqolApi()
    api.create(mode="audio")
    result = []
    for ch in range(2):
        ref = wavio.resample(x[:, ch], fs, 48000)
        deg = wavio.resample(y[:, ch], fs, 48000)
        result.append(float(api.measure_from_arrays(ref, deg, sample_rate=48000).moslqo))
    return float(np.mean(result))


def score(x, y, p, stats=None, use_visqol=True, crop=0):
    xx, yy = x[crop:], y[crop:]
    row = dict(snr_db=float(metrics.snr_db(xx, yy)), **band_snr(xx, yy, p))
    if use_visqol:
        row["visqol_moslqo"] = visqol_score(xx, yy, p.fs)
    if stats is not None:
        row["crc_fail"] = stats["A"]["crc_fail"]
        row["crc_fail_percent"] = 100 * stats["A"]["crc_fail"] / stats["A"]["frames"]
        row["plc_percent"] = 100 * stats["plc_samples"] / len(x)
    return row


def budget(p):
    lay = HybridLayout(p) if p.hybrid else Layout(p)
    tx = Transmitter(p)
    rs = channel.symbol_rate(p)
    return dict(profile=p.name, hybrid_start_k=p.hybrid_start_k,
                hybrid_bits=p.hybrid_bits if p.hybrid else None,
                hybrid_amplitude=p.hybrid_amplitude if p.hybrid else None,
                protected_before_crc_bits=lay.n_prot, protected_with_crc_bits=lay.n_prot_crc,
                fec_coded_bits=lay.n_coded, low_digital_unprotected_bits=lay.n_unp,
                digital_symbols=tx.digital_nsym, hybrid_symbols=lay.n_hybrid if p.hybrid else 0,
                preamble_symbols=len(modem.PREAMBLE),
                total_symbols_per_frame=tx.nsym + len(modem.PREAMBLE),
                symbol_rate_ksym_s=rs / 1000,
                rrc_support_khz=(1 + p.pulse_beta) * rs / 1000)


def spectrum(p, x):
    symbols = np.concatenate(Transmitter(p).run(x))
    rs = channel.symbol_rate(p)
    w = shape(symbols, beta=p.pulse_beta, span=p.pulse_span, sps=8)
    power = np.abs(w) ** 2
    papr = 10 * np.log10(np.max(power) / np.mean(power))
    f, psd = welch(w, fs=8 * rs, nperseg=4096, return_onesided=False,
                   scaling="density")
    order = np.argsort(f)
    f, psd = f[order], psd[order]
    cumulative = np.cumsum(psd) / np.sum(psd)
    occupied = f[np.searchsorted(cumulative, .995)] - f[np.searchsorted(cumulative, .005)]
    above = f[psd >= psd.max() * 1e-3]
    return dict(occupied_99_khz=float(occupied / 1000),
                bandwidth_minus30db_khz=float((above[-1] - above[0]) / 1000),
                papr_db=float(papr))


def run_case(x, p, cn0, scenario, sub=None, phase_only=False, use_visqol=True):
    kwargs = dict(sub=sub, hybrid_phase_only=phase_only, seed=1)
    crop = 0
    if scenario == "multipath_equalized" or scenario == "multipath_raw":
        training = min(50, int(len(x) / p.block / 3))
        y, stats, _ = channel.link_static_multipath(
            x, p, cn0, paths=((5e-6, -10, np.pi / 3),),
            equalize=scenario == "multipath_equalized", training_frames=training,
            frequency_spacing_hz=2.1e6, **kwargs)
        crop = training * p.block
    else:
        kind = {"awgn": "awgn", "rayleigh": "rayleigh", "main_minus10db": "fade10"}[scenario]
        y, stats, _ = channel.link(x, p, cn0, kind_main=kind,
                                    kind_sub="awgn" if kind == "fade10" else kind,
                                    **kwargs)
    return dict(profile=p.name, cn0_db_hz=cn0, scenario=scenario,
                secondary=sub, phase_only=phase_only,
                **score(x, y, p, stats, use_visqol, crop))


def save_result(path, seconds, use_visqol, budgets, spectra, rows):
    result = dict(description="同期済みシンボルと静的RRCマルチパスのシミュレーション。実RF測定ではない。",
                  source="samples/{material}__32k__reference.flac", seconds=seconds,
                  cn0_db_hz=CN0, seed=1, visqol_enabled=use_visqol,
                  rrc_sps=8, rrc_welch_nperseg=4096,
                  budgets=budgets, spectra=spectra, results=rows)
    with open(path, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=3.0)
    parser.add_argument("--no-visqol", action="store_true")
    parser.add_argument("--quick", action="store_true", help="AWGNとコーデックのみ")
    parser.add_argument("--material", choices=("fishin", "demo"), help="再評価する素材を限定する")
    parser.add_argument("--resume", action="store_true", help="他素材の保存済み結果を維持する")
    parser.add_argument("--json", default=os.path.join(ROOT, "docs/results/hybrid_eval.json"))
    args = parser.parse_args()
    if args.seconds < 1:
        parser.error("評価区間は1秒以上にしてください")
    use_visqol = not args.no_visqol
    if use_visqol and args.seconds < 3:
        parser.error("ViSQOLの評価区間は3秒以上にしてください")
    rows, budgets, spectra = [], [], []
    if args.resume and os.path.exists(args.json):
        with open(args.json, encoding="utf-8") as stream:
            previous = json.load(stream)
        if previous["seconds"] != args.seconds or previous["visqol_enabled"] != use_visqol:
            raise ValueError("保存済み結果の時間長またはViSQOL設定が異なります")
        rows, budgets, spectra = previous["results"], previous["budgets"], previous["spectra"]
    for baseline, hybrid, material, secondary in PAIRS:
        if args.material and material != args.material:
            continue
        def selected(name):
            return name in (baseline, hybrid, secondary) or name.startswith(hybrid + "-")
        rows = [row for row in rows if not selected(row["profile"])]
        budgets = [row for row in budgets if not selected(row["profile"])]
        spectra = [row for row in spectra if not selected(row["profile"])]
        x, fs = wavio.read(os.path.join(ROOT, "samples", f"{material}__32k__reference.flac"))
        x = x[:int(fs * args.seconds)]
        if fs != 32000 or len(x) != int(fs * args.seconds):
            raise ValueError("評価音源の長さ・標本化周波数が不足しています")
        sub_profile = PROFILES[secondary]
        budgets.append(budget(sub_profile))
        spectra.append(dict(profile=secondary, **spectrum(sub_profile, x)))
        for name in (baseline, hybrid):
            p = PROFILES[name]
            budgets.append(budget(p))
            spectra.append(dict(profile=name, **spectrum(p, x)))
            rows.append(dict(profile=name, scenario="codec_only", secondary=None,
                             **score(x, codec(x, p), p, use_visqol=use_visqol)))
            for cn0 in CN0:
                rows.append(run_case(x, p, cn0, "awgn", use_visqol=use_visqol))
                if p.hybrid:
                    rows.append(run_case(x, p, cn0, "awgn", phase_only=True,
                                         use_visqol=use_visqol))
                if not args.quick and cn0 in (60, 66):
                    for scenario in ("rayleigh", "main_minus10db"):
                        rows.append(run_case(x, p, cn0, scenario, sub=secondary,
                                             use_visqol=use_visqol))
                if not args.quick and cn0 in (66, 80):
                    for scenario in ("multipath_equalized", "multipath_raw"):
                        rows.append(run_case(x, p, cn0, scenario,
                                             use_visqol=use_visqol))
                if not args.quick and cn0 == 66:
                    rows.append(run_case(x, p, cn0, "awgn", sub=secondary,
                                         use_visqol=use_visqol))
        if not args.quick:
            base = PROFILES[baseline]
            for depth in (.04, .12):
                variant = make_hybrid(base, f"{hybrid}-a{depth:.2f}", PROFILES[hybrid].pid,
                                      amplitude=depth)
                budgets.append(budget(variant))
                spectra.append(dict(profile=variant.name, **spectrum(variant, x)))
                rows.append(run_case(x, variant, 66, "awgn", use_visqol=use_visqol))
            for bits in (10, 12):
                variant = make_hybrid(base, f"{hybrid}-{bits}bit", PROFILES[hybrid].pid,
                                      mantissa_bits=bits)
                budgets.append(budget(variant))
                spectra.append(dict(profile=variant.name, **spectrum(variant, x)))
                rows.append(run_case(x, variant, 66, "awgn", use_visqol=use_visqol))
            for start, label in ((4, "2khz"), (6, "8khz")):
                variant = make_hybrid(base, f"{hybrid}-{label}", PROFILES[hybrid].pid,
                                      start_k=start)
                budgets.append(budget(variant))
                spectra.append(dict(profile=variant.name, **spectrum(variant, x)))
                rows.append(run_case(x, variant, 66, "awgn", use_visqol=use_visqol))
        save_result(args.json, args.seconds, use_visqol, budgets, spectra, rows)
        print(material, "finished", len(rows), "conditions", flush=True)
    print(args.json, len(rows), "conditions", flush=True)


if __name__ == "__main__":
    main()
