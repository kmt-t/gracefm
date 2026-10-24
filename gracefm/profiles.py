"""
プロファイル定義。

各プロファイルは、サンプリング周波数・ブロック長・分解段数・帯域ごとのビット割り当て・
FEC で保護する仮数の上位ビット数・変調方式を固定する。受信機はフレームヘッダの
プロファイル ID からこれらを決める。
"""
from dataclasses import dataclass, replace
from typing import Optional, Tuple


@dataclass(frozen=True)
class Profile:
    pid: int                    # ヘッダに載せる ID (4bit)。現行カタログ内で一意（0・12～15は予約）
    name: str
    fs: int                     # サンプリング周波数 [Hz]
    block: int                  # 1ブロック = 1フレームのサンプル数
    levels: int                 # Haar の詳細帯域数。nbands は低域近似を加えた係数群数
    bits_m: Tuple[int, ...]     # M (= (L+R)/2) の帯域ごとの仮数ビット数 (低域→高域)。0 = 送らない
    bits_s: Tuple[int, ...]     # S (= (L-R)/2) の帯域ごとの仮数ビット数
    exp_bits: int = 4           # 帯域ごとの共有指数のビット数 (16段 × 約6dB)
    protect_k: int = 2          # FEC で保護する仮数の上位ビット数
    modulation: str = "qpsk"    # "qpsk" | "qam16h" | "qam64h"
    alpha: float = 1.0          # 階層 QAM の象限間距離パラメータ (1 = 通常の QAM)
    pulse_beta: float = 0.25    # スペクトル評価用 RRC パルスのロールオフ
    pulse_span: int = 16        # 同パルスの長さ [シンボル]
    pf_iters: int = 4           # 受信側ポストフィルタの繰り返し回数 (全プロファイル共通。docs/SPEC.md「フレームと受信」)
    base_m: Optional[Tuple[int, ...]] = None   # 階層化したときの基本層の仮数ビット数 (None = 階層化なし)
    base_s: Optional[Tuple[int, ...]] = None   # 同 S。基本層を超えるビット (拡張層) は変調の弱い位置に入る
    base_extra: Tuple[Tuple[str, int, int], ...] = ()  # 強い位置の余りへ次位bitを昇格する (成分, 帯域, 係数)
    exp_bits_m: Optional[Tuple[int, ...]] = None  # 評価用: M の帯域別指数幅。None は exp_bits を使う
    exp_bits_s: Optional[Tuple[int, ...]] = None  # 評価用: S の帯域別指数幅
    exp_offset_m: Optional[Tuple[int, ...]] = None  # 評価用: M の固定指数オフセット emin
    exp_offset_s: Optional[Tuple[int, ...]] = None  # 評価用: S の固定指数オフセット emin
    attn_group_m: Optional[Tuple[int, ...]] = None  # 0=無効、正数=その係数数ごとに1bit
    attn_group_s: Optional[Tuple[int, ...]] = None
    hybrid_start_k: Optional[int] = None  # 実験方式: この帯域から 1係数/複素シンボル
    hybrid_amplitude: float = 0.08 * 7.5 / 31.5  # 8bit時の隣接半径間隔 (正規化前)
    hybrid_bits: int = 8                  # 上位2bitが位相、残りは連続値で推定する半径
    hybrid_channels: Tuple[str, ...] = ("M", "S")
    experimental_tag: int = 3             # 2bitの形式識別子。値3はビット列11を表し、世代番号ではない。

    def __post_init__(self):
        if not 0 <= self.pid < 16 or not 0 <= self.experimental_tag < 4:
            raise ValueError("プロファイルIDは4bit、実験タグは2bitにしてください")
        if not 0 < self.pulse_beta <= 1 or self.pulse_span < 2 or self.pulse_span % 2:
            raise ValueError("RRC パルスのロールオフは (0, 1]、長さは正の偶数にしてください")
        if len(self.bits_m) != self.nbands or len(self.bits_s) != self.nbands:
            raise ValueError("仮数ビット割当の長さが帯域数と一致しません")
        for field in ("exp_bits_m", "exp_bits_s", "exp_offset_m", "exp_offset_s", "attn_group_m", "attn_group_s"):
            values = getattr(self, field)
            if values is not None and len(values) != self.nbands:
                raise ValueError(f"{field} は {self.nbands} 帯域ぶん必要です")
        for field in ("exp_bits_m", "exp_bits_s"):
            values = getattr(self, field)
            if values is not None and any(not 1 <= v <= 8 for v in values):
                raise ValueError(f"{field} は 1〜8 bit にしてください")
        for ch, bits in (("M", self.bits_m), ("S", self.bits_s)):
            for k, b in enumerate(bits):
                group = self.attenuator_group(ch, k)
                if group < 0 or (group and (b == 0 or self.ncoef(k) % group)):
                    raise ValueError("アッテネータの区間長は送信帯域の係数数を割り切る正数にしてください")
        if (self.base_m is None) != (self.base_s is None):
            raise ValueError("M/Sの基本層は両方指定してください")
        for ch, k, j in self.base_extra:
            if not self.layered or ch not in ("M", "S") or not 0 <= k < self.nbands or not 0 <= j < self.ncoef(k):
                raise ValueError("基本層の追加割当が不正です")
        if self.layered:
            for ch, widths in (("M", self.bits_m), ("S", self.bits_s)):
                base = self.base_m if ch == "M" else self.base_s
                if len(base) != self.nbands:
                    raise ValueError("基本層の帯域数が不正です")
                for k, width in enumerate(widths):
                    for j in range(self.ncoef(k)):
                        if not (min(self.protect_k, width) <= self.base_bits(ch, k, j) <= width):
                            raise ValueError("基本層幅が保護bit数または全幅と矛盾しています")
        if self.hybrid_start_k is not None:
            if self.hybrid_start_k not in (4, 5, 6) or self.fs not in (32000, 48000) or self.block != 64:
                raise ValueError("ハイブリッド境界は32/48kHz・64サンプルの帯域4, 5, 6から選んでください")
            if not 6 <= self.hybrid_bits <= 16:
                raise ValueError("ハイブリッド仮数幅は6〜16bitにしてください")
            half = (2 ** (self.hybrid_bits - 2) - 1) / 2
            if not 0 < self.hybrid_amplitude < 1 / half:
                raise ValueError("半径の最小値が正になる変調度にしてください")
            if self.protect_k not in (1, 2):
                raise ValueError("ハイブリッド方式は仮数上位1または2bitのFEC保護が必要です")
            if not self.hybrid_channels or any(ch not in ("M", "S") for ch in self.hybrid_channels):
                raise ValueError("ハイブリッド対象はM/Sから選んでください")
            for ch in self.hybrid_channels:
                bits = self.bits_m if ch == "M" else self.bits_s
                if any(b not in (0, self.hybrid_bits) for b in bits[self.hybrid_start_k:]):
                    raise ValueError("ハイブリッド帯域の仮数幅が設定値と一致しません")

    @property
    def hybrid(self) -> bool:
        return self.hybrid_start_k is not None

    def exponent_bits(self, ch: str, k: int) -> int:
        values = self.exp_bits_m if ch == "M" else self.exp_bits_s
        return self.exp_bits if values is None else values[k]

    def exponent_offset(self, ch: str, k: int) -> Optional[int]:
        values = self.exp_offset_m if ch == "M" else self.exp_offset_s
        return None if values is None else values[k]

    def attenuator_group(self, ch: str, k: int) -> int:
        values = self.attn_group_m if ch == "M" else self.attn_group_s
        return 0 if values is None else values[k]

    def attenuator_bits(self, ch: str, k: int) -> int:
        group = self.attenuator_group(ch, k)
        return self.ncoef(k) // group if group else 0

    @property
    def layered(self) -> bool:
        return self.base_m is not None

    def base_bits(self, ch: str, k: int, coefficient: int | None = None) -> int:
        """帯域共通幅。coefficient 指定時は昇格bitも含む実効幅。非階層は全幅。"""
        if not self.layered:
            return (self.bits_m if ch == "M" else self.bits_s)[k]
        return ((self.base_m if ch == "M" else self.base_s)[k]
                + (self.base_extra.count((ch, k, coefficient)) if coefficient is not None else 0))

    @property
    def nbands(self) -> int:
        """独立に符号化する係数群の数（低域近似1群＋詳細帯域 levels 群）。"""
        return self.levels + 1

    @property
    def frame_ms(self) -> float:
        """ブロック長 (= 1フレームが運ぶ音声の長さ、エンコーダの蓄積時間) [ms]。伝送込みの遅延ではない
        (伝送込みは gracefm.timing.min_latency。処理時間 0 で、この値の 2倍)"""
        return self.block / self.fs * 1000.0

    @property
    def frames_per_sec(self) -> float:
        return self.fs / self.block

    def ncoef(self, k: int) -> int:
        """帯域 k の 1ブロックあたりの係数の数"""
        return self.block >> band_level(k, self.levels)

    def payload_bits(self) -> int:
        """音声データ (指数 + 区間アッテネータ + 仮数) の 1ブロックあたりのビット数"""
        tot = 0
        for ch, bits in (("M", self.bits_m), ("S", self.bits_s)):
            for k, b in enumerate(bits):
                if b > 0:
                    tot += self.exponent_bits(ch, k) + self.attenuator_bits(ch, k) + self.ncoef(k) * b
        return tot

    def audio_kbps(self) -> float:
        return self.payload_bits() * self.frames_per_sec / 1000.0


def band_level(k: int, levels: int) -> int:
    """係数群 k の分解段数（k=0 は低域近似、k=1..levels は詳細帯域）。"""
    return levels if k == 0 else levels + 1 - k


def band_edges(fs: int, levels: int):
    edges = [(0.0, fs / 2 ** (levels + 1))]
    for k in range(1, levels + 1):
        edges.append((fs / 2 ** (levels + 2 - k), fs / 2 ** (levels + 1 - k)))
    return edges


def make_hybrid(base: Profile, name: str, pid: int, start_k: int = 5,
                amplitude: float = 0.08, mantissa_bits: int = 8,
                channels: Tuple[str, ...] = ("M",), experimental_tag: int = 3) -> Profile:
    """対象成分の境界以上だけを実験方式にし、他の成分は既存主系のままにする。

    amplitude は6bit時の隣接半径間隔として指定し、幅変更時は最大変調度を保つ。
    """
    if not 6 <= mantissa_bits <= 16:
        raise ValueError("ハイブリッド仮数幅は6〜16bitにしてください")

    def widths(ch, bits):
        return tuple(b if k < start_k or b == 0 or ch not in channels else mantissa_bits
                     for k, b in enumerate(bits))

    offsets_m = base.exp_offset_m
    attenuator_m = base.attn_group_m
    if "M" in channels:
        groups = list(attenuator_m or (0,) * base.nbands)
        for k in range(start_k, base.nbands):
            groups[k] = max(1, base.ncoef(k) // 8)
        attenuator_m = tuple(groups)
    # モノラル A4 の指数オフセットは15/13bit仮数向けなので、
    # ハイブリッド仮数幅に応じて量子化ステップの範囲をずらす。
    if base.name == "B200M":
        offsets_m = tuple(v if k < start_k else -19 - (mantissa_bits - 6)
                          for k, v in enumerate(offsets_m))
    # 階層Yではデジタル部の強い位置を基本層に使う。
    base_m, base_s = base.base_m, base.base_s
    return replace(base, pid=pid, name=name, bits_m=widths("M", base.bits_m),
                   bits_s=widths("S", base.bits_s),
                   base_m=base_m, base_s=base_s,
                   base_extra=base.base_extra,
                   exp_offset_m=offsets_m,
                   exp_offset_s=base.exp_offset_s, attn_group_m=attenuator_m,
                   hybrid_start_k=start_k,
                   hybrid_amplitude=amplitude * 7.5 / ((2 ** (mantissa_bits - 2) - 1) / 2),
                   hybrid_bits=mantissa_bits, hybrid_channels=channels,
                   experimental_tag=experimental_tag)

# Standard catalog. All active M/S components have interval attenuation.
# IDs: 1–4 32kHz main, 5–6 32kHz secondary, 7–10 48kHz main, 11 48kHz secondary. 0 and 12–15 are reserved.
# Every row has the same fields; bit widths are explicit, never expanded implicitly.
PROFILE_MATRIX = (
    dict(
        pid=1,
        name='B200M',
        base_extra=(),
        fs=32000,
        bits_m=(16, 16, 16, 16, 16, 15, 13),
        bits_s=(0, 0, 0, 0, 0, 0, 0),
        protect_k=1,
        modulation='qam16h',
        alpha=5.0,
        base_m=(9, 9, 9, 9, 8, 6, 4),
        base_s=(0, 0, 0, 0, 0, 0, 0),
        attn_group_m=(0, 0, 0, 0, 0, 0, 4),
        attn_group_s=(0, 0, 0, 0, 0, 0, 0),
        exp_offset_m=(-26, -26, -27, -27, -28, -27, -26),
        exp_offset_s=None,
        pulse_beta=0.25,
        pulse_span=16,
        hybrid_start_k=None,
        hybrid_channels=('M', 'S'),
        hybrid_bits=8,
        hybrid_amplitude=0.019047619047619046,
    ),
    dict(
        pid=2,
        name='B200',
        base_extra=(),
        fs=32000,
        bits_m=(16, 16, 16, 13, 10, 7, 7),
        bits_s=(14, 12, 11, 8, 7, 6, 6),
        protect_k=1,
        modulation='qam16h',
        alpha=5.0,
        base_m=(12, 11, 9, 7, 3, 1, 1),
        base_s=(7, 6, 5, 3, 2, 2, 2),
        attn_group_m=(0, 0, 0, 0, 0, 0, 8),
        attn_group_s=(0, 0, 0, 0, 0, 0, 4),
        exp_offset_m=(-25, -25, -26, -23, -21, -18, -19),
        exp_offset_s=(-23, -21, -21, -18, -18, -18, -19),
        pulse_beta=0.1,
        pulse_span=32,
        hybrid_start_k=None,
        hybrid_channels=('M', 'S'),
        hybrid_bits=8,
        hybrid_amplitude=0.019047619047619046,
    ),
    dict(
        pid=3,
        name='B200MY',
        base_extra=(),
        fs=32000,
        bits_m=(16, 16, 16, 16, 16, 8, 8),
        bits_s=(0, 0, 0, 0, 0, 0, 0),
        protect_k=1,
        modulation='qam16h',
        alpha=5.0,
        base_m=(9, 9, 9, 9, 8, 6, 4),
        base_s=(0, 0, 0, 0, 0, 0, 0),
        attn_group_m=(0, 0, 0, 0, 0, 2, 4),
        attn_group_s=(0, 0, 0, 0, 0, 0, 0),
        exp_offset_m=(-26, -26, -27, -27, -28, -21, -21),
        exp_offset_s=None,
        pulse_beta=0.25,
        pulse_span=16,
        hybrid_start_k=5,
        hybrid_channels=('M',),
        hybrid_bits=8,
        hybrid_amplitude=0.019047619047619046,
    ),
    dict(
        pid=4,
        name='B200Y',
        base_extra=(),
        fs=32000,
        bits_m=(12, 11, 9, 7, 4, 8, 8),
        bits_s=(7, 6, 5, 2, 2, 0, 2),
        protect_k=1,
        modulation='qam16h',
        alpha=5.0,
        base_m=(1, 1, 1, 1, 1, 1, 1),
        base_s=(1, 1, 1, 1, 1, 0, 1),
        attn_group_m=(0, 0, 0, 0, 0, 2, 4),
        attn_group_s=(0, 0, 0, 0, 0, 0, 4),
        exp_offset_m=None,
        exp_offset_s=None,
        pulse_beta=0.1,
        pulse_span=32,
        hybrid_start_k=5,
        hybrid_channels=('M',),
        hybrid_bits=8,
        hybrid_amplitude=0.019047619047619046,
    ),
    dict(
        pid=5,
        name='SUB50M',
        base_extra=(),
        fs=32000,
        bits_m=(8, 7, 6, 5, 3, 0, 0),
        bits_s=(0, 0, 0, 0, 0, 0, 0),
        protect_k=1,
        modulation='qpsk',
        alpha=1.0,
        base_m=None,
        base_s=None,
        attn_group_m=(0, 0, 0, 0, 4, 0, 0),
        attn_group_s=(0, 0, 0, 0, 0, 0, 0),
        exp_offset_m=None,
        exp_offset_s=None,
        pulse_beta=0.25,
        pulse_span=16,
        hybrid_start_k=None,
        hybrid_channels=('M', 'S'),
        hybrid_bits=8,
        hybrid_amplitude=0.019047619047619046,
    ),
    dict(
        pid=6,
        name='SUB100',
        base_extra=(),
        fs=32000,
        bits_m=(10, 9, 8, 6, 4, 2, 0),
        bits_s=(6, 5, 4, 2, 0, 0, 0),
        protect_k=1,
        modulation='qpsk',
        alpha=1.0,
        base_m=None,
        base_s=None,
        attn_group_m=(0, 0, 0, 0, 0, 4, 0),
        attn_group_s=(0, 0, 0, 4, 0, 0, 0),
        exp_offset_m=None,
        exp_offset_s=None,
        pulse_beta=0.25,
        pulse_span=16,
        hybrid_start_k=None,
        hybrid_channels=('M', 'S'),
        hybrid_bits=8,
        hybrid_amplitude=0.019047619047619046,
    ),
    dict(
        pid=7,
        name='M700M',
        base_extra=(),
        fs=48000,
        bits_m=(16, 14, 13, 12, 11, 9, 7),
        bits_s=(0, 0, 0, 0, 0, 0, 0),
        protect_k=2,
        modulation='qam16h',
        alpha=5.0,
        base_m=(2, 2, 2, 2, 2, 2, 2),
        base_s=(0, 0, 0, 0, 0, 0, 0),
        attn_group_m=(0, 0, 0, 0, 0, 0, 4),
        attn_group_s=(0, 0, 0, 0, 0, 0, 0),
        exp_offset_m=None,
        exp_offset_s=None,
        pulse_beta=0.25,
        pulse_span=16,
        hybrid_start_k=None,
        hybrid_channels=('M', 'S'),
        hybrid_bits=8,
        hybrid_amplitude=0.019047619047619046,
    ),
    dict(
        pid=8,
        name='M700',
        base_extra=(),
        fs=48000,
        bits_m=(16, 14, 13, 12, 11, 9, 7),
        bits_s=(12, 9, 8, 9, 7, 5, 3),
        protect_k=2,
        modulation='qam16h',
        alpha=5.0,
        base_m=(2, 2, 2, 2, 2, 2, 2),
        base_s=(2, 2, 2, 2, 2, 2, 2),
        attn_group_m=(0, 0, 0, 0, 0, 0, 4),
        attn_group_s=(0, 0, 0, 0, 0, 0, 4),
        exp_offset_m=None,
        exp_offset_s=None,
        pulse_beta=0.25,
        pulse_span=16,
        hybrid_start_k=None,
        hybrid_channels=('M', 'S'),
        hybrid_bits=8,
        hybrid_amplitude=0.019047619047619046,
    ),
    dict(
        pid=9,
        name='M700MY',
        base_extra=(),
        fs=48000,
        bits_m=(16, 14, 13, 12, 11, 8, 8),
        bits_s=(0, 0, 0, 0, 0, 0, 0),
        protect_k=2,
        modulation='qam16h',
        alpha=5.0,
        base_m=(2, 2, 2, 2, 2, 2, 2),
        base_s=(0, 0, 0, 0, 0, 0, 0),
        attn_group_m=(0, 0, 0, 0, 0, 2, 4),
        attn_group_s=(0, 0, 0, 0, 0, 0, 0),
        exp_offset_m=None,
        exp_offset_s=None,
        pulse_beta=0.25,
        pulse_span=16,
        hybrid_start_k=5,
        hybrid_channels=('M',),
        hybrid_bits=8,
        hybrid_amplitude=0.019047619047619046,
    ),
    dict(
        pid=10,
        name='M700Y',
        base_extra=(),
        fs=48000,
        bits_m=(16, 14, 13, 12, 11, 8, 8),
        bits_s=(12, 9, 8, 9, 7, 5, 3),
        protect_k=2,
        modulation='qam16h',
        alpha=5.0,
        base_m=(2, 2, 2, 2, 2, 2, 2),
        base_s=(2, 2, 2, 2, 2, 2, 2),
        attn_group_m=(0, 0, 0, 0, 0, 2, 4),
        attn_group_s=(0, 0, 0, 0, 0, 0, 4),
        exp_offset_m=None,
        exp_offset_s=None,
        pulse_beta=0.25,
        pulse_span=16,
        hybrid_start_k=5,
        hybrid_channels=('M',),
        hybrid_bits=8,
        hybrid_amplitude=0.019047619047619046,
    ),
    dict(
        pid=11,
        name='SUB100-48K',
        base_extra=(),
        fs=48000,
        bits_m=(9, 8, 7, 6, 4, 0, 0),
        bits_s=(5, 4, 3, 0, 0, 0, 0),
        protect_k=1,
        modulation='qpsk',
        alpha=1.0,
        base_m=None,
        base_s=None,
        attn_group_m=(0, 0, 0, 0, 4, 0, 0),
        attn_group_s=(0, 0, 2, 0, 0, 0, 0),
        exp_offset_m=None,
        exp_offset_s=None,
        pulse_beta=0.25,
        pulse_span=16,
        hybrid_start_k=None,
        hybrid_channels=('M', 'S'),
        hybrid_bits=8,
        hybrid_amplitude=0.019047619047619046,
    ),
)

PROFILES = {row["name"]: Profile(block=64, levels=6, experimental_tag=3, **row)
            for row in PROFILE_MATRIX}
BY_ID = {p.pid: p for p in PROFILES.values()}
BY_HEADER = {(p.pid, p.experimental_tag): p for p in PROFILES.values()}
if len(BY_ID) != len(PROFILES):
    raise ValueError("プロファイルIDが重複しています")
for _profile in PROFILES.values():
    for _ch, _bits in (("M", _profile.bits_m), ("S", _profile.bits_s)):
        if any(_bits) and not any(_profile.attenuator_bits(_ch, k) for k in range(_profile.nbands)):
            raise ValueError(f"{_profile.name}: {_ch} の標準アッテネータがありません")
