"""
評価用の通信路モデル (同期済みのシンボル列に直接かける。パルス成形・同期・等化は含まない)。

電波の強さは C/N0 [dB-Hz] (受信電力 ÷ 1Hz あたりの雑音) で与え、方式・系統ごとに
    Es/N0 [dB] = C/N0 + 10·log10(電力の割合) - 10·log10(シンボルレート [シンボル/秒])
に換算する。C/N [dB] (雑音帯域 Bn) = C/N0 - 10·log10(Bn)。
"""
import numpy as np

from . import modem
from .profiles import PROFILES
from .txrx import Transmitter, receive

# 主系に組み合わせる副系 (主系より低いビットレートで、別の周波数で送る受け皿)
DEFAULT_SUB = {"M700Q16": "S100W", "M700H": "S100W", "M700": "S100W", "B200MH": "S50M", "B200H": "S100", "B200M": "S50M", "B150M": "S50M", "B200": "S100", "B150": "S100"}


def symbol_rate(p):
    """1系統のシンボルレート [シンボル/秒] (プリアンブル込み)"""
    return (len(modem.PREAMBLE) + Transmitter(p).nsym) * p.frames_per_sec


def cn_db(cn0, bn=180e3):
    return cn0 - 10 * np.log10(bn)


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


def through(frames, esn0, gains, rng):
    return [modem.awgn(f, esn0 + 10 * np.log10(max(g, 1e-6)), rng) for f, g in zip(frames, gains)]


def link(x, main, cn0, sub="auto", power_main=0.5, kind_main="awgn", kind_sub="awgn", seed=1, cipher=None,
         **rx_kw):
    """
    送信 → 通信路 → 受信。送信電力の合計を C/N0 で与える。
    main, sub: プロファイル名。sub="auto" なら DEFAULT_SUB、None なら 1系統 (全電力を主系に)。
    power_main: 主系に回す電力の割合 (2系統のとき。既定は等分)。
    cipher: 暗号化するとき gracefm.crypto.StreamCipher (送受信で同じもの)。
    返り値: (音声, 受信の統計, {"esn0_main": .., "esn0_sub": ..})
    """
    pm = PROFILES[main]
    if sub == "auto":
        sub = DEFAULT_SUB.get(main)
    ps = PROFILES[sub] if sub else None
    frac = power_main if ps else 1.0
    rng = np.random.default_rng(seed)
    off = pm.block // 2
    esm = cn0 + 10 * np.log10(frac) - 10 * np.log10(symbol_rate(pm))
    fa = Transmitter(pm, 0, 0, cipher=cipher).run(x)
    fa = through(fa, esm, fading_gains(len(fa), kind_main, np.random.default_rng(seed + 100)), rng)
    fb, ess = None, None
    if ps:
        ess = cn0 + 10 * np.log10(1 - frac) - 10 * np.log10(symbol_rate(ps))
        fb = Transmitter(ps, 1, off, cipher=cipher).run(x)
        fb = through(fb, ess, fading_gains(len(fb), kind_sub, np.random.default_rng(seed + 200)), rng)
    y, st = receive(pm, fa, fb, len(x), off, profile_b=ps, cipher=cipher, **rx_kw)
    return y, st, {"esn0_main": esm, "esn0_sub": ess}
