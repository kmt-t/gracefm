"""
フレームのビット配置。1フレーム = 1ブロック。

保護部 (FEC で符号化する):
  ヘッダ 16bit   : プロファイルID 4 | 系統ID 1 | 暗号化 1 (=0) | 実験タグ 2 | フレーム番号 8   (各 MSB から)
  実験タグ非0はヘッダ24bitとし、フレーム番号を16bitに拡張する。
  (暗号化するとき 32bit: プロファイルID 4 | 系統ID 1 | 暗号化 1 (=1) | 実験タグ 2 | フレーム番号 24)
  実験タグ 0 は既存フレーム。既存IDを共有する48kHz Y系はタグ1とし、
  ヘッダ長・CRC位置も変えることで旧受信機による誤受理を防ぐ。
  指数           : M の係数群 0→6, 続いて S の係数群 0→6 (0bit の群は無し)。k=0 は低域近似、k=1..6 は詳細帯域。各 exp_bits, MSB から
  区間アッテネータ: 有効なプロファイルのみ。M→S、帯域低→高、区間先頭→末尾の順に1bitずつ
  仮数の上位 K bit: (M→S, 帯域 低→高, 係数 先頭→末尾) の順に、各係数の上位 K bit を MSB から
  CRC-16         : 以上すべてに対する CRC-16-CCITT
非保護部 (そのまま送る):
  残りの仮数ビットを「上から何ビット目か (rank)」の小さい順に並べる。
  同じ rank の中は (M→S, 帯域 低→高, 係数 先頭→末尾)。
  階層化したプロファイルでは、基本層のビットをすべて並べてから、拡張層のビットを同じ規則で並べる。
  → 誤りに強い位置 (変調の象限ビットなど) から重要なビットが埋まる。
仮数は通常 オフセットバイナリ u = m + qmax (b bit) で表す。
実験用ハイブリッド高域だけ u = m + 2^(b-1) として全2^b値を使う。
送信順: [保護部を畳み込み符号化したビット] [非保護部]
暗号化するときは、ヘッダ以外の保護部 (指数・区間アッテネータ・仮数の上位) と非保護部を、キーストリームとの XOR で暗号化してから
CRC と FEC をかける (CRC は暗号文に対してかかるので、鍵がなくても誤りは検出できる。gracefm.crypto)。
"""
import numpy as np

from . import fec
from .codec import BlockData, offset_of, qmax_of, qmin_of
from .profiles import Profile

HEADER_BITS = 16


def _bits(v, n):
    return [(int(v) >> (n - 1 - i)) & 1 for i in range(n)]


class Layout:
    def __init__(self, profile: Profile, encrypted: bool = False):
        p = profile
        self.p = p
        self.encrypted = encrypted
        self.header_bits = 32 if encrypted else (24 if p.experimental_tag else HEADER_BITS)
        self.exp_items = []         # (ch, k)
        self.attn_items = []        # (ch, k, group index)
        self.top_items = []         # (ch, k, j, pos)
        unp = []                    # (rank, order, ch, k, j, pos)
        order = 0
        for ch, bits in (("M", p.bits_m), ("S", p.bits_s)):
            for k, b in enumerate(bits):
                if b > 0:
                    self.exp_items.append((ch, k))
                    self.attn_items.extend((ch, k, j) for j in range(p.attenuator_bits(ch, k)))
        for ch, bits in (("M", p.bits_m), ("S", p.bits_s)):
            for k, b in enumerate(bits):
                if b == 0:
                    continue
                for j in range(p.ncoef(k)):
                    for rank in range(b):
                        pos = b - 1 - rank
                        if rank < p.protect_k:
                            self.top_items.append((ch, k, j, pos))
                        else:
                            ext = int(rank >= p.base_bits(ch, k))      # 拡張層 (階層化したときだけ 1)
                            unp.append((ext, rank, order, ch, k, j, pos))
                        order += 1
        unp.sort(key=lambda t: (t[0], t[1], t[2]))
        self.n_base_unp = sum(1 for t in unp if t[0] == 0)
        self.unp_items = [t[3:] for t in unp]
        self.n_prot = (self.header_bits + sum(p.exponent_bits(ch, k) for ch, k in self.exp_items)
                       + len(self.attn_items) + len(self.top_items))
        self.n_body = self.n_prot - self.header_bits      # 暗号化する保護部のビット数
        self.n_prot_crc = self.n_prot + 16
        self.n_coded = 2 * (self.n_prot_crc + fec.K - 1)
        self.n_unp = len(self.unp_items)
        self.n_tx = self.n_coded + self.n_unp
        self.n_keystream = self.n_body + self.n_unp       # 1フレームに使うキーストリームのビット数
        # 変調の強い位置に必ず入れるビット数 (階層化したときは基本層全体、それ以外は保護部の符号化ビット)
        self.n_strong = self.n_coded + (self.n_base_unp if p.layered else 0)
        # 非保護ビットの属性 (受信側で誤差のエネルギーを見積もるため)
        self.unp_ch = np.array([0 if t[0] == "M" else 1 for t in self.unp_items], np.int64)
        self.unp_k = np.array([t[1] for t in self.unp_items], np.int64)
        self.unp_pos = np.array([t[3] for t in self.unp_items], np.int64)
        # 係数を (M→S, 帯域 低→高, 係数 先頭→末尾) で一列に並べたときの番号
        self.coef_offset = {}
        off = 0
        for ch, bits in (("M", p.bits_m), ("S", p.bits_s)):
            for k, b in enumerate(bits):
                if b > 0:
                    self.coef_offset[(ch, k)] = off
                    off += p.ncoef(k)
        self.n_coef = off
        self.unp_flat = np.array([self.coef_offset[(t[0], t[1])] + t[2] for t in self.unp_items], np.int64)

    # ---------------------------------------------------------------- 送信側
    def pack(self, bd: BlockData, stream_id: int, counter: int, keystream=None):
        """keystream: 暗号化するとき、このフレームのキーストリーム (n_keystream ビット)"""
        p = self.p
        tag = _bits(p.experimental_tag, 2)
        if self.encrypted:
            hdr = _bits(p.pid, 4) + _bits(stream_id, 1) + [1] + tag + _bits(counter & 0xFFFFFF, 24)
        else:
            counter_bits = self.header_bits - 8
            hdr = (_bits(p.pid, 4) + _bits(stream_id, 1) + [0] + tag
                   + _bits(counter & ((1 << counter_bits) - 1), counter_bits))
        prot = list(hdr)
        bits_of = {"M": p.bits_m, "S": p.bits_s}
        for ch, k in self.exp_items:
            prot += _bits(bd.eidx[ch][k], p.exponent_bits(ch, k))
        for ch, k, j in self.attn_items:
            prot.append(int(bd.attn[ch][k][j]))
        for ch, k, j, pos in self.top_items:
            u = bd.mant[ch][k][j] + offset_of(bits_of[ch][k], p, ch, k)
            prot.append((int(u) >> pos) & 1)
        prot = np.array(prot, np.int64)
        unp = np.array([(int(bd.mant[ch][k][j] + offset_of(bits_of[ch][k], p, ch, k)) >> pos) & 1
                        for ch, k, j, pos in self.unp_items], np.int64)
        if self.encrypted:
            prot[self.header_bits:] ^= keystream[: self.n_body]
            unp = unp ^ keystream[self.n_body:]
        prot = np.concatenate([prot, fec.crc16(prot)])
        return np.concatenate([fec.conv_encode(prot), unp])

    # ---------------------------------------------------------------- 受信側
    def unpack(self, soft_coded, unp_bits, keystream_for=None):
        """
        soft_coded: 保護部の符号化ビットの軟値 (正 = 0 らしい), unp_bits: 非保護部の硬判定
        keystream_for: 暗号化するとき、ヘッダ (dict) からキーストリームを返す関数。使ったキーストリームは header["ks"]
        返り値: (BlockData, header dict) / CRC が合わなければ (None, None)
        """
        p = self.p
        prot = fec.viterbi_decode(soft_coded, self.n_prot_crc)
        body, crc = prot[: self.n_prot], prot[self.n_prot:]
        if not np.array_equal(fec.crc16(body), crc):
            return None, None
        hdr = body[: self.header_bits]
        val = lambda bb: int("".join(str(int(v)) for v in bb), 2)
        header = {"pid": val(hdr[0:4]), "stream": int(hdr[4]), "encrypted": bool(hdr[5]),
                  "counter": val(hdr[8: self.header_bits])}
        if (header["pid"] != p.pid or header["encrypted"] != self.encrypted
                or val(hdr[6:8]) != p.experimental_tag):
            return None, None
        if self.encrypted:
            ks = keystream_for(header)
            body = body.copy()
            body[self.header_bits:] ^= ks[: self.n_body]
            unp_bits = np.asarray(unp_bits, np.int64) ^ ks[self.n_body:]
            header["ks"] = ks
        i = self.header_bits
        eidx = {"M": [None] * p.nbands, "S": [None] * p.nbands}
        attn = {"M": [None] * p.nbands, "S": [None] * p.nbands}
        bits_of = {"M": p.bits_m, "S": p.bits_s}
        u = {ch: [np.zeros(p.ncoef(k), np.int64) if bits_of[ch][k] > 0 else None
                  for k in range(p.nbands)] for ch in ("M", "S")}
        for ch, k in self.exp_items:
            width = p.exponent_bits(ch, k)
            eidx[ch][k] = val(body[i:i + width])
            i += width
        for ch, k in self.exp_items:
            count = p.attenuator_bits(ch, k)
            attn[ch][k] = body[i:i + count].copy()
            i += count
        for ch, k, j, pos in self.top_items:
            u[ch][k][j] |= int(body[i]) << pos
            i += 1
        for (ch, k, j, pos), bit in zip(self.unp_items, unp_bits):
            u[ch][k][j] |= int(bit) << pos
        mant = {ch: [None if u[ch][k] is None else
                     np.clip(u[ch][k] - offset_of(bits_of[ch][k], p, ch, k),
                             qmin_of(bits_of[ch][k], p, ch, k), qmax_of(bits_of[ch][k]))
                     for k in range(p.nbands)] for ch in ("M", "S")}
        bd = BlockData(mant, eidx, attn)
        return bd, header


class HybridLayout(Layout):
    """FEC保護部を維持し、高域の非保護仮数を複素シンボルへ移す配置。"""

    def __init__(self, profile: Profile):
        if not profile.hybrid:
            raise ValueError("ハイブリッドプロファイルが必要です")
        super().__init__(profile)
        self.hybrid_items = [(ch, k, j)
                             for ch, bits in (("M", profile.bits_m), ("S", profile.bits_s))
                             if ch in profile.hybrid_channels
                             for k in range(profile.hybrid_start_k, profile.nbands)
                             if bits[k] for j in range(profile.ncoef(k))]
        keep = [i for i, (ch, k, _, _) in enumerate(self.unp_items)
                if ch not in profile.hybrid_channels or k < profile.hybrid_start_k]
        self.unp_items = [self.unp_items[i] for i in keep]
        self.unp_ch = self.unp_ch[keep]
        self.unp_k = self.unp_k[keep]
        self.unp_pos = self.unp_pos[keep]
        self.unp_flat = self.unp_flat[keep]
        self.n_base_unp = sum(1 for ch, k, _, pos in self.unp_items
                              if (profile.bits_m if ch == "M" else profile.bits_s)[k] - pos
                              <= profile.base_bits(ch, k))
        self.n_unp = len(self.unp_items)
        self.n_tx = self.n_coded + self.n_unp
        self.n_keystream = self.n_body + self.n_unp
        self.n_strong = self.n_coded + (self.n_base_unp if profile.layered else 0)
        self.n_hybrid = len(self.hybrid_items)

    def hybrid_u(self, bd: BlockData):
        return np.asarray([int(bd.mant[ch][k][j]) + offset_of(self.p.hybrid_bits, self.p, ch, k)
                           for ch, k, j in self.hybrid_items], np.int64)
