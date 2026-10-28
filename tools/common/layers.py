"""
階層16QAMの基本層・拡張層の配分を、強い位置と弱い位置の数が釣り合うように決める。

1シンボルは強い2位置（位相部）と弱い2位置（振幅部）を持つ。係数をシンボル単位で分け、位相部に置くHaar係数の仮数bitが
基本層 a_k、振幅部に置く仮数bitが拡張層 e_k = w_k - a_k である。位相部の先頭にはパリティ K_k bit も入る。
位相部（a_k + K_k）と振幅部（e_k）をどちらも2の倍数にするので、全幅は w_k = a_k + e_k = 4N - K_k になる（N は係数のシンボル数。
K=1 なら基本層 2N-1、拡張層 2N）。

ヘッダと終端は「パリティ（位相部）｜データ（振幅部）」の対で置くので、強弱どちらにも同数入り、差に効かない。したがって

    S - W = Σ n_k (2 a_k + K_k - w_k)      (n_k は帯域の係数数)

で、すべての係数を a_k + K_k = e_k（N シンボルずつ）にすれば S = W となり、詰め物はいらない。Y方式の高域Mなど専用シンボルの帯域は配分の対象外。
"""
from dataclasses import replace

from gracefm.profiles import Profile


def default_split(widths, protect_bits):
    """位相部 (基本層の仮数 + パリティ) と振幅部 (拡張層) が同じ大きさになる基本層を仮に置く。FEC長の計算用。"""
    out = []
    for k, w in enumerate(widths):
        if not w:
            out.append(0)
            continue
        kk = protect_bits(k)
        cands = range(max(kk, 1), w - 1, 2)
        out.append(min(cands, key=lambda a: abs(a + kk - (w - a))) if len(cands) else 1)
    return tuple(out)


def _bands(p: Profile):
    """配分の対象になる (成分, 帯域, 全幅, 係数数)"""
    return [(ch, k, w, p.ncoef(k))
            for ch, bits in (("M", p.bits_m), ("S", p.bits_s)) for k, w in enumerate(bits)
            if w and not p.y_band(ch, k)]


def solve(p: Profile):
    """p の全幅・FEC・変調はそのままに、釣り合う基本層 (位相部に置く仮数bit。パリティを除く) のbit数 (base_m, base_s) を返す"""
    bands = _bands(p)
    # ヘッダと終端は位相部と振幅部に同数ずつ置くので差に効かない。S - W = Σ n (2 a + K - w) を 0 に近づける。状態 = Σ n (2 a + K - w)。
    states = {0: (0, [])}
    for ch, k, w, n in bands:
        nxt = {}
        kk = p.protect_bits(k)
        for acc, (cost, picks) in states.items():
            for a in range(max(kk, 1), w - 1, 2):
                s_ = acc + n * (2 * a + kk - w)
                c = cost + n * abs(a + kk - (w - a))
                if s_ not in nxt or c < nxt[s_][0]:
                    nxt[s_] = (c, picks + [(ch, k, a)])
        states = nxt
    best = min(states, key=lambda s_: (abs(s_), states[s_][0]))
    chosen = {(ch, k): a for ch, k, a in states[best][1]}
    base_m = tuple(chosen.get(("M", k), 1 if p.bits_m[k] else 0) for k in range(p.nbands))
    base_s = tuple(chosen.get(("S", k), 1 if p.bits_s[k] else 0) for k in range(p.nbands))
    return base_m, base_s


def with_default_split(p: Profile) -> Profile:
    """全幅の半分に近い基本層を仮に置いた配分 (FEC長の計算用)"""
    return replace(p, base_m=default_split(p.bits_m, p.protect_bits),
                   base_s=default_split(p.bits_s, p.protect_bits))


def balanced(p: Profile) -> Profile:
    """全幅・FEC・変調はそのままに、基本層配分だけを釣り合う値に置き換えたプロファイル"""
    base_m, base_s = solve(with_default_split(p))
    return replace(p, base_m=base_m, base_s=base_s)
