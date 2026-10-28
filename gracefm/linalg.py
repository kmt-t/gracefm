"""
整数だけの線形代数 (対称正定値の連立方程式)。コレスキー分解 + 前進・後退代入。平方根は整数の平方根 (isqrt)、除算は整数除算。
等化器 (通信路の推定と MMSE 重みの設計) が使う。複素エルミート行列は、実部・虚部の 2n × 2n の実対称行列に直して解く。

係数は小数 FRAC bit (Q FRAC) の固定小数点。行列 A は最大の対角要素で割って Q FRAC にそろえ (ブロック浮動小数点)、
右辺 b も同じ尺度で割る。解 w = A^-1 b は尺度に依存せず、Q FRAC の整数で返す。幅は Python の整数 (任意精度) で、
ハードウェアでの桁は、行列の大きさ n と条件数から決める。
"""
from math import isqrt

FRAC = 24


def cholesky_solve(A, b, ridge=0):
    """A (n×n、対称正定値の整数)、b (n) → w (Q FRAC の整数、n)。ridge は対角に足す正則化 (A と同じ尺度の整数)"""
    n = len(b)
    A = [[int(v) for v in row] for row in A]
    for i in range(n):
        A[i][i] += int(ridge)
    top = max(A[i][i] for i in range(n))
    if top <= 0:
        return [0] * n
    An = [[(A[i][j] << FRAC) // top for j in range(n)] for i in range(n)]
    bn = [(int(b[i]) << FRAC) // top for i in range(n)]
    L = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = An[i][j] - sum(L[i][k] * L[j][k] for k in range(j)) // (1 << FRAC)
            if i == j:
                L[i][i] = max(isqrt(max(s, 0) << FRAC), 1)
            else:
                L[i][j] = (s << FRAC) // L[j][j]
    y = [0] * n
    for i in range(n):
        y[i] = ((bn[i] - sum(L[i][k] * y[k] for k in range(i)) // (1 << FRAC)) << FRAC) // L[i][i]
    w = [0] * n
    for i in reversed(range(n)):
        w[i] = ((y[i] - sum(L[k][i] * w[k] for k in range(i + 1, n)) // (1 << FRAC)) << FRAC) // L[i][i]
    return w


def hermitian_solve(Ar, Ai, br, bi, ridge=0):
    """複素エルミート行列 A = Ar + j·Ai、右辺 b = br + j·bi → (wr, wi) (Q FRAC)"""
    n = len(br)
    big = [[0] * (2 * n) for _ in range(2 * n)]
    for i in range(n):
        for j in range(n):
            big[i][j] = int(Ar[i][j])
            big[i][j + n] = -int(Ai[i][j])
            big[i + n][j] = int(Ai[i][j])
            big[i + n][j + n] = int(Ar[i][j])
    w = cholesky_solve(big, list(br) + list(bi), ridge)
    return w[:n], w[n:]
