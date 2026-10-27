"""
変調と通信路モデル。

QPSK (基本): 1シンボル = 2bit。ビット列を (I, Q, I, Q, ...) の順に各軸へ。bit0 → +, bit1 → −。
階層 QAM (オプション): 各軸の点 = ±(α, α+2, ...), α=1 で通常の QAM。
  16QAM: 1軸 = 符号 (HP) 1bit + 位置 (LP1) 1bit
  ビット列は「全シンボルの HP 位置 → 全シンボルの LP1 位置 → LP2 位置」の順に埋める
  (送信順の前方ほど強い位置に入る。保護部の符号化ビットは必ず HP 位置に収まる長さにする)。
平均シンボルエネルギーは 1。フレーム先頭に既知のプリアンブル (QPSK 16シンボル) を付ける。
プリアンブル以外のビット (端数の詰め物を含む) は、フレームごとに先頭から始める PRBS と排他的論理和をとって
送る (スクランブル。送信スペクトルに線スペクトルが立たないようにする)。
"""
import numpy as np

PREAMBLE = np.array([1, 1, 1, -1, -1, 1, 1, -1, 1, -1, -1, -1, 1, 1, -1, 1], float)
PREAMBLE = (PREAMBLE + 1j * np.roll(PREAMBLE, 5)) / np.sqrt(2)

HALF_AXIS_POINTS = {"qpsk": 1, "qam16h": 2}

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


def hybrid_scale(amplitude, lower_bits=6):
    """全点の平均シンボルエネルギーを1にする半径の倍率。"""
    levels = 1 << lower_bits
    radii = 1 + amplitude * (np.arange(levels) - (levels - 1) / 2)
    return float(np.sqrt(np.mean(radii ** 2)))


# Y方式 (QASK): 1係数 = 1複素シンボル。位相の2bitは (仮数の最上位bit, そのパリティ)、半径が残りの仮数 (lower_bits)。
# 位相は象限を (パリティ → I軸の符号, 最上位bit → Q軸の符号) に割り当てるので、1bitの誤りは隣の象限に当たる。
_QUADRANT = np.array([0, 1, 3, 2])          # 2*最上位bit + パリティ → 象限番号 (位相 = π/4 + 象限·π/2)
_QUADRANT_BITS = np.argsort(_QUADRANT)      # 象限番号 → 2*最上位bit + パリティ


def hybrid_modulate(u, parity, amplitude=0.08, scramble=None, lower_bits=6):
    """u = 最上位bit·2^lower_bits + 半径の段 (0〜2^(lower_bits+1)-1)、parity = 最上位bitのパリティ (0/1)。"""
    u = np.asarray(u, np.int64)
    parity = np.asarray(parity, np.int64)
    levels = 1 << lower_bits
    if np.any((u < 0) | (u >= 2 * levels)) or np.any((parity < 0) | (parity > 1)):
        raise ValueError("ハイブリッド仮数またはパリティが範囲外です")
    msb, L = u // levels, u % levels
    if scramble is not None:
        mask = np.asarray(scramble, np.int64).reshape(-1, 3)
        if len(mask) != len(u):
            raise ValueError("スクランブル長が係数数と一致しません")
        msb = msb ^ mask[:, 0]
        parity = parity ^ mask[:, 1]
        L = np.where(mask[:, 2] != 0, levels - 1 - L, L)
    theta = np.pi / 4 + _QUADRANT[2 * msb + parity] * np.pi / 2
    radius = (1 + amplitude * (L - (levels - 1) / 2)) / hybrid_scale(amplitude, lower_bits)
    return radius * np.exp(1j * theta)


def _hybrid_candidates(y, amplitude, lower_bits):
    """4つの象限それぞれを仮定したときの (射影した半径, 接線方向の誤差, 二乗誤差)。"""
    levels = 1 << lower_bits
    center = (levels - 1) / 2
    scale = hybrid_scale(amplitude, lower_bits)
    rmin, rmax = (1 - center * amplitude) / scale, (1 + center * amplitude) / scale
    unit = np.exp(1j * (np.pi / 4 + np.arange(4) * np.pi / 2))
    rotated = y[:, None] * np.conj(unit)[None, :]
    proj, tangent = rotated.real, rotated.imag
    err2 = (proj - np.clip(proj, rmin, rmax)) ** 2 + tangent ** 2
    return proj, tangent, err2, scale, center


def _hybrid_sigma2(y, tangent, err2, preamble):
    """既知プリアンブルと、最良の象限での接線方向の残差から、複素雑音の1軸分散を推定する。"""
    best = np.argmin(err2, axis=1)
    pilot_var = 0.0 if preamble is None else float(np.mean(np.abs(np.asarray(preamble) - PREAMBLE) ** 2) / 2)
    tangent_var = float(np.median(tangent[np.arange(len(y)), best] ** 2)) / 0.455 if len(y) else 0.0
    return max(1e-10, (pilot_var + tangent_var) / 2)


def hybrid_phase_llr(symbols, amplitude=0.08, scramble=None, preamble=None, lower_bits=6):
    """専用シンボルの位相だけから、最上位bitとパリティの対数尤度比 (正 = 0 らしい) と1軸の雑音分散を返す。"""
    y = np.asarray(symbols, complex)
    mask = np.zeros((len(y), 3), np.int64) if scramble is None else np.asarray(scramble, np.int64).reshape(-1, 3)
    if len(mask) != len(y):
        raise ValueError("スクランブル長が係数数と一致しません")
    _, tangent, err2, _, _ = _hybrid_candidates(y, amplitude, lower_bits)
    sigma2 = _hybrid_sigma2(y, tangent, err2, preamble)
    w = np.exp(-np.clip((err2 - err2.min(axis=1, keepdims=True)) / (2 * sigma2), 0, 700))
    w /= w.sum(axis=1, keepdims=True)
    sent = _QUADRANT_BITS[None, :]                       # (1, 4): 各象限で送られた 2*msb+parity
    msb_true = (sent >> 1) ^ mask[:, :1]
    par_true = (sent & 1) ^ mask[:, 1:2]
    p_msb = np.clip((w * msb_true).sum(axis=1), 1e-9, 1 - 1e-9)
    p_par = np.clip((w * par_true).sum(axis=1), 1e-9, 1 - 1e-9)
    return np.log((1 - p_msb) / p_msb), np.log((1 - p_par) / p_par), sigma2


def hybrid_demodulate(symbols, msb, parity, amplitude=0.08, scramble=None,
                      preamble=None, lower_bits=6, phase_only=False):
    """
    最上位bitとパリティ (ヘッダ部のFECで確定した値) を使って象限を決め、半径の連続推定値と分散を返す。
    返り値: (u = 最上位bit·2^lower_bits + 半径の段の推定値, 半径の段の分散, 1軸の雑音分散)
    """
    y = np.asarray(symbols, complex)
    msb = np.asarray(msb, np.int64)
    parity = np.asarray(parity, np.int64)
    if len(y) != len(msb) or len(y) != len(parity):
        raise ValueError("高域シンボル数が一致しません")
    mask = np.zeros((len(y), 3), np.int64) if scramble is None else np.asarray(scramble, np.int64).reshape(-1, 3)
    if len(mask) != len(y):
        raise ValueError("スクランブル長が係数数と一致しません")
    proj, tangent, err2, scale, center = _hybrid_candidates(y, amplitude, lower_bits)
    levels = 1 << lower_bits
    quadrant = _QUADRANT[2 * (msb ^ mask[:, 0]) + (parity ^ mask[:, 1])]
    rows = np.arange(len(y))
    sigma2 = _hybrid_sigma2(y, tangent, err2, preamble)
    obs_l = (proj[rows, quadrant] * scale - 1) / amplitude + center
    obs_l = np.where(mask[:, 2] != 0, levels - 1 - obs_l, obs_l)
    noise_l = sigma2 * scale ** 2 / amplitude ** 2
    prior_var = (levels ** 2 - 1) / 12
    gain = 0.0 if phase_only else prior_var / (prior_var + noise_l)
    l_est = np.clip(center + gain * (obs_l - center), 0, levels - 1)
    return msb * levels + l_est, np.full(len(y), gain * noise_l), sigma2


def hybrid_slice(values, amplitude=0.08, lower_bits=6):
    """受信点を最も近いY方式の信号点 (象限・半径の段) に判定する。スクランブルの影響を受けない。"""
    y = np.asarray(values, complex)
    levels = 1 << lower_bits
    center = (levels - 1) / 2
    scale = hybrid_scale(amplitude, lower_bits)
    quadrant = np.mod(np.rint((np.angle(y) - np.pi / 4) / (np.pi / 2)).astype(np.int64), 4)
    radial = np.clip(np.rint((np.abs(y) * scale - 1) / amplitude + center), 0, levels - 1)
    radius = (1 + amplitude * (radial - center)) / scale
    return radius * np.exp(1j * (np.pi / 4 + quadrant * np.pi / 2))
