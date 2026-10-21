"""
受信側ポストフィルタ: 半サンプルずらしの 3次補間 (シフテッドスプライン) + 量子化区間への射影。

Haar の係数は区間の平均値で、箱型のまま戻すと量子化誤差が振幅に応じた階段状の量子化歪みになる。各ブロックで
  1. 半サンプル 3次補間 (Keys, a=-0.5) で半サンプルずらし、ずらし戻す (対称な 7タップの平滑化)
  2. Haar で分解し直し、各係数を受信した量子化区間 [lo, hi] に収める
  3. 合成
を iters 回繰り返す (既定はプロファイルの pf_iters)。区間の外には出ないので、受信した情報と矛盾しない範囲で量子化歪みだけが滑らかになる。

参考 (考え方の出典):
  - T. Blu, P. Thévenaz, M. Unser, "Linear interpolation revitalized", IEEE Trans. Image Process., 2004
  - 量子化区間への射影を繰り返す復元 (POCS) は変換符号化のブロックノイズ除去などで用いられる手法

追加遅延なし版: 左側は確定済みの前ブロックの末尾 3サンプル、右側は現在の推定値の線形外挿で補う。
"""
import numpy as np

from .codec import haar_forward, haar_inverse
from .profiles import band_level

HALF_CUBIC = np.array([-1 / 16, 9 / 16, 9 / 16, -1 / 16])
KERNEL = np.convolve(HALF_CUBIC, HALF_CUBIC[::-1])        # 7タップ, 和 = 1
PAD = len(KERNEL) // 2


def _haar_matrix(block, levels):
    """ブロック内 Haar 分解の直交行列 (行 = 帯域 0→最高域の順に並べた係数)"""
    return np.concatenate(haar_forward(np.eye(block), levels), axis=-1).T


def _smooth_matrix(block):
    """[前の確定 PAD サンプル, 現ブロック, 右の線形外挿 PAD サンプル] → 平滑化した現ブロック"""
    n = block + 2 * PAD
    conv = np.zeros((block, n))
    for i in range(block):
        conv[i, i:i + len(KERNEL)] = KERNEL[::-1]
    # 右の外挿 y[-1] + (y[-1] - y[-2]) * t を現ブロックの線形結合で表す
    ext_y = np.zeros((n, block))
    ext_y[PAD:PAD + block] = np.eye(block)
    for t in range(1, PAD + 1):
        ext_y[PAD + block + t - 1, block - 1] = 1 + t
        ext_y[PAD + block + t - 1, block - 2] = -t
    ext_prev = np.zeros((n, PAD))
    ext_prev[:PAD] = np.eye(PAD)
    return conv @ ext_y, conv @ ext_prev


class PostFilter:
    def __init__(self, levels, iters=4, block=64):
        self.levels = levels
        self.iters = iters
        self.H = _haar_matrix(block, levels)
        A, B = _smooth_matrix(block)
        self.HA = self.H @ A                    # y → 平滑化して分解した係数
        self.HB = self.H @ B                    # 前の確定サンプル → 同上への寄与
        self.prev = {"M": np.zeros(PAD), "S": np.zeros(PAD)}

    def reset_history(self, ch, tail):
        self.prev[ch] = np.asarray(tail[-PAD:], float)

    def process(self, ch, coefs, cell):
        """
        coefs: 受信した帯域係数 [..], cell: 各帯域の (lo, hi) or None
        0bit の帯域 (送っていない帯域) は真の値が分からないので、区間を入力振幅の上限 ±2^(lev/2) まで開く
        (0 に固定すると真の信号が制約の集合に入らず、射影が階段を作り直す)。初期値は 0。
        返り値: 時間波形 (block,)
        """
        c = np.concatenate(coefs)
        lo, hi = [], []
        for k, (b, cl) in enumerate(zip(coefs, cell)):
            if cl is None:
                g = 2.0 ** (band_level(k, self.levels) / 2)
                lo.append(np.full(len(b), -g))
                hi.append(np.full(len(b), g))
            else:
                lo.append(cl[0])
                hi.append(cl[1])
        lo, hi = np.concatenate(lo), np.concatenate(hi)
        bias = self.HB @ self.prev[ch]
        y = self.H.T @ c
        for _ in range(self.iters):
            c = np.clip(self.HA @ y + bias, lo, hi)
            y = self.H.T @ c
        self.prev[ch] = y[-PAD:].copy()
        return y
