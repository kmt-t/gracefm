#!/usr/bin/env python3
"""固定指数幅・固定オフセット・最高域局所アッテネータを実音源で探索する。

音源取得: python tools/fetch_exp_audio.py (eval_audio/ は Git 管理外)
実行例: python tools/eval_attn_layout.py --json docs/results/attn_layout_eval.json
比較条件: B200M の6詳細帯域＋低域近似、Mのみ、各フレームの固定ビット予算。
訓練3素材×振幅3条件の正規化MSE平均を最小化し、保留2素材で検証する。
"""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from gracefm import channel, metrics, wavio  # noqa: E402
from gracefm.codec import dequantize, exp_range, haar_forward, haar_inverse, qmax_of, quantize_attenuated  # noqa: E402
from gracefm.framing import Layout  # noqa: E402
from gracefm.profiles import PROFILES  # noqa: E402
from eval_exp_layout import read_clips, visqol  # noqa: E402


def profile_for(base, spec):
    widths, shifts, group = spec
    groups = [0] * base.nbands
    groups[-1] = group
    offsets = tuple(exp_range(k, b, base, 'M')[1] - (2 ** widths[k] - 1) + shifts[k]
                    for k, b in enumerate(base.bits_m))
    return replace(base, exp_bits_m=tuple(widths), exp_offset_m=offsets,
                   attn_group_m=tuple(groups))


def evaluate_band(cases, base, widths, shifts, groups):
    energies = {case: float(np.sum(bands[0] ** 2) + sum(np.sum(c ** 2) for c in bands[1:]))
                for case, bands in cases.items()}
    cache = {}
    for k, b in enumerate(base.bits_m):
        gs = groups if k == base.nbands - 1 else (0,)
        for group in gs:
            for width in widths:
                for shift in shifts:
                    p = profile_for(base, (tuple(width if j == k else 4 for j in range(base.nbands)),
                                           tuple(shift if j == k else 0 for j in range(base.nbands)), group))
                    key = (k, width, shift, group)
                    cache[key] = {}
                    for case, bands in cases.items():
                        c = bands[k]
                        m, e, a = quantize_attenuated(c, k, b, p, ch='M')
                        rec = dequantize(m, e, k, b, p, 'M', a)
                        cache[key][case] = float(np.sum((c - rec) ** 2))
    return energies, cache


def optimize(manifest, energies, cache, base, group, budget, widths, shifts, train_peaks, headroom_db):
    """同じ保護ビット予算内で正規化MSEの訓練平均を最小化。帯域ごとの独立誤差をDPで加算。"""
    train = [case for case in energies if manifest[case[0]]['split'] == 'train']
    states = {0: (0.0, [])}
    for k in range(base.nbands):
        nxt = {}
        g = group if k == base.nbands - 1 else 0
        for used, (score, path) in states.items():
            for width in widths:
                for shift in shifts:
                    capacity = qmax_of(base.bits_m[k]) * 2 ** (exp_range(k, base.bits_m[k], base)[1] + shift)
                    if capacity < train_peaks[k] * 10 ** (headroom_db / 20):
                        continue
                    cost = used + width
                    if cost > budget - (base.ncoef(base.nbands - 1) // group if group else 0):
                        continue
                    err = np.mean([cache[(k, width, shift, g)][case] / energies[case] for case in train])
                    item = (score + err, path + [(width, shift)])
                    if cost not in nxt or item[0] < nxt[cost][0]:
                        nxt[cost] = item
        states = nxt
    if not states:
        return None
    used, (score, path) = min(states.items(), key=lambda item: item[1][0])
    spec = (tuple(w for w, _ in path), tuple(s for _, s in path), group)
    return spec, score, used + (base.ncoef(base.nbands - 1) // group if group else 0)


def case_rows(manifest, energies, cache, base, specs):
    rows = []
    for name, spec in specs.items():
        widths, shifts, group = spec
        for case in energies:
            error = sum(cache[(k, widths[k], shifts[k], group if k == base.nbands - 1 else 0)][case]
                        for k in range(base.nbands))
            rows.append(dict(layout=name, material=case[0], split=manifest[case[0]]['split'],
                             input_db=case[1], snr_db=float(10 * np.log10(energies[case] / error)),
                             normalized_mse=float(error / energies[case])))
    return rows


def perceptual_rows(clips, manifest, base, specs, levels):
    from visqol import VisqolApi
    api = VisqolApi()
    api.create(mode='audio')
    rows = []
    for material, blocks in clips.items():
        for db in levels:
            gain = 10 ** (db / 20)
            bands = haar_forward(blocks * gain, base.levels)
            for name, spec in specs.items():
                p = profile_for(base, spec)
                recon = []
                for k, (c, b) in enumerate(zip(bands, p.bits_m)):
                    m, e, a = quantize_attenuated(c, k, b, p, ch='M')
                    recon.append(dequantize(m, e, k, b, p, 'M', a))
                decoded = haar_inverse(recon).reshape(-1) / gain
                reference = blocks.reshape(-1)
                rows.append(dict(layout=name, material=material, split=manifest[material]['split'],
                                 input_db=db, snr_db=float(metrics.snr_db(reference, decoded)),
                                 visqol_moslqo=visqol(api, reference, decoded)))
    return rows


def link_rows(clips, manifest, base, specs, cn0s):
    from visqol import VisqolApi
    api = VisqolApi()
    api.create(mode='audio')
    rows = []
    for material, blocks in clips.items():
        if manifest[material]['split'] != 'holdout':
            continue
        x = np.repeat(blocks.reshape(-1, 1), 2, axis=1)
        for cn0 in cn0s:
            for name, spec in specs.items():
                p = profile_for(base, spec)
                y, st, _ = channel.link(x, p, cn0, sub='SUB50M', seed=1)
                row = dict(layout=name, material=material, cn0_db_hz=cn0,
                           snr_db=float(metrics.snr_db(x, y)),
                           visqol_moslqo=visqol(api, x[:, 0], y.mean(axis=1)),
                           plc_percent=float(100 * st['plc_samples'] / len(x)),
                           crc_fail=st['A']['crc_fail'],
                           symbol_rate_khz=float(channel.symbol_rate(p) / 1000))
                rows.append(row)
                print('link', material, cn0, name, row['snr_db'], row['visqol_moslqo'], flush=True)
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--audio-dir', type=Path, default=ROOT / 'eval_audio')
    ap.add_argument('--seconds', type=float, default=3.0)
    ap.add_argument('--widths', default='2,3,4')
    ap.add_argument('--shifts', default='-8,-7,-6,-5,-4,-3,-2,-1,0,1',
                    help='既定の固定オフセットからの差')
    ap.add_argument('--headroom-db', type=float, default=9.0,
                    help='訓練素材の帯域別最大係数に加えるピーク余裕。低域と高域に別の上限を与える')
    ap.add_argument('--groups', default='0,2,4,8,16')
    ap.add_argument('--link-cn0', default='60,66')
    ap.add_argument('--skip-link', action='store_true')
    ap.add_argument('--skip-perceptual', action='store_true')
    ap.add_argument('--json', type=Path)
    args = ap.parse_args()
    widths = tuple(sorted({int(v) for v in args.widths.split(',')}))
    shifts = tuple(sorted({int(v) for v in args.shifts.split(',')}))
    groups = tuple(sorted({int(v) for v in args.groups.split(',')}))
    if any(w not in range(1, 9) for w in widths) or 4 not in widths or 0 not in shifts or 0 not in groups:
        ap.error('幅に4、オフセットに0、グループに0を含めてください')
    base = PROFILES['B200M']
    manifest, clips = read_clips(args.audio_dir, args.seconds, base.block)
    levels = (0, -20, -40)
    cases = {(name, db): haar_forward(blocks * 10 ** (db / 20), base.levels)
             for name, blocks in clips.items() for db in levels}
    train_peaks = [max(float(np.max(np.abs(bands[k]))) for (name, db), bands in cases.items()
                       if manifest[name]['split'] == 'train' and db == 0)
                   for k in range(base.nbands)]
    holdout_peaks = [max(float(np.max(np.abs(bands[k]))) for (name, db), bands in cases.items()
                         if manifest[name]['split'] == 'holdout' and db == 0)
                     for k in range(base.nbands)]
    energies, cache = evaluate_band(cases, base, widths, shifts, groups)
    base_budget = sum(base.exponent_bits('M', k) for k in range(base.nbands))
    opt = {g: optimize(manifest, energies, cache, base, g, base_budget, widths, shifts,
                       train_peaks, args.headroom_db) for g in groups}
    baseline = ((4,) * base.nbands, (0,) * base.nbands, 0)
    # 追加ビットを許す比較では指数4bitを維持できる予算を各区間長に与える。
    extras = {g: optimize(manifest, energies, cache, base, g,
                          base_budget + base.ncoef(base.nbands - 1) // g,
                          widths, shifts, train_peaks, args.headroom_db)
              for g in groups if g}
    extra = extras[4]
    same = min((v for v in opt.values() if v is not None), key=lambda item: item[1])
    specs = {'baseline': baseline, 'same_rate_best': same[0],
             'attn4_same_rate': opt[4][0], 'attn4_plus8': extra[0]}
    rows = case_rows(manifest, energies, cache, base, specs)
    extra_codec = case_rows(manifest, energies, cache, base,
                            {f'attn{g}_plus{base.ncoef(base.nbands - 1) // g}': v[0]
                             for g, v in extras.items() if v is not None})
    print('chosen', specs, flush=True)
    print('options', {g: {'score': v[1], 'spec': v[0]} if v else None for g, v in opt.items()}, flush=True)
    perceptual = [] if args.skip_perceptual else perceptual_rows(clips, manifest, base, specs, (0, -40))
    link_specs = {name: spec for name, spec in specs.items() if name != 'same_rate_best' or spec != baseline}
    link = [] if args.skip_link else link_rows(clips, manifest, base, link_specs,
                                               tuple(float(v) for v in args.link_cn0.split(',')))
    layout = {}
    for name, spec in specs.items():
        p = profile_for(base, spec)
        lay = Layout(p)
        layout[name] = dict(widths=spec[0], offsets=p.exp_offset_m, offset_shifts=spec[1],
                            attenuator_group=spec[2], attenuator_bits=p.attenuator_bits('M', 6),
                            protected_bits_including_crc=lay.n_prot_crc,
                            audio_kbps=p.audio_kbps(), symbol_rate_khz=channel.symbol_rate(p) / 1000)
    result = dict(method='訓練3素材×0/-20/-40 dB の正規化MSE平均を最小化。指数オフセットは帯域ごとに固定。'
                         '6詳細帯域＋低域近似のまま最高域32係数のみ区間アッテネータを比較。保留2素材は選択に使わない。'
                         'リンクはB200M+SUB50M、独立チャンネル、AWGN、seed1。',
                  seconds=args.seconds, materials=manifest, widths=widths, offset_shifts=shifts,
                  groups=groups, headroom_db=args.headroom_db,
                  train_peak_per_band=train_peaks, holdout_peak_per_band=holdout_peaks,
                  exponent_plus_attenuator_budget=base_budget,
                  options={str(g): {'spec': v[0], 'train_normalized_mse': v[1],
                                    'exp_and_attn_bits': v[2]} if v else None for g, v in opt.items()},
                  extra_options={str(g): {'spec': v[0], 'train_normalized_mse': v[1],
                                           'exp_and_attn_bits': v[2]} if v else None
                                 for g, v in extras.items()},
                  specs=specs, layout=layout, codec=rows, extra_codec=extra_codec,
                  perceptual=perceptual, link=link)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    return result


if __name__ == '__main__':
    main()
