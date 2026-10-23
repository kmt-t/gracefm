"""Static multipath at the RRC matched-filter output and a trained MMSE equalizer.

The channel impulse response is obtained from the transmit/receive RRC pair at
eight samples per symbol, then sampled at symbol times. Convolution with this
response is equivalent to pulse shaping, a static linear channel, matched
filtering and ideal timing recovery. Noise is added at the matched-filter
output with the requested Es/N0. Carrier and timing acquisition are outside
this model.
"""
from __future__ import annotations

import numpy as np
from scipy.interpolate import CubicSpline
from scipy.signal import fftconvolve

from . import fec, modem
from .framing import HybridLayout, Layout, _bits
from .profiles import Profile
from .pulse import rrc_taps


def matched_channel_taps(profile: Profile, paths=(), rf_offset_hz=0.0, sps=8):
    """Return (lags, taps) for a unit direct path and (delay_s, dB, phase) echoes.

    The phase of an echo at another carrier is phase - 2*pi*rf_offset_hz*delay_s.
    C/N0 is referenced to the direct path, so no received-power normalization
    is performed after adding echoes.
    """
    from .channel import symbol_rate

    paths = tuple(paths)
    rs = symbol_rate(profile)
    root = rrc_taps(profile.pulse_beta, sps, profile.pulse_span)
    pulse = np.convolve(root, root[::-1])
    t = (np.arange(len(pulse)) - (len(pulse) - 1) / 2) / sps
    interp = CubicSpline(t, pulse, extrapolate=False)
    max_delay = max((delay * rs for delay, _, _ in paths), default=0.0)
    lags = np.arange(-profile.pulse_span, profile.pulse_span + int(np.ceil(max_delay)) + 1)

    def sample(at):
        out = interp(at)
        return np.where(np.isfinite(out), out, 0.0)

    taps = sample(lags).astype(complex)
    for delay, rel_db, phase in paths:
        if delay < 0:
            raise ValueError("echo delay must be nonnegative")
        gain = 10 ** (rel_db / 20) * np.exp(1j * (phase - 2 * np.pi * rf_offset_hz * delay))
        taps += gain * sample(lags - delay * rs)
    return lags, taps


def through_matched_channel(frames, profile: Profile, esn0_db, paths=(),
                            rf_offset_hz=0.0, seed=1):
    """Transmit continuous frames through static RRC multipath and AWGN.

    Returns received frames and the noiseless symbol-spaced channel. A fixed
    seed makes comparisons between equalized and unequalized reception paired.
    """
    symbols = np.concatenate(frames)
    lags, taps = matched_channel_taps(profile, paths, rf_offset_hz)
    y = fftconvolve(symbols, taps, mode="full")[int(-lags[0]):int(-lags[0]) + len(symbols)]
    n0 = 10 ** (-esn0_db / 10)
    rng = np.random.default_rng(seed)
    y += np.sqrt(n0 / 2) * (rng.standard_normal(len(y)) + 1j * rng.standard_normal(len(y)))
    return y.reshape(len(frames), len(frames[0])), (lags, taps)


def header_training_symbols(profile: Profile, stream_id: int, frame_no: int, encrypted=False):
    """Preamble and expected header symbols, with known QAM signs only.

    The frame counter must already be tracked for the header to be usable as
    training. QAM position bits are payload; their axis amplitude is replaced
    by its equally likely mean, and decision-directed training refines it.
    """
    width = Layout(profile, encrypted=encrypted).header_bits
    tag = _bits(profile.experimental_tag, 2)
    header = (_bits(profile.pid, 4) + _bits(stream_id, 1) +
              [int(encrypted)] + tag +
              _bits(frame_no & ((1 << (width - 8)) - 1), width - 8))
    coded = fec.conv_encode(np.asarray(header, np.int64))[:2 * width]
    hp = coded ^ modem.prbs(len(coded))
    half_axis = modem.HALF_AXIS_POINTS[profile.modulation]
    amplitude = float(np.mean(modem._axis_pos(half_axis, profile.alpha if half_axis > 1 else 1.0)))
    axis = (1 - 2 * hp) * amplitude
    return np.concatenate([modem.PREAMBLE, axis[0::2] + 1j * axis[1::2]])


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
            targets.append(received[frame_no, j])
    return np.asarray(rows), np.asarray(targets)


def estimate_channel(received, profile: Profile, stream_id=0, training_frames=100,
                     lag_min=-4, lag_max=10, encrypted=False):
    """Causal calibration from the first training_frames, without payload symbols."""
    count = min(training_frames, len(received))
    if count < 1:
        raise ValueError("at least one training frame is required")
    X, y = _training_matrix(received, profile, stream_id, range(count), lag_min, lag_max, encrypted)
    if len(X) < len(X[0]) or np.linalg.matrix_rank(X) < X.shape[1]:
        raise ValueError("header training does not span the requested channel taps")
    taps = np.linalg.lstsq(X, y, rcond=None)[0]
    residual = y - X @ taps
    return np.arange(lag_min, lag_max + 1), taps, float(np.mean(np.abs(residual) ** 2))


def design_mmse_equalizer(lags, taps, noise_power, ntaps=11, max_lookahead=4):
    """Linear FIR with unity desired-tap gain; choose causal lookahead by MSE."""
    if ntaps < 1 or max_lookahead >= ntaps or noise_power < 0:
        raise ValueError("invalid equalizer size or noise power")
    best = None
    lo, hi = int(lags[0]), int(lags[-1])
    for lead in range(max_lookahead + 1):
        q = np.arange(-lead, ntaps - lead)
        effective_lags = np.arange(lo + q[0], hi + q[-1] + 1)
        H = np.zeros((len(effective_lags), ntaps), complex)
        for j, shift in enumerate(q):
            src = effective_lags - shift
            valid = (src >= lo) & (src <= hi)
            H[valid, j] = taps[src[valid] - lo]
        desired = (effective_lags == 0).astype(complex)
        w = np.linalg.solve(H.conj().T @ H + max(noise_power, 1e-10) * np.eye(ntaps), H.conj().T @ desired)
        response = H @ w
        gain = response[np.flatnonzero(effective_lags == 0)[0]]
        if abs(gain) < 1e-8:
            continue
        w /= gain
        mse = float(np.sum(np.abs(H @ w - desired) ** 2) + noise_power * np.sum(np.abs(w) ** 2))
        if best is None or mse < best[0]:
            best = mse, lead, w
    if best is None:
        raise ValueError("no usable equalizer")
    return best[1], best[2], best[0]


def apply_equalizer(received, lead, weights):
    flat = np.asarray(received).reshape(-1)
    out = fftconvolve(flat, weights, mode="full")[lead:lead + len(flat)]
    return out.reshape(np.shape(received))


def _slice_constellation(values, profile: Profile):
    levels = modem.HALF_AXIS_POINTS[profile.modulation]
    points = modem._axis_pos(levels, profile.alpha if levels > 1 else 1.0)
    result = np.empty_like(values)
    for v, out in ((values.real, result.real), (values.imag, result.imag)):
        nearest = points[np.abs(np.abs(v)[:, None] - points).argmin(axis=1)]
        out[:] = np.where(v < 0, -nearest, nearest)
    if profile.hybrid:
        lay = HybridLayout(profile)
        digital = modem.n_symbols(lay.n_tx, lay.n_strong, profile.modulation)
        frame_len = len(modem.PREAMBLE) + digital + lay.n_hybrid
        if len(result) % frame_len:
            raise ValueError("等化器の入力がフレーム長の整数倍ではありません")
        src = np.asarray(values).reshape(-1, frame_len)
        dst = result.reshape(-1, frame_len)
        high = src[:, len(modem.PREAMBLE) + digital:]
        lower_bits = profile.hybrid_bits - 2
        levels = 1 << lower_bits
        center = (levels - 1) / 2
        phase = np.mod(np.rint((np.angle(high) - np.pi / 4) / (np.pi / 2)).astype(np.int64), 4)
        scale = modem.hybrid_scale(profile.hybrid_amplitude, lower_bits)
        radial = np.clip(np.rint((np.abs(high) * scale - 1) / profile.hybrid_amplitude + center),
                         0, levels - 1).astype(np.int64)
        dst[:, len(modem.PREAMBLE) + digital:] = modem.hybrid_modulate(
            (phase * levels + radial).ravel(), profile.hybrid_amplitude,
            lower_bits=lower_bits).reshape(high.shape)
    return result


def refine_channel_decisions(received, profile: Profile, lags, taps, noise_power,
                             training_frames=100, ntaps=11, max_lookahead=4, passes=2):
    """Refine static channel using decisions from calibration frames only."""
    count = min(training_frames, len(received))
    flat = np.asarray(received[:count]).reshape(-1)
    frame_len = len(received[0])
    lag_min, lag_max = int(lags[0]), int(lags[-1])
    fitted = np.asarray(taps)
    for _ in range(passes):
        lead, w, _ = design_mmse_equalizer(lags, fitted, noise_power, ntaps, max_lookahead)
        decisions = _slice_constellation(apply_equalizer(flat, lead, w), profile).reshape(count, frame_len)
        decisions[:, :len(modem.PREAMBLE)] = modem.PREAMBLE
        rows = []
        target = []
        for f in range(count):
            for j in range(lag_max, frame_len + lag_min):
                rows.append(decisions[f, j - lags])
                target.append(received[f, j])
        X, y = np.asarray(rows), np.asarray(target)
        candidate = np.linalg.lstsq(X, y, rcond=None)[0]
        residual = y - X @ candidate
        fitted = candidate
        noise_power = float(np.mean(np.abs(residual) ** 2))
    return fitted, noise_power


def equalize_static(received, profile: Profile, stream_id=0, training_frames=100,
                    ntaps=11, max_lookahead=4, decision_passes=2, encrypted=False):
    """Calibrate on past frames, then return equalized symbols and diagnostics.

    Callers should evaluate only frames after training_frames; returning the
    complete signal simplifies subsequent frame decoding and steady-state
    benchmark cropping.
    """
    lags, taps, noise = estimate_channel(received, profile, stream_id, training_frames,
                                         encrypted=encrypted)
    if decision_passes:
        taps, noise = refine_channel_decisions(received, profile, lags, taps, noise,
                                               training_frames, ntaps, max_lookahead, decision_passes)
    lead, weights, predicted_mse = design_mmse_equalizer(lags, taps, noise, ntaps, max_lookahead)
    output = apply_equalizer(received, lead, weights)
    return output, dict(training_frames=min(training_frames, len(received)), lookahead_symbols=lead,
                        residual_power=noise, predicted_mse=predicted_mse,
                        channel_lags=lags.tolist(),
                        channel_taps=[[float(z.real), float(z.imag)] for z in taps])
