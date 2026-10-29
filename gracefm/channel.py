"""
評価用の通信路モデル (アナログの通信路を模擬するので、浮動小数点を使う。ハードウェアではない)。
link は同期済みシンボルに直接雑音を加え、12 bit の ADC で量子化して、受信側が受け取る小数 22 bit の固定小数点の整数に直す。
link_static_multipath は RRC 送受信フィルタと静的マルチパスの等価応答を使い、
等化器も選択できる。どちらもシンボル時刻・搬送波位相の同期は理想とする。

電波の強さは C/N0 [dB-Hz] (受信電力 ÷ 1Hz あたりの雑音) で与え、方式・系統ごとに
    Es/N0 [dB] = C/N0 + 10·log10(電力の割合) - 10·log10(シンボルレート [シンボル/秒])
に換算する。C/N [dB] (雑音帯域 Bn) = C/N0 - 10·log10(Bn)。
"""
import numpy as np

from . import modem
from .profiles import PROFILES, Profile
from .txrx import Transmitter, receive

# 主系に組み合わせる副系 (主系より低いビットレートで、別の周波数で送る受け皿)
DEFAULT_SUB = {
    "B200M": "SUB50M", "B200MY": "SUB50M",
    "B200": "SUB100", "B200Y": "SUB100",
    "M700M": "SUB100-48K", "M700MY": "SUB100-48K",
    "M700": "SUB100-48K", "M700Y": "SUB100-48K",
}


def symbol_rate(p):
    """1系統のシンボルレート [シンボル/秒] (プリアンブル込み)"""
    return (modem.N_PREAMBLE + Transmitter(p).nsym) * p.frames_per_sec


def fading_gains(nfr, kind, rng, tau_frames=50):
    """
    フレームごとの電力利得 (平均 1)。
    awgn: 1。fade10: 0.1 (10dB 落ちたまま)。
    rayleigh: レイリーフェージング。複素利得を AR(1) で相関させる (時定数 tau_frames、既定 50 フレーム = 100ms)。
    受信側は理想的な AGC とし、利得の分だけ Es/N0 が変わるモデル。
    """
    if kind == "awgn":
        return np.ones(nfr)
    if kind == "fade10":
        return np.full(nfr, 0.1)
    if kind == "rayleigh":
        rho = np.exp(-1.0 / tau_frames)
        cn = lambda: (rng.normal() + 1j * rng.normal()) / np.sqrt(2)  # noqa: E731
        h = np.empty(nfr, complex)
        h[0] = cn()
        for i in range(1, nfr):
            h[i] = rho * h[i - 1] + np.sqrt(1 - rho ** 2) * cn()
        return np.abs(h) ** 2
    raise ValueError(kind)


ADC_BITS = 12
ADC_ONE = 1 << (ADC_BITS - 2)                    # 信号点の大きさ 1.0 に対する ADC の符号 (±2 までを表す)


def awgn(sym, snr_db, rng):
    """Es/N0 = snr_db の複素白色雑音を加える。sym は実数の (n, 2)"""
    n0 = 10 ** (-snr_db / 10)
    return sym + rng.normal(0, np.sqrt(n0 / 2), sym.shape)


def adc(sym):
    """実数のシンボル (n, 2) を ADC の符号 (12 bit) にして、受信側の小数 22 bit 固定小数点 (±1 = 2^SYM_FRAC) の整数に直す"""
    code = np.clip(np.rint(sym * ADC_ONE), -(1 << (ADC_BITS - 1)), (1 << (ADC_BITS - 1)) - 1).astype(np.int64)
    return code << (modem.SYM_FRAC - ADC_BITS + 2)


def through(frames, esn0, gains, rng):
    """整数のシンボル (n, 2) のリスト → 雑音を加え、ADC で量子化した整数のシンボルのリスト"""
    return [adc(awgn(f / float(1 << modem.SYM_FRAC), esn0 + 10 * np.log10(max(g, 1e-6)), rng)) for f, g in zip(frames, gains)]


def link(x, main, cn0, sub="auto", cn0_sub=None, kind_main="awgn", kind_sub="awgn", seed=1, cipher=None,
         **rx_kw):
    """
    送信 → 通信路 → 受信。主系と副系は別送信機・別周波数の独立したチャンネルで、電力を分け合わない。
    cn0: 主系の C/N0。cn0_sub: 副系の C/N0 (既定は cn0 と同じ)。ノイズは主系・副系で独立。
    main, sub: プロファイル名または Profile。sub="auto" なら DEFAULT_SUB、None なら 1系統。
    cipher: 暗号化するとき gracefm.crypto.StreamCipher (送受信で同じもの)。
    返り値: (音声, 受信の統計, {"esn0_main": .., "esn0_sub": ..})
    """
    pm = main if isinstance(main, Profile) else PROFILES[main]
    if sub == "auto":
        sub = DEFAULT_SUB.get(pm.name)
    ps = (sub if isinstance(sub, Profile) else PROFILES[sub]) if sub else None
    rng = np.random.default_rng(seed)
    esm = cn0 - 10 * np.log10(symbol_rate(pm))
    fa = Transmitter(pm, 0, 0, cipher=cipher).run(x)
    fa = through(fa, esm, fading_gains(len(fa), kind_main, np.random.default_rng(seed + 100)), rng)
    fb, ess = None, None
    if ps:
        ess = (cn0 if cn0_sub is None else cn0_sub) - 10 * np.log10(symbol_rate(ps))
        fb = Transmitter(ps, 1, 0, cipher=cipher).run(x)
        fb = through(fb, ess, fading_gains(len(fb), kind_sub, np.random.default_rng(seed + 200)), rng)
    y, st = receive(pm, fa, fb, len(x), 0, profile_b=ps, cipher=cipher, **rx_kw)
    return y, st, {"esn0_main": esm, "esn0_sub": ess}
