"""
スクランブル (送信) とその逆 (受信)。同じ PRBS (gracefm.modem.prbs) を、ビットと LLR の両方に掛ける。

scramble   : 送信ビット → 送信ビット (排他的論理和)
descramble : 受信の軟値と硬判定 → 元の極性の軟値と硬判定。LLR は符号を反転する (正 = 0 らしい)
"""
import numpy as np

from . import modem


def scramble(bits):
    bits = np.asarray(bits, np.int64)
    return bits ^ modem.prbs(len(bits))


def descramble(llr, hard):
    """llr: 軟値 (正 = 0 らしい)、hard: 硬判定 (0/1)。返り値: (llr, hard) を元の極性に戻したもの"""
    s = modem.prbs(len(hard))
    return np.where(s == 1, -np.asarray(llr), llr), np.asarray(hard) ^ s
