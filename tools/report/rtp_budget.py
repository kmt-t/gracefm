#!/usr/bin/env python3
"""
GraceFM/RTP のペイロード長とビットレート (docs/RTP.md の表)。

  python tools/report/rtp_budget.py

1フレームの本体 = スケール 1 byte + フレームのビット列 (n_tx bit) + Yシンボルのデータ (1個 9 bit: 最上位bit・パリティ・半径7 bit)
+ ズレ (deviation=2 のとき、デジタルシンボル 1個 4 bit)。ビット列、Yデータ、ズレは、それぞれ byte 単位に切り上げる。
ペイロード = ペイロードヘッダ 2 byte + フレーム数 F × 本体。F は {1,2,4,8} のうちペイロードが MAX_PAYLOAD 以下の最大値。
IP/UDP/RTP のヘッダは IPv4 で 40 byte、IPv6 で 60 byte。

出力: docs/results/rtp_budget.json
"""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from gracefm.profiles import PROFILES  # noqa: E402
from gracefm.txrx import Transmitter  # noqa: E402

MAX_PAYLOAD = 1400
HEADER_BYTES = 2


def budget(name, p, deviation):
    tx = Transmitter(p)
    body = 1 + -(-tx.layout.n_tx // 8) + -(-9 * tx.layout.n_y // 8)
    if deviation:
        body += -(-tx.digital_nsym // 2)
    frames = max(f for f in (1, 2, 4, 8) if HEADER_BYTES + f * body <= MAX_PAYLOAD)
    fps = p.fs / p.block
    payload = HEADER_BYTES + frames * body
    pps = fps / frames
    return dict(name=name, deviation=deviation, fs=p.fs, frame_bytes=body, frames_per_packet=frames, payload_bytes=payload,
                packets_per_s=pps, packet_ms=frames * p.block / p.fs * 1000,
                payload_kbps=payload * 8 * pps / 1000, ipv4_kbps=(payload + 40) * 8 * pps / 1000,
                ipv6_kbps=(payload + 60) * 8 * pps / 1000)


def main():
    rows = [budget(name, p, d) for d in (2, 0) for name, p in PROFILES.items()]
    (ROOT / "docs/results/rtp_budget.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    for r in rows:
        print(f"| {r['name']} | {r['deviation']} | {r['frame_bytes']} | {r['frames_per_packet']} | {r['payload_bytes']} | {r['packet_ms']:.2f} | "
              f"{r['packets_per_s']:g} | {r['payload_kbps']:.0f} | {r['ipv4_kbps']:.0f} |")


if __name__ == "__main__":
    main()
