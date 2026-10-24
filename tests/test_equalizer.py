"""Run with pytest or ``python tests/test_equalizer.py``."""
import os
import sys

import numpy as np
from scipy.fft import fft, fftfreq, ifft, next_fast_len
from scipy.signal import lfilter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gracefm import modem  # noqa: E402
from gracefm.crypto import StreamCipher  # noqa: E402
from gracefm.equalizer import (equalize_static, estimate_channel, header_training_symbols,
                               matched_channel_taps, through_matched_channel)  # noqa: E402
from gracefm.profiles import PROFILES  # noqa: E402
from gracefm.pulse import rrc_taps  # noqa: E402
from gracefm.timing import min_latency, waveform_timing  # noqa: E402
from gracefm.txrx import Transmitter  # noqa: E402


def test_header_training_matches_transmitted_quadrants():
    for name in ("B200MH", "SUB50M", "B200H", "SUB100"):
        p = PROFILES[name]
        sid = int(name in ("SUB50M", "SUB100"))
        transmitter = Transmitter(p, sid)
        pilot = header_training_symbols(p, sid, 7)
        transmitter.frame_no = 7
        transmitted = transmitter.frame(np.zeros((p.block, 2)))
        assert np.array_equal(pilot[:len(modem.PREAMBLE)], transmitted[:len(modem.PREAMBLE)])
        actual = transmitted[len(modem.PREAMBLE):len(pilot)]
        expected = pilot[len(modem.PREAMBLE):]
        assert np.array_equal(np.sign(actual.real), np.sign(expected.real))
        assert np.array_equal(np.sign(actual.imag), np.sign(expected.imag))
        if p.modulation == "qpsk":
            assert np.allclose(actual, expected)

    p = PROFILES["B200MH"]
    cipher = StreamCipher(bytes(range(16)), bytes(8))
    transmitter = Transmitter(p, 0, cipher=cipher)
    transmitter.frame_no = 7
    pilot = header_training_symbols(p, 0, 7, encrypted=True)
    transmitted = transmitter.frame(np.zeros((p.block, 2)))
    actual = transmitted[len(modem.PREAMBLE):len(pilot)]
    expected = pilot[len(modem.PREAMBLE):]
    assert np.array_equal(np.sign(actual.real), np.sign(expected.real))
    assert np.array_equal(np.sign(actual.imag), np.sign(expected.imag))


def test_frequency_separation_can_align_the_same_fade():
    p = PROFILES["B200MH"]
    path = ((5e-6, -3.0, np.pi),)
    _, same = matched_channel_taps(p, path, rf_offset_hz=0)
    _, one_mhz = matched_channel_taps(p, path, rf_offset_hz=1e6)
    _, hundred_khz = matched_channel_taps(p, path, rf_offset_hz=100e3)
    assert np.allclose(same, one_mhz)
    assert not np.allclose(same, hundred_khz)


def test_symbol_channel_matches_shaped_fractional_delay_waveform():
    from gracefm.channel import symbol_rate

    p = PROFILES["B200MH"]
    symbols = np.concatenate(Transmitter(p).run(np.zeros((p.block * 30, 2))))
    sps = 8
    pulse = rrc_taps(p.pulse_beta, sps, p.pulse_span)
    up = np.zeros((len(symbols) + p.pulse_span + 2) * sps, complex)
    up[::sps][:len(symbols)] = symbols
    shaped = lfilter(pulse, 1, up)
    delay = 5e-6
    fs = sps * symbol_rate(p)
    nfft = next_fast_len(2 * len(shaped))
    echo = ifft(fft(shaped, nfft) * np.exp(-2j * np.pi * fftfreq(nfft, 1 / fs) * delay))[:len(shaped)]
    received = lfilter(pulse, 1, shaped + 10 ** (-10 / 20) * np.exp(1j * np.pi / 3) * echo)
    sampled = received[p.pulse_span * sps::sps][:len(symbols)]
    lags, taps = matched_channel_taps(p, ((delay, -10, np.pi / 3),))
    equivalent = np.convolve(symbols, taps, "full")[-lags[0]:-lags[0] + len(symbols)]
    assert np.sqrt(np.mean(np.abs(sampled[50:-50] - equivalent[50:-50]) ** 2)) < 1e-5


def test_trained_equalizer_removes_static_echo_without_future_training():
    p = PROFILES["B200MH"]
    frames = Transmitter(p).run(np.zeros((p.block * 150, 2)))
    y, _ = through_matched_channel(frames, p, 24.0, ((5e-6, -10, np.pi / 3),))
    direct, _ = through_matched_channel(frames, p, 24.0)
    s = np.asarray(frames)
    assert np.mean(np.abs(direct[100:] - s[100:]) ** 2) < 0.006
    lags, taps, noise = estimate_channel(y, p, training_frames=100)
    changed = y.copy()
    changed[100:] = 0
    lags2, taps2, noise2 = estimate_channel(changed, p, training_frames=100)
    assert np.array_equal(lags, lags2)
    assert np.allclose(taps, taps2) and np.isclose(noise, noise2)
    equalized, diag = equalize_static(y, p, training_frames=100)
    raw_error = np.mean(np.abs(y[100:] - s[100:]) ** 2)
    eq_error = np.mean(np.abs(equalized[100:] - s[100:]) ** 2)
    assert diag["lookahead_symbols"] <= 4
    assert eq_error < raw_error / 5


def test_filter_and_equalizer_delay_is_accounted_per_stream():
    mono, sub = PROFILES["B200MH"], PROFILES["SUB50M"]
    tm = waveform_timing(mono, sub, lookahead_symbols=4)
    assert np.isclose(min_latency(mono, True, "half", tm) * 1000, 4.3125, atol=1e-5)
    stereo, sub_st = PROFILES["B200H"], PROFILES["SUB100"]
    ts = waveform_timing(stereo, sub_st, lookahead_symbols=4)
    assert np.isclose(min_latency(stereo, True, "half", ts) * 1000, 4.2033898, atol=1e-4)


if __name__ == "__main__":
    for name, fun in list(globals().items()):
        if name.startswith("test_"):
            fun()
            print("ok", name)
