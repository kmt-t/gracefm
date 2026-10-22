#!/usr/bin/env python3
"""
samples/ のサンプル FLAC と、その説明 (samples/README.md) を作る。

  python tools/make_samples.py                     # samples/*_orig.flac を入力に使う
  python tools/make_samples.py --fishin Karissa_Hobbs_-_Lets_Go_Fishin.ogg を48kHzに変換したwav \
                               --vibeace Kevin_MacLeod_-_Vibe_Ace.ogg を48kHzに変換したwav   # 原音から作り直す

試験信号 (demo) はこのスクリプトの中で合成する。放送用は32kHz、モニター用は48kHz、各10秒。
通信路込みのサンプルは採用構成 (主系 = 階層16QAM の B200MH-A4 / B200H、副系 = S50M / S100、帯域ごとの融合、
軟判定の復号、ポストフィルタ4回) で、同じ受信電力のアナログFM (モノラル) も並べる。
"""
import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gracefm import channel, metrics, wavio  # noqa: E402
from gracefm.analog_fm import AnalogFM  # noqa: E402
from gracefm.codec import decode_coeffs, encode_block, haar_inverse, ms_to_lr  # noqa: E402
from gracefm.postfilter import PostFilter  # noqa: E402
from gracefm.profiles import PROFILES  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "samples")
SEC = 10.0


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


def codec(x, p, postfilter=True):
    n = len(x)
    nfr = int(np.ceil(n / p.block))
    xp = np.pad(x, ((0, nfr * p.block - n), (0, 0)))
    pf = PostFilter(p.levels, p.pf_iters, p.block) if postfilter else None
    out = np.zeros_like(xp)
    for i in range(nfr):
        coefs, cell = decode_coeffs(encode_block(xp[i * p.block:(i + 1) * p.block], p), p)
        if pf is None:
            M, S = haar_inverse(coefs["M"]), haar_inverse(coefs["S"])
        else:
            M, S = pf.process("M", coefs["M"], cell["M"]), pf.process("S", coefs["S"], cell["S"])
        out[i * p.block:(i + 1) * p.block] = ms_to_lr(M, S)
    return out[:n]


POWER_MAIN = 0.5                     # 主系に回す電力の割合 (送信電力の合計は固定)
CN0_LIST = (80, 66, 60, 57, 54)      # C/N0 [dB-Hz]。66 は 5m・室内の保守的な見積もり (SPEC 付録D)
BN = 180e3                           # C/N を表示する雑音帯域 [Hz] (FM放送 1波ぶん)
ROWS = []
MON_ROWS = []
MON_CN0 = (80, 75, 70, 65)           # モニター (近距離) の C/N0 [dB-Hz]


def cn(c):
    return c - 10 * np.log10(BN)


def save(name, y, mono, x, desc, fs=32000, rows=None, sub=""):
    path = os.path.join(OUT, sub, name)
    if not (y is x and os.path.exists(path)):          # 原音のファイルはそのまま使う (書き直さない)
        wavio.write_flac24(path, y[:, :1] if mono else y, fs)
    if y is x:
        snr = float("inf")
    else:
        source = name.split("_", 1)[0]
        reference = os.path.join(OUT, sub, f"{source}_orig48.flac" if sub else f"{source}_orig.flac")
        stored_ref, _ = wavio.read(reference)
        stored_y, _ = wavio.read(path)
        snr = metrics.snr_db(stored_ref, stored_y)
    (ROWS if rows is None else rows).append((os.path.join(sub, name) if sub else name, desc, snr))
    print(f"  {name:40s} {snr:6.1f}dB  {desc}")


def link_desc(main, sub, cn0, es, kind):
    ch = {"awgn": "白色雑音のみ", "rayleigh": "系統ごとに独立なフェージング（時定数約100ms）",
          "fade10": "主系の周波数だけ10dB落ちている"}[kind]
    em = es["esn0_main"] - (10.0 if kind == "fade10" else 0.0)
    avg = "平均の " if kind == "rayleigh" else ""
    return (f"{ch}。C/N0 {cn0}dB-Hz（C/N {cn(cn0):.1f}dB）。{avg}主系 {main} Es/N0 {em:.1f}dB、"
            f"副系 {sub} Es/N0 {es['esn0_sub']:.1f}dB（電力 {POWER_MAIN * 100:.0f}:{(1 - POWER_MAIN) * 100:.0f}）")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fishin", help="Let's Go Fishin' (48kHz wav)")
    ap.add_argument("--vibeace", help="Vibe Ace (48kHz wav)")
    ap.add_argument("--adopted-only", action="store_true",
                    help="既存のステレオ・モニター・FM・基本層音声を保ち、採用したモノラル主系だけ再生成")
    ap.add_argument("--stereo-only", action="store_true",
                    help="既存のモノラル・モニター・基本層音声を保ち、ステレオ主系の音声だけ再生成")
    ap.add_argument("--workers", type=int, default=3, help="並列に処理する素材数")
    args = ap.parse_args()
    if args.workers < 1:
        ap.error("workers は 1 以上にしてください")
    if args.adopted_only and args.stereo_only:
        ap.error("--adopted-only と --stereo-only は同時に指定できません")
    os.makedirs(OUT, exist_ok=True)

    sources = []
    for name, path, start, mono in (("demo", None, 0.0, False), ("fishin", args.fishin, 30.0, True),
                                    ("vibeace", args.vibeace, 0.0, True)):
        orig = os.path.join(OUT, f"{name}_orig.flac")
        if path:
            x, fs = wavio.read(path)
            x = x[int(start * fs):int((start + SEC) * fs)]
        elif name == "demo" and not os.path.exists(orig):
            x, fs = make_demo(48000), 48000
        elif os.path.exists(orig):
            x, fs = wavio.read(orig)
        else:
            continue
        if fs != 32000:
            x = x * (0.89 / np.abs(x).max())
            x = wavio.resample(x, fs, 32000)
        x = x[: int(SEC * 32000)]
        x = x * (0.89 / np.abs(x).max())
        if mono:
            x = np.repeat(x[:, :1], 2, axis=1)
        sources.append((name, x, mono))

    tasks = [(name, x, mono, args.adopted_only or args.stereo_only) for name, x, mono in sources
             if (not args.adopted_only or mono) and (not args.stereo_only or not mono)]
    if not tasks:
        ap.error("入力音源がありません")
    with ProcessPoolExecutor(max_workers=min(args.workers, len(tasks))) as executor:
        for rows, mon_rows in executor.map(generate_source, tasks):
            ROWS.extend(rows)
            MON_ROWS.extend(mon_rows)
    if args.stereo_only:
        update_readme_stereo_only()
    elif args.adopted_only:
        update_readme_adopted_only()
    else:
        write_readme()


def generate_source(task):
    global ROWS, MON_ROWS
    ROWS, MON_ROWS = [], []
    name, x, mono, adopted_only = task
    main_p, base_p = ("B200MH-A4", "B200M") if mono else ("B200H", "B200")
    sub = channel.DEFAULT_SUB[main_p]
    print(name, flush=True)
    save(f"{name}_orig.flac", x, mono, x, "原音（32kHzに変換したもの）")
    if not adopted_only:
        if name == "demo":
            demo48 = make_demo(48000)
            demo48 = demo48 * (0.89 / np.abs(demo48).max())
        monitor(name, demo48 if name == "demo" else wavio.resample(x, 32000, 48000), mono)
    save(f"{name}_{main_p}.flac", codec(x, PROFILES[main_p]), mono, x,
         f"コーデックだけ（通信路なし）。{main_p} の全ビット（基本層＋拡張層、約{PROFILES[main_p].audio_kbps():.0f}kbps）")
    if not adopted_only:
        base_desc = (f"コーデックだけ。基本層だけ（{base_p}、約{PROFILES[base_p].audio_kbps():.0f}kbps）＝拡張層が全部崩れたときの音"
                     if mono else f"コーデックだけ。{base_p}（約{PROFILES[base_p].audio_kbps():.0f}kbps）。B200H の区間アッテネータは含まない")
        save(f"{name}_{base_p}.flac", codec(x, PROFILES[base_p]), mono, x,
             base_desc)
        save(f"{name}_{base_p}_nopf.flac", codec(x, PROFILES[base_p], postfilter=False), mono, x,
             f"同上、ポストフィルタなし")
    fm = AnalogFM(x[:, 0], 32000) if mono and not adopted_only else None
    for cn0 in CN0_LIST:
        y, st, es = channel.link(x, main_p, cn0, sub=sub, power_main=POWER_MAIN, seed=1)
        save(f"{name}_final_cn0-{cn0}.flac", y, mono, x, link_desc(main_p, sub, cn0, es, "awgn"))
        if fm is not None:
            y1 = fm.receive(cn0, np.random.default_rng(1))
            save(f"{name}_fm_cn0-{cn0}.flac", np.stack([y1, y1], 1), mono, x,
                 f"アナログFMモノラル。白色雑音のみ。C/N0 {cn0}dB-Hz（C/N {cn(cn0):.1f}dB）。ゴーストなし")
    for kind, cn0 in (("rayleigh", 60), ("fade10", 66)):
        y, st, es = channel.link(x, main_p, cn0, sub=sub, power_main=POWER_MAIN, kind_main=kind,
                                 kind_sub="awgn" if kind == "fade10" else kind, seed=1)
        plc = st["plc_samples"] / len(x) * 100
        save(f"{name}_final_{kind}_cn0-{cn0}.flac", y, mono, x,
             link_desc(main_p, sub, cn0, es, kind) + f"。欠けて予測で埋めた時間 {plc:.1f}%")
        if fm is not None:
            g = channel.fading_gains(int(np.ceil(len(x) / 64)), kind, np.random.default_rng(101))
            y1 = fm.receive(cn0, np.random.default_rng(1), g)
            what = "フェージング（同じモデル）" if kind == "rayleigh" else "その周波数が10dB落ちている"
            save(f"{name}_fm_{kind}_cn0-{cn0}.flac", np.stack([y1, y1], 1), mono, x,
                 f"アナログFMモノラル。{what}。C/N0 {cn0}dB-Hz（C/N {cn(cn0):.1f}dB）")
    return ROWS, MON_ROWS


def monitor(name, x, mono):
    """モニター用 (48kHz、近距離) のサンプル: M700 (QPSK) と M700H (階層16QAM)"""
    from dataclasses import replace
    os.makedirs(os.path.join(OUT, "monitor"), exist_ok=True)
    mh = PROFILES["M700H"]
    base = replace(mh, name="M700H基本層", bits_m=mh.base_m, bits_s=mh.base_s, base_m=None, base_s=None,
                   modulation="qpsk", alpha=1.0)
    kw = dict(fs=48000, rows=MON_ROWS, sub="monitor")
    src = "原音（合成試験信号を48kHzで作ったもの、全帯域）" if name == "demo" else "原音（32kHz の原音を48kHzに変換したもの。元の音源の帯域は約11kHz）"
    save(f"{name}_orig48.flac", x, mono, x, src, **kw)
    save(f"{name}_M700.flac", codec(x, PROFILES["M700"]), mono, x, "コーデックだけ。M700（約691kbps）", **kw)
    save(f"{name}_M700H.flac", codec(x, mh), mono, x, f"コーデックだけ。M700H の全ビット（約{mh.audio_kbps():.0f}kbps）", **kw)
    save(f"{name}_M700H-base.flac", codec(x, base), mono, x,
         f"コーデックだけ。M700H の基本層だけ（約{base.audio_kbps():.0f}kbps）＝拡張層が全部崩れたときの音", **kw)
    for prof, cl in (("M700H", MON_CN0), ("M700", (70, 65))):
        p = PROFILES[prof]
        bw = 1.25 * channel.symbol_rate(p) / 1e3
        for cn0 in cl:
            y, st, es = channel.link(x, prof, cn0, sub=None, seed=1)
            mod = "階層16QAM" if p.modulation != "qpsk" else "QPSK"
            save(f"{name}_{prof}_cn0-{cn0}.flac", y, mono, x,
                 f"{prof}（{mod}、1.25×Rs 約{bw:.0f}kHz）1系統。白色雑音のみ。C/N0 {cn0}dB-Hz（C/N {cn(cn0):.1f}dB）、"
                 f"Es/N0 {es['esn0_main']:.1f}dB", **kw)


def write_readme():
    lines = [l for l in README_HEAD.splitlines()]
    lines += ["", "## ファイル一覧", "",
              "波形SNR：保存したFLACを読み戻し、原音FLACとの差から求めた値（大きいほど良い。聴感の評価点ではない）。", "",
              "| ファイル | 内容 | 波形SNR |", "|---|---|---|"]
    for name, desc, snr in ROWS:
        lines.append(f"| `{name}` | {desc} | {'—' if not np.isfinite(snr) else f'{snr:.1f}dB'} |")
    lines += ["", MONITOR_HEAD, "", "| ファイル | 内容 | 波形SNR |", "|---|---|---|"]
    for name, desc, snr in MON_ROWS:
        lines.append(f"| `{name}` | {desc} | {'—' if not np.isfinite(snr) else f'{snr:.1f}dB'} |")
    lines += ["", README_TAIL]
    with open(os.path.join(OUT, "README.md"), "w") as f:
        f.write("\n".join(lines) + "\n")


def update_readme_adopted_only():
    """既存の別方式の測定行を保ち、モノラル主系の測定行だけ置き換える。"""
    path = os.path.join(OUT, "README.md")
    measurements = {name: (desc, snr) for name, desc, snr in ROWS}
    lines = []
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if "ここに掲載した既存のモノラル音声は" in line:
            continue
        line = line.replace("このサンプルを生成した時点の構成（主系 B200MH / B200H",
                            "この方式の放送の採用構成（主系 B200MH-A4 / B200H")
        line = line.replace("この方式の放送の最終構成（主系 B200MH / B200H",
                            "この方式の放送の採用構成（主系 B200MH-A4 / B200H")
        line = line.replace("`*_B200MH`・`*_B200H`", "`*_B200MH-A4`・`*_B200H`")
        if line.startswith("| `"):
            name = line.split("`", 2)[1]
            if name.endswith("_B200MH.flac") or name.endswith("_B200MH-A4.flac"):
                continue
            if name in measurements:
                desc, snr = measurements[name]
                line = f"| `{name}` | {desc} | {'—' if not np.isfinite(snr) else f'{snr:.1f}dB'} |"
        lines.append(line)
        if line.startswith("| `fishin_orig.flac`") or line.startswith("| `vibeace_orig.flac`"):
            name = line.split("`", 2)[1].replace("_orig.flac", "_B200MH-A4.flac")
            desc, snr = measurements[name]
            lines.append(f"| `{name}` | {desc} | {snr:.1f}dB |")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def update_readme_stereo_only():
    """採用ステレオ主系を再符号化した行だけ更新し、ほかの音声例の行を保つ。"""
    path = os.path.join(OUT, "README.md")
    measurements = {name: (desc, snr) for name, desc, snr in ROWS}
    lines = []
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if line.startswith("| `"):
            name = line.split("`", 2)[1]
            if name in measurements:
                desc, snr = measurements[name]
                line = f"| `{name}` | {desc} | {'—' if not np.isfinite(snr) else f'{snr:.1f}dB'} |"
        lines.append(line)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


README_HEAD = """# サンプル音声（GraceFM）

- 劣化音は24bit FLAC、原音は既存の16bit FLAC。各10秒。放送用は32kHz（このフォルダ）、モニター用は48kHz（`monitor/`）
- `tools/make_samples.py` で生成（このファイルも同じスクリプトが書く）

## 聴き比べ

| ファイル | 内容 |
|---|---|
| `*_final_*` | この方式の放送の採用構成（主系 B200MH-A4 / B200H ＋ 副系 S50M / S100、送信電力 50:50） |
| `*_fm_*` | 同じ受信電力のアナログFM（モノラル、ゴーストなし） |
| `*_B200MH-A4`・`*_B200H` | コーデックだけ、全ビット（拡張層まで届いたときの上限） |
| `*_B200M` | B200M（QPSK、194kbps）の比較用音声。A4の基本層（198kbps）とは別プロファイル |
| `*_B200` | B200（QPSK、200kbps）。B200H の基本層とは区間アッテネータの有無が異なる |

- おすすめ：`fishin_final_cn0-57` と `fishin_fm_cn0-57`（FM がスレッショルドを割る強さ）、`*_rayleigh_cn0-60`（途切れ方）
- demo（ステレオ）は FM ステレオのモデルがないため FM なし

## 電波の強さ

| C/N0 | C/N（180kHz） | 目安 |
|---|---|---|
| 80dB-Hz | 27.4dB | 良好 |
| 66dB-Hz | 13.4dB | 5m・室内の保守的な見積もり。FM はスレッショルドの少し上 |
| 60dB-Hz | 7.4dB | FM はスレッショルド割れ（クリック） |
| 57dB-Hz | 4.4dB | FM はかなり荒れる |
| 54dB-Hz | 1.4dB | FM はほぼ雑音 |

- 通信路：白色雑音のみ／系統ごとに独立なレイリーフェージング（時定数100ms、FM も同じ変動）／主系の周波数だけ10dB 低下（FM はその周波数で受信）
- 同期・等化は理想。FM のゴーストは含まない"""

MONITOR_HEAD = """## モニター用（48kHz、`monitor/`）

| ファイル | 内容 |
|---|---|
| `*_M700H*` | 階層16QAM、1.25×Rs 約343kHz（推奨） |
| `*_M700*` | QPSK、1.25×Rs 約629kHz（比較用） |
| `*_M700H-base` | M700H の基本層だけ（約329kbps） |

- 1系統・全電力、白色雑音のみ。近距離（1m 程度）は C/N0 約80dB-Hz の見込み
- fishin・vibeace は32kHz の原音を48kHz に変換したもの（元の帯域は約11kHz）"""

README_TAIL = """## 楽曲の出典とライセンス

[librosa/data](https://github.com/librosa/data) 収録の音源を、抜粋・サンプリング周波数の変換・音量の正規化・本方式による符号化と復号で加工。元の楽曲は CC BY 3.0、加工したサンプルは [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)（元の楽曲の出典表示を含む）。

- **"Let's Go Fishin'" by Karissa Hobbs** — [Free Music Archive](https://freemusicarchive.org/music/Karissa_Hobbs/Age_of_Flowers/09_Lets_Go_Fishin)、[CC BY 3.0](https://creativecommons.org/licenses/by/3.0/)
- **"Vibe Ace" by Kevin MacLeod** — [Free Music Archive](https://freemusicarchive.org/music/Kevin_MacLeod/Jazz_Sampler/Vibe_Ace)、[CC BY 3.0](https://creativecommons.org/licenses/by/3.0/)
- `demo_*`：合成した試験信号（全帯域・ステレオ）"""


if __name__ == "__main__":
    main()
