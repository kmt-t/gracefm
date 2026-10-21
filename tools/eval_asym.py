"""主系と副系のビットレート差の評価。送信電力の合計 (C/N0) を固定して比べる。
通信路: awgn / mainfade (主系だけ 10dB 落ちる) / rayleigh (系統ごとに独立なゆっくりしたレイリーフェージング、
コヒーレンス約100ms、平均電力は同じ、受信側は理想的な AGC)。"""
import sys; sys.path.insert(0, __import__("os").path.join(__import__("os").path.dirname(__file__), ".."))
import numpy as np, json
from gracefm import metrics, modem, wavio, txrx
from gracefm.profiles import PROFILES
from concurrent.futures import ProcessPoolExecutor
R = __import__("os").path.join(__import__("os").path.dirname(__file__), "..", "samples") + "/"
def rs(p):
    t = txrx.Transmitter(p); return (len(modem.PREAMBLE) + t.nsym) * p.frames_per_sec
def configs(main, subs):
    c = {"単系統": (main, None, 1.0), "対称 等電力": (main, main, 0.5)}
    for s in subs:
        c[f"+{s} 等電力"] = (main, s, 0.5)
        a = rs(PROFILES[main]) / (rs(PROFILES[main]) + rs(PROFILES[s]))
        c[f"+{s} 等密度"] = (main, s, a)
    return c
def gains(nfr, kind, rng):
    if kind == "awgn": return np.ones(nfr)
    if kind == "mainfade": return np.full(nfr, 10 ** (-10 / 10))
    if kind == "rayleigh":   # 1フレーム 2ms、AR(1) で相関 (時定数 50 フレーム = 100ms)
        rho = np.exp(-1 / 50); h = np.zeros(nfr, complex); h[0] = (rng.normal() + 1j * rng.normal()) / np.sqrt(2)
        for i in range(1, nfr):
            h[i] = rho * h[i - 1] + np.sqrt(1 - rho ** 2) * (rng.normal() + 1j * rng.normal()) / np.sqrt(2)
        return np.abs(h) ** 2
def chan(frames, esn0, g, rng):
    return [modem.awgn(f, esn0 + 10 * np.log10(max(gi, 1e-6)), rng) for f, gi in zip(frames, g)]
def job(a):
    name, main, subs, cn0, kind, seed, sec = a
    x, fs = wavio.read(R + f"{name}_orig.flac"); x = x[:sec * fs]; bm = metrics.BandMetric(x, fs)
    out = {}
    for cname, (pm, ps, frac) in configs(main, subs).items():
        rng = np.random.default_rng(seed)
        PM = PROFILES[pm]; off = PM.block // 2
        fa = txrx.Transmitter(PM, 0, 0).run(x)
        ga = gains(len(fa), kind, np.random.default_rng(seed + 100))
        fa = chan(fa, cn0 + 10 * np.log10(frac) - 10 * np.log10(rs(PM)), ga, rng)
        fb = None
        if ps:
            PS = PROFILES[ps]; fb = txrx.Transmitter(PS, 1, off).run(x)
            gb = gains(len(fb), "awgn" if kind == "mainfade" else kind, np.random.default_rng(seed + 200))
            fb = chan(fb, cn0 + 10 * np.log10(1 - frac) - 10 * np.log10(rs(PS)), gb, rng)
        y, st = txrx.receive(PM, fa, fb, len(x), off, profile_b=PROFILES[ps] if ps else None)
        out[cname] = (metrics.snr_db(x, y), bm(y - x), st["plc_samples"] / len(x) * 100)
    return a, out
if __name__ == "__main__":
    sec = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    sets = [("fishin", "B200M", ("S85M", "S50M")), ("vibeace", "B200M", ("S85M", "S50M")), ("demo", "B200", ("S100",))]
    jobs = [(n, m, s, cn0, kind, sd, sec) for n, m, s in sets for kind in ("awgn", "mainfade", "rayleigh")
            for cn0 in (56, 58, 60, 63) for sd in ((1, 2, 3) if kind == "rayleigh" else (1,))]
    res = {}
    with ProcessPoolExecutor() as ex:
        for a, o in ex.map(job, jobs):
            res.setdefault(f"{a[0]}|{a[4]}|{a[3]}", []).append(o)
    summ = {k: {c: np.mean([o[c] for o in L], axis=0).round(2).tolist() for c in L[0]} for k, L in res.items()}
    json.dump(summ, open(__import__("os").path.join(__import__("os").path.dirname(__file__), "..", "docs", "results", "asym_eval.json"), "w"), ensure_ascii=False, indent=1)
    for k, d in summ.items():
        print(k, " | ".join(f"{c} {v[0]:5.1f}/{v[1]:5.1f}/{v[2]:4.1f}%" for c, v in d.items()), flush=True)
