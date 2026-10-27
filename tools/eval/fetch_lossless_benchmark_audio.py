#!/usr/bin/env python3
"""Download clearly licensed lossless sources to ignored eval_audio/lossless/.

The audio is deliberately never placed in samples/ or committed to Git. Wikimedia
Commons metadata is checked at download time; the local manifest records hashes.
"""
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

import soundfile as sf

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "eval_audio", "lossless")
FILES = {
    "piano": ("Emotional piano.wav", "9661f81d37c59f230b324b830ab68c0482336af3ec117c92e73108ffb4095f15",
              "CC0", "triangelx", None),
    "percussion": ("Ceramic Djembe.wav", "09c83e84846072281ff4d46d47383c56417c4284bd719db3b2127c4f366f8551",
                   "CC0", "RutgerMuller", None),
    "guitar": ("344211 giomilko c-major-9-bossa-nova-guitar.wav",
               "f991d202484010cc4ade9fa80ce19997ba2746583e68f4466a2a9c7cec31c348",
               "CC BY 4.0", "GioMilko", "https://freesound.org/people/GioMilko/sounds/344211/"),
}
USER_AGENT = "GraceFM audio quality evaluation (Wikimedia Commons API)"


def image_info(filename, expected_license):
    query = urllib.parse.urlencode({
        "action": "query", "format": "json", "titles": f"File:{filename}",
        "prop": "imageinfo", "iiprop": "url|extmetadata|sha1|size|mime",
    })
    request = urllib.request.Request(f"https://commons.wikimedia.org/w/api.php?{query}",
                                     headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        pages = json.load(response)["query"]["pages"]
    info = next(iter(pages.values()))["imageinfo"][0]
    license_name = info["extmetadata"]["LicenseShortName"]["value"]
    if license_name != expected_license or info["mime"] != "audio/wav":
        raise ValueError(f"{filename}: expected {expected_license} WAV, got {license_name}, {info['mime']}")
    return info


def download(url, destination):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt, delay in enumerate((0, 3, 10, 30)):
        if delay:
            time.sleep(delay)
        try:
            with urllib.request.urlopen(request, timeout=120) as response, open(destination + ".part", "wb") as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
            os.replace(destination + ".part", destination)
            return
        except urllib.error.HTTPError as error:
            if error.code != 429 or attempt == 3:
                raise


def main():
    os.makedirs(OUT, exist_ok=True)
    entries = []
    for name, (filename, expected_sha256, expected_license, artist, original_source_page) in FILES.items():
        info = image_info(filename, expected_license)
        destination = os.path.join(OUT, filename.replace(" ", "_"))
        if not os.path.exists(destination):
            download(info["url"], destination)
        with open(destination, "rb") as source:
            data = source.read()
        sha1 = hashlib.sha1(data).hexdigest()
        if sha1 != info["sha1"] or len(data) != info["size"]:
            raise ValueError(f"{filename}: downloaded data differs from Commons metadata")
        sha256 = hashlib.sha256(data).hexdigest()
        if sha256 != expected_sha256:
            raise ValueError(f"{filename}: source file changed since this benchmark was measured")
        format_info = sf.info(destination)
        if format_info.format != "WAV" or format_info.subtype not in ("PCM_16", "PCM_24", "PCM_32", "FLOAT", "DOUBLE"):
            raise ValueError(f"{filename}: unexpected audio format {format_info}")
        entry = {
            "name": name, "file": os.path.relpath(destination, os.path.join(ROOT, "eval_audio")),
            "source_page": info["descriptionurl"],
            "original_source_page": original_source_page,
            "artist": artist,
            "license": "CC0 1.0" if expected_license == "CC0" else expected_license,
            "sha1": sha1, "sha256": sha256,
            "sample_rate_hz": format_info.samplerate, "channels": format_info.channels,
            "subtype": format_info.subtype, "duration_s": round(format_info.duration, 3),
        }
        entries.append(entry)
        print(f"{name}: {format_info.samplerate} Hz, {format_info.channels} ch, "
              f"{format_info.subtype}, {format_info.duration:.1f} s, {len(data)} bytes", flush=True)
    with open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8") as output:
        json.dump({"sources": entries}, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print("Audio and manifest saved only in ignored eval_audio/lossless/", flush=True)


if __name__ == "__main__":
    main()
