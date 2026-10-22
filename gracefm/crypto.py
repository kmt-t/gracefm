"""
暗号化 (オプション): AES-128-CTR のストリーム暗号。

鍵で作った乱数列 (キーストリーム) と、指数・区間アッテネータ・仮数のビットの排他的論理和をとる。受信で誤った1ビットは、復号後も
その1ビットの誤りのまま (誤りが広がらない) なので、「下位ビットの誤りは雑音として受け入れる」設計と、
軟判定の復号 (事後確率 p1 を 1 - p1 に入れ替えるだけ) がそのまま使える。乱数列は事前に作れるので遅延は増えない。

キーストリームは フレームごとに AES-CTR の初期カウンタ
    nonce (8バイト) | 系統ID (1バイト) | フレーム番号 (5バイト、40bit) | ブロック番号 (2バイト、0 から)
から作る。同じ鍵と nonce の組を別のセッションで使い回してはいけない (セッションごとに新しい乱数の nonce)。
"""
import numpy as np


class StreamCipher:
    def __init__(self, key: bytes, nonce: bytes):
        if len(key) != 16:
            raise ValueError("鍵は16バイト (AES-128)")
        if len(nonce) != 8:
            raise ValueError("nonce は8バイト")
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        self._mk = lambda iv: Cipher(algorithms.AES(key), modes.CTR(iv)).encryptor()
        self.nonce = nonce

    def keystream(self, stream_id: int, frame_no: int, nbits: int) -> np.ndarray:
        """系統 stream_id のフレーム frame_no (0〜2^40-1) のキーストリーム (0/1 の配列、nbits 個)"""
        iv = self.nonce + bytes([stream_id & 0xFF]) + int(frame_no % (1 << 40)).to_bytes(5, "big") + b"\0\0"
        ks = self._mk(iv).update(b"\0" * ((nbits + 7) // 8))
        return np.unpackbits(np.frombuffer(ks, np.uint8))[:nbits].astype(np.int64)


def unwrap_counter(c24: int, last_full: int) -> int:
    """ヘッダの24bit のフレーム番号から、直前に受けたフレーム番号 last_full に最も近い40bit の番号を復元する"""
    m = 1 << 24
    base = (last_full + 1) - ((last_full + 1) % m)
    cands = [base + c24 - m, base + c24, base + c24 + m]
    return min((c for c in cands if c >= 0), key=lambda c: abs(c - (last_full + 1)))
