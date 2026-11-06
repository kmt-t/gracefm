#!/usr/bin/env python3
"""試聴音声の一式を検証し、索引 (samples/index.json) と samples/README.md を作る。

--check は何も書かず、FLAC と音声を作るコードが索引と一致するかだけを確かめる (不一致なら終了コード 1)。
"""
import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from gracefm.iir import ALT_DELAY
from gracefm.profiles import PROFILES
from tools.common import metrics, wavio
from tools.samples.make_samples import (
    ALL_SETS,
    CASES,
    CN0_LIST,
    MATERIALS,
    SEC,
    cn,
    paired_sub,
    source_name,
)
from tools.samples.sample_names import reference_name, sample_name

SOURCES = [
    ('piano', '"Emotional piano" by triangelx', 'https://commons.wikimedia.org/wiki/File:Emotional_piano.wav', 'CC0 1.0'),
    ('percussion', '"Ceramic Djembe" by RutgerMuller', 'https://commons.wikimedia.org/wiki/File:Ceramic_Djembe.wav', 'CC0 1.0'),
]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def code_digests():
    """試料の中身を左右するコードのハッシュ。評価や文書の道具は含めない"""
    return {str(p.relative_to(ROOT)): digest(p)
            for d in ('gracefm', 'tools/common', 'tools/samples') for p in sorted((ROOT / d).rglob('*.py'))}


def expected_names():
    return {r[4] for r in expected()} | {reference_name(source_name(m, f), fs) for m, _, _ in MATERIALS for fs, f, _, _, _ in ALL_SETS}


def check():
    """索引と現状の違いの一覧を返す"""
    index = json.loads((ROOT / 'samples' / 'index.json').read_text())
    want = expected_names()
    found = {p.name for p in (ROOT / 'samples').glob('*.flac')}
    problems = [f'missing: {n}' for n in sorted(want - found)] + [f'unexpected: {n}' for n in sorted(found - want)]
    recorded = {Path(e['file']).name: e['sha256'] for e in index['samples']}
    recorded.update({Path(e['reference_file']).name: e['reference_sha256'] for e in index['samples']})
    problems += [f'not in index: {n}' for n in sorted(want - set(recorded))]
    problems += [f'hash differs: {n}' for n in sorted(want & found & set(recorded)) if digest(ROOT / 'samples' / n) != recorded[n]]
    code = code_digests()
    problems += [f'code changed: {n}' for n in sorted(set(code) | set(index['code_sha256'])) if code.get(n) != index['code_sha256'].get(n)]
    return problems


def expected():
    """(素材, 形, 構成, 条件, ファイル名, サンプリング周波数) の一覧"""
    rows = []
    for material, _, _ in MATERIALS:
        for fs, form, mains, subs, cases in ALL_SETS:
            src = source_name(material, form)
            for main in mains:
                if not subs:
                    rows.append((material, form, main, 'codec', sample_name(src, fs, main), fs))
                for sub in (paired_sub(main, s) for s in subs):
                    for case in cases:
                        rows.append((material, form, main + (f'+{sub}' if sub else ''), case,
                                     sample_name(src, fs, main, case, sub=sub), fs))
            if form == 'mono' and fs == 32000:
                for case in CASES:
                    rows.append((material, form, 'FM', case, sample_name(src, fs, 'FM', case), fs))
    return rows


def snr_db(reference, audio, case, config, fs):
    """波形SNR。通信路を通した試料は末尾 ALT_DELAY サンプルが遅れ分の無音 (make_samples.aligned) なので、それを除いて測る。
    除かないと、高い C/N0 では末尾の数サンプルの誤差だけで値が 2 dB 下がる。コーデックだけと FM は除かない。"""
    if case == 'codec' or config == 'FM':
        return metrics.snr_db(reference, audio)
    n = len(audio) - ALT_DELAY[fs]
    return metrics.snr_db(reference[:n], audio[:n])


def build():
    rows = expected()
    folder = ROOT / 'samples'
    want = expected_names()
    found = {p.name for p in folder.glob('*.flac')}
    if want != found:
        raise ValueError({'missing': sorted(want - found), 'unexpected': sorted(found - want)})
    entries = []
    for material, form, config, case, name, row_fs in rows:
        path = folder / name
        src = source_name(material, form)
        audio, fs = wavio.read(path)
        refpath = folder / reference_name(src, row_fs)
        reference, ref_fs = wavio.read(refpath)
        assert fs == ref_fs == row_fs and audio.shape == reference.shape and len(audio) == fs * SEC
        assert np.all(np.isfinite(audio))
        profiles = [asdict(PROFILES[n]) for n in config.split('+') if n in PROFILES]
        entries.append({'file': f'samples/{name}', 'sha256': digest(path), 'material': material, 'form': form,
                            'reference_file': f'samples/{refpath.name}', 'reference_sha256': digest(refpath),
                            'sample_rate_hz': fs, 'seconds': len(audio) / fs, 'channels': sf.info(path).channels,
                            'configuration': config, 'condition': case, 'profiles': profiles,
                            'snr_db': float(snr_db(reference, audio, case, config, fs))})
    code = code_digests()
    report = {'description': '10-second listening samples; decoded FLAC measurements, not RF capture',
                  'expected_sample_count': len(rows), 'seed': 1, 'code_sha256': code, 'samples': entries}
    destination = ROOT / 'samples' / 'index.json'
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    write_readme(entries)
    print(destination, len(entries), 'validated samples')


def write_readme(entries):
    by = {(e['material'], e['form'], e['configuration'], e['condition']): e for e in entries}
    lines = ['# サンプル音声（GraceFM）', '',
             ('ファイル名の読み方は[命名規則](NAMING.md)。各10秒・32 kHzと48 kHz、劣化音は24bit FLAC。`tools/samples/make_samples.py` で生成し、'
             '`tools/samples/sample_catalog.py` で検証してこのファイルを書く。設定・測定値・SHA-256は[音源一覧JSON](index.json)。'), '',
             '## マトリクス', '',
             ('素材 3（demo・piano・percussion）。モノラル形は (L+R)/2 で、通信路を通す（主系＋副系）。ステレオ形は、コーデックだけ（通信路なし）と C/N0 57 の通信路（主系＋副系）。'
             '2系統は主系・副系とも独立のチャンネルで、電力を分け合わない（C/N0は同じ値）。'), '',
             '| 軸 | 内容 |', '|---|---|',
             '| 主系 | B200M（32 kHz） |',
             '| 副系 | SUB50M |',
             '| ステレオ主系 | 32 kHz：B200・B200Y、48 kHz：M700・M700Y |',
             '| ステレオ副系・条件 | 32 kHz：SUB50M、48 kHz：SUB100-48K。C/N0 57 だけ |',
             '| LeGall 5/3 | 上の主系それぞれに `-L` 版があり、副系も `-L` にそろえる |',
             '| 条件 | 白色雑音 C/N0 ' + '・'.join(map(str, CN0_LIST)) + ' |',
             '| アナログFM | 32 kHzのモノラル形だけ、上の通信路条件 |', '',
             '## 電波の強さ', '', '| C/N0 | C/N（180kHz） |', '|---|---|']
    for c in sorted(CN0_LIST, reverse=True):
        lines.append(f'| {c} dB-Hz | {cn(c):.1f} dB |')
    lines += ['', '66 dB-Hz は5m・室内の保守的な見積もり（[比較資料](../docs/COMPARISON.md)の「C/Nと音質の対応」）。通信路は白色雑音のみ。同期・等化は理想で、FMのゴーストは含まない。', '']
    for fs, form, mains, subs, cases in ALL_SETS:
        label = ('モノラル形' if form == 'mono' else 'ステレオ形') + f'・{fs // 1000} kHz'
        configs = [m + (f'+{paired_sub(m, s)}' if s else '') for m in mains for s in (subs or (None,))] + (['FM'] if form == 'mono' and fs == 32000 else [])
        cols = ('codec',) if not subs else cases
        lines += [f'## {label}（波形SNR dB、保存したFLACと原音の差）', '']
        for material, _, _ in MATERIALS:
            lines += [f'### {material}', '', '| 構成 | ' + ' | '.join(cols) + ' |',
                      '|---|' + '---:|' * len(cols)]
            for config in configs:
                cells = []
                for case in cols:
                    e = by.get((material, form, config, case))
                    cells.append('—' if e is None else f'[{e["snr_db"]:.1f}]({Path(e["file"]).name})')
                lines.append(f'| {config} | ' + ' | '.join(cells) + ' |')
            lines.append('')
    lines += ['## 原音と出典', '']
    for material, _, _ in MATERIALS:
        for fs, form, _, _, _ in ALL_SETS:
            lines.append(f'- [{source_name(material, form)} ({fs // 1000} kHz)]({reference_name(source_name(material, form), fs)})')
    lines += ['', '- `demo`：合成した試験信号（全帯域・ステレオ）']
    for _, title, url, lic in SOURCES:
        lines.append(f'- {title} — [Wikimedia Commons]({url})、{lic}')
    lines += ['', '加工したサンプルは [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)。']
    (ROOT / 'samples/README.md').write_text('\n'.join(lines) + '\n')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--check', action='store_true', help='何も書かず、索引との一致だけを確かめる')
    if ap.parse_args().check:
        problems = check()
        print('\n'.join(problems) if problems else 'samples match the index and the code')
        sys.exit(1 if problems else 0)
    build()
