"""
訓練つきの MMSE 等化器 (静的な通信路)。すべて整数演算。シンボルは (n, 2) の整数 (Q FRAC)、複素数は (実部, 虚部) の組。

通信路は、フレーム先頭の既知のシンボル (プリアンブルとヘッダの位相部) を使った最小二乗法で推定する (過去のフレームだけ)。
正規方程式 (XᴴX + 正則化) h = Xᴴ y は gracefm.linalg の整数コレスキー分解で解く。等化器の重みも、通信路のタップから
(HᴴH + σ²I) w = Hᴴ d を同じソルバで解いて作り、先読み量 (0〜max_lookahead) は予測誤差が最小のものを選ぶ。
FIR は重みを DSP の乗算器の幅に収まる Q14 の整数にして畳み込む (gracefm.dsp)。判定指向の再推定を passes 回行う。
通信路のモデル (RRC の応答、エコー、雑音) は評価の道具 tools/sim/multipath.py にある。
"""
import numpy as np

from . import fec, modem
from .dsp import saturate
from .layout import Layout, int_bits
from .linalg import FRAC as W_FRAC, hermitian_solve
from .profiles import Profile

CORR_SHIFT = modem.SYM_FRAC - 10     # 相関を取る前にシンボルを Q10 に縮める
FIR_FRAC = 14                       # FIR の重みの小数bit数 (18 bit符号つきに収まる)


def header_training_symbols(profile: Profile, stream_id: int, frame_no: int, encrypted=False):
    """プリアンブルと、ヘッダの位相部の期待値 (QAM の符号が既知の分だけ) → (n, 2) の整数。
    フレーム番号が追跡できていれば、ヘッダは訓練に使える。QAM の位置ビットは仮数なので、軸の大きさは等確率の平均で置き換える。"""
    width = Layout(profile, encrypted=encrypted).header_bits
    tag = int_bits(profile.format_id, 2)
    header = (int_bits(profile.pid, 4) + int_bits(stream_id, 1) + [int(encrypted)] + tag
              + int_bits(frame_no & ((1 << (width - 8)) - 1), width - 8))
    # ヘッダのパリティは因果的 (t 番目のパリティは先頭 t+1 bit だけで決まる) なので、先頭のヘッダ bit 数ぶんの
    # パリティ = 先頭の width/2 シンボルの象限 (位相部) は、既知のヘッダだけから分かる。
    parity = fec.rsc_parity(np.asarray(header, np.int64))[0][:width]
    hp = parity ^ modem.prbs(len(parity))
    mags = modem.axis_points(profile.modulation, profile.alpha)[3]
    amplitude = sum(mags) // len(mags)
    axis = (1 - 2 * hp) * amplitude
    return np.concatenate([modem.PREAMBLE, np.stack([axis[0::2], axis[1::2]], axis=1)])


def _normal_equations(X, y):
    """X (rows, n, 2)、y (rows, 2) (Q10) → A = XᴴX の (実部, 虚部)、b = Xᴴ y の (実部, 虚部) (Q20)"""
    xr, xi, yr, yi = X[..., 0], X[..., 1], y[:, 0], y[:, 1]
    Ar = xr.T @ xr + xi.T @ xi
    Ai = xr.T @ xi - xi.T @ xr
    br = xr.T @ yr + xi.T @ yi
    bi = xr.T @ yi - xi.T @ yr
    return Ar, Ai, br, bi


def _solve_taps(X, y):
    """最小二乗の通信路タップ (n, 2) (Q W_FRAC) と、残差の電力 (Q20)"""
    Ar, Ai, br, bi = _normal_equations(X, y)
    top = int(max(Ar[i, i] for i in range(len(br))))
    hr, hi = hermitian_solve(Ar.tolist(), Ai.tolist(), br.tolist(), bi.tolist(), ridge=top >> 24)
    taps = np.stack([np.array(hr, np.int64), np.array(hi, np.int64)], axis=1)
    xr, xi = X[..., 0], X[..., 1]
    pr = xr @ taps[:, 0] - xi @ taps[:, 1]
    pim = xr @ taps[:, 1] + xi @ taps[:, 0]
    rr = (y[:, 0] << W_FRAC) - pr
    ri = (y[:, 1] << W_FRAC) - pim
    rr, ri = rr >> 20, ri >> 20                                  # 残差 (Q10 + Q24 = Q34) を Q14 に
    noise = int((rr ** 2 + ri ** 2).sum() // len(y)) >> 8        # Q28 → Q20
    return taps, noise


def _q10(sym):
    return np.asarray(sym, np.int64) >> CORR_SHIFT


def _training_matrix(received, profile, stream_id, frame_numbers, lag_min, lag_max, encrypted):
    frame_len = len(received[0])
    rows, targets = [], []
    lags = np.arange(lag_min, lag_max + 1)
    for frame_no in frame_numbers:
        pilot = header_training_symbols(profile, stream_id, int(frame_no), encrypted)
        if len(pilot) > frame_len:
            raise ValueError("header exceeds frame length")
        for j in range(lag_max, len(pilot) + lag_min):
            rows.append(pilot[j - lags])
            targets.append(received[frame_no][j])
    return _q10(np.asarray(rows)), _q10(np.asarray(targets))


def estimate_channel(received, profile: Profile, stream_id=0, training_frames=100,
                     lag_min=-4, lag_max=10, encrypted=False):
    """過去の training_frames フレームの既知シンボルだけから通信路を推定する (ペイロードは使わない)。
    返り値: (ラグ, タップ (n, 2) Q24, 残差の電力 Q20)"""
    count = min(training_frames, len(received))
    if count < 1:
        raise ValueError("at least one training frame is required")
    X, y = _training_matrix(received, profile, stream_id, range(count), lag_min, lag_max, encrypted)
    if len(X) < X.shape[1]:
        raise ValueError("header training does not span the requested channel taps")
    taps, noise = _solve_taps(X, y)
    return np.arange(lag_min, lag_max + 1), taps, noise


def design_mmse_equalizer(lags, taps, noise_power, ntaps=11, max_lookahead=4):
    """単位ゲインの FIR。因果的な先読み量は予測誤差で選ぶ。返り値: (先読み, 重み (ntaps, 2) Q24, 予測誤差 Q24)"""
    if ntaps < 1 or max_lookahead >= ntaps or noise_power < 0:
        raise ValueError("invalid equalizer size or noise power")
    best = None
    lo, hi = int(lags[0]), int(lags[-1])
    noise_q24 = max(noise_power << 4, 1)
    for lead in range(max_lookahead + 1):
        q = np.arange(-lead, ntaps - lead)
        eff = np.arange(lo + q[0], hi + q[-1] + 1)
        H = np.zeros((len(eff), ntaps, 2), np.int64)
        for j, shift in enumerate(q):
            src = eff - shift
            valid = (src >= lo) & (src <= hi)
            H[valid, j] = taps[src[valid] - lo]
        zero = int(np.flatnonzero(eff == 0)[0])
        hr, hi_ = H[..., 0], H[..., 1]
        Ar = (hr.T @ hr + hi_.T @ hi_) >> W_FRAC
        Ai = (hr.T @ hi_ - hi_.T @ hr) >> W_FRAC
        br, bi = hr[zero].copy(), -hi_[zero]                        # Hᴴ d  (d は 0 ラグだけ 1)
        wr, wi = hermitian_solve(Ar.tolist(), Ai.tolist(), br.tolist(), bi.tolist(), ridge=noise_q24)
        w = np.stack([np.array(wr, np.int64), np.array(wi, np.int64)], axis=1)
        gr = int((hr[zero] * w[:, 0] - hi_[zero] * w[:, 1]).sum() >> W_FRAC)
        gi = int((hr[zero] * w[:, 1] + hi_[zero] * w[:, 0]).sum() >> W_FRAC)
        mag2 = (gr * gr + gi * gi) >> W_FRAC
        if mag2 < (1 << W_FRAC) >> 16:
            continue
        nr = (w[:, 0] * gr + w[:, 1] * gi) >> W_FRAC                # w · conj(g)
        ni = (w[:, 1] * gr - w[:, 0] * gi) >> W_FRAC
        w = np.stack([(nr << W_FRAC) // mag2, (ni << W_FRAC) // mag2], axis=1)
        rr = ((hr @ w[:, 0] - hi_ @ w[:, 1]) >> W_FRAC)
        ri = ((hr @ w[:, 1] + hi_ @ w[:, 0]) >> W_FRAC)
        rr[zero] -= 1 << W_FRAC
        err = int(((rr >> 8) ** 2 + (ri >> 8) ** 2).sum())                         # Q32
        mse = err + int((noise_q24 * ((w[:, 0] >> 8) ** 2 + (w[:, 1] >> 8) ** 2).sum()) >> W_FRAC)
        if best is None or mse < best[0]:
            best = mse, lead, w
    if best is None:
        raise ValueError("no usable equalizer")
    return best[1], best[2], best[0]


def apply_equalizer(received, lead, weights):
    """received (..., n, 2) を一列にして FIR を掛け、同じ形で返す。重みは Q14 に縮めて畳み込む"""
    arr = np.asarray(received, np.int64)
    flat = arr.reshape(-1, 2)
    w = (np.asarray(weights, np.int64) + (1 << (W_FRAC - FIR_FRAC - 1))) >> (W_FRAC - FIR_FRAC)
    xr, xi = flat[:, 0], flat[:, 1]
    re = np.convolve(xr, w[:, 0]) - np.convolve(xi, w[:, 1])
    im = np.convolve(xr, w[:, 1]) + np.convolve(xi, w[:, 0])
    out = np.stack([re[lead:lead + len(flat)], im[lead:lead + len(flat)]], axis=1)
    out = (out + (1 << (FIR_FRAC - 1))) >> FIR_FRAC
    return saturate(out).reshape(arr.shape)


def _slice_constellation(values, profile: Profile):
    """受信点 (n, 2) → 最も近い信号点 (n, 2)"""
    vals = modem.axis_points(profile.modulation, profile.alpha)[0]
    values = np.asarray(values, np.int64)
    result = vals[np.abs(values[..., None] - vals[None, None, :]).argmin(axis=-1)]
    if profile.has_y:
        lay = Layout(profile)
        digital = modem.n_symbols(lay.n_tx, lay.n_strong, profile.modulation)
        frame_len = modem.N_PREAMBLE + digital + lay.n_y
        if len(result) % frame_len:
            raise ValueError("等化器の入力がフレーム長の整数倍ではありません")
        src = values.reshape(-1, frame_len, 2)
        dst = result.reshape(-1, frame_len, 2)
        high = src[:, modem.N_PREAMBLE + digital:].reshape(-1, 2)
        quadrant, level = modem.y_slice(high, profile.y_step, profile.y_bits - 1)
        dst[:, modem.N_PREAMBLE + digital:] = modem.y_points(quadrant, level, profile.y_step, profile.y_bits - 1).reshape(-1, lay.n_y, 2)
    return result


def refine_channel_decisions(received, profile: Profile, lags, taps, noise_power,
                             training_frames=100, ntaps=11, max_lookahead=4, passes=2):
    """較正用のフレームの判定結果を使って静的な通信路を精密化する"""
    count = min(training_frames, len(received))
    flat = np.asarray(received[:count]).reshape(-1, 2)
    frame_len = len(received[0])
    lag_min, lag_max = int(lags[0]), int(lags[-1])
    fitted = np.asarray(taps)
    for _ in range(passes):
        lead, w, _ = design_mmse_equalizer(lags, fitted, noise_power, ntaps, max_lookahead)
        decisions = _slice_constellation(apply_equalizer(flat, lead, w), profile).reshape(count, frame_len, 2)
        decisions[:, :modem.N_PREAMBLE] = modem.PREAMBLE
        rows, target = [], []
        for f in range(count):
            for j in range(lag_max, frame_len + lag_min):
                rows.append(decisions[f, j - lags])
                target.append(received[f][j])
        fitted, noise_power = _solve_taps(_q10(np.asarray(rows)), _q10(np.asarray(target)))
    return fitted, noise_power


def equalize_static(received, profile: Profile, stream_id=0, training_frames=100,
                    ntaps=11, max_lookahead=4, decision_passes=2, encrypted=False):
    """過去のフレームで較正し、等化後のシンボルと診断を返す。評価は training_frames より後のフレームで行うこと。"""
    lags, taps, noise = estimate_channel(received, profile, stream_id, training_frames, encrypted=encrypted)
    if decision_passes:
        taps, noise = refine_channel_decisions(received, profile, lags, taps, noise,
                                               training_frames, ntaps, max_lookahead, decision_passes)
    lead, weights, predicted_mse = design_mmse_equalizer(lags, taps, noise, ntaps, max_lookahead)
    output = apply_equalizer(received, lead, weights)
    return output, dict(training_frames=min(training_frames, len(received)), lookahead_symbols=lead,
                        residual_power=noise, predicted_mse=predicted_mse,
                        channel_lags=lags.tolist(), channel_taps=taps.tolist())
