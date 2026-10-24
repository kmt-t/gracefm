"""軟判定の復号の評価 (SPEC 5.5節)。python tools/eval_softdec.py single|iq"""
import sys; import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
from gracefm import metrics, modem, wavio, txrx
from gracefm.profiles import PROFILES
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "samples") + "/"


def frames_noisy(x, p, snr, seed, off=0, sid=0, iq=None):
    rng = np.random.default_rng(seed)
    out = []
    for f in txrx.Transmitter(p, sid, off).run(x):
        if iq is None:
            out.append(modem.awgn(f, snr, rng))
        else:   # I/Q で雑音の大きさが違い、相関もある雑音 (全体の電力は Es/N0 と同じ)
            n0 = 10 ** (-snr / 10)
            C = np.array([[1.0, iq[1]], [iq[1], iq[0]]]); C *= n0 / np.trace(C)
            w = rng.multivariate_normal([0, 0], C, len(f))
            out.append(f + w[:, 0] + 1j * w[:, 1])
    return out


def dec(p, fr, n, off, soft):
    d = txrx.StreamDecoder(p, soft_decode=soft)
    y, v = d.run(fr, n, off)
    return y, v, d.r_trace


def single():
    print("== 1系統: 硬判定 → 軟判定 (波形SNR dB / BandMetric、2 seed 平均) ==")
    for name, prof in (("fishin", "B200M"), ("vibeace", "B200M"), ("demo", "B200Y")):
        p = PROFILES[prof]; x, fs = wavio.read(R + f"{name}__32k__reference.flac"); bm = metrics.BandMetric(x, fs)
        row = []
        for snr in (4, 6, 8, 10, 12):
            r = []
            for soft in (False, True):
                vals = []
                for seed in (1, 2):
                    y, v, _ = dec(p, frames_noisy(x, p, snr, seed), len(x), 0, soft)
                    y = txrx.plc.conceal(y, v, fs)
                    vals.append((metrics.snr_db(x, y), bm(y - x)))
                r.append(np.mean(vals, axis=0))
            row.append(f"{snr}dB {r[0][0]:5.1f}→{r[1][0]:5.1f} / {r[0][1]:5.1f}→{r[1][1]:5.1f}")
        print(f"{name:8s} " + " | ".join(row), flush=True)


def iq_eval():
    print("== I/Q の雑音が不均等・相関あり (1系統, fishin SUB50M, Es/N0 8dB, 軟判定の復号)："
          "軸ごと独立・等分散とみなす → 2次元の共分散を使う (波形SNR dB) ==")
    p = PROFILES["SUB50M"]; x, fs = wavio.read(R + "fishin__32k__reference.flac")
    orig = modem.bit_probs

    def diag_probs(sym, n_bits, mod="qpsk", alpha=1.0):
        s = sym[len(modem.PREAMBLE):]
        a = 1 / np.sqrt(2)
        vv = np.empty(2 * len(s)); vv[0::2] = s.real; vv[1::2] = s.imag
        sig2 = np.mean((np.abs(vv) - a) ** 2)
        p1 = 1 / (1 + np.exp(np.clip(2 * a * vv / sig2, -60, 60)))
        p1 = np.clip(p1[:n_bits], 1e-12, 1 - 1e-12)
        return p1, np.log((1 - p1) / p1)

    for iq in ((1.0, 0.0), (4.0, 0.0), (1.0, 0.6), (4.0, 1.2)):
        r = []
        for fn in (diag_probs, orig):
            modem.bit_probs = fn
            vals = []
            for seed in (1, 2):
                y, v, _ = dec(p, frames_noisy(x, p, 8, seed, iq=iq), len(x), 0, True)
                vals.append(metrics.snr_db(x, txrx.plc.conceal(y, v, fs)))
            r.append(np.mean(vals))
        modem.bit_probs = orig
        print(f"  Q/I 分散比 {iq[0]:.0f}, 相関係数 {iq[1] / np.sqrt(iq[0]):.1f}: {r[0]:5.1f} → {r[1]:5.1f} dB", flush=True)


if __name__ == "__main__":
    {"single": single, "iq": iq_eval}[sys.argv[1]]()
