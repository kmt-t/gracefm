#!/usr/bin/env python3
"""Download clearly licensed lossless sources for decoder-side model training.

Lossy sources (Ogg Vorbis, MP3) are not used: their psychoacoustic band cutting would be learned
as part of the target. Only WAV/FLAC files whose Wikimedia Commons metadata gives CC0, public
domain or CC BY are fetched, into the git-ignored eval_audio/train_lossless/. The license and
SHA-1 are checked against Commons at download time and the local manifest records the hashes.
Historic (pre-1930) recordings are deliberately not used: they have no high-frequency content.
"""
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

import numpy as np
import soundfile as sf
from scipy.signal import welch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "eval_audio", "train_lossless")
USER_AGENT = "GraceFM audio quality evaluation (Wikimedia Commons API)"
ALLOWED = {"CC0", "Public domain", "CC BY 3.0", "CC BY 4.0"}
TITLES = (
    "Alexi Action - I Am Robot (dark synthwave).flac",
    "C418 - Bushes and Marshmallows - 02 Incredible.flac",
    "C418 - Bushes and Marshmallows - 04 Question.flac",
    "C418 - Bushes and Marshmallows - 07 Phaos.flac",
    "C418 - Mixes - 01 20 kids.flac",
    "C418 - Mixes - 03 Incredibly detailed acid trip.flac",
    "C418 - bps - 01 aeiouw.flac",
    "C418 - sine - 01 test.flac",
    "Cloudkicker - Let Yourself Be Huge.flac",
    "Entre-dos-aguas-laucke-version-sample.flac",
    "Eternity from Light Years by Stellardrone.flac",
    "Parallel - me time.flac",
    "Petscop Soundtrack - 16 explore.flac",
    "Raspberrymusic - Epic Trailer Dramatic.flac",
    "Raspberrymusic - Ambient (10 minutes).flac",
    "Resonant Bodies - Resonant Bodies I - 03 Abundant Decay.flac",
    "Resonant Bodies - Resonant Bodies I - 07 Derelict Bow.flac",
    "Tamaki Tso - La Silla - 01 Interstellar.flac",
    "HOME - Resting State - 1.flac",
    "HOME - Resting State - 12.flac",
    "HOME - Resting State - 15.flac",
    "HOME - Resting State - 21.flac",
    "HOME - Resting State - 23.flac",
    "HOME - Resting State - 29.flac",
    "Sillycat Shore.wav",
    "Urban Street on a Rainy Afternoon.flac",
)
# タイトルが完全一致しないものは、Commons 上の正式名を検索して補う (先頭一致)
PREFIXES = (
    "Snowmelt flowing into lake at Okanagan Mountain Provinc",
    "Krystyna Czubówna. Wawel. Królestwo odkryte (narracja)",
    "Resonant Bodies - Resonant Bodies I - 05 Grain of Wood",
    "Raspberrymusic - Aliens (trailer music",
)


def api(params):
    for delay in (1.5, 30, 90, 180):
        time.sleep(delay)
        try:
            request = urllib.request.Request("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params),
                                             headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code != 429:
                raise
    raise RuntimeError("Commons API rate limit")


def info_for(title):
    pages = api({"action": "query", "format": "json", "titles": f"File:{title}", "prop": "imageinfo",
                 "iiprop": "url|extmetadata|sha1|size|mime"})["query"]["pages"]
    page = next(iter(pages.values()))
    if "imageinfo" not in page:
        return None
    return page["imageinfo"][0]


def resolve_prefix(prefix):
    hits = api({"action": "query", "format": "json", "list": "prefixsearch", "pssearch": f"File:{prefix}",
                "pslimit": "5"})["query"]["prefixsearch"]
    return hits[0]["title"][len("File:"):] if hits else None


def download(url, destination):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for delay in (10, 60, 180, 300):
        time.sleep(delay)
        try:
            with urllib.request.urlopen(request, timeout=300) as response, open(destination + ".part", "wb") as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
            os.replace(destination + ".part", destination)
            return
        except urllib.error.HTTPError as error:
            if error.code != 429:
                raise
    raise RuntimeError("download rate limit")


def looks_transcoded(path):
    """15-16 kHz から 16-17 kHz で急に落ちる (MP3 などの帯域制限) ファイルを見つける"""
    x, fs = sf.read(path, always_2d=True, frames=48000 * 30)
    if fs < 44100:
        return False
    freq, power = welch(x.mean(axis=1), fs, nperseg=4096)
    level = 10 * np.log10(power + 1e-20)
    band = lambda a, b: level[(freq >= a) & (freq < b)].mean()
    return band(15000, 16000) - band(16000, 17000) > 15.0


def main():
    os.makedirs(OUT, exist_ok=True)
    titles = list(TITLES) + [t for t in (resolve_prefix(p) for p in PREFIXES) if t]
    entries, seen = [], set()
    for title in titles:
        if title in seen:
            continue
        seen.add(title)
        info = info_for(title)
        if info is None:
            print("skip (not found):", title, flush=True)
            continue
        license_name = info["extmetadata"]["LicenseShortName"]["value"]
        if license_name not in ALLOWED or info["mime"] not in ("audio/wav", "audio/x-wav", "audio/flac", "audio/x-flac"):
            print(f"skip ({license_name}, {info['mime']}):", title, flush=True)
            continue
        destination = os.path.join(OUT, title.replace(" ", "_").replace("/", "_"))
        if not os.path.exists(destination):
            try:
                download(info["url"], destination)
            except RuntimeError as error:
                print(f"skip ({error}):", title, flush=True)
                continue
        with open(destination, "rb") as source:
            data = source.read()
        if hashlib.sha1(data).hexdigest() != info["sha1"] or len(data) != info["size"]:
            raise ValueError(f"{title}: downloaded data differs from Commons metadata")
        if looks_transcoded(destination):
            print("skip (16 kHz で帯域制限されている。非可逆からの変換の疑い):", title, flush=True)
            os.remove(destination)
            continue
        fmt = sf.info(destination)
        entries.append({
            "name": os.path.splitext(os.path.basename(destination))[0],
            "file": os.path.relpath(destination, os.path.join(ROOT, "eval_audio")),
            "source_page": info["descriptionurl"],
            "artist": info["extmetadata"].get("Artist", {}).get("value", ""),
            "license": "CC0 1.0" if license_name == "CC0" else license_name,
            "sha1": info["sha1"], "sha256": hashlib.sha256(data).hexdigest(),
            "sample_rate_hz": fmt.samplerate, "channels": fmt.channels, "subtype": fmt.subtype,
            "duration_s": round(fmt.duration, 3),
        })
        print(f"{title}: {fmt.samplerate} Hz, {fmt.channels} ch, {fmt.subtype}, {fmt.duration:.1f} s", flush=True)
    with open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8") as output:
        json.dump({"sources": entries}, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print(f"{len(entries)} files; saved only in ignored eval_audio/train_lossless/", flush=True)


if __name__ == "__main__":
    main()
