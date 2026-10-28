#!/usr/bin/env python3
"""Generate/check the current profile matrix and derived frame budgets."""
import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from gracefm.codec import exp_range
from gracefm.layout import Layout
from gracefm.profiles import PROFILES
from gracefm.txrx import Transmitter


def vector(values):
    return ', '.join(map(str, values))


def render():
    lines = ['# 現行プロファイル設定マトリクス', '',
             '`gracefm/profiles.py` の `PROFILE_MATRIX` から生成。更新は `python tools/report/profile_matrix.py`、一致確認は `--check`。アルゴリズムと測定条件は[技術論文](SPEC.md)を参照。', '',
             '全登録プロファイルに区間アッテネータを標準装備する。名前の数字は系列名であり、現在の実ビットレートは下表を参照。', '',
             '共通設定：64サンプル、Haar 4段（最低域の帯域幅が2 kHz未満になるまで分割）、指数4bit/送信帯域、基本CRC-12とH1/H2用の高域CRC-10（該当帯域を送る場合のみ）、系統符号 K=7・r=1/2（位相部＝パリティ、振幅部＝データ）。**ヘッダ**（ヘッダ・指数・区間アッテネータ・CRC）と**Haar係数部**（係数ごとのパリティと仮数bit）に分けて送る。ヘッダはパリティを位相部、情報を振幅部に置く。係数のパリティは各係数の先頭シンボル（位相部）に置き、仮数bitはFEC・CRCなし。上位Kbit自体は仮数bitの先頭にある（Y帯域は仮数が仮数bitに無いので、最上位bitとそのパリティを専用シンボルの位相に載せる）。Kは高域（最後の2帯域 H2/H1）とそれより低い帯域で別に決められる。ヘッダは非暗号化24bit（カウンタ16bit）、暗号化32bit（カウンタ24bit）。ID 0・12～15は予約。副系SUBはQPSK、ステレオ差分Sは主系の階層QAMで送る。M接尾辞はモノラル、Y接尾辞はQASKを表す。', '',
             '## ID・方式・伝送予算', '',
             '非暗号化の値。シンボル数にはプリアンブル16シンボルとY専用シンボルを含む。理論支持幅は `(1+β)Rs` で、99%占有帯域の実測値ではない。音声量には指数とアッテネータを含む。強い位置は、位相部の列（ヘッダのパリティ、終端、係数のパリティ、基本層の仮数）の長さ、弱い位置は振幅部の列（ヘッダの情報、終端、拡張層の仮数）の長さ（階層16QAMのみ。両者は一致し、`--check` で検査する）。', '',
             '| ID | 名前 | fs kHz | M/S | 変調 / α | Y開始k | パリティで守るK 低域/高域 | 音声 kbps | CRC本数 | ヘッダCRC込 bit | ヘッダFEC後 bit | パリティ bit | 仮数 bit | 強い位置 | 弱い位置 | シンボル/フレーム | Rs ksym/s | RRC β / span | 理論支持幅 kHz |',
             '|---|---|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|']
    budgets=[]
    for p in PROFILES.values():
        tx=Transmitter(p); l=tx.layout; ns=tx.nsym+16; rs=tx.symbol_rate()
        strong=l.n_strong_raw if p.layered else '—'
        weak=l.n_weak_raw if p.layered else '—'
        lines.append(f'| {p.pid} | {p.name} | {p.fs/1000:g} | {"M/S" if any(p.bits_s) else "M"} | {p.modulation} / {p.alpha} | {p.y_start_k if p.has_y else "—"} | {p.protect_bits(0)}/{p.protect_bits(p.high_k)} | {p.audio_kbps():g} | {2 if l.has_high_crc else 1} | {l.n_prot_crc} | {l.n_header} | {l.n_parity} | {l.n_coef_bits} | {strong} | {weak} | {ns} | {rs/1000:g} | {p.pulse_beta_pct / 100:g} / {p.pulse_span} | {rs*(100+p.pulse_beta_pct)/100/1000:g} |')
        budgets.append(dict(profile=asdict(p), header_bits=l.header_bits, crc_count=2 if l.has_high_crc else 1,
                            header_crc_bits=l.n_prot_crc, header_fec_bits=l.n_header, parity_bits=l.n_parity,
                            protect_bits_low=p.protect_bits(0), protect_bits_high=p.protect_bits(p.high_k),
                            fec_bits=l.n_coded, coefficient_part_bits=l.n_coef_bits,
                            strong_positions=l.n_strong_raw if p.layered else None,
                            weak_positions=l.n_weak_raw if p.layered else None,
                            symbols_per_frame=ns, symbol_rate=rs,
                            audio_kbps=float(p.audio_kbps()), theoretical_bandwidth_hz=rs*(100+p.pulse_beta_pct)/100))
    lines += ['', '## 成分ごとの全設定', '',
              'ベクトルは `k=0…4`（k0〜k4 は 32 kHz で 0〜1、1〜2、2〜4、4〜8、8〜16 kHz）。M/Sの各行に同じ項目を表示する。アッテネータ区間長0はその帯域では不使用。各成分の最高送信帯域に配置し、4係数を基本とする（係数数が4未満ならその係数数）。Y帯域は各帯域4区間。', '',
              '階層16QAMでは、係数をシンボル単位で分け、位相部（強い2位置）に置く仮数bitが基本層、振幅部（弱い2位置）に置く仮数bitが拡張層。位相部には基本層の仮数のほかにパリティKbitが入るので、位相部（基本層 + K）と振幅部（拡張層）がどちらも2の倍数で、全幅 = 基本層 + 拡張層。K=1でNシンボルの係数は基本層 2N−1、拡張層 2N、全幅 4N−1。基本層幅は、係数ごとに位相部（基本層 + パリティ）と振幅部（拡張層）が同じ大きさになるように `tools/common/layers.py` が決める。Y高域Mは専用シンボルで、デジタル層分割の対象外。QPSKは全幅が2の倍数で、層分割なし。', '',
              '| ID | 名前 | 成分 | 全幅 | 基本層 | 拡張層 | アッテネータ区間長 | 指数幅 | 指数最小値 |',
              '|---|---|---|---|---|---|---|---|---|']
    for p in PROFILES.values():
        for ch,bits in [('M',p.bits_m),('S',p.bits_s)]:
            if not any(bits):
                lines.append(f'| {p.pid} | {p.name} | {ch} | — | — | — | — | — | — |'); continue
            base=[]; ext=[]
            for k,b in enumerate(bits):
                if not b or p.y_band(ch,k) or not p.layered:
                    base.append('—');ext.append('—')
                else:
                    base.append(p.base_bits(ch,k));ext.append(b-p.base_bits(ch,k))
            exps=[p.exp_bits if b else '—' for k,b in enumerate(bits)]
            offsets=[exp_range(k,b,p)[0] if b else '—' for k,b in enumerate(bits)]
            lines.append(f'| {p.pid} | {p.name} | {ch} | {vector(bits)} | {vector(base)} | {vector(ext)} | {vector(p.attenuator_group(ch,k) for k in range(p.nbands))} | {vector(exps)} | {vector(offsets)} |')
    lines += ['', 'Y帯域は標準7bit（位相＝最上位bit＋パリティ、半径6bit）、半径間隔は `0.08 * 7.5 / 31.5`。Y帯域の仮数は仮数bitに入らず専用シンボルで送り、位相に最上位bitとそのパリティを載せてFEC保護する（終端bitだけヘッダ側）。Yの暗号化は未対応。', '',
              'フレーム予算は現行設定から計算した値。', '']
    return '\n'.join(lines), json.dumps(dict(profiles=budgets), ensure_ascii=False, indent=2)+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    md,data=render()
    if args.check:
        for p in PROFILES.values():
            l=Layout(p)
            if p.layered and l.n_strong_raw!=l.n_weak_raw:
                raise SystemExit(f'strong != weak positions: {p.name} {l.n_strong_raw} {l.n_weak_raw}')
    for path,content in [(ROOT/'docs/PROFILES.md',md),(ROOT/'docs/results/profile_matrix.json',data)]:
        if args.check:
            if not path.exists() or path.read_text()!=content:
                raise SystemExit(f'out of date: {path}')
        else: path.write_text(content)
    print('profile matrix matches implementation' if args.check else 'profile matrix generated')

if __name__=='__main__': main()
