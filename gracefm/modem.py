"""
変調と通信路モデル。

QPSK (基本): 1シンボル = 2bit。ビット列を (I, Q, I, Q, ...) の順に各軸へ。bit0 → +, bit1 → −。
階層 QAM (オプション): 各軸の点 = ±(α, α+2, ...), α=1 で通常の QAM。
  16QAM: 1軸 = 符号 (HP) 1bit + 位置 (LP1) 1bit
  64QAM: 1軸 = 符号 (HP) 1bit + 位置 (LP1, LP2) 2bit (グレイ符号)
  ビット列は「全シンボルの HP 位置 → 全シンボルの LP1 位置 → LP2 位置」の順に埋める
  (送信順の前方ほど強い位置に入る。保護部の符号化ビットは必ず HP 位置に収まる長さにする)。
平均シンボルエネルギーは 1。フレーム先頭に既知のプリアンブル (QPSK 16シンボル) を付ける。
プリアンブル以外のビット (端数の詰め物を含む) は、フレームごとに先頭から始める PRBS と排他的論理和をとって
送る (スクランブル。送信スペクトルに線スペクトルが立たないようにする)。
"""
import numpy as np

PREAMBLE = np.array([1, 1, 1, -1, -1, 1, 1, -1, 1, -1, -1, -1, 1, 1, -1, 1], float)
PREAMBLE = (PREAMBLE + 1j * np.roll(PREAMBLE, 5)) / np.sqrt(2)

HALF_AXIS_POINTS = {"qpsk": 1, "qam16h": 2, "qam64h": 4}

_PRBS_CACHE = np.zeros(0, np.int64)


def prbs(n):
    """スクランブル系列: 1 + x^14 + x^15 (DVB と同じ)、初期値 100101010000000。フレームごとに先頭から使う"""
    global _PRBS_CACHE
    if len(_PRBS_CACHE) < n:
        reg = [1, 0, 0, 1, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0]
        out = np.empty(max(n, 4096), np.int64)
        for i in range(len(out)):
            b = reg[13] ^ reg[14]
            out[i] = b
            reg = [b] + reg[:14]
        _PRBS_CACHE = out
    return _PRBS_CACHE[:n]


def bits_per_symbol(mod):
    L = HALF_AXIS_POINTS[mod]
    return 2 * (1 + int(np.log2(L)))


def n_symbols(n_tx, n_coded, mod):
    bps = bits_per_symbol(mod)
    return int(max(np.ceil(n_tx / bps), np.ceil(n_coded / 2)))


def _axis_pos(L, alpha):
    pos = alpha + 2 * np.arange(L, dtype=float)
    return pos / np.sqrt(np.mean(pos ** 2) * 2)


def modulate(bits, nsym, mod="qpsk", alpha=1.0):
    L = HALF_AXIS_POINTS[mod]
    nlp = int(np.log2(L)) if L > 1 else 0
    nslot = 2 * nsym
    buf = np.zeros(nslot * (1 + nlp), np.int64)
    buf[: len(bits)] = bits
    hp = buf[:nslot]
    code = np.zeros(nslot, np.int64)
    for j in range(nlp):
        code = (code << 1) | buf[nslot * (1 + j): nslot * (2 + j)]
    g2i = np.zeros(max(L, 1), np.int64)
    for i in range(L):
        g2i[i ^ (i >> 1)] = i
    v = np.where(hp == 1, -1.0, 1.0) * _axis_pos(L, alpha if L > 1 else 1.0)[g2i[code]]
    return np.concatenate([PREAMBLE, v[0::2] + 1j * v[1::2]])


def demodulate(sym, n_bits, mod="qpsk", alpha=1.0):
    """返り値: (軟値 [HP 位置のみ, 送信順], 硬判定ビット [全位置, 送信順])"""
    L = HALF_AXIS_POINTS[mod]
    nlp = int(np.log2(L)) if L > 1 else 0
    s = sym[len(PREAMBLE):]
    nslot = 2 * len(s)
    v = np.empty(nslot)
    v[0::2] = s.real
    v[1::2] = s.imag
    hard = np.zeros(nslot * (1 + nlp), np.int64)
    hard[:nslot] = v < 0
    if nlp:
        pos = _axis_pos(L, alpha)
        idx = np.abs(np.abs(v)[:, None] - pos).argmin(axis=1)
        g = idx ^ (idx >> 1)
        for j in range(nlp):
            hard[nslot * (1 + j): nslot * (2 + j)] = (g >> (nlp - 1 - j)) & 1
    return v, hard[:n_bits]


def _axis_points(mod, alpha):
    """1軸の信号点の値と、そのビットのラベル (象限ビット, 位置ビット1, 2, ...)"""
    L = HALF_AXIS_POINTS[mod]
    nlp = int(np.log2(L)) if L > 1 else 0
    pos = _axis_pos(L, alpha if L > 1 else 1.0)
    vals, labels = [], []
    for hp in (0, 1):
        for idx in range(L):
            g = idx ^ (idx >> 1)
            vals.append((1 - 2 * hp) * pos[idx])
            labels.append([hp] + [(g >> (nlp - 1 - j)) & 1 for j in range(nlp)])
    return np.array(vals), np.array(labels), nlp


def bit_probs(sym, n_bits, mod="qpsk", alpha=1.0):
    """
    各ビットが 1 である事後確率 (送信順) と、保護部のビタビに渡す対数尤度比 (正 = 0 らしい)。

    受信点を複素平面 (I, Q) の 2次元で扱い、雑音を 2変量正規分布 N(0, Σ) とする。Σ (2×2) はフレームごとに、
    各受信点と最寄りの信号点の差から推定する (I と Q の雑音の大きさの違いや相関も含む)。
    各シンボルについて全信号点の尤度 exp(-½ dᵀ Σ⁻¹ d) を求め、ビットごとに「そのビットが 1 の点」の
    尤度の和の割合を事後確率とする (信号点は等確率と仮定)。
    """
    s = sym[len(PREAMBLE):]
    y = np.stack([s.real, s.imag], axis=1)
    v, lab, nlp = _axis_points(mod, alpha)
    # 最寄りの信号点 (軸ごと) との差から共分散を推定
    near = np.stack([v[np.abs(y[:, a][:, None] - v[None, :]).argmin(1)] for a in (0, 1)], axis=1)
    r = y - near
    cov = r.T @ r / len(r) + np.eye(2) * 1e-6
    ic = np.linalg.inv(cov)
    P = np.array([(vi, vq) for vi in v for vq in v])                     # 2次元の信号点
    LI = np.repeat(lab, len(v), axis=0)                                  # I 軸のラベル
    LQ = np.tile(lab, (len(v), 1))                                       # Q 軸のラベル
    d = y[:, None, :] - P[None, :, :]
    ll = -0.5 * np.einsum("nmi,ij,nmj->nm", d, ic, d)
    ll -= ll.max(axis=1, keepdims=True)
    w = np.exp(ll)
    tot = w.sum(axis=1)
    nsym = len(s)
    nslot = 2 * nsym
    p1 = np.zeros(nslot * (1 + nlp))
    for level in range(1 + nlp):
        for axis, Lab in ((0, LI), (1, LQ)):
            pr = (w * (Lab[:, level] == 1)[None, :]).sum(axis=1) / tot
            p1[nslot * level + axis: nslot * (level + 1): 2] = pr
    p1 = np.clip(p1[:n_bits], 1e-12, 1 - 1e-12)
    llr = np.log((1 - p1) / p1)
    return p1, llr


def awgn(sym, snr_db, rng):
    """Es/N0 = snr_db の複素白色雑音"""
    n0 = 10 ** (-snr_db / 10)
    return sym + (rng.normal(0, np.sqrt(n0 / 2), sym.shape)
                  + 1j * rng.normal(0, np.sqrt(n0 / 2), sym.shape))


def hybrid_scale(amplitude, lower_bits=4):
    """全点の平均シンボルエネルギーを1にする半径の倍率。"""
    levels = 1 << lower_bits
    radii = 1 + amplitude * (np.arange(levels) - (levels - 1) / 2)
    return float(np.sqrt(np.mean(radii ** 2)))


def hybrid_modulate(u, amplitude=0.08, scramble=None, lower_bits=4):
    """上位2bit+半径方向の仮数を1係数/複素シンボルにする。"""
    u = np.asarray(u, np.int64)
    levels = 1 << lower_bits
    if np.any((u < 0) | (u >= 4 * levels)):
        raise ValueError("ハイブリッド仮数が範囲外です")
    H, L = u // levels, u % levels
    if scramble is not None:
        mask = np.asarray(scramble, np.int64).reshape(-1, 3)
        if len(mask) != len(u):
            raise ValueError("スクランブル長が係数数と一致しません")
        H = H ^ (2 * mask[:, 0] + mask[:, 1])
        L = np.where(mask[:, 2] != 0, levels - 1 - L, L)
    theta = np.pi / 4 + H * np.pi / 2
    radius = (1 + amplitude * (L - (levels - 1) / 2)) / hybrid_scale(amplitude, lower_bits)
    return radius * np.exp(1j * theta)


def hybrid_demodulate(symbols, protected_top, amplitude=0.08, scramble=None,
                      preamble=None, lower_bits=4, phase_only=False,
                      protected_second=None):
    """FECで確定した位相bitを拘束に使い、仮数の連続推定値と分散を返す。"""
    y = np.asarray(symbols, complex)
    top = np.asarray(protected_top, np.int64)
    if len(y) != len(top):
        raise ValueError("高域シンボル数が一致しません")
    mask = np.zeros((len(y), 3), np.int64) if scramble is None else np.asarray(scramble, np.int64).reshape(-1, 3)
    if len(mask) != len(y):
        raise ValueError("スクランブル長が係数数と一致しません")
    levels = 1 << lower_bits
    center = (levels - 1) / 2
    if protected_second is None:
        h = 2 * top[:, None] + np.array([0, 1])[None, :]
    else:
        second = np.asarray(protected_second, np.int64)
        if second.shape != top.shape or np.any((second < 0) | (second > 1)):
            raise ValueError("FEC保護済み位相第2bitの数または値が不正です")
        h = (2 * top + second)[:, None]
    sent_h = h ^ (2 * mask[:, :1] + mask[:, 1:2])
    unit = np.exp(1j * (np.pi / 4 + sent_h * np.pi / 2))
    rotated = y[:, None] * np.conj(unit)
    proj = rotated.real
    tangent = rotated.imag
    scale = hybrid_scale(amplitude, lower_bits)
    rmin, rmax = (1 - center * amplitude) / scale, (1 + center * amplitude) / scale
    nearest = np.clip(proj, rmin, rmax)
    err2 = (proj - nearest) ** 2 + tangent ** 2
    best = np.argmin(err2, axis=1)
    # 既知プリアンブルと位相方向の残差を使い、複素雑音の1軸分散を推定する。
    pilot_var = 0.0 if preamble is None else float(np.mean(np.abs(np.asarray(preamble) - PREAMBLE) ** 2) / 2)
    tangent_var = float(np.median(tangent[np.arange(len(y)), best] ** 2)) / 0.455 if len(y) else 0.0
    sigma2 = max(1e-10, (pilot_var + tangent_var) / 2)
    weights = np.exp(-np.clip((err2 - np.min(err2, axis=1, keepdims=True)) / (2 * sigma2), 0, 700))
    weights /= weights.sum(axis=1, keepdims=True)
    obs_l = (proj * scale - 1) / amplitude + center
    obs_l = np.where(mask[:, 2:3] != 0, levels - 1 - obs_l, obs_l)
    noise_l = sigma2 * scale ** 2 / amplitude ** 2
    prior_var = (levels ** 2 - 1) / 12
    gain = 0.0 if phase_only else prior_var / (prior_var + noise_l)
    l_est = np.clip(center + gain * (obs_l - center), 0, levels - 1)
    candidates = levels * h + l_est
    mean = np.sum(weights * candidates, axis=1)
    var = np.sum(weights * ((candidates - mean[:, None]) ** 2 + gain * noise_l), axis=1)
    return np.clip(mean, 0, 4 * levels - 1), var, sigma2
