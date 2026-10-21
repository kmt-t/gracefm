"""
送信のパルス成形 (評価用)。ルートレイズドコサイン (ロールオフ β = 0.25) で、シンボル列を複素ベースバンドの波形にする。
リファレンス実装の通信路モデル (gracefm.channel) はシンボル単位で、この波形は送信スペクトルの評価にだけ使う。
"""
import numpy as np
from scipy.signal import lfilter


def rrc_taps(beta=0.25, sps=8, span=16):
    """ルートレイズドコサインのタップ (エネルギー 1 に正規化)。span はシンボル数"""
    t = np.arange(-span * sps / 2, span * sps / 2 + 1) / sps
    h = np.empty_like(t)
    for i, ti in enumerate(t):
        if abs(ti) < 1e-12:
            h[i] = 1 - beta + 4 * beta / np.pi
        elif abs(abs(ti) - 1 / (4 * beta)) < 1e-9:
            h[i] = beta / np.sqrt(2) * ((1 + 2 / np.pi) * np.sin(np.pi / (4 * beta))
                                        + (1 - 2 / np.pi) * np.cos(np.pi / (4 * beta)))
        else:
            h[i] = (np.sin(np.pi * ti * (1 - beta)) + 4 * beta * ti * np.cos(np.pi * ti * (1 + beta))) / (
                np.pi * ti * (1 - (4 * beta * ti) ** 2))
    return h / np.sqrt(np.sum(h ** 2))


def shape(symbols, beta=0.25, sps=8, span=16):
    """シンボル列 → 複素ベースバンド波形 (サンプリング周波数 = sps × シンボルレート)"""
    up = np.zeros(len(symbols) * sps, complex)
    up[::sps] = symbols
    return lfilter(rrc_taps(beta, sps, span), 1.0, up)
