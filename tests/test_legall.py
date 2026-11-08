#!/usr/bin/env python3
"""ブロックをまたぐ帯域分割 (LeGall 5/3) のプロファイル"""
import sys
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gracefm import channel
from gracefm.codec import analyze_stream, encode_block, legall_forward, legall_inverse, overlap_valid
from gracefm.decoder import OK, Decoder, reconstruct, roundtrip
from gracefm.encoder import Encoder
from gracefm.iir import ALT_DELAY
from gracefm.profiles import FORMAT_LEGALL, LEGALL_SUFFIX, PROFILES
from gracefm.receiver import receive
from gracefm.timing import min_latency

LEGALL = [p for p in PROFILES.values() if p.overlapped]
P = PROFILES["B200M-L"]


def _audio(p, frames, seed=1):
    """低域に寄せた帯域の広い信号 (符号つき24 bit整数の L/R)"""
    n = p.block * frames
    t = np.arange(n) / p.fs
    rng = np.random.default_rng(seed)
    x = 0.3 * np.sin(2 * np.pi * 220 * t) + 0.15 * np.sin(2 * np.pi * 1800 * t) + 0.02 * rng.normal(size=n)
    side = 0.1 * np.sin(2 * np.pi * 500 * t) if any(p.bits_s) else 0.0
    return np.rint(np.stack([x + side, x - side], axis=1) * 2 ** 23).astype(np.int64)


def test_transform_is_reversible_and_keeps_the_dc_gain():
    x = np.random.default_rng(2).integers(-2 ** 21, 2 ** 21, 64 * 16)
    bands = legall_forward(x, 4)
    assert [len(b) for b in bands] == [4 * 16, 4 * 16, 8 * 16, 16 * 16, 32 * 16]
    assert np.array_equal(legall_inverse(bands), x)                     # 整数可逆
    assert legall_forward(np.full(64, 1 << 20, np.int64), 4)[0][0] == 1 << 20   # 直流の利得は 1


def test_reach_constants_match_the_transform():
    block, frames, j = P.block, 8, 4
    counts = [P.ncoef(k) for k in range(P.nbands)]
    before = after = 0
    for k, c in enumerate(counts):
        for i in range(c):
            bands = [np.zeros(frames * cc, np.int64) for cc in counts]
            bands[k][j * c + i] = 1 << 20
            touched = np.nonzero(legall_inverse(bands))[0]
            before = max(before, j * block - int(touched.min()))
            after = max(after, int(touched.max()) - ((j + 1) * block - 1))
    assert (before, after) == (P.synth_reach_before, P.synth_reach_after)
    lookahead = 0
    for pos in range((j + 1) * block, (j + 2) * block):
        x = np.zeros((frames * block, 2), np.int64)
        x[pos] = 1 << 20
        if any(np.any(b) for b in analyze_stream(x, P)[j]["M"]):
            lookahead = pos - ((j + 1) * block - 1)
    assert lookahead == P.encoder_lookahead


def test_link_matches_the_codec_for_all_profiles():
    for p in LEGALL:
        x = _audio(p, 12)
        res = Decoder(p).run(Encoder(p).run(x), len(x))
        assert res.valid.all(), p.name
        assert np.abs(res.pcm - roundtrip(x, p)).max() <= (1 << 16 if p.has_y else 64), p.name


def test_roundtrip_is_better_than_haar_on_the_same_bits():
    for name in ("B200M", "B200MY", "M700"):
        haar = PROFILES[name]
        legall = replace(haar, name=f"{name}-same-bits", transform="legall53", format_id=FORMAT_LEGALL)
        x = _audio(haar, 80)

        def error(p):
            return ((x - roundtrip(x, p)).astype(float) ** 2).sum()
        assert error(legall) < error(haar), name


def test_legall_profiles_use_no_more_symbols_than_haar():
    for p in LEGALL:
        haar = PROFILES[p.name.removesuffix(LEGALL_SUFFIX)]
        assert p.pid == haar.pid and p.fs == haar.fs and p.modulation == haar.modulation
        assert Encoder(p).nsym <= Encoder(haar).nsym, p.name
        assert p.payload_bits() <= haar.payload_bits(), p.name


def test_format_identifier_separates_haar_from_legall():
    x = _audio(P, 2)
    assert Decoder(PROFILES["B200M"]).decode_frame(Encoder(P).run(x)[0]).status != OK
    assert Decoder(P).decode_frame(Encoder(PROFILES["B200M"]).frame(x[:P.block])).status != OK


def test_block_only_interfaces_refuse_overlapped_profiles():
    x = _audio(P, 1)
    for call in (lambda: encode_block(x, P), lambda: Encoder(P).frame(x), lambda: reconstruct(None, P)):
        try:
            call()
        except ValueError:
            continue
        raise AssertionError("ブロック単位の処理は使えないはず")


def test_lost_frame_invalidates_exactly_its_reach():
    x = _audio(P, 12)
    frames = Encoder(P).run(x)
    full = Decoder(P).run(frames, len(x))
    j = 5
    frames[j] = None
    res = Decoder(P).run(frames, len(x))
    start, end = j * P.block - P.synth_reach_before, (j + 1) * P.block + P.synth_reach_after
    expected = np.ones(len(x), bool)
    expected[start:end] = False
    assert np.array_equal(res.valid, expected)
    assert np.array_equal(res.pcm[expected], full.pcm[expected])        # 影響範囲の外は 1 LSB も変わらない
    assert not res.pcm[~expected].any()


def test_overlap_valid_at_stream_edges():
    v = np.ones(4, bool)
    v[0] = False
    out = overlap_valid(v, P, 4 * P.block)
    assert not out[: P.block + P.synth_reach_after].any() and out[P.block + P.synth_reach_after:].all()
    v = np.ones(4, bool)
    v[-1] = False
    out = overlap_valid(v, P, 4 * P.block)
    assert out[: 3 * P.block - P.synth_reach_before].all() and not out[3 * P.block - P.synth_reach_before:].any()


def test_encoder_and_decoder_only_look_as_far_as_the_timing_model_says():
    x = _audio(P, 12)
    j = 5
    edge = (j + 1) * P.block
    changed = x.copy()
    changed[edge + P.encoder_lookahead:] = 0
    a, b = Encoder(P).run(x), Encoder(P).run(changed)
    assert all(np.array_equal(a[i], b[i]) for i in range(j + 1))        # フレーム j までは先読みより先に依存しない
    other = a[:j + 1] + b[j + 1:]
    y, z = Decoder(P).run(a, len(x)).pcm, Decoder(P).run(other, len(x)).pcm
    limit = edge - P.synth_reach_before
    assert np.array_equal(y[:limit], z[:limit])                         # 出力単位 j はフレーム j までで決まる


def test_latency_adds_the_lookahead():
    for p in LEGALL:
        extra = Fraction(p.encoder_lookahead + p.synth_reach_before + ALT_DELAY[p.fs], p.fs)
        assert (p.encoder_lookahead, p.synth_reach_before) == (15, 15)
        assert min_latency(p) == 2 * Fraction(p.block, p.fs) + extra


def test_fusion_covers_a_frame_lost_on_one_stream():
    p, sub = PROFILES["B200M-L"], PROFILES["SUB50M-L"]
    x = _audio(p, 16)
    fa, fb = Encoder(p, 0, 0).run(x), Encoder(sub, 1, 0).run(x)
    clean, _ = receive(p, fa, fb, len(x), 0, profile_b=sub, plc_order=16)
    lost_a = list(fa)
    lost_a[6] = None
    y, st = receive(p, lost_a, fb, len(x), 0, profile_b=sub)
    assert st["plc_samples"] == 0
    bad = 6 * p.block
    assert np.abs(y[:bad - 64] - clean[:bad - 64]).max() <= 64          # 離れた区間は変わらない
    both = list(fb)
    both[6] = None
    _, st = receive(p, lost_a, both, len(x), 0, profile_b=sub)
    assert st["plc_samples"] == p.block + p.synth_reach_before + p.synth_reach_after


def test_main_and_sub_must_share_the_transform():
    p = PROFILES["B200M-L"]
    x = _audio(p, 4)
    try:
        receive(p, Encoder(p).run(x), Encoder(PROFILES["SUB50M"], 1, 0).run(x), len(x), 0, profile_b=PROFILES["SUB50M"])
    except ValueError:
        return
    raise AssertionError("Haar の副系とは融合できないはず")


def test_default_subs_pair_the_same_transform():
    for main, sub in channel.DEFAULT_SUB.items():
        assert PROFILES[main].transform == PROFILES[sub].transform, main


def test_noisy_link_error_is_lower_than_haar_at_high_frequencies():
    """低域に寄せた信号で、同じ電波の強さなら 2 kHz 以上の誤差が減る"""
    def high_error(name):
        p = PROFILES[name]
        x = _audio(p, 200)
        y, _, _ = channel.link(x, name, 66, sub=None, seed=3)
        n = len(y) - ALT_DELAY[p.fs]
        err = (y[ALT_DELAY[p.fs]:, 0] - x[:n, 0]).astype(float)
        spectrum = np.abs(np.fft.rfft(err * np.hanning(n))) ** 2
        return spectrum[np.fft.rfftfreq(n, 1 / p.fs) >= 2000].sum()
    assert high_error("B200M-L") < high_error("B200M") / 2


if __name__ == '__main__':
    for name, function in list(globals().items()):
        if name.startswith('test_'):
            function()
    print('ok')
