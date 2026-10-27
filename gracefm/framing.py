"""
フレームのビット配置。1フレーム = 1ブロック。ヘッダ (制御情報) とHaar係数部に分け、FECは
「位相部 (強い2位置) にパリティ、振幅部 (弱い2位置) にデータ」を置く系統符号で統一する。

系統符号: (133,171) の符号語集合を、情報bit x を第1系列とする再帰形で使う。パリティ (第2系列, n+6 bit) を位相部へ、
  情報bit x (と終端の情報bit 6 bit) を振幅部へ置くので、1シンボルが「パリティ2bit | データ2bit」になる。
  受信側は両方の軟値を合わせて軟判定ビタビで復号する (gracefm.fec.rsc_parity / rsc_decode)。

ヘッダ (先頭の (n+6)/2 シンボル):
  情報bit x = ヘッダ24bit | 指数 | 区間アッテネータ | 基本CRC 12 | 高域CRC 10※
  現行ヘッダ24bit: プロファイルID 4 | 系統ID 1 | 暗号化 1 (=0) | 形式識別子 2 | フレーム番号 16 (各 MSB から)
  タグ0の旧16bitヘッダは互換性検証用の明示的な設定でのみ使用する。
  (暗号化するとき 32bit: プロファイルID 4 | 系統ID 1 | 暗号化 1 (=1) | 形式識別子 2 | フレーム番号 24)
  現行カタログは全てタグ3・ヘッダ24bit。タグ0/1/2の旧フレームとは互換性がない。
  指数           : M の係数群 0→6, 続いて S の係数群 0→6 (0bit の群は無し)。k=0 は低域近似、k=1..6 は詳細帯域。各 exp_bits, MSB から
  区間アッテネータ: 全登録プロファイルに標準装備。M→S、帯域低→高、区間先頭→末尾の順に1bitずつ
  CRC            : 基本CRC (12bit) (ヘッダ・k=0..4 の指数/アッテネータ・k=0..4 の仮数上位K bit) と、
                   高域CRC (10bit。k=5,6 の指数/アッテネータ・仮数上位K bit・Y帯域の最上位bit)。高域を送らないプロファイルは基本CRCのみ。
Haar係数部 (ヘッダの直後。係数順 = 成分M→S、帯域 低→高、係数 先頭→末尾):
  終端: 仮数上位bit用の系統符号の終端 (パリティ6bit | 情報6bit)。Y帯域があればその分もう一組
  位相部の列: 係数ごとに [その係数の上位K bit のパリティ K bit | 基本層の仮数bit (rank の小さい順)]
  振幅部の列: 係数ごとに [拡張層の仮数bit (rank の小さい順)]
  上位K bit は基本層の先頭にあり、パリティと別の場所にある。係数の先頭のシンボルだけがパリティ付きで、続くシンボルにはない。
  K=1 で係数が N シンボルなら、位相部は 2N bit = パリティ1 + 基本層 2N-1、振幅部は拡張層 2N bit、仮数幅は 4N-1 bit。
  QPSKは全ビットが同じ位置種別なので、ヘッダ、終端、係数の順に並べるだけ (振幅部の列は空)。
  Y帯域の仮数は専用シンボルで送り、この列には入らない。専用シンボルは位相が「最上位bit｜そのパリティ」、半径が残りの仮数。
仮数は通常 オフセットバイナリ u = m + qmax (b bit) で表す。
Y高域だけ u = m + 2^(b-1) として全2^b値を使い、この帯域の仮数は専用シンボルで送る。
送信順: [位相部の列 全体] [振幅部の列 全体] (階層16QAMでは、両者を同じ長さにそろえるために末尾へ0の詰めを入れる)
暗号化するときは、ヘッダ以外のヘッダの内容と仮数bitをキーストリームとの XOR で暗号化してから
CRC とパリティをかける (CRC とパリティは暗号文に対してかかるので、鍵がなくても誤りは検出・訂正できる。gracefm.crypto)。
"""
import numpy as np

from . import fec
from .codec import BlockData, offset_of, qmax_of, qmin_of
from .profiles import Profile

HEADER_BITS = 16


def _bits(v, n):
    return [(int(v) >> (n - 1 - i)) & 1 for i in range(n)]


class Layout:
    def __init__(self, profile: Profile, encrypted: bool = False, with_y: bool = False):
        p = profile
        self.p = p
        self.encrypted = encrypted
        self.header_bits = 32 if encrypted else (24 if p.format_id else HEADER_BITS)
        self.exp_items = []         # (ch, k)
        self.attn_items = []        # (ch, k, group index)
        self.y_items = []      # (ch, k, j): Y帯域の係数 (専用シンボルで送る)
        for ch, bits in (("M", p.bits_m), ("S", p.bits_s)):
            for k, b in enumerate(bits):
                if b > 0:
                    self.exp_items.append((ch, k))
                    self.attn_items.extend((ch, k, j) for j in range(p.attenuator_bits(ch, k)))
        # 係数順に、強い位置の列 (パリティ + 基本層) と弱い位置の列 (拡張層) を作る
        strong, weak = [], []       # ("P", t) = t 番目のパリティ / ("C", ch, k, j, pos) = 仮数bit
        top_k = []                  # 上位K bit (情報列 x) の帯域
        top_item = []               # x の各bitの (ch, k, j, pos)
        for ch, bits in (("M", p.bits_m), ("S", p.bits_s)):
            for k, b in enumerate(bits):
                if b == 0:
                    continue
                in_y = with_y and p.y_band(ch, k)
                K, base = p.protect_bits(k), p.base_bits(ch, k)
                for j in range(p.ncoef(k)):
                    if in_y:
                        self.y_items.append((ch, k, j))
                        continue
                    for rank in range(K):
                        strong.append(("P", len(top_item)))
                        top_k.append(k)
                        top_item.append((ch, k, j, b - 1 - rank))
                    strong.extend(("C", ch, k, j, b - 1 - rank) for rank in range(base))
                    weak.extend(("C", ch, k, j, b - 1 - rank) for rank in range(base, b))
        self.n_top = len(top_item)
        self.n_prot = (self.header_bits + sum(p.exp_bits for ch, k in self.exp_items)
                       + len(self.attn_items))
        self.n_body = self.n_prot - self.header_bits      # 暗号化するヘッダの内容のビット数
        core, high = list(range(self.header_bits)), []
        bit = self.header_bits
        for items, widths in ((self.exp_items, (p.exp_bits for ch, k in self.exp_items)),
                              (self.attn_items, (1 for _ in self.attn_items))):
            for item, width in zip(items, widths):
                (high if item[1] >= 5 else core).extend(range(bit, bit + width))
                bit += width
        assert bit == self.n_prot
        top_k = [k for k in top_k]
        self.core_prot_indices = np.asarray(core, np.int64)
        self.high_prot_indices = np.asarray(high, np.int64)
        self.core_top_indices = np.asarray([t for t, k in enumerate(top_k) if k < 5], np.int64)
        self.high_top_indices = np.asarray([t for t, k in enumerate(top_k) if k >= 5], np.int64)
        y_k = [k for _, k, _ in self.y_items]
        self.core_y_indices = np.asarray([t for t, k in enumerate(y_k) if k < 5], np.int64)
        self.high_y_indices = np.asarray([t for t, k in enumerate(y_k) if k >= 5], np.int64)
        self.has_high_crc = bool(len(high) or len(self.high_top_indices) or len(self.high_y_indices))
        self.n_prot_crc = self.n_prot + fec.CRC_CORE[0] + (fec.CRC_HIGH[0] if self.has_high_crc else 0)
        T = fec.K - 1                                                   # 終端 6 bit
        self.n_hdata = self.n_prot_crc                                  # ヘッダの情報bit (CRC込み)
        self.n_header = 2 * (self.n_hdata + T)                          # ヘッダが使う位置 (パリティ + データ)
        self.n_tail = 2 * T if self.n_top else 0                        # 上位K bit用の終端 (パリティ + 情報)
        self.n_ytail = 2 * T if self.y_items else 0                # Y帯域の最上位bit用の終端
        self.n_parity = self.n_top + self.n_tail + self.n_ytail         # 係数のパリティ (終端込み)
        self.n_block_a, self.n_block_b = self.n_header, self.n_parity
        self.n_coded = self.n_header + self.n_parity                    # 仮数以外が使う位置
        # 位相部の列 (強い位置) と振幅部の列 (弱い位置)
        strong_list = [("HP", i) for i in range(self.n_hdata + T)]
        weak_list = [("HD", i) for i in range(self.n_hdata)] + [("HT", i) for i in range(T)]
        if self.n_top:
            strong_list += [("CP", i) for i in range(T)]
            weak_list += [("CT", i) for i in range(T)]
        if self.y_items:
            strong_list += [("YP", i) for i in range(T)]
            weak_list += [("YT", i) for i in range(T)]
        strong_list += strong
        weak_list += weak
        if p.layered:
            length = 2 * -(-max(len(strong_list), len(weak_list)) // 2)   # 同じ長さ・偶数にそろえる
            strong_list += [("Z",)] * (length - len(strong_list))
            weak_list += [("Z",)] * (length - len(weak_list))
            self.n_strong = length
        stream_list = strong_list + weak_list
        if not p.layered:
            self.n_strong = len(stream_list)
        self.n_tx = len(stream_list)
        T6 = np.arange(T)
        self.hpar_idx = np.zeros(self.n_hdata + T, np.int64)
        self.hdata_idx = np.zeros(self.n_hdata, np.int64)
        self.htail_idx = np.zeros(T, np.int64)
        self.tail_idx = np.zeros(2 * T if self.n_top else 0, np.int64)      # 先頭 T = パリティ、後ろ T = 情報
        self.ytail_idx = np.zeros(2 * T if self.y_items else 0, np.int64)
        self.parity_idx = np.zeros(self.n_top, np.int64)
        coef_items, coef_stream = [], []
        for pos, token in enumerate(stream_list):
            kind = token[0]
            if kind == "HP":
                self.hpar_idx[token[1]] = pos
            elif kind == "HD":
                self.hdata_idx[token[1]] = pos
            elif kind == "HT":
                self.htail_idx[token[1]] = pos
            elif kind == "CP":
                self.tail_idx[token[1]] = pos
            elif kind == "CT":
                self.tail_idx[T + token[1]] = pos
            elif kind == "YP":
                self.ytail_idx[token[1]] = pos
            elif kind == "YT":
                self.ytail_idx[T + token[1]] = pos
            elif kind == "P":
                self.parity_idx[token[1]] = pos
            elif kind == "C":
                coef_items.append(token[1:])
                coef_stream.append(pos)
        self.coef_items = coef_items
        self.coef_stream_idx = np.asarray(coef_stream, np.int64)
        self.n_coef_bits = len(coef_items)
        self.n_base_bits = sum(1 for t in strong if t[0] == "C")
        index_of = {item: i for i, item in enumerate(coef_items)}
        self.top_coef_idx = np.asarray([index_of[item] for item in top_item], np.int64)
        self.top_stream_idx = self.coef_stream_idx[self.top_coef_idx]
        self.n_keystream = self.n_body + self.n_coef_bits       # 1フレームに使うキーストリームのビット数
        # Haar係数ビットの属性 (受信側で誤差のエネルギーを見積もるため)
        self.coef_ch = np.array([0 if t[0] == "M" else 1 for t in self.coef_items], np.int64)
        self.coef_k = np.array([t[1] for t in self.coef_items], np.int64)
        self.coef_pos = np.array([t[3] for t in self.coef_items], np.int64)
        # 係数を (M→S, 帯域 低→高, 係数 先頭→末尾) で一列に並べたときの番号
        self.coef_offset = {}
        off = 0
        for ch, bits in (("M", p.bits_m), ("S", p.bits_s)):
            for k, b in enumerate(bits):
                if b > 0:
                    self.coef_offset[(ch, k)] = off
                    off += p.ncoef(k)
        self.n_coef = off
        self.coef_flat = np.array([self.coef_offset[(t[0], t[1])] + t[2] for t in self.coef_items], np.int64)

    def header_info(self, stream):
        """送信ビット列からヘッダの情報bit (CRC込み) を取り出す (振幅部にある)"""
        return np.asarray(stream)[self.hdata_idx].copy()

    def with_header(self, stream, header_x):
        """ヘッダの情報bitを差し替え、パリティと終端を作り直した送信ビット列を返す (試験・解析用)"""
        out = np.array(stream, np.int64)
        parity, tail = fec.rsc_parity(np.asarray(header_x, np.int64))
        out[self.hpar_idx] = parity
        out[self.hdata_idx] = header_x
        out[self.htail_idx] = tail
        return out

    def _crc_inputs(self, prot, top, ymsb):
        core = np.concatenate([prot[self.core_prot_indices], top[self.core_top_indices],
                               ymsb[self.core_y_indices]])
        high = np.concatenate([prot[self.high_prot_indices], top[self.high_top_indices],
                               ymsb[self.high_y_indices]])
        return core, high

    def y_u(self, bd: BlockData):
        """Y帯域の仮数 (オフセットバイナリ。最上位bitが位相、残りが半径の段)"""
        return np.asarray([int(bd.mant[ch][k][j]) + offset_of(self.p.y_bits, self.p, ch, k)
                           for ch, k, j in self.y_items], np.int64)

    def y_parts(self, bd: BlockData):
        """Y専用シンボルに載せる (u, 最上位bitのパリティ) と、ヘッダ部の終端bit (12個)"""
        u = self.y_u(bd)
        msb = u >> (self.p.y_bits - 1)
        parity, tail = fec.rsc_parity(msb)
        return u, parity[: len(u)], np.concatenate([parity[len(u):], tail])

    # ---------------------------------------------------------------- 送信側
    def pack(self, bd: BlockData, stream_id: int, counter: int, keystream=None):
        """keystream: 暗号化するとき、このフレームのキーストリーム (n_keystream ビット)"""
        p = self.p
        tag = _bits(p.format_id, 2)
        if self.encrypted:
            hdr = _bits(p.pid, 4) + _bits(stream_id, 1) + [1] + tag + _bits(counter & 0xFFFFFF, 24)
        else:
            counter_bits = self.header_bits - 8
            hdr = (_bits(p.pid, 4) + _bits(stream_id, 1) + [0] + tag
                   + _bits(counter & ((1 << counter_bits) - 1), counter_bits))
        prot = list(hdr)
        bits_of = {"M": p.bits_m, "S": p.bits_s}
        for ch, k in self.exp_items:
            prot += _bits(bd.eidx[ch][k], p.exp_bits)
        for ch, k, j in self.attn_items:
            prot.append(int(bd.attn[ch][k][j]))
        prot = np.array(prot, np.int64)
        coef = np.array([(int(bd.mant[ch][k][j] + offset_of(bits_of[ch][k], p, ch, k)) >> pos) & 1
                         for ch, k, j, pos in self.coef_items], np.int64)
        if self.encrypted:
            prot[self.header_bits:] ^= keystream[: self.n_body]
            coef = coef ^ keystream[self.n_body:]
        top = coef[self.top_coef_idx]
        if self.y_items:
            y_u, _, y_tail = self.y_parts(bd)
            ymsb = y_u >> (p.y_bits - 1)
        else:
            ymsb, y_tail = np.zeros(0, np.int64), np.zeros(0, np.int64)
        core, high = self._crc_inputs(prot, top, ymsb)
        checks = [fec.crc_core(core)]
        if self.has_high_crc:
            checks.append(fec.crc_high(high))
        stream = np.zeros(self.n_tx, np.int64)
        header_x = np.concatenate([prot, *checks])
        header_parity, header_tail = fec.rsc_parity(header_x)
        stream[self.hpar_idx] = header_parity
        stream[self.hdata_idx] = header_x
        stream[self.htail_idx] = header_tail
        if self.n_top:
            parity, tail = fec.rsc_parity(top)
            stream[self.parity_idx] = parity[: self.n_top]
            stream[self.tail_idx] = np.concatenate([parity[self.n_top:], tail])
        stream[self.ytail_idx] = y_tail
        stream[self.coef_stream_idx] = coef
        return stream

    # ---------------------------------------------------------------- 受信側
    def unpack(self, soft, bits, keystream_for=None, y_soft=None):
        """
        soft: 送信ビット列全体の軟値 (正 = 0 らしい。足りない分は0とみなす。ヘッダのデータは振幅部にあるので、振幅部の軟値も必要)、
        bits: 送信ビット列全体の硬判定 (n_tx 個)
        y_soft: Y帯域があるとき、専用シンボルの位相から得た (最上位bitの軟値, パリティの軟値) (Y係数の数ずつ。省略時は消失扱い)
        keystream_for: 暗号化するとき、ヘッダ (dict) からキーストリームを返す関数。使ったキーストリームは header["ks"]
        返り値: (BlockData, header dict) / 基本CRCが合わなければ (None, None)。
        高域CRCだけが不一致なら header["high_ok"] が False。header["top_bits"] は訂正後の上位K bit (平文)。
        """
        p = self.p
        soft = np.pad(np.asarray(soft, float), (0, max(0, self.n_tx - len(soft))))
        bits = np.pad(np.asarray(bits, np.int64), (0, max(0, self.n_tx - len(bits))))
        prot = fec.rsc_decode(soft[self.hdata_idx], soft[self.hpar_idx], soft[self.htail_idx])
        body = prot[: self.n_prot]
        if self.n_top:
            top = fec.rsc_decode(soft[self.top_stream_idx],
                                 np.concatenate([soft[self.parity_idx], soft[self.tail_idx[: fec.K - 1]]]),
                                 soft[self.tail_idx[fec.K - 1:]])
        else:
            top = np.zeros(0, np.int64)
        if self.y_items:
            if y_soft is None:                         # 位相の情報が無ければ消失扱い
                y_soft = (np.zeros(len(self.y_items)), np.zeros(len(self.y_items)))
            msb_soft, parity_soft = (np.asarray(v, float) for v in y_soft)
            ymsb = fec.rsc_decode(msb_soft, np.concatenate([parity_soft, soft[self.ytail_idx[: fec.K - 1]]]),
                                  soft[self.ytail_idx[fec.K - 1:]])
        else:
            ymsb = np.zeros(0, np.int64)
        core, high = self._crc_inputs(body, top, ymsb)
        n_core = fec.CRC_CORE[0]
        if not np.array_equal(fec.crc_core(core), prot[self.n_prot:self.n_prot + n_core]):
            return None, None
        high_ok = (not self.has_high_crc or
                   np.array_equal(fec.crc_high(high), prot[self.n_prot + n_core:]))
        hdr = body[: self.header_bits]
        val = lambda bb: int("".join(str(int(v)) for v in bb), 2)
        header = {"pid": val(hdr[0:4]), "stream": int(hdr[4]), "encrypted": bool(hdr[5]),
                  "counter": val(hdr[8: self.header_bits]), "high_ok": high_ok}
        if (header["pid"] != p.pid or header["encrypted"] != self.encrypted
                or val(hdr[6:8]) != p.format_id):
            return None, None
        coef_bits = bits[self.coef_stream_idx].copy()
        coef_bits[self.top_coef_idx] = top                 # 訂正後の上位K bit (暗号化時は暗号文)
        if self.encrypted:
            ks = keystream_for(header)
            body = body.copy()
            body[self.header_bits:] ^= ks[: self.n_body]
            coef_bits ^= ks[self.n_body:]
            top = coef_bits[self.top_coef_idx]
            header["ks"] = ks
        header["top_bits"] = top
        header["y_msb"] = ymsb
        i = self.header_bits
        eidx = {"M": [None] * p.nbands, "S": [None] * p.nbands}
        attn = {"M": [None] * p.nbands, "S": [None] * p.nbands}
        bits_of = {"M": p.bits_m, "S": p.bits_s}
        u = {ch: [np.zeros(p.ncoef(k), np.int64) if bits_of[ch][k] > 0 else None
                  for k in range(p.nbands)] for ch in ("M", "S")}
        for ch, k in self.exp_items:
            width = p.exp_bits
            eidx[ch][k] = val(body[i:i + width])
            i += width
        for ch, k in self.exp_items:
            count = p.attenuator_bits(ch, k)
            attn[ch][k] = body[i:i + count].copy()
            i += count
        for (ch, k, j), bit in zip(self.y_items, ymsb):
            u[ch][k][j] |= int(bit) << (p.y_bits - 1)
        for (ch, k, j, pos), bit in zip(self.coef_items, coef_bits):
            u[ch][k][j] |= int(bit) << pos
        mant = {ch: [None if u[ch][k] is None else
                     np.clip(u[ch][k] - offset_of(bits_of[ch][k], p, ch, k),
                             qmin_of(bits_of[ch][k], p, ch, k), qmax_of(bits_of[ch][k]))
                     for k in range(p.nbands)] for ch in ("M", "S")}
        bd = BlockData(mant, eidx, attn)
        return bd, header


class YLayout(Layout):
    """高域の仮数をHaar係数部から外し、1係数1複素シンボルの専用シンボルへ移す配置。"""

    def __init__(self, profile: Profile):
        if not profile.has_y:
            raise ValueError("Yプロファイルが必要です")
        super().__init__(profile, with_y=True)
        self.n_y = len(self.y_items)
