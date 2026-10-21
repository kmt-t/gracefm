"""
系統ごとの帯域カルマン (オプション)。

各系統のデコーダの中で、自分のブロックの格子のまま、Haar の帯域 k の係数列 (ブロックをまたいで続く) を
状態とし、軟判定で得た係数 (観測) と、持続モデルの予測を合わせる。

  観測   z      : 軟判定の仮数の期待値 × ステップ。分散 R は受信座標から分かっている (事後分散 + 量子化誤差)
  予測   x⁻     : 自分の過去の事後推定から AR(p) で 1つ先を予測 (AR 係数は事後推定の履歴から Yule-Walker)
  予測の分散 P  : イノベーション r = z - x⁻ について E[r²] = P + R なので、P = 平均(r²) - R を指数平滑で推定
  更新   x̂      = x⁻ + K r,  K = P / (P + R),  事後分散 P R / (P + R)

予測が当たらない帯域では P ≫ R となって K ≈ 1 (観測をほぼそのまま使う) になるので、全帯域にかけても、
効くのは予測が当たり、かつ観測が不確かな係数に限られる。R を音声から推定しないので、時定数の問題がない。
欠落したフレームでは予測だけで状態を進める (出力は PLC に任せる)。
"""
import numpy as np


def ar_fit(h, p):
    """x[n] ≈ Σ c_i x[n-i] の係数 (Yule-Walker / Levinson。帯域拡張つき)"""
    h = np.asarray(h, float)
    if len(h) < 4 * p or not np.any(h):
        return np.zeros(p)
    r = np.array([np.dot(h[: len(h) - i], h[i:]) for i in range(p + 1)])
    if r[0] <= 0:
        return np.zeros(p)
    r[0] *= 1.001
    a = np.zeros(p + 1)
    a[0] = 1.0
    err = r[0]
    for i in range(1, p + 1):
        acc = r[i] + np.dot(a[1:i], r[i - 1:0:-1])
        k = -acc / err
        a[1:i] = a[1:i] + k * a[i - 1:0:-1]
        a[i] = k
        err *= 1.0 - k * k
    return -a[1:] * 0.999 ** np.arange(1, p + 1)


class StreamBandKalman:
    def __init__(self, nbands, bands=None, order=2, hist=256, tau_blocks=16.0, gate=3.0):
        """
        bands     : カルマンをかける帯域の番号 (None なら全帯域)
        tau_blocks: 予測の分散 P の指数平滑の時定数 (ブロック数)
        """
        self.bands = set(range(nbands)) if bands is None else set(bands)
        self.order = order
        self.gate = gate
        self.hist = hist
        self.lam = float(np.exp(-1.0 / tau_blocks))
        self.h = {}
        self.a = {}
        self.P = {}

    def _key(self, ch, k):
        key = (ch, k)
        if key not in self.h:
            self.h[key] = np.zeros(0)
            self.a[key] = np.zeros(self.order)
            self.P[key] = None
        return key

    def update(self, ch, k, z, R, scale=1.0):
        """
        z: 帯域 k の観測 (係数の配列)、R: 観測の分散 (同じ形)、scale: このブロックのこの帯域の大きさの目安
        (指数から決まるステップ × qmax。指数は保護部で確実に届く)。返り値: (事後推定, 事後分散)

        予測の分散 P は「scale² に対する比」を平滑して持つ (P = pn · scale²)。大きいブロックほど
        予測の外れも観測の誤差も大きくなるので、比で持たないと音量の変わり目で P が遅れて予測を信じすぎる。
        イノベーションが r² > gate² (P + R) のときは予測が外れたとみなし観測をそのまま使う。
        """
        if k not in self.bands:
            return z, R
        key = self._key(ch, k)
        h, a = self.h[key], self.a[key]
        p = self.order
        s2 = float(scale) ** 2 if scale > 0 else 1.0
        pn = self.P[key]
        xs = np.empty(len(z))
        vs = np.empty(len(z))
        rr = []
        for j in range(len(z)):
            xp = float(np.dot(a, h[::-1][:p])) if len(h) >= p else 0.0
            r = z[j] - xp
            if pn is None:
                K = 1.0
            else:
                P = pn * s2
                K = P / (P + R[j]) if (P + R[j]) > 0 else 1.0
                if r * r > self.gate ** 2 * (P + R[j]):
                    K = 1.0
            xs[j] = xp + K * r
            vs[j] = K * R[j]                      # = P R / (P + R)
            rr.append((r * r - R[j]) / s2)
            h = np.append(h, xs[j])
        pe = max(float(np.mean(rr)), 0.0)
        pn = pe if pn is None else self.lam * pn + (1 - self.lam) * pe
        self.P[key] = max(pn, 1e-12)
        self.h[key] = h[-self.hist:]
        self.a[key] = ar_fit(self.h[key], p)
        return xs, vs

    def predict_only(self, ch, k, n):
        """欠落したフレーム: 予測だけで状態を進める"""
        if k not in self.bands:
            return
        key = self._key(ch, k)
        h, a = self.h[key], self.a[key]
        p = self.order
        for _ in range(n):
            xp = float(np.dot(a, h[::-1][:p])) if len(h) >= p else 0.0
            h = np.append(h, xp)
        self.h[key] = h[-self.hist:]
