"""
プロファイル定義。

各プロファイルは、サンプリング周波数・ブロック長・分解段数・帯域ごとのビット割り当て・
FEC で保護する仮数の上位ビット数・変調方式を固定する。受信機はフレームヘッダの
プロファイル ID からこれらを決める。
"""
from dataclasses import dataclass, replace
from fractions import Fraction
from math import gcd
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
    protect_k: int = 1          # ヘッダ部に入れてFECで保護する仮数の上位ビット数 (高域より低い帯域。protect_k_high が None なら全帯域)
    protect_k_high: Optional[int] = None   # 高域 H2/H1 (最後の2帯域) だけ別の保護bit数にするとき
    modulation: str = "qpsk"    # "qpsk" | "qam16h"
    alpha: int = 1              # 階層 QAM の象限間距離パラメータ (1 = 通常の QAM)
    pulse_beta_pct: int = 25    # RRC パルスのロールオフ [%]
    pulse_span: int = 16        # 同パルスの長さ [シンボル]
    base_m: Optional[Tuple[int, ...]] = None   # 階層化したときの基本層 (位相部に置くHaar係数の仮数bit。パリティを除く) のビット数 (None = 階層化なし)
    base_s: Optional[Tuple[int, ...]] = None   # 同 S。基本層を超えるbit (拡張層) は変調の弱い位置に入る
    attn_group_m: Optional[Tuple[int, ...]] = None  # 0=無効、正数=その係数数ごとに1bit
    attn_group_s: Optional[Tuple[int, ...]] = None
    y_start_k: Optional[int] = None  # Y: この帯域から 1係数/複素シンボル
    y_step: Tuple[int, int] = (2, 105)   # 隣接する半径の段の間隔 (正規化前) の分子・分母。7bit時 (半径の段が64) は 0.08 × 7.5 / 31.5 = 2/105
    y_bits: int = 7                  # 最上位bitは位相 (パリティと対)、残りは連続値で推定する半径
    y_channels: Tuple[str, ...] = ("M", "S")
    format_id: int = 3             # 2bitの形式識別子。値3はビット列11を表し、世代番号ではない。

    def __post_init__(self):
        if not 0 <= self.pid < 16 or not 0 <= self.format_id < 4:
            raise ValueError("プロファイルIDは4bit、形式識別子は2bitにしてください")
        if not 0 < self.pulse_beta_pct <= 100 or self.pulse_span < 2 or self.pulse_span % 2:
            raise ValueError("RRC パルスのロールオフは (0, 100] %、長さは正の偶数にしてください")
        if len(self.bits_m) != self.nbands or len(self.bits_s) != self.nbands:
            raise ValueError("仮数ビット割当の長さが帯域数と一致しません")
        for field in ("attn_group_m", "attn_group_s"):
            values = getattr(self, field)
            if values is not None and len(values) != self.nbands:
                raise ValueError(f"{field} は {self.nbands} 帯域ぶん必要です")
        for ch, bits in (("M", self.bits_m), ("S", self.bits_s)):
            for k, b in enumerate(bits):
                group = self.attenuator_group(ch, k)
                if group < 0 or (group and (b == 0 or self.ncoef(k) % group)):
                    raise ValueError("アッテネータの区間長は送信帯域の係数数を割り切る正数にしてください")
        if (self.base_m is None) != (self.base_s is None):
            raise ValueError("M/Sの基本層は両方指定してください")
        # 仮数bitとそのパリティは変調シンボルの位置対に揃える。QPSKは1シンボル2bit、階層16QAMは強い2bit＋弱い2bit。
        # 上位K bitのパリティ (K bit) と合わせて偶数になるよう、仮数幅は K と同じ偶奇にする。
        for ch, widths in (("M", self.bits_m), ("S", self.bits_s)):
            for k, width in enumerate(widths):
                if width and not self.y_band(ch, k) and (width + self.protect_bits(k)) % 2:
                    raise ValueError("仮数幅とFEC保護bit数の和は2の倍数にしてください")
        if self.layered:
            for ch, widths in (("M", self.bits_m), ("S", self.bits_s)):
                base = self.base_m if ch == "M" else self.base_s
                if len(base) != self.nbands:
                    raise ValueError("基本層の帯域数が不正です")
                for k, width in enumerate(widths):
                    if width == 0 or self.y_band(ch, k):
                        continue
                    kk = self.protect_bits(k)
                    if (base[k] + kk) % 2 or (width - base[k]) % 2 \
                            or not max(kk, 1) <= base[k] <= width - 2:
                        raise ValueError("位相部は基本層の仮数とパリティの和、振幅部は拡張層で、どちらも2の倍数にしてください。"
                                         "基本層はFEC保護bit数以上、拡張層は2以上です")
        if self.y_start_k is not None:
            if any(self.protect_bits(k) != 1 for k in range(self.y_start_k, self.nbands)):
                raise ValueError("Y帯域は最上位1bitをパリティで守る必要があります (protect_bits = 1)")
            if self.y_start_k not in range(self.nbands - 3, self.nbands) or self.fs not in (32000, 48000) or self.block != 64:
                raise ValueError("Y境界は32/48kHz・64サンプルの、高域側3帯域から選んでください")
            if not 5 <= self.y_bits <= 16:
                raise ValueError("Y仮数幅は6〜16bitにしてください")
            num, den = self.y_step
            if not 0 < num * (2 ** (self.y_bits - 1) - 1) < 2 * den:
                raise ValueError("半径の最小値が正になる変調度にしてください")
            if not self.y_channels or any(ch not in ("M", "S") for ch in self.y_channels):
                raise ValueError("Y対象はM/Sから選んでください")
            for ch in self.y_channels:
                bits = self.bits_m if ch == "M" else self.bits_s
                if any(b not in (0, self.y_bits) for b in bits[self.y_start_k:]):
                    raise ValueError("Y帯域の仮数幅が設定値と一致しません")

    @property
    def has_y(self) -> bool:
        return self.y_start_k is not None

    def attenuator_group(self, ch: str, k: int) -> int:
        values = self.attn_group_m if ch == "M" else self.attn_group_s
        return 0 if values is None else values[k]

    def attenuator_bits(self, ch: str, k: int) -> int:
        group = self.attenuator_group(ch, k)
        return self.ncoef(k) // group if group else 0

    @property
    def layered(self) -> bool:
        return self.base_m is not None

    def base_bits(self, ch: str, k: int) -> int:
        """基本層 (位相部に置くHaar係数の仮数bit。パリティを除く) のbit数。非階層は全幅。"""
        if not self.layered:
            return (self.bits_m if ch == "M" else self.bits_s)[k]
        return (self.base_m if ch == "M" else self.base_s)[k]

    def protect_bits(self, k: int) -> int:
        """帯域 k の仮数上位のうち、ヘッダ部に入れて FEC で保護するbit数"""
        return self.protect_k if self.protect_k_high is None or k < self.high_k else self.protect_k_high

    def y_band(self, ch: str, k: int) -> bool:
        return self.has_y and ch in self.y_channels and k >= self.y_start_k

    @property
    def high_k(self) -> int:
        """高域 H2/H1 (最後の2帯域) の先頭の帯域番号。高域CRCと高域の消去はここから"""
        return self.nbands - 2

    @property
    def nbands(self) -> int:
        """独立に符号化する係数群の数（低域近似1群＋詳細帯域 levels 群）。"""
        return self.levels + 1

    @property
    def frame_ms(self) -> Fraction:
        """ブロック長 (= 1フレームが運ぶ音声の長さ、エンコーダの蓄積時間) [ms]。伝送込みの遅延ではない
        (伝送込みは gracefm.timing.min_latency。処理時間 0 で、この値の 2倍)"""
        return Fraction(self.block * 1000, self.fs)

    @property
    def frames_per_sec(self) -> int:
        assert self.fs % self.block == 0
        return self.fs // self.block

    def ncoef(self, k: int) -> int:
        """帯域 k の 1ブロックあたりの係数の数"""
        return self.block >> band_level(k, self.levels)

    def payload_bits(self) -> int:
        """音声データ (指数 + 区間アッテネータ + 仮数) の 1ブロックあたりのビット数"""
        tot = 0
        for ch, bits in (("M", self.bits_m), ("S", self.bits_s)):
            for k, b in enumerate(bits):
                if b > 0:
                    tot += self.exp_bits + self.attenuator_bits(ch, k) + self.ncoef(k) * b
        return tot

    def audio_kbps(self) -> Fraction:
        return Fraction(self.payload_bits() * self.frames_per_sec, 1000)


def levels_for(fs: int, block: int) -> int:
    """最低域の帯域幅 (fs/2 / 2^段数) が 2 kHz を下回るまで Haar を分割した段数。32 kHz も 48 kHz も 4 段"""
    levels = 1
    while fs >= (4000 << levels):
        levels += 1
    if block >> levels < 1:
        raise ValueError("ブロック長に対して段数が多すぎます")
    return levels


def band_level(k: int, levels: int) -> int:
    """係数群 k の分解段数（k=0 は低域近似、k=1..levels は詳細帯域）。"""
    return levels if k == 0 else levels + 1 - k


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


def _reduce(num, den):
    g = gcd(num, den)
    return (num // g, den // g)


def make_y_profile(base: Profile, name: str, pid: int, start_k: Optional[int] = None,
                amplitude: Tuple[int, int] = (2, 25), mantissa_bits: int = 7,
                channels: Tuple[str, ...] = ("M",), format_id: int = 3,
                bits_m: Optional[Tuple[int, ...]] = None,
                bits_s: Optional[Tuple[int, ...]] = None) -> Profile:
    """対象成分の境界以上だけをY(位相・半径シンボル)にし、他の成分は既存主系のままにする。

    amplitude = (分子, 分母) は半径の段が64 (仮数7bit) のときの隣接半径間隔 (既定 2/25 = 0.08) で、幅変更時は最大変調度を保つ。
    bits_m / bits_s を指定すると、M / Sの仮数幅を主系と別の値にする (Y系だけ音質と帯域の釣り合いを変えるとき)。
    """
    if not 5 <= mantissa_bits <= 16:
        raise ValueError("Y仮数幅は5〜16bitにしてください")
    if start_k is None:
        start_k = base.nbands - 3

    def widths(ch, bits):
        return tuple(b if k < start_k or b == 0 or ch not in channels else mantissa_bits
                     for k, b in enumerate(bits))

    attenuator_s = base.attn_group_s
    if bits_s is not None:
        top = max((k for k, w in enumerate(bits_s) if w), default=None)
        attenuator_s = tuple(min(4, base.ncoef(k)) if k == top else 0 for k in range(base.nbands))
    if "S" in channels:                                  # SもY帯域にするときは、MのY帯域と同じ4区間ずつ
        sbits = base.bits_s if bits_s is None else bits_s
        groups_s = list(attenuator_s or (0,) * base.nbands)
        for k in range(start_k, base.nbands):
            if sbits[k]:
                groups_s[k] = max(1, base.ncoef(k) // 4)
        attenuator_s = tuple(groups_s)
    attenuator_m = base.attn_group_m
    if "M" in channels:
        groups = list(attenuator_m or (0,) * base.nbands)
        for k in range(start_k, base.nbands):
            groups[k] = max(1, base.ncoef(k) // 4)
        attenuator_m = tuple(groups)
    new_m = widths("M", base.bits_m if bits_m is None else bits_m)
    new_s = widths("S", base.bits_s if bits_s is None else bits_s)

    def keep_where_width_unchanged(groups, new, old):
        """主系と仮数幅が変わった非Y帯域のアッテネータは引き継がない"""
        return None if groups is None else tuple(0 if k < start_k and new[k] != old[k] else g for k, g in enumerate(groups))
    attenuator_m = keep_where_width_unchanged(attenuator_m, new_m, base.bits_m)
    attenuator_s = keep_where_width_unchanged(attenuator_s, new_s, base.bits_s)
    y = replace(base, pid=pid, name=name, bits_m=new_m, bits_s=new_s,
                base_m=default_split(new_m, base.protect_bits) if base.layered else None,
                base_s=default_split(new_s, base.protect_bits) if base.layered else None,
                attn_group_m=attenuator_m, attn_group_s=attenuator_s,
                y_start_k=start_k,
                y_step=_reduce(15 * amplitude[0], amplitude[1] * (2 ** (mantissa_bits - 1) - 1)),
                y_bits=mantissa_bits, y_channels=channels,
                format_id=format_id)
    if not y.layered:
        return y
    from .layers import balanced      # Yの専用シンボル分だけ強弱の釣り合いが変わるので配分を取り直す
    return balanced(y)

# Standard catalog. All active M/S components have interval attenuation.
# IDs: 1–4 32kHz main, 5–6 32kHz secondary, 7–10 48kHz main, 11 48kHz secondary. 0 and 12–15 are reserved.
# Every row has the same fields; bit widths are explicit, never expanded implicitly.
PROFILE_MATRIX = (
    dict(
        pid=1,
        name='B200M',
        fs=32000,
        bits_m=(11, 11, 7, 7, 7),
        bits_s=(0, 0, 0, 0, 0),
        protect_k=1,
        protect_k_high=None,
        modulation='qam16h',
        alpha=5,
        base_m=(5, 5, 3, 3, 3),
        base_s=(0, 0, 0, 0, 0),
        attn_group_m=(0, 0, 2, 0, 4),
        attn_group_s=(0, 0, 0, 0, 0),
        pulse_beta_pct=25,
        pulse_span=16,
        y_start_k=None,
        y_channels=('M', 'S'),
        y_bits=7,
        y_step=(2, 105),
    ),
    dict(
        pid=2,
        name='B200',
        fs=32000,
        bits_m=(11, 11, 7, 7, 7),
        bits_s=(11, 7, 7, 7, 7),
        protect_k=1,
        protect_k_high=None,
        modulation='qam16h',
        alpha=5,
        base_m=(5, 5, 3, 3, 3),
        base_s=(5, 3, 3, 3, 3),
        attn_group_m=(0, 0, 2, 0, 4),
        attn_group_s=(0, 0, 2, 0, 4),
        pulse_beta_pct=10,
        pulse_span=32,
        y_start_k=None,
        y_channels=('M', 'S'),
        y_bits=7,
        y_step=(2, 105),
    ),
    dict(
        pid=3,
        name='B200MY',
        fs=32000,
        bits_m=(11, 11, 7, 7, 7),
        bits_s=(0, 0, 0, 0, 0),
        protect_k=1,
        protect_k_high=None,
        modulation='qam16h',
        alpha=5,
        base_m=(5, 5, 1, 1, 1),
        base_s=(0, 0, 0, 0, 0),
        attn_group_m=(0, 0, 2, 4, 8),
        attn_group_s=(0, 0, 0, 0, 0),
        pulse_beta_pct=25,
        pulse_span=16,
        y_start_k=2,
        y_channels=('M', 'S'),
        y_bits=7,
        y_step=(2, 105),
    ),
    dict(
        pid=4,
        name='B200Y',
        fs=32000,
        bits_m=(11, 11, 7, 7, 7),
        bits_s=(11, 11, 7, 7, 7),
        protect_k=1,
        protect_k_high=None,
        modulation='qam16h',
        alpha=5,
        base_m=(5, 5, 1, 1, 1),
        base_s=(5, 5, 1, 1, 1),
        attn_group_m=(0, 0, 2, 4, 8),
        attn_group_s=(0, 0, 2, 4, 8),
        pulse_beta_pct=10,
        pulse_span=32,
        y_start_k=2,
        y_channels=('M', 'S'),
        y_bits=7,
        y_step=(2, 105),
    ),
    dict(
        pid=5,
        name='SUB50M',
        fs=32000,
        bits_m=(7, 5, 3, 0, 0),
        bits_s=(0, 0, 0, 0, 0),
        protect_k=1,
        protect_k_high=None,
        modulation='qpsk',
        alpha=1,
        base_m=None,
        base_s=None,
        attn_group_m=(0, 0, 4, 0, 0),
        attn_group_s=(0, 0, 0, 0, 0),
        pulse_beta_pct=25,
        pulse_span=16,
        y_start_k=None,
        y_channels=('M', 'S'),
        y_bits=7,
        y_step=(2, 105),
    ),
    dict(
        pid=6,
        name='SUB100',
        fs=32000,
        bits_m=(7, 7, 3, 0, 0),
        bits_s=(5, 3, 3, 0, 0),
        protect_k=1,
        protect_k_high=None,
        modulation='qpsk',
        alpha=1,
        base_m=None,
        base_s=None,
        attn_group_m=(0, 0, 4, 0, 0),
        attn_group_s=(0, 0, 4, 0, 0),
        pulse_beta_pct=25,
        pulse_span=16,
        y_start_k=None,
        y_channels=('M', 'S'),
        y_bits=7,
        y_step=(2, 105),
    ),
    dict(
        pid=7,
        name='M700M',
        fs=48000,
        bits_m=(11, 11, 7, 7, 7),
        bits_s=(0, 0, 0, 0, 0),
        protect_k=1,
        protect_k_high=None,
        modulation='qam16h',
        alpha=5,
        base_m=(5, 5, 3, 3, 3),
        base_s=(0, 0, 0, 0, 0),
        attn_group_m=(0, 0, 2, 0, 4),
        attn_group_s=(0, 0, 0, 0, 0),
        pulse_beta_pct=25,
        pulse_span=16,
        y_start_k=None,
        y_channels=('M', 'S'),
        y_bits=7,
        y_step=(2, 105),
    ),
    dict(
        pid=8,
        name='M700',
        fs=48000,
        bits_m=(11, 11, 7, 7, 7),
        bits_s=(11, 7, 7, 7, 3),
        protect_k=1,
        protect_k_high=None,
        modulation='qam16h',
        alpha=5,
        base_m=(5, 5, 3, 3, 3),
        base_s=(5, 3, 3, 3, 1),
        attn_group_m=(0, 0, 2, 0, 4),
        attn_group_s=(0, 0, 2, 0, 4),
        pulse_beta_pct=25,
        pulse_span=16,
        y_start_k=None,
        y_channels=('M', 'S'),
        y_bits=7,
        y_step=(2, 105),
    ),
    dict(
        pid=9,
        name='M700MY',
        fs=48000,
        bits_m=(11, 11, 7, 7, 7),
        bits_s=(0, 0, 0, 0, 0),
        protect_k=1,
        protect_k_high=None,
        modulation='qam16h',
        alpha=5,
        base_m=(5, 5, 1, 1, 1),
        base_s=(0, 0, 0, 0, 0),
        attn_group_m=(0, 0, 2, 4, 8),
        attn_group_s=(0, 0, 0, 0, 0),
        pulse_beta_pct=25,
        pulse_span=16,
        y_start_k=2,
        y_channels=('M', 'S'),
        y_bits=7,
        y_step=(2, 105),
    ),
    dict(
        pid=10,
        name='M700Y',
        fs=48000,
        bits_m=(11, 11, 7, 7, 7),
        bits_s=(11, 11, 7, 7, 7),
        protect_k=1,
        protect_k_high=None,
        modulation='qam16h',
        alpha=5,
        base_m=(5, 5, 1, 1, 1),
        base_s=(5, 5, 1, 1, 1),
        attn_group_m=(0, 0, 2, 4, 8),
        attn_group_s=(0, 0, 2, 4, 8),
        pulse_beta_pct=25,
        pulse_span=16,
        y_start_k=2,
        y_channels=('M', 'S'),
        y_bits=7,
        y_step=(2, 105),
    ),
    dict(
        pid=11,
        name='SUB100-48K',
        fs=48000,
        bits_m=(7, 7, 3, 0, 0),
        bits_s=(5, 3, 0, 0, 0),
        protect_k=1,
        protect_k_high=None,
        modulation='qpsk',
        alpha=1,
        base_m=None,
        base_s=None,
        attn_group_m=(0, 0, 4, 0, 0),
        attn_group_s=(0, 4, 0, 0, 0),
        pulse_beta_pct=25,
        pulse_span=16,
        y_start_k=None,
        y_channels=('M', 'S'),
        y_bits=7,
        y_step=(2, 105),
    ),
)

PROFILES = {row["name"]: Profile(block=64, levels=levels_for(row["fs"], 64), format_id=3, **row)
            for row in PROFILE_MATRIX}
BY_ID = {p.pid: p for p in PROFILES.values()}
BY_HEADER = {(p.pid, p.format_id): p for p in PROFILES.values()}
if len(BY_ID) != len(PROFILES):
    raise ValueError("プロファイルIDが重複しています")
for _profile in PROFILES.values():
    for _ch, _bits in (("M", _profile.bits_m), ("S", _profile.bits_s)):
        if any(_bits) and not any(_profile.attenuator_bits(_ch, k) for k in range(_profile.nbands)):
            raise ValueError(f"{_profile.name}: {_ch} の標準アッテネータがありません")
