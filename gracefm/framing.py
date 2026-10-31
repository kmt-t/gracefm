"""
フレームの送信 (pack) と受信 (unpack)。ビット配置は gracefm.layout.Layout が決める。

pack  : BlockData → 送信ビット列 (ヘッダ、CRC、系統符号のパリティ、仮数を Layout の位置へ置く。暗号化はここで行う)
unpack: 軟値・硬判定 → Unpacked (純粋な関数。救済や暗号の番号管理は持たない。受信側は gracefm.decoder)。
        ヘッダとYの最上位bit、係数の上位K bit は軟判定ビタビで訂正し、CRCを検査する。
"""
from dataclasses import dataclass

import numpy as np

from . import fec
from .codec import BlockData, offset_of, qmax_of, qmin_of
from .layout import Layout, int_bits


def coefficient_bits(lay: Layout, bd: BlockData):
    """係数の仮数 bit を係数の並びで返す (Y 帯域を除く)。オフセットを足した値の、各係数の位置 (coef_pos) の bit。pack と硬判定の再構成が使う"""
    flat_mant = np.concatenate([np.asarray(bd.mant[ch][k], np.int64) for ch, k in lay.coef_groups])
    return ((flat_mant[lay.coef_flat] + lay.coef_offset_bits) >> lay.coef_pos) & 1


def pack(lay: Layout, bd: BlockData, stream_id: int, counter: int, keystream=None):
    """keystream: 暗号化するとき、このフレームのキーストリーム (n_keystream ビット)"""
    p = lay.p
    tag = int_bits(p.format_id, 2)
    if lay.encrypted:
        hdr = int_bits(p.pid, 4) + int_bits(stream_id, 1) + [1] + tag + int_bits(counter & 0xFFFFFF, 24)
    else:
        counter_bits = lay.header_bits - 8
        hdr = (int_bits(p.pid, 4) + int_bits(stream_id, 1) + [0] + tag
               + int_bits(counter & ((1 << counter_bits) - 1), counter_bits))
    prot = list(hdr)
    for ch, k in lay.exp_items:
        prot += int_bits(bd.eidx[ch][k], p.exp_bits)
    for ch, k, j in lay.attn_items:
        prot.append(int(bd.attn[ch][k][j]))
    prot = np.array(prot, np.int64)
    coef = coefficient_bits(lay, bd)
    if lay.encrypted:
        prot[lay.header_bits:] ^= keystream[: lay.n_body]
        coef = coef ^ keystream[lay.n_body:]
    top = coef[lay.top_coef_idx]
    if lay.y_items:
        y_u, _, y_tail = lay.y_parts(bd)
        ymsb = y_u >> (p.y_bits - 1)
    else:
        ymsb, y_tail = np.zeros(0, np.int64), np.zeros(0, np.int64)
    core, high = lay._crc_inputs(prot, top, ymsb)
    checks = [fec.crc_core(core)]
    if lay.has_high_crc:
        checks.append(fec.crc_high(high))
    stream = np.zeros(lay.n_tx, np.int64)
    header_x = np.concatenate([prot, *checks])
    header_parity, header_tail = fec.rsc_parity(header_x)
    stream[lay.hpar_idx] = header_parity
    stream[lay.hdata_idx] = header_x
    stream[lay.htail_idx] = header_tail
    if lay.n_top:
        parity, tail = fec.rsc_parity(top)
        stream[lay.parity_idx] = parity[: lay.n_top]
        stream[lay.tail_idx] = np.concatenate([parity[lay.n_top:], tail])
    stream[lay.ytail_idx] = y_tail
    stream[lay.coef_stream_idx] = coef
    return stream


@dataclass
class Unpacked:
    bd: BlockData                       # 復号した量子化結果
    pid: int                            # プロファイルの識別子
    stream: int                         # 系統番号
    counter: int                        # ヘッダの 24 bit のフレーム番号
    high_ok: bool                       # 高域CRCが通ったか (基本CRCは通っている)
    top_bits: np.ndarray                # 訂正後の上位K bit (平文)
    y_msb: np.ndarray                   # Y帯域の最上位bit (訂正後)
    ks: np.ndarray | None = None     # 暗号化時に使ったキーストリーム (本体部と係数部を続けたもの)
    frame_no: int | None = None      # 暗号化時の 40 bit のフレーム番号 (keystream_for が返す)


def _uint(bb):
    """0/1 の並び (先頭が上位) を整数にする"""
    return int("".join(str(int(v)) for v in bb), 2)


def unpack(lay: Layout, soft, bits, keystream_for=None, y_soft=None):
    """
    soft: 送信ビット列全体の軟値 (正 = 0 らしい。足りない分は0とみなす。ヘッダのデータは振幅部にあるので、振幅部の軟値も必要)、
    bits: 送信ビット列全体の硬判定 (n_tx 個)
    y_soft: Y帯域があるとき、専用シンボルの位相から得た (最上位bitの軟値, パリティの軟値) (Y係数の数ずつ。省略時は消失扱い)
    keystream_for: 暗号化するとき、(stream, counter24) → (キーストリーム, 40 bit のフレーム番号) を返す関数
    返り値: Unpacked / 基本CRCが合わない・プロファイルが違うときは None。
    高域CRCだけが不一致なら high_ok が False。
    """
    p = lay.p
    soft = np.pad(np.asarray(soft), (0, max(0, lay.n_tx - len(soft))))
    bits = np.pad(np.asarray(bits, np.int64), (0, max(0, lay.n_tx - len(bits))))
    prot = fec.rsc_decode(soft[lay.hdata_idx], soft[lay.hpar_idx], soft[lay.htail_idx])
    body = prot[: lay.n_prot]
    if lay.n_top:
        top = fec.rsc_decode(soft[lay.top_stream_idx],
                             np.concatenate([soft[lay.parity_idx], soft[lay.tail_idx[: fec.K - 1]]]),
                             soft[lay.tail_idx[fec.K - 1:]])
    else:
        top = np.zeros(0, np.int64)
    if lay.y_items:
        if y_soft is None:                         # 位相の情報が無ければ消失扱い
            y_soft = (np.zeros(len(lay.y_items), np.int64), np.zeros(len(lay.y_items), np.int64))
        msb_soft, parity_soft = (np.asarray(v, np.int64) for v in y_soft)
        ymsb = fec.rsc_decode(msb_soft, np.concatenate([parity_soft, soft[lay.ytail_idx[: fec.K - 1]]]),
                              soft[lay.ytail_idx[fec.K - 1:]])
    else:
        ymsb = np.zeros(0, np.int64)
    core, high = lay._crc_inputs(body, top, ymsb)
    n_core = fec.CRC_CORE[0]
    if not np.array_equal(fec.crc_core(core), prot[lay.n_prot:lay.n_prot + n_core]):
        return None
    high_ok = (not lay.has_high_crc or
               np.array_equal(fec.crc_high(high), prot[lay.n_prot + n_core:]))
    hdr = body[: lay.header_bits]
    pid, stream, encrypted, counter = _uint(hdr[0:4]), int(hdr[4]), bool(hdr[5]), _uint(hdr[8: lay.header_bits])
    if pid != p.pid or encrypted != lay.encrypted or _uint(hdr[6:8]) != p.format_id:
        return None
    coef_bits = bits[lay.coef_stream_idx].copy()
    coef_bits[lay.top_coef_idx] = top                 # 訂正後の上位K bit (暗号化時は暗号文)
    ks, frame_no = None, None
    if lay.encrypted:
        ks, frame_no = keystream_for(stream, counter)
        body = body.copy()
        body[lay.header_bits:] ^= ks[: lay.n_body]
        coef_bits ^= ks[lay.n_body:]
        top = coef_bits[lay.top_coef_idx]
    i = lay.header_bits
    eidx = {"M": [None] * p.nbands, "S": [None] * p.nbands}
    attn = {"M": [None] * p.nbands, "S": [None] * p.nbands}
    bits_of = {"M": p.bits_m, "S": p.bits_s}
    for ch, k in lay.exp_items:
        width = p.exp_bits
        eidx[ch][k] = _uint(body[i:i + width])
        i += width
    for ch, k in lay.exp_items:
        count = p.attenuator_bits(ch, k)
        attn[ch][k] = body[i:i + count].copy()
        i += count
    u_flat = lay.segment_sum(np.asarray(coef_bits, np.int64) << lay.coef_pos)
    if lay.n_y:
        u_flat[lay.y_flat] += np.asarray(ymsb, np.int64) << (p.y_bits - 1)
    mant = {"M": [None] * p.nbands, "S": [None] * p.nbands}
    for ch, k in lay.coef_groups:
        o, n = lay.coef_offset[(ch, k)], p.ncoef(k)
        mant[ch][k] = np.clip(u_flat[o:o + n] - offset_of(bits_of[ch][k], p, ch, k),
                              qmin_of(bits_of[ch][k], p, ch, k), qmax_of(bits_of[ch][k]))
    return Unpacked(BlockData(mant, eidx, attn), pid, stream, counter, high_ok, top, ymsb, ks, frame_no)
